import base64
import binascii

from ..auth import ApiError
from . import brands as B

MIMES = {"image/png", "image/jpeg", "image/webp", "image/gif", "image/svg+xml", "application/pdf", "text/plain", "text/markdown"}


def upload(store, cfg, user, d):
    name, mime = B.s(d.get("name"), 200), str(d.get("mime") or "")
    if mime not in MIMES:
        raise ApiError(415, "Unsupported file type. Use PNG, JPEG, WebP, GIF, SVG, PDF, TXT or MD.")
    try:
        raw = base64.b64decode(str(d.get("data") or ""), validate=True)
    except (binascii.Error, ValueError):
        raise ApiError(422, "The file could not be read")
    if not raw:
        raise ApiError(422, "The file is empty")
    if len(raw) > cfg.max_asset_bytes:
        raise ApiError(413, f"Files can be up to {cfg.max_asset_bytes // 1000} KB")
    aid = B.nid("a")
    store.put("asset", aid, {"id": aid, "name": name or "file", "mime": mime, "size": len(raw), "data": d["data"], "uploadedBy": user["name"], "uploadedAt": B.now()})
    return {"assetId": aid, "name": name or "file", "mime": mime, "size": len(raw), "kind": d.get("kind") if d.get("kind") in B.KINDS else "other"}


def fetch(store, aid):
    a = store.get("asset", aid)
    if not a:
        raise ApiError(404, "File not found")
    return a["mime"], base64.b64decode(a["data"]), a["name"]
