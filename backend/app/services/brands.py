"""Brand and product profiles: validation, storage, versions, and the approved-context builder.

Isolation: every function takes explicit ids. A product always belongs to exactly one brand, and the review
context is built from that one brand (+ optionally one of its products) and nothing else.
Items carry status "approved" or "draft". Only approved items are ever used as facts in a review.
"""
import re
import uuid
from datetime import datetime, timezone

from ..auth import ApiError

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
KINDS = ("logo", "image", "guideline", "other")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def nid(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def s(v, n=2000):
    return re.sub(r"[ \t]+\n", "\n", str(v or "")).strip()[:n]


def _strs(v, n=40, m=120):
    if not isinstance(v, list):
        return []
    return [s(x, m) for x in v if s(x, m)][:n]


def _status(x):
    return "draft" if x.get("status") == "draft" else "approved"


def _list(v, build, limit=100):
    out = []
    for x in (v if isinstance(v, list) else [])[:limit]:
        if isinstance(x, dict):
            item = build(x)
            if item:
                item["id"] = s(x.get("id"), 40) or nid("i")
                item["status"] = _status(x)
                if x.get("generated"):
                    item["generated"] = True
                out.append(item)
    return out


def _claim(x):
    t = s(x.get("text"), 500)
    return {"text": t, "source": s(x.get("source"), 300)} if t else None


def _restricted(x):
    t = s(x.get("text"), 300)
    return {"text": t, "reason": s(x.get("reason"), 400)} if t else None


def _term(x):
    a, p = s(x.get("avoid"), 120), s(x.get("prefer"), 120)
    return {"avoid": a, "prefer": p, "strict": bool(x.get("strict")), "source": s(x.get("source"), 300)} if a and p else None


def _tone(x):
    ph = s(x.get("phrase"), 120)
    return {"phrase": ph, "prefer": s(x.get("prefer"), 120), "reason": s(x.get("reason"), 300)} if ph else None


def _guideline(x):
    t = s(x.get("text"), 600)
    return {"text": t, "source": s(x.get("source"), 300)} if t else None


def _spec(x):
    n, v = s(x.get("name"), 120), s(x.get("value"), 200)
    return {"name": n, "value": v, "source": s(x.get("source"), 300)} if n and v else None


def _colour(x):
    h = s(x.get("hex"), 7)
    if not HEX.match(h):
        return None
    return {"name": s(x.get("name"), 60) or h.upper(), "hex": h.upper(), "role": x.get("role") if x.get("role") in ("primary", "secondary", "accent") else "primary"}


def _asset(x):
    aid = s(x.get("assetId"), 40)
    if not aid:
        return None
    return {"assetId": aid, "name": s(x.get("name"), 200), "kind": x.get("kind") if x.get("kind") in KINDS else "other",
            "mime": s(x.get("mime"), 80), "size": int(x.get("size") or 0), "note": s(x.get("note"), 300)}


COMMON = (("approvedClaims", _claim), ("restrictedClaims", _restricted), ("terminology", _term), ("assets", _asset))


def clean_brand(d):
    name = s(d.get("name"), 100)
    if not name:
        raise ApiError(422, "A brand needs a name")
    out = {"name": name, "description": s(d.get("description"), 2000), "heritage": s(d.get("heritage"), 3000),
           "personality": _strs(d.get("personality"), 20, 60), "toneGuidance": s(d.get("toneGuidance"), 2000),
           "previousNames": _strs(d.get("previousNames"), 10, 100), "fonts": _strs(d.get("fonts"), 10, 80),
           "deprecatedAssets": _strs(d.get("deprecatedAssets"), 20, 120), "logoAssetId": s(d.get("logoAssetId"), 40),
           "toneAvoid": _list(d.get("toneAvoid"), _tone),
           "tagline": s(d.get("tagline"), 200), "industry": s(d.get("industry"), 120), "history": s(d.get("history"), 4000),
           "values": _strs(d.get("values"), 20, 80), "voice": s(d.get("voice"), 1500), "targetAudience": s(d.get("targetAudience"), 1500),
           "guidelines": _list(d.get("guidelines"), _guideline), "legal": _list(d.get("legal"), _guideline),
           "colours": _list(d.get("colours"), _colour, 24)}
    for k, fn in COMMON:
        out[k] = _list(d.get(k), fn)
    return out


def clean_product(d):
    name = s(d.get("name"), 100)
    if not name:
        raise ApiError(422, "A product needs a name")
    out = {"name": name, "description": s(d.get("description"), 3000), "previousNames": _strs(d.get("previousNames"), 10, 100),
           "imageAssetId": s(d.get("imageAssetId"), 40), "specs": _list(d.get("specs"), _spec),
           "notes": s(d.get("notes"), 3000), "guidelines": _list(d.get("guidelines"), _guideline), "legal": _list(d.get("legal"), _guideline)}
    for k, fn in COMMON:
        out[k] = _list(d.get(k), fn)
    return out


# ---------- brands ----------
def list_brands(store):
    return sorted(store.list("brand"), key=lambda b: b["name"].lower())


def get_brand(store, bid):
    b = store.get("brand", bid or "")
    if not b:
        raise ApiError(404, "Brand not found")
    return b


def _unique(store, name, ignore=None):
    if any(b["name"].lower() == name.lower() and b["id"] != ignore for b in store.list("brand")):
        raise ApiError(409, f"A brand called “{name}” already exists")


def save_brand(store, user, d, bid=None):
    new = clean_brand(d)
    with store.lock:
        if bid is None:
            _unique(store, new["name"])
            rec = {"id": nid("b"), "version": 1, "createdBy": user["name"], "createdAt": now(), **new}
        else:
            cur = get_brand(store, bid)
            if int(d.get("version") or 0) != cur["version"]:
                raise ApiError(409, "This brand was changed by someone else. Reload it before saving.", currentVersion=cur["version"])
            _unique(store, new["name"], ignore=bid)
            rec = {**new, "id": bid, "version": cur["version"] + 1, "createdBy": cur["createdBy"], "createdAt": cur["createdAt"],
                   **({"demo": True} if cur.get("demo") else {})}
        rec.update({"updatedBy": user["name"], "updatedAt": now(), "changeNote": s(d.get("changeNote"), 300)})
        store.put("brand", rec["id"], rec)
        store.put("brand_version", f"{rec['id']}:{rec['version']}", rec)
    return rec


# ---------- products ----------
def list_products(store, brand_id=None):
    ps = store.list("product")
    if brand_id:
        ps = [p for p in ps if p["brandId"] == brand_id]
    return sorted(ps, key=lambda p: p["name"].lower())


def get_product(store, pid, brand_id=None):
    p = store.get("product", pid or "")
    if not p or (brand_id and p["brandId"] != brand_id):
        raise ApiError(404, "Product not found for this brand")
    return p


def save_product(store, user, brand_id, d, pid=None):
    get_brand(store, brand_id)
    new = clean_product(d)
    with store.lock:
        siblings = list_products(store, brand_id)
        if any(p["name"].lower() == new["name"].lower() and p["id"] != pid for p in siblings):
            raise ApiError(409, f"This brand already has a product called “{new['name']}”")
        if pid is None:
            rec = {"id": nid("p"), "brandId": brand_id, "version": 1, "createdBy": user["name"], "createdAt": now(), **new}
        else:
            cur = get_product(store, pid, brand_id)
            if int(d.get("version") or 0) != cur["version"]:
                raise ApiError(409, "This product was changed by someone else. Reload it before saving.", currentVersion=cur["version"])
            rec = {**new, "id": pid, "brandId": brand_id, "version": cur["version"] + 1, "createdBy": cur["createdBy"], "createdAt": cur["createdAt"],
                   **({"demo": True} if cur.get("demo") else {})}
        rec.update({"updatedBy": user["name"], "updatedAt": now(), "changeNote": s(d.get("changeNote"), 300)})
        store.put("product", rec["id"], rec)
        store.put("product_version", f"{rec['id']}:{rec['version']}", rec)
    return rec


def versions(store, kind, id):
    out = [v for v in store.list(f"{kind}_version") if v["id"] == id]
    return sorted(out, key=lambda v: v["version"], reverse=True)


# ---------- approved context for a review ----------
def build_context(store, brand_id, product_id):
    """Everything a review may use as fact, taken from ONE brand and optionally ONE of its products. Drafts excluded."""
    if not brand_id:
        raise ApiError(422, "Select a brand before running a review")
    brand = get_brand(store, brand_id)
    product = None
    if product_id:
        product = get_product(store, product_id, brand_id)  # 404 if it belongs to another brand
    approved = lambda items: [i for i in items if i.get("status") != "draft"]  # noqa: E731
    ctx = {
        "brand": {"id": brand["id"], "name": brand["name"], "version": brand["version"]},
        "product": {"id": product["id"], "name": product["name"], "version": product["version"]} if product else None,
        "brandName": brand["name"], "productName": product["name"] if product else None,
        "previousNames": [(n, brand["name"], "brand") for n in brand.get("previousNames", [])]
        + ([(n, product["name"], "product") for n in product.get("previousNames", [])] if product else []),
        "claims": [], "restricted": [], "terms": [], "toneAvoid": approved(brand.get("toneAvoid", [])), "specs": [],
        "colours": [c for c in brand.get("colours", []) if c.get("status") != "draft"], "fonts": brand.get("fonts", []),
        "deprecatedAssets": brand.get("deprecatedAssets", []), "approvedAssetNames": [a["name"] for a in approved(brand.get("assets", []))],
        "voice": {"personality": brand.get("personality", []), "toneGuidance": brand.get("toneGuidance", "")},
        "descriptions": [brand.get("description", ""), brand.get("heritage", "")] + ([product.get("description", "")] if product else []),
    }
    for level, label, rec in (("brand", f"{brand['name']} brand profile", brand), ("product", f"{product['name']} fact sheet" if product else "", product)):
        if not rec:
            continue
        for c in approved(rec.get("approvedClaims", [])):
            ctx["claims"].append({**c, "level": level, "doc": label})
        for r in approved(rec.get("restrictedClaims", [])):
            ctx["restricted"].append({**r, "level": level, "doc": label})
        for t in approved(rec.get("terminology", [])):
            ctx["terms"].append({**t, "level": level, "doc": label})
    if product:
        for sp in approved(product.get("specs", [])):
            ctx["specs"].append({**sp, "doc": f"{product['name']} fact sheet"})
    ctx["hasApproved"] = bool(ctx["claims"] or ctx["restricted"] or ctx["terms"] or ctx["specs"] or ctx["toneAvoid"] or ctx["previousNames"])
    return ctx
