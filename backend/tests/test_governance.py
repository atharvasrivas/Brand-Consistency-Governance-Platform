from tests.conftest import CREATOR, OWNER, REV, H, mk_brand, mk_product

DRAFT = {"type": "blog", "audience": "shoppers"}
CREATOR2 = H("creator", "creat-0000002", "Dan Creator", "Writer")


def submit(c, bid, pid, text, headers=CREATOR):
    r = c.post("/api/submissions", headers=headers, json={"brandId": bid, "productId": pid, "title": "T", "content": text, "meta": DRAFT, "findings": []})
    assert r.status_code == 201, r.json
    return r.json["submission"]


def test_new_profile_fields_are_saved(client):
    b = mk_brand(client, tagline="Made simple", industry="Appliances", history="Founded by makers", values=["Honest"], voice="Warm", targetAudience="Families",
                 colours=[{"name": "Ink", "hex": "#112233", "role": "secondary"}])
    got = client.get(f"/api/brands/{b['id']}", headers=CREATOR).json["brand"]
    assert got["tagline"] == "Made simple" and got["industry"] == "Appliances" and got["values"] == ["Honest"]
    assert got["colours"][0]["role"] == "secondary"


def test_drift_groups_repeats_across_submissions_and_creators(client):
    b = mk_brand(client, terminology=[{"avoid": "cheap", "prefer": "affordable", "strict": False}])
    submit(client, b["id"], None, "A cheap option for you.")
    submit(client, b["id"], None, "Another cheap deal.", CREATOR2)
    submit(client, b["id"], None, "A calm hello.")
    d = client.get("/api/governance/drift", headers=REV).json
    top = d["recurring"][0]
    assert top["submissions"] == 2 and top["creators"] == 2 and top["pattern"] == "multiple creators"
    assert any("terminology" in a.lower() or "cheap" in a.lower() for a in d["alerts"]), d["alerts"]
    assert client.get("/api/governance/drift", headers=CREATOR).status_code == 403


def test_change_impact_finds_content_with_the_old_fact(client):
    b = mk_brand(client)
    p = mk_product(client, b["id"], specs=[{"name": "Warranty", "value": "2 years", "source": "sheet"}])
    sub = submit(client, b["id"], p["id"], "Enjoy a 2 years warranty with every kettle.")
    spec = client.get(f"/api/brands/{b['id']}/products/{p['id']}", headers=OWNER).json["product"] if False else p
    upd = {**spec, "specs": [{"id": spec["specs"][0]["id"], "name": "Warranty", "value": "3 years", "source": "sheet"}], "changeNote": "Warranty extended"}
    assert client.put(f"/api/brands/{b['id']}/products/{p['id']}", headers=OWNER, json=upd).status_code == 200
    r = client.get(f"/api/governance/impact?brandId={b['id']}", headers=REV).json
    hit = [a for a in r["affected"] if a["submissionId"] == sub["id"]]
    assert hit and hit[0]["before"] == "Warranty: 2 years" and hit[0]["after"] == "Warranty: 3 years" and r["open"] == 1
    d = client.post("/api/governance/impact/decision", headers=REV, json={"key": hit[0]["key"], "decision": "recheck", "note": "please fix"})
    assert d.status_code == 201
    assert client.get(f"/api/governance/impact?brandId={b['id']}", headers=REV).json["open"] == 0


def test_impact_is_scoped_to_the_brand(client):
    a, b = mk_brand(client, "Alpha Co"), mk_brand(client, "Beta Co")
    pa = mk_product(client, a["id"], specs=[{"name": "Warranty", "value": "2 years", "source": "s"}])
    mk_product(client, b["id"], "Kettle", specs=[{"name": "Warranty", "value": "2 years", "source": "s"}])
    submit(client, b["id"], None, "A 2 years warranty.")
    upd = {**pa, "specs": [{"id": pa["specs"][0]["id"], "name": "Warranty", "value": "3 years", "source": "s"}]}
    client.put(f"/api/brands/{a['id']}/products/{pa['id']}", headers=OWNER, json=upd)
    assert client.get(f"/api/governance/impact?brandId={a['id']}", headers=REV).json["affected"] == []


def test_conflict_detector_shows_both_rules_and_never_resolves_itself(client):
    b = mk_brand(client, terminology=[{"avoid": "cheap", "prefer": "affordable"}, {"avoid": "cheap", "prefer": "budget"}],
                 guidelines=[{"text": "The product name must always be written in uppercase."}, {"text": "The product name must be written in title case."}],
                 approvedClaims=[{"text": "Cures colds fast"}], restrictedClaims=[{"text": "cures colds", "reason": "health"}])
    r = client.get(f"/api/governance/conflicts?brandId={b['id']}", headers=REV).json
    kinds = {c["type"] for c in r["conflicts"]}
    assert {"terminology", "claim-vs-restricted", "formatting"} <= kinds
    c = r["conflicts"][0]
    assert len(c["rules"]) == 2 and c["explanation"] and c["decision"] is None
    assert client.post("/api/governance/conflicts/resolve", headers=REV, json={"key": c["key"], "resolution": "keep_first"}).status_code == 403
    ok = client.post("/api/governance/conflicts/resolve", headers=OWNER, json={"key": c["key"], "resolution": "needs_rewrite", "note": "owner will rewrite"})
    assert ok.status_code == 201
    again = client.get(f"/api/governance/conflicts?brandId={b['id']}", headers=REV).json
    assert again["open"] == r["open"] - 1 and len(again["conflicts"]) == len(r["conflicts"])
    assert client.get(f"/api/brands/{b['id']}", headers=OWNER).json["brand"]["terminology"]  # rules untouched


def test_drafts_do_not_conflict(client):
    b = mk_brand(client, terminology=[{"avoid": "cheap", "prefer": "affordable"}, {"avoid": "cheap", "prefer": "budget", "status": "draft"}])
    assert client.get(f"/api/governance/conflicts?brandId={b['id']}", headers=REV).json["conflicts"] == []


def test_insights_timeline_and_scope(client):
    b = mk_brand(client)
    submit(client, b["id"], None, "A calm hello.")
    i = client.get("/api/insights", headers=REV).json
    assert i["timeline"][0]["submissions"] == 1 and i["byBrand"][0]["complianceRate"] in (0.0, None, 0)
    assert client.get("/api/insights", headers=CREATOR).status_code == 403


def test_identity_needs_only_name_and_role(client):
    h = {"X-User-Id": "owner-0000009", "X-User-Role": "owner", "X-User-Name": "Olive Owner"}
    assert client.get("/api/bootstrap", headers=h).status_code == 200
