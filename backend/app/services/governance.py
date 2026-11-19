"""Brand Drift Radar, Brand Change Impact Scanner and Guideline Conflict Detector.

All three read stored data only. They flag and explain; a person decides. Nothing here edits a profile or a submission.
"""
import re
from collections import defaultdict
from datetime import datetime

from ..auth import ApiError
from . import brands as B

RANK = {"critical": 3, "warning": 2, "suggestion": 1}


def _norm(t):
    return re.sub(r"[^a-z0-9 ]+", " ", str(t or "").lower()).split()


def _week(iso):
    d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


# ---------------------------------------------------------------- drift
def drift(subs, brand_id=None):
    if brand_id:
        subs = [s for s in subs if s.get("brandId") == brand_id]
    groups = defaultdict(lambda: {"count": 0, "subs": set(), "authors": set(), "weeks": defaultdict(int), "sample": None, "severity": "suggestion"})
    for s in subs:
        wk = _week(s["createdAt"])
        for f in s.get("findings", []):
            if f.get("category") == "Content patterns":
                continue  # structural nudges are not brand drift
            k = (s.get("brandId"), s.get("productId"), f.get("ruleId") or f.get("label"), f.get("label"))
            g = groups[k]
            n = f.get("occurrences") or 1
            g["count"] += n
            g["subs"].add(s["id"])
            g["authors"].add(s["author"])
            g["weeks"][wk] += n
            g["sample"] = g["sample"] or f.get("quote")
            g["category"] = f.get("category")
            g["rule"] = (f.get("source") or {}).get("ref") or f.get("label")
            g["brandName"], g["productName"] = s.get("brandName"), s.get("productName")
            if RANK.get(f.get("severity"), 0) > RANK[g["severity"]]:
                g["severity"] = f["severity"]
    items = []
    for (bid, pid, _rid, label), g in groups.items():
        if len(g["subs"]) < 2:
            continue
        items.append({"brandId": bid, "brandName": g["brandName"], "productId": pid, "productName": g["productName"], "label": label,
                      "category": g["category"], "guideline": g["rule"], "severity": g["severity"], "occurrences": g["count"],
                      "submissions": len(g["subs"]), "creators": len(g["authors"]), "example": g["sample"],
                      "trend": [{"week": w, "count": c} for w, c in sorted(g["weeks"].items())],
                      "pattern": "multiple creators" if len(g["authors"]) > 1 else "same creator repeating"})
    items.sort(key=lambda x: (-RANK[x["severity"]], -x["submissions"], -x["occurrences"]))
    by_target = defaultdict(int)
    for s in subs:
        by_target[(s.get("brandName"), s.get("productName"))] += sum(f.get("occurrences") or 1 for f in s.get("findings", []) if f.get("category") != "Content patterns")
    hot = [{"brandName": b, "productName": p, "issues": n} for (b, p), n in sorted(by_target.items(), key=lambda x: -x[1]) if n]
    alerts = [f"“{i['label']}” has appeared in {i['submissions']} submissions for {i['brandName']}"
              f"{' / ' + i['productName'] if i['productName'] else ''} ({i['pattern']})." for i in items][:5]
    weeks = defaultdict(int)
    for i in items:
        for t in i["trend"]:
            weeks[t["week"]] += t["count"]
    return {"recurring": items, "hotspots": hot[:8], "alerts": alerts, "trend": [{"week": w, "count": c} for w, c in sorted(weeks.items())],
            "analysed": len(subs)}


# ---------------------------------------------------------------- change impact
def _facts(rec):
    """Map a stable key -> displayed text for everything checkable in one brand or product record."""
    out = {}
    for c in rec.get("approvedClaims", []):
        if c.get("status") != "draft":
            out[f"claim:{c['id']}"] = ("Approved claim", c["text"])
    for r in rec.get("restrictedClaims", []):
        out[f"restricted:{r['id']}"] = ("Restricted claim", r["text"])
    for t in rec.get("terminology", []):
        out[f"term:{t['id']}"] = ("Terminology", f"{t['avoid']} → {t['prefer']}")
    for sp in rec.get("specs", []):
        out[f"spec:{sp['id']}"] = ("Specification", f"{sp['name']}: {sp['value']}")
    for i, n in enumerate(rec.get("previousNames", [])):
        out[f"prev:{n.lower()}"] = ("Previous name", n)
    out["name"] = ("Name", rec.get("name", ""))
    out["logo"] = ("Logo", rec.get("logoAssetId", ""))
    for g in rec.get("guidelines", []):
        out[f"guideline:{g['id']}"] = ("Guideline", g["text"])
    return out


def _diff(old, new):
    a, b = _facts(old), _facts(new)
    changes = []
    for k, (kind, txt) in a.items():
        if k not in b:
            changes.append({"kind": kind, "change": "removed", "before": txt, "after": None})
        elif b[k][1] != txt:
            changes.append({"kind": kind, "change": "changed", "before": txt, "after": b[k][1]})
    for k, (kind, txt) in b.items():
        if k not in a and txt:
            changes.append({"kind": kind, "change": "added", "before": None, "after": txt})
    return changes


def _tokens_of(change):
    """Distinctive old text to look for in saved content: the old value of a spec, the old claim text, the old name."""
    before = change["before"] or ""
    if change["kind"] == "Specification" and ":" in before:
        before = before.split(":", 1)[1]
    if change["kind"] == "Terminology":
        before = before.split("→")[1] if "→" in before else before  # old preferred term is no longer approved
    return before.strip()


def impact(store, brand_id, decisions):
    brand = B.get_brand(store, brand_id)
    subs = [s for s in store.list("submission") if s.get("brandId") == brand_id]
    targets = [("brand", None, brand)] + [("product", p["id"], p) for p in B.list_products(store, brand_id)]
    results = []
    for level, pid, rec in targets:
        vs = sorted(B.versions(store, level, rec["id"]), key=lambda v: v["version"])
        for older, newer in zip(vs, vs[1:]):
            for ch in _diff(older, newer):
                if ch["change"] == "added":
                    continue
                needle = _tokens_of(ch)
                if len(needle) < 3:
                    continue
                pattern = re.compile(rf"(?<![\w]){re.escape(needle)}(?![\w])", re.I)
                for s in subs:
                    if pid and s.get("productId") != pid:
                        continue
                    latest = s["versions"][-1]
                    if s.get("profileVersion") is not None and level == "brand" and s.get("brandVersion", 0) >= newer["version"]:
                        continue
                    m = pattern.search(latest["content"])
                    if not m:
                        continue
                    key = f"{s['id']}|{rec['id']}|{newer['version']}|{ch['kind']}|{needle.lower()}"
                    a, b = max(0, m.start() - 40), min(len(latest["content"]), m.end() + 40)
                    d = decisions.get(key)
                    results.append({"key": key, "submissionId": s["id"], "title": s["title"], "status": s["status"], "author": s["author"],
                                    "level": level, "subject": rec["name"], "version": newer["version"], "kind": ch["kind"], "change": ch["change"],
                                    "before": ch["before"], "after": ch["after"], "snippet": latest["content"][a:b].replace("\n", " "),
                                    "recommendation": ("Recheck this content against the updated fact sheet and replace the outdated wording."
                                                       if s["status"] != "approved" else "Approved content may now be out of date. Decide whether to recheck or withdraw it."),
                                    "decision": d})
    results.sort(key=lambda r: (r["decision"] is not None, r["status"] == "approved", r["submissionId"]))
    return {"affected": results, "open": sum(1 for r in results if not r["decision"])}


def decide_impact(store, user, d):
    key, choice = str(d.get("key") or ""), d.get("decision")
    if not key or choice not in ("recheck", "dismiss", "withdraw"):
        raise ApiError(422, "Choose recheck, dismiss or withdraw")
    rec = {"key": key, "decision": choice, "note": B.s(d.get("note"), 400), "by": user["name"], "at": B.now()}
    store.put("impact_decision", B.nid("imp"), rec)
    return rec


def impact_decisions(store):
    return {r["key"]: r for r in store.list("impact_decision")}


# ---------------------------------------------------------------- guideline conflicts
def _items(rec, level, label):
    out = []
    for c in rec.get("approvedClaims", []):
        if c.get("status") != "draft":
            out.append(("claim", c["id"], c["text"], level, label, c))
    for r in rec.get("restrictedClaims", []):
        if r.get("status") != "draft":
            out.append(("restricted", r["id"], r["text"], level, label, r))
    for t in rec.get("terminology", []):
        if t.get("status") != "draft":
            out.append(("term", t["id"], f"Use “{t['prefer']}” instead of “{t['avoid']}”", level, label, t))
    for g in rec.get("guidelines", []):
        if g.get("status") != "draft":
            out.append(("guideline", g["id"], g["text"], level, label, g))
    for tv in rec.get("toneAvoid", []):
        if tv.get("status") != "draft":
            out.append(("tone", tv["id"], f"Avoid the phrase “{tv['phrase']}”", level, label, tv))
    return out


CASE_WORDS = {"uppercase": "upper", "all caps": "upper", "capital letters": "upper", "lowercase": "lower", "title case": "title", "sentence case": "sentence"}


def _case(text):
    t = text.lower()
    for w, c in CASE_WORDS.items():
        if w in t:
            return c
    return None


def conflicts(store, brand_id, decisions):
    brand = B.get_brand(store, brand_id)
    scopes = [(brand, "brand", brand["name"], None)] + [(p, "product", p["name"], p["id"]) for p in B.list_products(store, brand_id)]
    found = []

    def add(kind, why, a, b, product_id):
        key = f"{kind}|{min(a[1], b[1])}|{max(a[1], b[1])}"
        found.append({"key": key, "type": kind, "brandId": brand_id, "brandName": brand["name"], "productId": product_id,
                      "productName": next((s[2] for s in scopes if s[3] == product_id and product_id), None), "explanation": why,
                      "rules": [{"level": x[3], "where": x[4], "kind": x[0], "text": x[2]} for x in (a, b)], "decision": decisions.get(key)})

    for rec, level, label, pid in scopes:
        pool = _items(rec, level, label)
        if level == "product":
            pool += _items(brand, "brand", brand["name"])
        for i, a in enumerate(pool):
            for b in pool[i + 1:]:
                if a[1] == b[1]:
                    continue
                if {a[0], b[0]} == {"claim", "restricted"}:
                    ta, tb = set(_norm(a[2])), set(_norm(b[2]))
                    if ta and tb and (len(ta & tb) / min(len(ta), len(tb))) >= 0.8:
                        add("claim-vs-restricted", "An approved claim says almost the same thing as a claim that is restricted.", a, b, pid)
                if a[0] == "term" and b[0] == "term":
                    x, y = a[5], b[5]
                    if x["avoid"].lower() == y["avoid"].lower() and x["prefer"].lower() != y["prefer"].lower():
                        add("terminology", f"Both rules replace “{x['avoid']}” but with different wording.", a, b, pid)
                    elif x["prefer"].lower() == y["avoid"].lower() and x["avoid"].lower() == y["prefer"].lower():
                        add("terminology", "These two rules replace each other’s wording, so no wording can satisfy both.", a, b, pid)
                    elif x["prefer"].lower() == y["avoid"].lower():
                        add("terminology", f"One rule requires “{x['prefer']}”, while another says to avoid it.", a, b, pid)
                if {a[0], b[0]} == {"claim", "tone"} or {a[0], b[0]} == {"term", "tone"}:
                    t = a if a[0] == "tone" else b
                    o = b if t is a else a
                    phrase = t[5]["phrase"].lower()
                    target = o[5].get("text") or o[5].get("prefer", "")
                    if phrase and phrase in target.lower():
                        add("tone-vs-approved", f"An approved item uses “{t[5]['phrase']}”, which the tone guidance says to avoid.", a, b, pid)
                ca, cb = _case(a[2]), _case(b[2])
                if a[0] == b[0] == "guideline" and ca and cb and ca != cb:
                    wa, wb = set(_norm(a[2])) - set(CASE_WORDS) - {"must", "always", "be", "written", "in", "use", "the"}, set(_norm(b[2]))
                    if len(wa & wb) >= 1:
                        add("formatting", "Two guidelines ask for different letter-casing of the same text.", a, b, pid)
    seen, unique = set(), []
    for c in found:
        if c["key"] not in seen:
            seen.add(c["key"])
            unique.append(c)
    return {"conflicts": unique, "open": sum(1 for c in unique if not c["decision"])}


def resolve_conflict(store, user, d):
    key, choice = str(d.get("key") or ""), d.get("resolution")
    if not key or choice not in ("keep_first", "keep_second", "both_intended", "needs_rewrite"):
        raise ApiError(422, "Choose how to resolve this conflict")
    rec = {"key": key, "resolution": choice, "note": B.s(d.get("note"), 500), "by": user["name"], "at": B.now()}
    store.put("conflict_decision", B.nid("cf"), rec)
    return rec


def conflict_decisions(store):
    return {r["key"]: r for r in store.list("conflict_decision")}
