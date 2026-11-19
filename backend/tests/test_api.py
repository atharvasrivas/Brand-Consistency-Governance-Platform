import base64

from tests.conftest import CREATOR, OWNER, REV, H, mk_brand, mk_product

DRAFT = {"type": "blog", "audience": "shoppers"}


def review(c, bid, pid, text, headers=CREATOR):
    return c.post("/api/review", headers=headers, json={"brandId": bid, "productId": pid, "content": text, "meta": DRAFT})


def test_identity_required_and_validated(client):
    assert client.get("/api/bootstrap").status_code == 401
    assert client.get("/api/bootstrap", headers={**CREATOR, "X-User-Role": "admin"}).status_code == 401
    assert client.get("/api/bootstrap", headers={**CREATOR, "X-User-Name": "x"}).status_code == 401
    assert client.get("/api/bootstrap", headers=CREATOR).json["user"]["role"] == "creator"


def test_no_data_exists_until_owner_creates_it(client):
    b = client.get("/api/bootstrap", headers=OWNER).json
    assert b["brands"] == [] and b["submissions"] == []


def test_role_permissions_enforced_on_server(client):
    assert client.post("/api/brands", headers=CREATOR, json={"name": "X"}).status_code == 403
    assert client.post("/api/brands", headers=REV, json={"name": "X"}).status_code == 403
    b = mk_brand(client)
    assert client.put(f"/api/brands/{b['id']}", headers=CREATOR, json={"name": "Y"}).status_code == 403
    assert client.post(f"/api/brands/{b['id']}/products", headers=REV, json={"name": "P"}).status_code == 403
    assert client.get("/api/insights", headers=CREATOR).status_code == 403
    assert client.get("/api/insights", headers=REV).status_code == 200
    assert client.get("/api/insights", headers=OWNER).status_code == 200
    assert client.get("/api/brands", headers=CREATOR).status_code == 200  # view only
    assert client.post("/api/assistant/factsheet", headers=CREATOR, json={"scope": "brand"}).status_code == 403
    assert client.post("/api/assets", headers=CREATOR, json={}).status_code == 403
    assert client.post("/api/suggestions", headers=OWNER, json={"brandId": b["id"], "title": "t", "proposal": "p"}).status_code == 403


def test_multiple_brands_are_independent_and_versioned(client):
    a, b = mk_brand(client, "Brand One"), mk_brand(client, "Brand Two", terminology=[{"avoid": "gadget", "prefer": "tool"}])
    assert client.post("/api/brands", headers=OWNER, json={"name": "brand one"}).status_code == 409
    pa = mk_product(client, a["id"])
    r = client.put(f"/api/brands/{a['id']}", headers=OWNER, json={**a, "description": "v2", "version": a["version"]})
    assert r.json["brand"]["version"] == 2
    stale = client.put(f"/api/brands/{a['id']}", headers=OWNER, json={**a, "description": "late", "version": 1})
    assert stale.status_code == 409
    got = client.get("/api/brands", headers=CREATOR).json["brands"]
    assert {x["name"] for x in got} == {"Brand One", "Brand Two"}
    assert [p["name"] for p in next(x for x in got if x["id"] == a["id"])["products"]] == ["Kettle"]
    assert next(x for x in got if x["id"] == b["id"])["products"] == []
    assert len(client.get(f"/api/brands/{a['id']}/versions", headers=CREATOR).json["versions"]) == 2
    assert pa["version"] == 1


def test_review_requires_selection_and_isolates_brands(client):
    a, b = mk_brand(client, "Brand One"), mk_brand(client, "Brand Two", terminology=[{"avoid": "gadget", "prefer": "tool"}], restrictedClaims=[])
    pa = mk_product(client, a["id"])
    text = "Our cheap gadget cures colds."
    assert client.post("/api/review", headers=CREATOR, json={"content": text, "meta": DRAFT}).status_code == 422  # no brand
    assert client.post("/api/review", headers=CREATOR, json={"brandId": a["id"], "content": text, "meta": DRAFT}).status_code == 422  # no product choice
    assert review(client, "nope", None, text).status_code == 404
    assert review(client, b["id"], pa["id"], text).status_code == 404  # product of another brand
    ra = review(client, a["id"], None, text).json
    rb = review(client, b["id"], None, text).json
    qa = {f["quote"] for f in ra["findings"]}
    qb = {f["quote"] for f in rb["findings"]}
    assert "cheap" in qa and "cures colds" in qa and "gadget" not in qa
    assert "gadget" in qb and "cheap" not in qb and "cures colds" not in qb
    assert ra["context"]["brand"]["name"] == "Brand One" and ra["context"]["product"] is None


def test_product_scope_adds_product_facts_only(client):
    a = mk_brand(client)
    k, t = mk_product(client, a["id"]), mk_product(client, a["id"], "Toaster", previousNames=[], specs=[{"name": "Slots", "value": "4", "source": "s"}])
    txt = "The Hotpot has a capacity of 2 litres."
    f_k = review(client, a["id"], k["id"], txt).json["findings"]
    f_t = review(client, a["id"], t["id"], txt).json["findings"]
    assert {"NAME-OLD", "SPEC-MISMATCH"} <= {f["ruleId"] for f in f_k}
    assert not {"NAME-OLD", "SPEC-MISMATCH"} & {f["ruleId"] for f in f_t}
    assert review(client, a["id"], k["id"], txt).json["context"]["product"]["version"] == 1


def test_no_approved_content_is_explained_not_faked(client):
    b = client.post("/api/brands", headers=OWNER, json={"name": "Empty"}).json["brand"]
    r = review(client, b["id"], None, "Cheap cures colds, 99% love it!").json
    assert r["findings"] == [] and "no approved" in r["notice"].lower()


def test_draft_items_are_not_used_as_facts(client):
    b = mk_brand(client, terminology=[{"avoid": "cheap", "prefer": "affordable", "status": "draft"}], restrictedClaims=[])
    assert not any(f["quote"] == "cheap" for f in review(client, b["id"], None, "It is cheap.").json["findings"])


def test_findings_are_meaningful_and_deduplicated(client):
    b = mk_brand(client)
    p = mk_product(client, b["id"])
    fs = review(client, b["id"], p["id"], "Hotpot rocks!!! Hotpot is great,, really.  Hotpot.").json["findings"]
    assert all(f["quote"].strip() not in ("!", ",", ".", "!!!", ",,") for f in fs)
    old = [f for f in fs if f["ruleId"] == "NAME-OLD"]
    assert len(old) == 1 and old[0]["occurrences"] == 3 and len(old[0]["ranges"]) == 3
    assert all(f["severity"] in ("critical", "warning", "suggestion") and f["source"] and f["quote"] for f in fs)


def test_unverified_claims_route_to_human_never_invent_source(client):
    b = mk_brand(client)
    fs = review(client, b["id"], None, "We are the best in the world. 99% of users agree.").json["findings"]
    un = [f for f in fs if f["ruleId"] in ("CLAIM-UNVERIFIED", "STAT-UNVERIFIED")]
    assert un and all(f["needsHuman"] or f["severity"] != "critical" for f in un)
    assert all(f["strictness"] != "mandatory" or f["source"] for f in fs)


def test_workflow_gating_roles_and_versions(client):
    b = mk_brand(client)
    body = {"brandId": b["id"], "productId": None, "title": "Post", "content": "It cures colds.", "meta": DRAFT, "findings": []}
    r = client.post("/api/submissions", headers=CREATOR, json=body)
    assert r.status_code == 422 and r.json["blockers"]  # mandatory finding unresolved
    body["content"] = "It is affordable."
    assert client.post("/api/submissions", headers=REV, json=body).status_code == 403  # reviewers don't submit
    s = client.post("/api/submissions", headers=CREATOR, json=body)
    assert s.status_code == 201
    sub = s.json["submission"]
    assert sub["brandVersion"] == 1 and sub["productId"] is None
    sid = sub["id"]
    other = H("creator", "creat-0000002", "Other Person", "Writer")
    assert client.get(f"/api/submissions/{sid}", headers=other).status_code == 404
    assert client.post(f"/api/submissions/{sid}/decision", headers=CREATOR, json={"status": "approved"}).status_code == 403
    assert client.post(f"/api/submissions/{sid}/decision", headers=REV, json={"status": "rejected"}).status_code == 422  # needs comment
    assert client.post(f"/api/submissions/{sid}/decision", headers=REV, json={"status": "approved"}).json["submission"]["status"] == "approved"
    assert client.post(f"/api/submissions/{sid}/decision", headers=OWNER, json={"status": "approved"}).status_code == 409


def test_submission_requires_product_choice(client):
    b = mk_brand(client)
    r = client.post("/api/submissions", headers=CREATOR, json={"brandId": b["id"], "title": "t", "content": "hi", "meta": DRAFT})
    assert r.status_code == 422


def test_creator_suggestion_goes_to_owner_without_changing_profile(client):
    b = mk_brand(client)
    r = client.post("/api/suggestions", headers=CREATOR, json={"brandId": b["id"], "title": "Add claim", "proposal": "Add X"})
    assert r.status_code == 201
    assert client.get(f"/api/brands/{b['id']}", headers=OWNER).json["brand"]["version"] == 1
    assert len(client.get("/api/suggestions", headers=OWNER).json["suggestions"]) == 1
    assert client.get("/api/suggestions", headers=H("creator", "creat-0000002", "Other Person", "Writer")).json["suggestions"] == []
    sid = r.json["suggestion"]["id"]
    assert client.post(f"/api/suggestions/{sid}/resolve", headers=CREATOR, json={"status": "accepted"}).status_code == 403
    assert client.post(f"/api/suggestions/{sid}/resolve", headers=OWNER, json={"status": "dismissed"}).json["suggestion"]["status"] == "dismissed"
    assert client.get(f"/api/brands/{b['id']}", headers=OWNER).json["brand"]["version"] == 1


def test_assets_upload_validation(client):
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n0000").decode()
    r = client.post("/api/assets", headers=OWNER, json={"name": "logo.png", "mime": "image/png", "data": png})
    assert r.status_code == 201
    g = client.get(f"/api/assets/{r.json['assetId']}")
    assert g.status_code == 200 and g.mimetype == "image/png" and g.data.startswith(b"\x89PNG")
    assert client.post("/api/assets", headers=OWNER, json={"name": "a.exe", "mime": "application/x-msdownload", "data": png}).status_code == 415
    assert client.post("/api/assets", headers=OWNER, json={"name": "a.png", "mime": "image/png", "data": "!!notb64"}).status_code == 422
    big = base64.b64encode(b"0" * 1_600_000).decode()
    assert client.post("/api/assets", headers=OWNER, json={"name": "a.png", "mime": "image/png", "data": big}).status_code == 413


def test_assistant_makes_drafts_only(client):
    r = client.post("/api/assistant/factsheet", headers=OWNER, json={"scope": "product", "name": "Kettle", "answers": {
        "specs": "Capacity: 1.7 litres | spec sheet", "approvedClaims": "Boils fast | lab test", "terminology": "cheap -> affordable"}})
    d = r.json
    assert d["notice"].startswith("Draft") and d["usedAI"] is False
    items = d["draft"]["specs"] + d["draft"]["approvedClaims"] + d["draft"]["terminology"]
    assert items and all(i["status"] == "draft" for i in items)


def test_insights_from_stored_data_only(client):
    assert client.get("/api/insights", headers=REV).json["totals"]["submissions"] == 0
    b = mk_brand(client)
    client.post("/api/submissions", headers=CREATOR, json={"brandId": b["id"], "productId": None, "title": "t", "content": "It is cheap.", "meta": DRAFT, "findings": []})
    i = client.get("/api/insights", headers=OWNER).json
    assert i["totals"]["submissions"] == 1


def test_demo_data_is_owner_only_and_labelled(client):
    assert client.post("/api/demo/load", headers=CREATOR).status_code == 403
    b = client.post("/api/demo/load", headers=OWNER).json["brand"]
    assert "demo" in b["name"].lower() and b["products"] and "demo" in b["products"][0]["name"].lower()
    assert len(client.get("/api/brands", headers=OWNER).json["brands"]) == 1
    client.post("/api/demo/load", headers=OWNER)
    assert len(client.get("/api/brands", headers=OWNER).json["brands"]) == 1


def test_health_and_cors(client):
    assert client.get("/api/health").json["ok"]
    r = client.options("/api/review", headers={"Origin": "http://localhost:5173"})
    assert r.status_code in (200, 204)
