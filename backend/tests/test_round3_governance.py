from tests.conftest import CREATOR, OWNER, REV, mk_brand, mk_product
from tests.test_governance import CREATOR2, submit


def put(c, b, **kw):
    cur = c.get(f"/api/brands/{b['id']}", headers=OWNER).json["brand"]
    r = c.put(f"/api/brands/{b['id']}", headers=OWNER, json={**cur, **kw})
    assert r.status_code == 200, r.json
    return r.json["brand"]


def test_version_history_preserves_every_version_compare_and_restore(client):
    b = mk_brand(client, tagline="One")
    b = put(client, b, tagline="Two", changeNote="v2")
    b = put(client, b, tagline="Three", terminology=[{"avoid": "cheap", "prefer": "affordable"}, {"avoid": "tiny", "prefer": "compact"}], changeNote="v3")
    b = put(client, b, tagline="Four", terminology=[{"avoid": "tiny", "prefer": "compact"}], changeNote="v4")
    h = client.get(f"/api/brands/{b['id']}/versions", headers=CREATOR).json["versions"]
    assert [v["version"] for v in h] == [4, 3, 2, 1] and all(v["updatedBy"] for v in h)
    v1 = client.get(f"/api/brands/{b['id']}/versions/1", headers=CREATOR).json
    assert v1["version"]["tagline"] == "One"
    cmp = client.get(f"/api/brands/{b['id']}/versions/compare?from=1&to=4", headers=CREATOR).json
    kinds = {(c["field"], c["change"]) for c in cmp["changes"]}
    assert ("tagline", "modified") in kinds and ("terminology", "added") in kinds
    r = client.post(f"/api/brands/{b['id']}/versions/1/restore", headers=OWNER, json={})
    assert r.status_code == 201 and r.json["brand"]["version"] == 5 and r.json["brand"]["tagline"] == "One"
    assert len(client.get(f"/api/brands/{b['id']}/versions", headers=CREATOR).json["versions"]) == 5
    assert client.get(f"/api/brands/{b['id']}/versions/4", headers=CREATOR).json["version"]["tagline"] == "Four"
    assert client.post(f"/api/brands/{b['id']}/versions/1/restore", headers=CREATOR, json={}).status_code == 403


def test_impact_new_avoid_term_and_recheck_clears_alert(client):
    b = mk_brand(client)
    sub = submit(client, b["id"], None, "A flimsy kettle for you.")
    put(client, b, terminology=[{"avoid": "cheap", "prefer": "affordable"}, {"avoid": "flimsy", "prefer": "light"}], changeNote="new avoid")
    r = client.get(f"/api/governance/impact?brandId={b['id']}", headers=REV).json
    hit = [a for a in r["affected"] if a["submissionId"] == sub["id"]]
    assert hit and "avoid" in hit[0]["reason"].lower() and r["open"] == 1
    assert client.post("/api/governance/impact/decision", headers=REV, json={"key": hit[0]["key"], "decision": "resolved"}).status_code == 201
    assert client.get(f"/api/governance/impact?brandId={b['id']}", headers=REV).json["open"] == 0
    client.post("/api/governance/impact/decision", headers=REV, json={"key": hit[0]["key"], "decision": "reopen"})
    assert client.get(f"/api/governance/impact?brandId={b['id']}", headers=REV).json["open"] == 1
    hist = client.get(f"/api/governance/impact/history?key={hit[0]['key']}", headers=REV).json["history"]
    assert [h["decision"] for h in hist] == ["resolved", "reopen"]
    client.post(f"/api/submissions/{sub['id']}/recheck", headers=REV)
    again = client.get(f"/api/governance/impact?brandId={b['id']}", headers=REV).json
    assert again["open"] == 0 and again["scanned"]["clearedByRecheck"] >= 1
    assert client.post("/api/governance/impact/decision", headers=CREATOR, json={"key": "x", "decision": "dismiss"}).status_code == 403


def test_drift_has_domains_examples_recommendation_and_matches_insights(client):
    b = mk_brand(client)
    submit(client, b["id"], None, "A cheap option.")
    submit(client, b["id"], None, "Another cheap deal.", CREATOR2)
    d = client.post("/api/submissions", headers=CREATOR, json={"brandId": b["id"], "title": "Draft", "content": "cheap cheap", "meta": {"type": "blog", "audience": "x"},
                                                                 "findings": [], "saveAsDraft": True})
    drift = client.get("/api/governance/drift", headers=REV).json
    item = drift["recurring"][0]
    assert item["domain"] == "text" and item["submissions"] == 2 and item["examples"] and item["recommendation"]["correction"]
    assert drift["analysed"] == 2 or d.status_code != 201 or drift["analysed"] >= 2
    ins = client.get("/api/insights", headers=REV).json
    assert {r["label"] for r in ins["recurring"]} == {i["label"] for i in drift["recurring"]}
    assert ins["totals"]["draft"] == 0 or ins["totals"]["submissions"] == drift["analysed"]


def test_reviewer_cannot_approve_own_submission(client):
    b = mk_brand(client)
    s = submit(client, b["id"], None, "A calm hello.", OWNER)
    r = client.post(f"/api/submissions/{s['id']}/decision", headers=OWNER, json={"status": "approved"})
    assert r.status_code == 403 and "independent" in r.json["error"].lower()


def test_impact_and_conflicts_work_across_all_brands(client):
    b = mk_brand(client)
    sub = submit(client, b["id"], None, "A flimsy kettle for you.")
    put(client, b, terminology=[{"avoid": "flimsy", "prefer": "light"}], changeNote="new avoid")
    r = client.get("/api/governance/impact", headers=REV)
    assert r.status_code == 200 and r.json["open"] == 1 and r.json["affected"][0]["submissionId"] == sub["id"]
    assert client.get("/api/governance/conflicts", headers=REV).status_code == 200
