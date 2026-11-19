"""Creator-to-Owner profile suggestions. A suggestion never changes the official profile; the Owner edits it manually."""
from ..auth import ApiError
from . import brands as B


def create(store, user, d):
    brand = B.get_brand(store, d.get("brandId"))
    pid = d.get("productId") or None
    prod = B.get_product(store, pid, brand["id"]) if pid else None
    title, proposal = B.s(d.get("title"), 200), B.s(d.get("proposal"), 3000)
    if not title or not proposal:
        raise ApiError(422, "Add a short title and describe the change you suggest")
    rec = {"id": B.nid("s"), "brandId": brand["id"], "brandName": brand["name"], "productId": pid, "productName": prod["name"] if prod else None,
           "title": title, "proposal": proposal, "status": "pending", "authorId": user["id"], "author": user["name"], "authorDesignation": user.get("designation"),
           "authorRole": user["role"], "createdAt": B.now()}
    store.put("suggestion", rec["id"], rec)
    return rec


def visible(store, user):
    items = store.list("suggestion")
    if user["role"] != "owner":
        items = [s for s in items if s["authorId"] == user["id"]]
    return sorted(items, key=lambda s: s["createdAt"], reverse=True)


def resolve(store, user, sid, d):
    s = store.get("suggestion", sid)
    if not s:
        raise ApiError(404, "Suggestion not found")
    if s["status"] != "pending":
        raise ApiError(409, "This suggestion was already resolved")
    status = d.get("status")
    if status not in ("accepted", "dismissed"):
        raise ApiError(422, "Status must be accepted or dismissed")
    s.update(status=status, resolvedBy=user["name"], resolvedAt=B.now(), resolutionNote=B.s(d.get("note"), 500))
    store.put("suggestion", sid, s)
    return s
