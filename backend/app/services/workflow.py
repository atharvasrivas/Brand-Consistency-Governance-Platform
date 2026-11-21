"""Submission workflow. Rules enforced on the server regardless of what the browser sends:
  * a submission is tied to one brand (+ optionally one of its products) and the profile versions used are recorded
  * findings are re-run on the server against that profile; the client cannot hide one
  * a mandatory finding must be fixed, or rejected with a written reason (an override); items that need a person are
    routed to the reviewer instead of blocking
  * reviewers do not submit; nobody decides their own submission; changes/rejection need a comment
  * approving with open or overridden mandatory findings needs explicit acknowledgement
Status lifecycle: draft -> submitted -> under_review -> (approved | rejected | changes_requested);
changes_requested -> resubmitted -> under_review ... Every decision, comment and revision is recorded with who and when.
"""
import base64
import binascii

from ..auth import ApiError
from ..engine import review as engine
from . import assets
from . import brands as B

TYPES = ("blog", "social", "ad", "email", "document")
STATUSES = ("draft", "submitted", "under_review", "changes_requested", "resubmitted", "approved", "rejected")
PENDING = ("submitted", "under_review", "resubmitted")  # waiting on a reviewer
LABEL = {"approved": "Approved the content", "changes_requested": "Requested changes", "rejected": "Rejected the content"}
KEEP_IMG = ("IMG-PALETTE", "IMG-CONTRAST", "IMG-AI", "IMG-UNANALYSED")  # browser pixel analysis / AI vision: the server cannot recompute these on submit
ADVISORY_IMG = ("IMG-AI", "IMG-UNANALYSED")  # always flexible and routed to a person, whatever the browser claims
IMG_MIMES = ("image/png", "image/jpeg", "image/webp", "image/gif")


def light(f):
    st = f.get("status") or "open"
    return {"key": f["key"], "ruleId": f.get("ruleId"), "label": f.get("label"), "category": f.get("category"), "severity": f.get("severity", "suggestion"),
            "strictness": f.get("strictness", "flexible"), "quote": f.get("quote"), "status": st, "note": f.get("note"), "suggestion": f.get("suggestion"),
            "source": f.get("source"), "occurrences": f.get("occurrences", 1), "needsHuman": bool(f.get("needsHuman")) if st == "open" else False,
            **({"approvedFact": f["approvedFact"]} if f.get("approvedFact") else {}), **({"applied": str(f["applied"])[:300]} if f.get("applied") else {}),
            **({"scope": f["scope"]} if f.get("scope") else {})}


def clean_meta(d):
    m = d.get("meta") if isinstance(d.get("meta"), dict) else d
    if m.get("type") not in TYPES:
        raise ApiError(422, "Choose a content type: " + ", ".join(TYPES))
    return {"type": m["type"], "audience": str(m.get("audience") or "")[:300], "purpose": str(m.get("purpose") or "")[:300]}


def clean_image(img, max_bytes=1_400_000):
    """The advert image as sent for review. `data` (base64) + `mime` carry the pixels for AI analysis; they are validated here and are
    never kept inline on a submission (see persist_image)."""
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
    mime = str(img.get("mime") or "")[:60]
    if img.get("data"):
        if mime not in IMG_MIMES:
            out["unsupported"] = mime or "unknown"
        else:
            try:
                raw = base64.b64decode(str(img["data"]), validate=True)
            except (binascii.Error, ValueError):
                raise ApiError(422, "The image could not be read")
            if not raw:
                raise ApiError(422, "The image is empty")
            if len(raw) > max_bytes:
                raise ApiError(413, f"The image is too large to analyse ({len(raw) // 1000} KB, limit {max_bytes // 1000} KB). Use a smaller copy.")
            out.update(data=str(img["data"]), mime=mime, size=len(raw))
    else:
        if mime:
            out["mime"] = mime
        if img.get("assetId"):
            out["assetId"] = str(img["assetId"])[:40]
        if img.get("unsupported"):
            out["unsupported"] = str(img["unsupported"])[:60]
    return out


def persist_image(store, user, image):
    """Keep the picture as a stored asset (so a reviewer can see what was checked) and drop the inline base64 from the submission record."""
    if not image or not image.get("data"):
        return image
    aid = assets.save_raw(store, user, image.get("name") or "advert image", image["mime"], image["data"], image.get("size", 0))
    return {k: v for k, v in image.items() if k != "data"} | {"assetId": aid}


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
            adv = {"strictness": "flexible", "needsHuman": True} if str(cf.get("ruleId", "")) in ADVISORY_IMG else {}
            out.append(light({**cf, **adv, "status": cf.get("status") if cf.get("status") in ("accepted", "rejected") else "open"}))
    return out, blockers


def norm(sub):
    """Records written before the status list was extended used a single 'in_review' state."""
    if sub and sub.get("status") == "in_review":
        sub["status"] = "submitted"
    if sub is not None:
        sub.setdefault("decisions", [])
    return sub


def _comment(sub, user, text):
    sub["comments"].append({"id": f"{sub['id']}-c{len(sub['comments'])}", "by": user["name"], "byId": user["id"], "designation": user.get("designation"),
                            "role": user["role"], "text": text, "at": B.now(), "version": len(sub["versions"])})


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
    meta, image = clean_meta(d), clean_image(d.get("image"), cfg.max_image_bytes)
    ctx = B.build_context(store, *scope_from(d))
    findings, blockers = verified_findings(content, meta, image, ctx, d.get("findings"))
    draft = bool(d.get("draft"))
    if blockers and not draft:
        raise ApiError(422, "Mandatory brand rules still need a decision", blockers=blockers)
    at = B.now()
    with store.lock:
        if not draft:
            for o in map(norm, store.list("submission")):
                if (o["authorId"] == user["id"] and o["brandId"] == ctx["brand"]["id"] and o.get("productId") == (ctx["product"]["id"] if ctx["product"] else None)
                        and o["status"] in PENDING and o["versions"][-1]["content"] == content):
                    raise ApiError(409, f"This exact content is already waiting for review as {o['id']}.", submissionId=o["id"])
        image = persist_image(store, user, image)  # only once the submission is certain to be created
        sub = {"id": _next_id(store), "title": title, **meta, "authorId": user["id"], "author": user["name"], "authorDesignation": user.get("designation"),
               "status": "draft" if draft else "submitted", "createdAt": at, "updatedAt": at,
               "versions": [{"n": 1, "content": content, "at": at, "by": user["name"], "note": "Draft saved" if draft else "First submission"}], "image": image, "findings": findings,
               "comments": [], "decisions": [], "activity": [{"at": at, "by": user["name"], "text": "Saved as draft" if draft else "Submitted for review"}],
               "noApprovedContent": not ctx["hasApproved"]}
        _stamp(sub, ctx)
        if (d.get("note") or "").strip():
            _comment(sub, user, d["note"].strip()[:4000])
        store.put("submission", sub["id"], sub)
    return sub


def get(store, user, sid):
    s = norm(store.get("submission", sid))
    if not s or (user["role"] == "creator" and s["authorId"] != user["id"]):
        raise ApiError(404, "Submission not found")
    return s


def visible(store, user):
    subs = [norm(x) for x in store.list("submission")]
    if user["role"] == "creator":
        subs = [s for s in subs if s["authorId"] == user["id"]]
    else:  # drafts are private to their author
        subs = [s for s in subs if s["status"] != "draft" or s["authorId"] == user["id"]]
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
    if sub["versions"][-1]["content"] == content:
        raise ApiError(409, "Nothing has changed since the last version. Edit the content before resubmitting.")
    fields = {k: str(d[k]).strip()[:200] for k in ("title", "audience", "purpose") if d.get(k)}
    if d.get("type"):
        fields["type"] = d["type"]
    merged = {**sub, **fields}
    meta = clean_meta(merged)
    image = clean_image(d["image"], cfg.max_image_bytes) if "image" in d else sub.get("image")
    ctx = B.build_context(store, sub["brandId"], sub["productId"])  # a revision stays on the same brand/product, latest profile
    findings, blockers = verified_findings(content, meta, image, ctx, d.get("findings"))
    if blockers:
        raise ApiError(422, "Mandatory brand rules still need a decision", blockers=blockers)
    at, n = B.now(), len(sub["versions"]) + 1
    image = persist_image(store, user, image)
    with store.lock:
        sub.update(fields)
        sub.update({"image": image, "status": "resubmitted", "updatedAt": at, "findings": findings, "noApprovedContent": not ctx["hasApproved"]})
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
    if sub["status"] not in PENDING:
        raise ApiError(409, f"This submission is already {sub['status'].replace('_', ' ')}.")
    if sub["authorId"] == user["id"]:
        raise ApiError(403, "You cannot approve or reject your own submission: approval is an independent check, so a different reviewer or owner has to make this decision. Ask another reviewer.")
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
        sub["decisions"].append({"n": len(sub["decisions"]) + 1, "status": status, "version": len(sub["versions"]), "by": user["name"], "byId": user["id"],
                                 "role": user["role"], "at": at, "comment": comment[:4000], "acknowledged": bool(d.get("acknowledged"))})
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


def submit_draft(store, cfg, user, sid, d):
    sub = get(store, user, sid)
    if sub["authorId"] != user["id"]:
        raise ApiError(403, "Only the author can submit a draft.")
    if sub["status"] != "draft":
        raise ApiError(409, f"This submission is already {sub['status'].replace('_', ' ')}.")
    content = d.get("content") or sub["versions"][-1]["content"]
    check_content(cfg, content)
    meta, image = clean_meta({**sub, **{k: d[k] for k in ("type", "audience", "purpose") if d.get(k)}}), sub.get("image")
    ctx = B.build_context(store, sub["brandId"], sub["productId"])
    findings, blockers = verified_findings(content, meta, image, ctx, d.get("findings"))
    if blockers:
        raise ApiError(422, "Mandatory brand rules still need a decision", blockers=blockers)
    at = B.now()
    with store.lock:
        sub.update({**meta, "findings": findings, "status": "submitted", "updatedAt": at, "noApprovedContent": not ctx["hasApproved"]})
        _stamp(sub, ctx)
        if content != sub["versions"][-1]["content"]:
            sub["versions"].append({"n": len(sub["versions"]) + 1, "content": content, "at": at, "by": user["name"], "note": "Edited before submission"})
        sub["activity"].append({"at": at, "by": user["name"], "text": "Submitted for review"})
        store.put("submission", sid, sub)
    return sub


def start_review(store, user, sid):
    if user["role"] not in ("reviewer", "owner"):
        raise ApiError(403, "Only reviewers and owners can start a review.")
    sub = get(store, user, sid)
    if sub["authorId"] == user["id"]:
        raise ApiError(403, "You cannot review your own submission.")
    if sub["status"] not in ("submitted", "resubmitted"):
        raise ApiError(409, f"This submission is {sub['status'].replace('_', ' ')}; it cannot be taken into review.")
    at = B.now()
    with store.lock:
        sub.update(status="under_review", updatedAt=at, reviewer=user["name"], reviewerId=user["id"])
        sub["activity"].append({"at": at, "by": user["name"], "text": "Started review"})
        store.put("submission", sid, sub)
    return sub
