"""Version history for brand profiles and product fact sheets.

Every save already writes an immutable full snapshot (`brand_version` / `product_version`). This module makes that history usable:
what was in each version, what changed between any two versions (added / modified / removed, with before and after values),
and restoring an earlier version as a NEW version. Nothing here can edit or delete a stored version.
"""
from ..auth import ApiError
from . import brands as B

META_KEYS = {"id", "version", "createdAt", "createdBy", "updatedAt", "updatedBy", "changeNote", "demo", "brandId", "restoredFrom"}

SCALARS = {"name": "Name", "description": "Description", "heritage": "Heritage", "tagline": "Tagline", "industry": "Industry", "history": "History",
           "voice": "Voice", "toneGuidance": "Tone and communication guidance", "targetAudience": "Target audience", "logoAssetId": "Logo file",
           "notes": "Notes", "imageAssetId": "Product image"}
STRING_LISTS = {"personality": "Brand personality", "previousNames": "Previous names", "fonts": "Approved fonts", "deprecatedAssets": "Retired assets", "values": "Values"}
ITEM_LISTS = {  # field -> (label, one-line summary of an item, keys compared for "modified")
    "approvedClaims": ("Approved claims", lambda x: x.get("text", ""), ("text", "source", "status")),
    "restrictedClaims": ("Restricted claims", lambda x: x.get("text", ""), ("text", "reason", "status")),
    "terminology": ("Terminology", lambda x: f"{x.get('avoid', '')} → {x.get('prefer', '')}", ("avoid", "prefer", "strict", "source", "status")),
    "toneAvoid": ("Off-voice wording", lambda x: x.get("phrase", ""), ("phrase", "prefer", "reason", "status")),
    "guidelines": ("Guidelines", lambda x: x.get("text", ""), ("text", "source", "status")),
    "legal": ("Legal notes", lambda x: x.get("text", ""), ("text", "source", "status")),
    "colours": ("Colour palette", lambda x: f"{x.get('name', '')} {x.get('hex', '')}".strip(), ("name", "hex", "role", "status")),
    "assets": ("Uploaded assets", lambda x: f"{x.get('name', '')} ({x.get('kind', '')})", ("assetId", "name", "kind", "note")),
    "specs": ("Specifications", lambda x: f"{x.get('name', '')}: {x.get('value', '')}", ("name", "value", "source", "status")),
}
ORDER = [*SCALARS, *STRING_LISTS, *ITEM_LISTS]
LABEL = {**SCALARS, **STRING_LISTS, **{k: v[0] for k, v in ITEM_LISTS.items()}}


def _txt(v):
    return "" if v is None else str(v)


def _detail(a, b, keys):
    out = []
    for k in keys:
        if _txt(a.get(k)) != _txt(b.get(k)):
            out.append(f"{k}: “{_txt(a.get(k))}” → “{_txt(b.get(k))}”")
    return "; ".join(out)


def diff(old, new):
    """Field-level changes from `old` to `new` (either may be {} for 'nothing')."""
    old, new, out = old or {}, new or {}, []
    for k in ORDER:
        if k in SCALARS:
            a, b = _txt(old.get(k)).strip(), _txt(new.get(k)).strip()
            if a != b:
                out.append({"field": k, "label": LABEL[k], "change": "added" if not a else "removed" if not b else "modified", "before": a or None, "after": b or None})
        elif k in STRING_LISTS:
            a, b = list(old.get(k) or []), list(new.get(k) or [])
            for x in a:
                if x not in b:
                    out.append({"field": k, "label": LABEL[k], "change": "removed", "before": x, "after": None})
            for x in b:
                if x not in a:
                    out.append({"field": k, "label": LABEL[k], "change": "added", "before": None, "after": x})
        else:
            _, summ, keys = ITEM_LISTS[k]
            a, b = {x.get("id"): x for x in old.get(k) or []}, {x.get("id"): x for x in new.get(k) or []}
            for i, x in a.items():
                if i not in b:
                    out.append({"field": k, "label": LABEL[k], "change": "removed", "before": summ(x), "after": None, "itemId": i})
                elif any(_txt(x.get(c)) != _txt(b[i].get(c)) for c in keys):
                    out.append({"field": k, "label": LABEL[k], "change": "modified", "before": summ(x), "after": summ(b[i]), "itemId": i, "detail": _detail(x, b[i], keys)})
            for i, x in b.items():
                if i not in a:
                    out.append({"field": k, "label": LABEL[k], "change": "added", "before": None, "after": summ(x), "itemId": i})
    return out


def changed_fields(changes):
    """Group a diff by field for a compact 'what changed' summary."""
    by = {}
    for c in changes:
        g = by.setdefault(c["field"], {"field": c["field"], "label": c["label"], "added": 0, "modified": 0, "removed": 0})
        g[c["change"]] += 1
    return [by[k] for k in ORDER if k in by]


def _kind(level):
    return "brand" if level == "brand" else "product"


def history(store, level, rid):
    """All versions, newest first, each with who/when, the change note and a summary of the fields it changed."""
    vs = sorted(B.versions(store, _kind(level), rid), key=lambda v: v["version"])
    out, prev = [], None
    for v in vs:
        ch = diff(prev, v) if prev else []
        out.append({"version": v["version"], "updatedAt": v.get("updatedAt"), "updatedBy": v.get("updatedBy"), "changeNote": v.get("changeNote") or "",
                    "initial": prev is None, "restoredFrom": v.get("restoredFrom"), "changedFields": changed_fields(ch), "changeCount": len(ch),
                    "name": v.get("name")})
        prev = v
    return list(reversed(out))


def get_version(store, level, rid, n):
    v = store.get(f"{_kind(level)}_version", f"{rid}:{n}")
    if not v:
        raise ApiError(404, f"Version {n} was not found")
    return v


def snapshot(store, level, rid, n):
    """One version in full, plus what it changed compared with the version before it."""
    v = get_version(store, level, rid, n)
    prev = store.get(f"{_kind(level)}_version", f"{rid}:{n - 1}") if n > 1 else None
    ch = diff(prev, v)
    return {"version": v, "previous": n - 1 if prev else None, "changes": ch, "changedFields": changed_fields(ch)}


def compare(store, level, rid, a, b):
    va, vb = get_version(store, level, rid, a), get_version(store, level, rid, b)
    ch = diff(va, vb)
    meta = lambda v: {"version": v["version"], "updatedAt": v.get("updatedAt"), "updatedBy": v.get("updatedBy"), "changeNote": v.get("changeNote") or ""}  # noqa: E731
    return {"from": meta(va), "to": meta(vb), "changes": ch, "changedFields": changed_fields(ch),
            "counts": {k: sum(1 for c in ch if c["change"] == k) for k in ("added", "modified", "removed")}}


def restore(store, user, level, rid, n, d, brand_id=None):
    """Restoring never rewinds history: the old content becomes a new, latest version and every earlier version stays."""
    old = get_version(store, level, rid, n)
    note = B.s(d.get("changeNote"), 250)
    payload = {k: v for k, v in old.items() if k not in META_KEYS}
    cur = B.get_brand(store, rid) if level == "brand" else B.get_product(store, rid, brand_id)
    if d.get("version") is not None and int(d["version"] or 0) != cur["version"]:
        raise ApiError(409, "This was changed by someone else. Reload it before restoring.", currentVersion=cur["version"])
    if old["version"] == cur["version"] and not diff(old, cur):
        raise ApiError(409, f"Version {n} is already the current version.")
    payload.update(version=cur["version"], changeNote=(f"Restored from version {n}" + (f": {note}" if note else "")))
    if level == "brand":
        return B.save_brand(store, user, payload, rid, restored_from=n)
    return B.save_product(store, user, brand_id, payload, rid, restored_from=n)
