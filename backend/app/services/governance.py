"""Brand Drift Radar, Brand Change Impact Scanner and Guideline Conflict Detector.

All three read stored data only. They flag and explain; a person decides. Nothing here edits a profile or a submission.
"""
import re
from collections import defaultdict
from datetime import datetime

from ..auth import ApiError
from . import brands as B
from . import versions as V

RANK = {"critical": 3, "warning": 2, "suggestion": 1}


def _norm(t):
    return re.sub(r"[^a-z0-9 ]+", " ", str(t or "").lower()).split()


def _week(iso):
    d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


# ---------------------------------------------------------------- drift
def _domain(f):
    rid = str(f.get("ruleId") or "")
    return "visual" if rid.startswith("IMG") or f.get("category") == "Visual identity" else "text"


def live(subs):
    """Submissions that count towards analytics: drafts are private work in progress and are excluded everywhere."""
    return [s for s in subs if s.get("status") != "draft"]


def drift(subs, brand_id=None, product_id=None):
    """Recurring textual and visual patterns: the same finding in two or more submissions of the same brand/product.
    Every number is a count of stored submissions or findings; nothing is estimated."""
    subs = live(subs)
    if brand_id:
        subs = [s for s in subs if s.get("brandId") == brand_id]
    if product_id:
        subs = [s for s in subs if s.get("productId") == product_id]
    groups = {}
    for s in subs:
        wk = _week(s["createdAt"])
        for f in s.get("findings", []):
            if f.get("category") == "Content patterns" or f.get("status") == "dismissed":
                continue
            k = (s.get("brandId"), s.get("productId"), f.get("ruleId") or f.get("label"), f.get("label"))
            g = groups.setdefault(k, {"count": 0, "subs": {}, "authors": set(), "weeks": defaultdict(int), "examples": [], "severity": "suggestion", "fixes": defaultdict(int),
                                      "types": defaultdict(int), "resolved": 0, "mandatory": False})
            n = f.get("occurrences") or 1
            g["count"] += n
            g["subs"][s["id"]] = s["title"]
            g["authors"].add(s["author"])
            g["weeks"][wk] += n
            g["types"][s.get("type") or "other"] += 1
            if f.get("quote") and f["quote"] not in [e["text"] for e in g["examples"]] and len(g["examples"]) < 3:
                g["examples"].append({"text": f["quote"], "submissionId": s["id"], "title": s["title"]})
            if f.get("suggestion"):
                g["fixes"][f["suggestion"]] += 1
            g["resolved"] += f.get("status") == "accepted"
            g["mandatory"] = g["mandatory"] or f.get("strictness") == "mandatory"
            g.update(category=f.get("category"), rule=(f.get("source") or {}).get("ref") or f.get("label"), domain=_domain(f), why=f.get("why"),
                     brandName=s.get("brandName"), productName=s.get("productName"))
            if RANK.get(f.get("severity"), 0) > RANK[g["severity"]]:
                g["severity"] = f["severity"]
    total, items = len(subs), []
    for (bid, pid, _rid, label), g in groups.items():
        if len(g["subs"]) < 2:
            continue
        best = max(g["fixes"].items(), key=lambda kv: kv[1])[0] if g["fixes"] else None
        visual = g["domain"] == "visual"
        items.append({"brandId": bid, "brandName": g["brandName"], "productId": pid, "productName": g["productName"], "label": label, "domain": g["domain"],
                      "category": g["category"], "guideline": g["rule"], "severity": g["severity"], "mandatory": g["mandatory"], "occurrences": g["count"],
                      "submissions": len(g["subs"]), "submissionIds": sorted(g["subs"]), "share": round(len(g["subs"]) / total, 2) if total else None,
                      "creators": len(g["authors"]), "example": g["examples"][0]["text"] if g["examples"] else None, "examples": g["examples"],
                      "contentTypes": [{"type": t, "submissions": n} for t, n in sorted(g["types"].items(), key=lambda kv: -kv[1])],
                      "trend": [{"week": w, "count": c} for w, c in sorted(g["weeks"].items())], "correctionsAccepted": g["resolved"],
                      "pattern": "multiple creators" if len(g["authors"]) > 1 else "same creator repeating",
                      "recommendation": {
                          "explanation": g["why"] or f"{label} keeps appearing in {len(g['subs'])} of {total} submissions.",
                          "correction": best,
                          "preferredLanguage": None if visual else best,
                          "visualDirection": best if visual else None,
                          "guidance": (f"Before writing, check the brand's {'visual identity' if visual else 'approved wording'} for “{g['rule']}”. "
                                       f"Share this with the {len(g['authors'])} creator{'s' if len(g['authors']) != 1 else ''} involved.")}})
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
    hit = {sid for i in items for sid in i["submissionIds"]}
    return {"recurring": items, "text": [i for i in items if i["domain"] == "text"], "visual": [i for i in items if i["domain"] == "visual"],
            "hotspots": hot[:8], "alerts": alerts, "trend": [{"week": w, "count": c} for w, c in sorted(weeks.items())], "analysed": total,
            "submissionsWithPatterns": len(hit),
            "consistency": round(1 - len(hit) / total, 2) if total else None,
            "definition": "A pattern is the same finding in two or more submissions. Drafts and structural 'content pattern' hints are excluded."}


# ---------------------------------------------------------------- change impact
VISUAL_FIELDS = {"logoAssetId", "imageAssetId", "assets", "colours", "fonts", "deprecatedAssets"}
IMPACT_CHOICES = ("recheck", "dismiss", "withdraw", "resolved", "reopen")


def _after_colon(t):
    return t.split(":", 1)[1].strip() if ":" in (t or "") else (t or "")


def _needles(c):
    """(text to look for in saved content, why it matters) for one field change. Empty when there is nothing text-checkable."""
    f, ch, b, a = c["field"], c["change"], c.get("before") or "", c.get("after") or ""
    out = []
    if f == "approvedClaims" and ch in ("removed", "modified"):
        out.append((b, "This claim is no longer approved in its old wording."))
    elif f == "restrictedClaims" and ch in ("added", "modified"):
        out.append((a, "This wording is now a restricted claim."))
    elif f == "terminology":
        if ch == "added" and "→" in a:
            out.append((a.split("→")[0].strip(), "This wording is now on the avoid list."))
        if ch == "modified":
            if "→" in b:
                out.append((b.split("→")[1].strip(), "This term is no longer the preferred wording."))
            if "→" in a:
                out.append((a.split("→")[0].strip(), "This wording is now on the avoid list."))
    elif f == "specs" and ch in ("removed", "modified"):
        out.append((_after_colon(b), "This specification value is no longer approved."))
    elif f == "name" and ch == "modified":
        out.append((b, "The brand or product name changed."))
    elif f == "toneAvoid" and ch in ("added", "modified"):
        out.append((a, "This phrase is now off-voice."))
    return [(n.strip(), why) for n, why in out if len(n.strip()) >= 2]


def _stamped(sub, level, pid):
    v = sub.get("brandVersion") if level == "brand" else sub.get("productVersion")
    return v or 0


def impact(store, brand_id, decisions):
    """One brand, or every brand when none is chosen."""
    if brand_id:
        return _impact_one(store, brand_id, decisions)
    outs = []
    for b in B.list_brands(store):
        try:
            outs.append(_impact_one(store, b["id"], decisions))
        except ApiError:
            continue
    aff = sorted((r for o in outs for r in o["affected"]), key=lambda r: (not (not r["decision"] or r["decision"]["decision"] == "reopen"), r["status"] == "approved", r["submissionId"]))
    sc = {k: sum(o["scanned"][k] for o in outs) for k in ("submissions", "versionChanges", "clearedByRecheck")}
    return {"affected": aff, "open": sum(o["open"] for o in outs), "scanned": sc, "warnings": sorted({w for o in outs for w in o["warnings"]})[:10]}


def _impact_one(store, brand_id, decisions):
    """Compares every consecutive pair of saved versions of the brand and each product, and lists the saved submissions whose
    current text still uses wording that a later version changed. A submission re-checked against the newer version is not listed.
    One bad record is reported in `warnings`; it never stops the scan."""
    if not brand_id:
        raise ApiError(422, "Choose a brand to scan")
    brand = B.get_brand(store, brand_id)
    subs, warnings = [s for s in store.list("submission") if s.get("brandId") == brand_id and s.get("versions")], []
    targets = [("brand", None, brand)] + [("product", p["id"], p) for p in B.list_products(store, brand_id)]
    results, changes_seen, cleared = [], 0, 0
    for level, pid, rec in targets:
        try:
            vs = sorted(B.versions(store, level, rec["id"]), key=lambda v: v["version"])
        except Exception as e:  # noqa: BLE001
            warnings.append(f"{rec.get('name', rec.get('id'))}: version history could not be read ({e})")
            continue
        for older, newer in zip(vs, vs[1:]):
            for c in V.diff(older, newer):
                changes_seen += 1
                visual = c["field"] in VISUAL_FIELDS
                needles = [] if visual else _needles(c)
                if not visual and not needles:
                    continue
                for s in subs:
                    try:
                        if pid and s.get("productId") != pid:
                            continue
                        if _stamped(s, level, pid) >= newer["version"]:
                            cleared += 1
                            continue
                        latest = s["versions"][-1]
                        content = latest.get("content") or ""
                        if visual:
                            if not (s.get("image") or s.get("imageAssetId")):
                                continue
                            hit, why, snippet = True, "The approved visual identity changed (logo, colours, fonts or assets). Images in this submission were checked against the older version.", (s.get("image") or {}).get("name") or "attached image"
                            needle = c["field"]
                        else:
                            hit = None
                            for needle, why in needles:
                                m = re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", content, re.I)
                                if m:
                                    hit = m
                                    break
                            if not hit:
                                continue
                            a_, b_ = max(0, hit.start() - 40), min(len(content), hit.end() + 40)
                            snippet = content[a_:b_].replace("\n", " ")
                        key = f"{s['id']}|{rec['id']}|{newer['version']}|{c['field']}|{c.get('itemId') or ''}|{needle.lower()}"
                        d = decisions.get(key)
                        results.append({"key": key, "submissionId": s["id"], "title": s["title"], "status": s["status"], "author": s["author"],
                                        "level": level, "subject": rec["name"], "version": newer["version"], "kind": c["label"], "change": c["change"],
                                        "before": c.get("before"), "after": c.get("after"), "reason": why, "snippet": snippet,
                                        "checkedAgainst": _stamped(s, level, pid), "changedBy": newer.get("updatedBy"), "changedAt": newer.get("updatedAt"),
                                        "recommendation": ("Re-check this content against the updated profile and replace the outdated wording."
                                                           if s["status"] != "approved" else "Approved content may now be out of date. Decide whether to re-check or withdraw it."),
                                        "decision": d})
                    except Exception as e:  # noqa: BLE001
                        warnings.append(f"{s.get('id', '?')}: skipped ({type(e).__name__})")
    seen, uniq = set(), []
    for r in results:
        if r["key"] not in seen:
            seen.add(r["key"])
            uniq.append(r)
    isopen = lambda r: not r["decision"] or r["decision"]["decision"] == "reopen"  # noqa: E731
    uniq.sort(key=lambda r: (not isopen(r), r["status"] == "approved", r["submissionId"]))
    return {"affected": uniq, "open": sum(1 for r in uniq if isopen(r)), "scanned": {"submissions": len(subs), "versionChanges": changes_seen, "clearedByRecheck": cleared},
            "warnings": sorted(set(warnings))[:10]}


def decide_impact(store, user, d):
    key, choice = str(d.get("key") or ""), d.get("decision")
    if not key or choice not in IMPACT_CHOICES:
        raise ApiError(422, "Choose recheck, dismiss, withdraw, resolved or reopen")
    rec = {"key": key, "decision": choice, "note": B.s(d.get("note"), 400), "by": user["name"], "byId": user["id"], "at": B.now()}
    store.put("impact_decision", B.nid("imp"), rec)
    return rec


def impact_history(store, key=None):
    rows = sorted(store.list("impact_decision"), key=lambda r: r.get("at") or "")
    return [r for r in rows if not key or r["key"] == key]


def impact_decisions(store):
    return {r["key"]: r for r in impact_history(store)}  # latest decision per alert wins


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
    if not brand_id:
        outs = [conflicts(store, b["id"], decisions) for b in B.list_brands(store)]
        lst = [c for o in outs for c in o["conflicts"]]
        return {"conflicts": lst, "open": sum(o["open"] for o in outs)}
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
