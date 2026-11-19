from .conftest import CREATOR, H, OWNER, REV, mk_brand, mk_product

META = {"type": "blog", "audience": "shoppers", "purpose": "awareness"}


def body(b, content, **kw):
    return {"brandId": b["id"], "productId": None, "title": "Spring post", "content": content, "meta": META, "findings": [], **kw}


def test_full_approval_journey(client):
    b = mk_brand(client)
    other_rev = H("reviewer", "review-000002", "Rita Reviewer", "Editor")
    # 1. creator submits -> "submitted"; the same content cannot be submitted twice
    s = client.post("/api/submissions", headers=CREATOR, json=body(b, "A kettle for the morning."))
    assert s.status_code == 201 and s.json["submission"]["status"] == "submitted"
    sid = s.json["submission"]["id"]
    dup = client.post("/api/submissions", headers=CREATOR, json=body(b, "A kettle for the morning."))
    assert dup.status_code == 409 and dup.json.get("submissionId") == sid
    # 2. reviewer takes it into review; a second attempt is refused
    assert client.post(f"/api/submissions/{sid}/start-review", headers=CREATOR).status_code == 403
    assert client.post(f"/api/submissions/{sid}/start-review", headers=REV).json["submission"]["status"] == "under_review"
    assert client.post(f"/api/submissions/{sid}/start-review", headers=other_rev).status_code == 409
    # 3. request changes needs a comment, then is recorded with reviewer, revision and time
    assert client.post(f"/api/submissions/{sid}/decision", headers=REV, json={"status": "changes_requested"}).status_code == 422
    r = client.post(f"/api/submissions/{sid}/decision", headers=REV, json={"status": "changes_requested", "comment": "Add the capacity."})
    assert r.json["submission"]["status"] == "changes_requested"
    d = r.json["submission"]["decisions"][0]
    assert d["by"] == "Ravi Reviewer" and d["version"] == 1 and d["comment"] == "Add the capacity." and d["at"]
    # repeated decision is refused
    assert client.post(f"/api/submissions/{sid}/decision", headers=REV, json={"status": "approved"}).status_code == 409
    # 4. creator sees the feedback, but a resubmission with unchanged text is refused
    got = client.get(f"/api/submissions/{sid}", headers=CREATOR).json["submission"]
    assert got["comments"][-1]["text"] == "Add the capacity." and got["comments"][-1]["version"] == 1
    assert client.post(f"/api/submissions/{sid}/versions", headers=CREATOR, json={"content": "A kettle for the morning."}).status_code == 409
    # 5. creator revises and resubmits -> "resubmitted"; version 1 stays available
    r = client.post(f"/api/submissions/{sid}/versions", headers=CREATOR, json={"content": "A 1.7 litre kettle for the morning.", "note": "Added capacity"})
    sub = r.json["submission"]
    assert sub["status"] == "resubmitted" and [v["n"] for v in sub["versions"]] == [1, 2]
    assert sub["versions"][0]["content"] == "A kettle for the morning."
    assert sub["comments"][-1]["version"] == 2
    # a pending submission cannot be revised again, and the creator cannot decide
    assert client.post(f"/api/submissions/{sid}/versions", headers=CREATOR, json={"content": "Other text."}).status_code == 409
    assert client.post(f"/api/submissions/{sid}/decision", headers=CREATOR, json={"status": "approved"}).status_code == 403
    # 6. approve once; a repeat is refused and the history keeps both decisions
    assert client.post(f"/api/submissions/{sid}/decision", headers=other_rev, json={"status": "approved"}).json["submission"]["status"] == "approved"
    assert client.post(f"/api/submissions/{sid}/decision", headers=OWNER, json={"status": "approved"}).status_code == 409
    final = client.get(f"/api/submissions/{sid}", headers=OWNER).json["submission"]
    assert [x["status"] for x in final["decisions"]] == ["changes_requested", "approved"]
    assert [x["version"] for x in final["decisions"]] == [1, 2]
    assert len(final["activity"]) >= 5


def test_draft_then_submit(client):
    b = mk_brand(client)
    s = client.post("/api/submissions", headers=CREATOR, json=body(b, "Work in progress.", draft=True)).json["submission"]
    assert s["status"] == "draft"
    assert client.get("/api/submissions", headers=REV).json["submissions"] == []  # drafts stay private to the author
    assert client.post(f"/api/submissions/{s['id']}/start-review", headers=REV).status_code == 409  # not submitted yet
    assert client.post(f"/api/submissions/{s['id']}/decision", headers=REV, json={"status": "approved"}).status_code == 409
    assert client.post(f"/api/submissions/{s['id']}/submit", headers=H("creator", "creat-0000009", "Else", ""), json={}).status_code in (403, 404)
    r = client.post(f"/api/submissions/{s['id']}/submit", headers=CREATOR, json={"content": "Finished text."})
    assert r.json["submission"]["status"] == "submitted" and len(r.json["submission"]["versions"]) == 2
    assert client.post(f"/api/submissions/{s['id']}/submit", headers=CREATOR, json={}).status_code == 409  # no double submit


def test_isolation_and_incomplete_fact_sheets(client):
    a, b = mk_brand(client, "Alpha"), mk_brand(client, "Beta", terminology=[{"avoid": "fast", "prefer": "swift"}], restrictedClaims=[])
    pa = mk_product(client, a["id"], "Kettle")
    empty = client.post(f"/api/brands/{b['id']}/products", headers=OWNER, json={"name": "Bare Product"}).json["product"]
    # Alpha's term rules do not fire on Beta content and vice versa
    ra = client.post("/api/review", headers=CREATOR, json={"brandId": b["id"], "productId": None, "content": "It is cheap and cures colds.", "meta": META}).json
    labels = " ".join(f["label"] for f in ra["findings"]) + " ".join(f.get("explanation", "") for f in ra["findings"])
    assert "cheap" not in labels.lower() or "Alpha" not in labels
    assert not any("Alpha" in str(f) for f in ra["findings"])
    rb = client.post("/api/review", headers=CREATOR, json={"brandId": a["id"], "productId": None, "content": "A fast kettle.", "meta": META}).json
    assert not any("swift" in str(f).lower() for f in rb["findings"])
    # a product from another brand cannot be selected
    bad = client.post("/api/review", headers=CREATOR, json={"brandId": a["id"], "productId": empty["id"], "content": "Hello.", "meta": META})
    assert bad.status_code in (404, 422)
    # an incomplete fact sheet never yields invented facts: an unsupported figure is flagged as unverified
    r = client.post("/api/review", headers=CREATOR, json={"brandId": b["id"], "productId": empty["id"], "content": "Loved by 99% of owners.", "meta": META}).json
    assert r["findings"] and all(f.get("source") or f.get("needsHuman") or f["severity"] != "critical" for f in r["findings"])
    # submissions keep their brand/product after a fresh read
    s = client.post("/api/submissions", headers=CREATOR, json={"brandId": a["id"], "productId": pa["id"], "title": "T", "content": "Fine text.", "meta": META, "findings": []}).json["submission"]
    again = client.get(f"/api/submissions/{s['id']}", headers=OWNER).json["submission"]
    assert again["brandId"] == a["id"] and again["productId"] == pa["id"] and again["productName"] == "Kettle"


def test_insights_counts_match_submissions(client):
    b = mk_brand(client)
    ids = []
    for i in range(3):
        s = client.post("/api/submissions", headers=CREATOR, json=body(b, f"Text number {i}.", title=f"Post {i}")).json["submission"]
        ids.append(s["id"])
    client.post(f"/api/submissions/{ids[0]}/decision", headers=REV, json={"status": "approved"})
    client.post(f"/api/submissions/{ids[1]}/decision", headers=REV, json={"status": "rejected", "comment": "Off brand."})
    t = client.get("/api/insights", headers=OWNER).json["totals"]
    assert (t["submissions"], t["approved"], t["rejected"], t["pending"]) == (3, 1, 1, 1)
