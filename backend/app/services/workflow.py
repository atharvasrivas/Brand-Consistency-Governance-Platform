"""Submission workflow. Rules enforced on the server regardless of what the browser sends:
  * a submission is tied to one brand (+ optionally one of its products) and the profile versions used are recorded
  * findings are re-run on the server against that profile; the client cannot hide one
  * a mandatory finding must be fixed, or rejected with a written reason (an override); items that need a person are
    routed to the reviewer instead of blocking
  * reviewers do not submit; nobody decides their own submission; changes/rejection need a comment
  * approving with open or overridden mandatory findings needs explicit acknowledgement
"""
from ..auth import ApiError
from ..engine import review as engine
from . import brands as B

TYPES = ("blog", "social", "ad", "email", "document")
LABEL = {"approved": "Approved the content", "changes_requested": "Requested changes", "rejected": "Rejected the content"}
KEEP_IMG = ("IMG-PALETTE", "IMG-CONTRAST")  # need browser-side pixel analysis; the server cannot recompute them


def light(f):
    st = f.get("status") or "open"
    return {"key": f["key"], "ruleId": f.get("ruleId"), "label": f.get("label"), "category": f.get("category"), "severity": f.get("severity", "suggestion"),
            "strictness": f.get("strictness", "flexible"), "quote": f.get("quote"), "status": st, "note": f.get("note"), "suggestion": f.get("suggestion"),
            "source": f.get("source"), "occurrences": f.get("occurrences", 1), "needsHuman": bool(f.get("needsHuman")) if st == "open" else False}


def clean_meta(d):
    m = d.get("meta") if isinstance(d.get("meta"), dict) else d
    if m.get("type") not in TYPES:
        raise ApiError(422, "Choose a content type: " + ", ".join(TYPES))
    return {"type": m["type"], "audience": str(m.get("audience") or "")[:300], "purpose": str(m.get("purpose") or "")[:300]}


def clean_image(img):
    if not img:
        return None
    if not isinstance(img, dict):
        raise ApiError(422, "image must be an object")
    out = {k: str(img.get(k) or "")[:2000] for k in ("name", "alt", "fonts", "textInImage")}
    a = img.get("analysis")
    if isinstance(a, dict):
        off = [c for c in (a.get("offPalette") or [])[:6] if isinstance(c, dict) and isinstance(c.get("nearest"), dict) and isinstance(c.get("hex"), str)
               and isinstance(c.get("share"), (int, float))]
        lc = a.get("lowContrast") if isinstance(a.get("lowContrast"), dict) and isinstance(a["lowContrast"].get("ratio"), (int, float)) else None
        out["analysis"] = {"offPalette": off, "lowContrast": lc}
    return out


def scope_from(d):
    if "productId" not in d:
        raise ApiError(422, "Select a product, or choose “Brand-level content / no product”.")
    return d.get("brandId"), (d.get("productId") or None)


def check_content(cfg, content):
    if not isinstance(content, str) or not content.strip():
        raise ApiError(422, "Add some content")
    if len(content) > cfg.max_content_chars:
        raise ApiError(413, "Content is too long")


def verified_findings(content, meta, image, ctx, client):
    server = engine.review(content, meta, image, ctx)
    cl = {f.get("key"): f for f in (client or []) if isinstance(f, dict) and f.get("key")}
    out, seen, blockers = [], set(), []
    for sf in server:
        seen.add(sf["key"])
        cf = cl.get(sf["key"], {})
        status = cf.get("status") if cf.get("status") in ("accepted", "rejected") else "open"
        note = (cf.get("note") or "").strip() or None
        f = light({**sf, "status": status, "note": note})
        info = {"key": f["key"], "label": f["label"], "quote": f["quote"]}
        if f["strictness"] == "mandatory" and status == "rejected" and not note:
            blockers.append({**info, "reason": "An override needs a written reason"})
        elif f["strictness"] == "mandatory" and status == "open" and not f["needsHuman"]:
            blockers.append({**info, "reason": "Fix it, or reject it with a reason"})
        out.append(f)
    for k, cf in cl.items():
        if k not in seen and (cf.get("status") == "accepted" or str(cf.get("ruleId", "")) in KEEP_IMG):
            out.append(light({**cf, "status": cf.get("status") if cf.get("status") in ("accepted", "rejected") else "open"}))
    return out, blockers


def _comment(sub, user, text):
    sub["comments"].append({"id": f"{sub['id']}-c{len(sub['comments'])}", "by": user["name"], "byId": user["id"], "designation": user.get("designation"),
                            "role": user["role"], "text": text, "at": B.now()})


def _next_id(store):
    return "S-%d" % (max([int(s["id"].split("-")[1]) for s in store.list("submission")] or [1000]) + 1)


def _stamp(sub, ctx):
    sub.update({"brandId": ctx["brand"]["id"], "brandName": ctx["brand"]["name"], "brandVersion": ctx["brand"]["version"],
                "productId": ctx["product"]["id"] if ctx["product"] else None, "productName": ctx["product"]["name"] if ctx["product"] else None,
                "productVersion": ctx["product"]["version"] if ctx["product"] else None})


def create(store, cfg, user, d):
    if user["role"] == "reviewer":
        raise ApiError(403, "Reviewers approve content; they do not submit it.")
    title = str(d.get("title") or "").strip()[:200]
    if not title:
        raise ApiError(422, "Add a title")
    content = d.get("content")
    check_content(cfg, content)
    meta, image = clean_meta(d), clean_image(d.get("image"))
    ctx = B.build_context(store, *scope_from(d))
    findings, blockers = verified_findings(content, meta, image, ctx, d.get("findings"))
    if blockers:
        raise ApiError(422, "Mandatory brand rules still need a decision", blockers=blockers)
    at = B.now()
    with store.lock:
        sub = {"id": _next_id(store), "title": title, **meta, "authorId": user["id"], "author": user["name"], "authorDesignation": user.get("designation"),
               "status": "in_review", "createdAt": at, "updatedAt": at,
               "versions": [{"n": 1, "content": content, "at": at, "by": user["name"], "note": "First submission"}], "image": image, "findings": findings,
               "comments": [], "activity": [{"at": at, "by": user["name"], "text": "Submitted for review"}],
               "noApprovedContent": not ctx["hasApproved"]}
        _stamp(sub, ctx)
        if (d.get("note") or "").strip():
            _comment(sub, user, d["note"].strip()[:4000])
        store.put("submission", sub["id"], sub)
    return sub


def get(store, user, sid):
    s = store.get("submission", sid)
    if not s or (user["role"] == "creator" and s["authorId"] != user["id"]):
        raise ApiError(404, "Submission not found")
    return s


def visible(store, user):
    subs = store.list("submission")
    if user["role"] == "creator":
        subs = [s for s in subs if s["authorId"] == user["id"]]
    return sorted(subs, key=lambda s: s["updatedAt"], reverse=True)


def resubmit(store, cfg, user, sid, d):
    sub = get(store, user, sid)
    if user["role"] == "reviewer":
        raise ApiError(403, "Reviewers cannot resubmit content.")
    if sub["authorId"] != user["id"] and user["role"] != "owner":
        raise ApiError(403, "Only the author or a brand owner can revise this.")
    if sub["status"] not in ("changes_requested", "rejected"):
        raise ApiError(409, f"A submission that is {sub['status'].replace('_', ' ')} cannot be revised.")
    content = d.get("content")
    check_content(cfg, content)
    fields = {k: str(d[k]).strip()[:200] for k in ("title", "audience", "purpose") if d.get(k)}
    if d.get("type"):
        fields["type"] = d["type"]
    merged = {**sub, **fields}
    meta = clean_meta(merged)
    image = clean_image(d["image"]) if "image" in d else sub.get("image")
    ctx = B.build_context(store, sub["brandId"], sub["productId"])  # a revision stays on the same brand/product, latest profile
    findings, blockers = verified_findings(content, meta, image, ctx, d.get("findings"))
    if blockers:
        raise ApiError(422, "Mandatory brand rules still need a decision", blockers=blockers)
    at, n = B.now(), len(sub["versions"]) + 1
    with store.lock:
        sub.update(fields)
        sub.update({"image": image, "status": "in_review", "updatedAt": at, "findings": findings, "noApprovedContent": not ctx["hasApproved"]})
        _stamp(sub, ctx)
        note = (d.get("note") or "").strip()
        sub["versions"].append({"n": n, "content": content, "at": at, "by": user["name"], "note": note or "Revised"})
        sub["activity"].append({"at": at, "by": user["name"], "text": f"Resubmitted as version {n}"})
        if note:
            _comment(sub, user, note[:4000])
        store.put("submission", sid, sub)
    return sub


def decide(store, user, sid, d):
    if user["role"] not in ("reviewer", "owner"):
        raise ApiError(403, "Only reviewers and owners can decide.")
    status = d.get("status")
    if status not in LABEL:
        raise ApiError(422, "Status must be approved, changes_requested or rejected")
    sub = get(store, user, sid)
    if sub["status"] != "in_review":
        raise ApiError(409, f"This submission is already {sub['status'].replace('_', ' ')}.")
    if sub["authorId"] == user["id"]:
        raise ApiError(403, "You cannot decide your own submission. Ask another reviewer.")
    comment = (d.get("comment") or "").strip()
    if status != "approved" and not comment:
        raise ApiError(422, "Say what needs to change: a comment is required.")
    if status == "approved":
        attn = [f for f in sub["findings"] if f["strictness"] == "mandatory" and f["status"] in ("open", "rejected")]
        if attn and not d.get("acknowledged"):
            raise ApiError(409, "This submission has unresolved or overridden mandatory findings. Acknowledge them to approve.", needsAcknowledgement=True, count=len(attn))
    at = B.now()
    with store.lock:
        sub.update(status=status, updatedAt=at)
        if comment:
            _comment(sub, user, comment[:4000])
        sub["activity"].append({"at": at, "by": user["name"], "text": LABEL[status] + (" (mandatory findings acknowledged)" if status == "approved" and d.get("acknowledged") else "")})
        store.put("submission", sid, sub)
    return sub


def comment(store, user, sid, d):
    text = (d.get("text") or "").strip()
    if not text:
        raise ApiError(422, "Write a comment")
    sub = get(store, user, sid)
    with store.lock:
        _comment(sub, user, text[:4000])
        store.put("submission", sid, sub)
    return sub


def recheck(store, user, sid):
    if user["role"] not in ("reviewer", "owner"):
        raise ApiError(403, "Only reviewers and owners can re-check submissions.")
    sub = get(store, user, sid)
    ctx = B.build_context(store, sub["brandId"], sub["productId"])
    meta = {"type": sub["type"], "audience": sub["audience"], "purpose": sub["purpose"]}
    server = engine.review(sub["versions"][-1]["content"], meta, sub.get("image"), ctx)
    prior = {f["key"]: f for f in sub["findings"]}
    out = [light({**f, "status": prior[f["key"]]["status"] if f["key"] in prior else "open", "note": prior.get(f["key"], {}).get("note")}) for f in server]
    out += [f for k, f in prior.items() if k not in {x["key"] for x in out} and f["ruleId"] in KEEP_IMG]
    added = len([f for f in out if f["key"] not in prior])
    with store.lock:
        sub["findings"] = out
        _stamp(sub, ctx)
        sub["activity"].append({"at": B.now(), "by": user["name"], "text": f"Re-checked against {ctx['brand']['name']} v{ctx['brand']['version']}: {added} new finding{'' if added == 1 else 's'}"})
        store.put("submission", sid, sub)
    return sub
