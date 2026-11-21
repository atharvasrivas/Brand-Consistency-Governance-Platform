"""Deterministic review engine. Checks a draft against ONE brand (+ optionally ONE product) approved context.

Every finding: key, ruleId, label, category, severity (critical|warning|suggestion), strictness (mandatory|flexible),
kind (replace|advice|conflict), scope (text|image), start/end/quote (+ ranges/occurrences when the same issue repeats),
suggestion, why, source{doc,ref}, confidence, needsHuman. Offsets are UTF-16 code units (what the browser uses).

Nothing here invents facts: a claim or figure that is not in the approved context is reported as unverified and routed
to a person. Punctuation-only preferences are not checked.
"""
from __future__ import annotations

import difflib
import re

FL = re.ASCII
SEV_RANK = {"critical": 3, "warning": 2, "suggestion": 1}


# ---------- UTF-16 handling (offsets match JavaScript string indices) ----------
def to_js(s: str) -> str:
    return "".join(c if ord(c) < 0x10000 else chr(0xD800 + ((ord(c) - 0x10000) >> 10)) + chr(0xDC00 + ((ord(c) - 0x10000) & 0x3FF)) for c in s)


def from_js(s: str) -> str:
    return s.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")


def _walk(v, fn):
    if isinstance(v, str):
        return fn(v)
    if isinstance(v, list):
        return [_walk(x, fn) for x in v]
    if isinstance(v, tuple):
        return tuple(_walk(x, fn) for x in v)
    if isinstance(v, dict):
        return {k: _walk(x, fn) for k, x in v.items()}
    return v


def word_re(term: str, cs: bool = False) -> re.Pattern:
    return re.compile(r"(?<![\w-])" + re.escape(term) + r"(?![\w-])", FL | (0 if cs else re.IGNORECASE))


def phrase_re(text: str) -> re.Pattern:
    parts = [re.escape(p) for p in text.split()]
    return re.compile(r"(?<![\w-])" + r"\s+".join(parts) + r"(?![\w-])", FL | re.IGNORECASE)


def cap(s):
    return s[:1].upper() + s[1:]


def match_case(orig, repl):
    if orig[:1].isupper() and repl[:1].islower():
        return cap(repl)
    return repl


def norm(s):
    return re.sub(r"[\s,]+", "", s.lower())


def sentence_at(content, start, end):
    a = max(content.rfind(".", 0, start), content.rfind("!", 0, start), content.rfind("?", 0, start), content.rfind("\n", 0, start))
    cands = [i for i in (content.find(".", end), content.find("!", end), content.find("?", end), content.find("\n", end)) if i != -1]
    b = min(cands) if cands else len(content)
    return content[a + 1:b]


class Raw(dict):
    pass


def _raw(rule, label, cat, sev, quote, start, end, *, kind="replace", suggestion=None, why="", source=None, conf=0.9,
         human=None, strict=None, extra=None):
    strict = strict or ("mandatory" if sev in ("critical", "warning") else "flexible")
    r = Raw(ruleId=rule, label=label, category=cat, severity=sev, strictness=strict, kind=kind, scope="text", quote=quote,
            start=start, end=end, suggestion=suggestion, why=why, source=source, confidence=conf,
            needsHuman=(conf < 0.7) if human is None else human)
    if extra:
        r.update(extra)
    return r


def src(doc, ref):
    return {"doc": doc, "ref": ref}


# ---------- detectors ----------
def _previous_names(c, ctx):
    out = []
    for old, new, level in ctx["previousNames"]:
        doc = f"{new} fact sheet" if level == "product" else f"{ctx['brandName']} brand profile"
        for m in word_re(old).finditer(c):
            out.append(_raw("NAME-OLD", "Outdated name", "Terminology", "critical", m.group(0), m.start(), m.end(), suggestion=new,
                            why=f"“{old}” is a previous name. The current name is “{new}”.", source=src(doc, "Name history"), conf=0.97))
    return out


def _terms(c, ctx):
    out, by_avoid = [], {}
    for t in ctx["terms"]:
        by_avoid.setdefault(t["avoid"].lower(), []).append(t)
    for avoid, items in by_avoid.items():
        distinct = {i["prefer"] for i in items}
        for m in word_re(avoid).finditer(c):
            if len(distinct) > 1:
                opts = [{"label": f"Follow {i['doc']}: use “{i['prefer']}”", "text": match_case(m.group(0), i["prefer"]),
                         "source": src(i["doc"], i.get("source") or "Terminology")} for i in items]
                out.append(_raw("TERM-CONFLICT", "Conflicting terminology", "Terminology", "warning", m.group(0), m.start(), m.end(), kind="conflict",
                                why=f"Approved sources disagree about “{avoid}”. A person decides, the platform will not guess.",
                                source=opts[0]["source"], conf=0.5, human=True, extra={"options": opts}))
                continue
            t = items[0]
            sev = "warning" if t.get("strict") else "suggestion"
            out.append(_raw("TERM", "Preferred terminology", "Terminology", sev, m.group(0), m.start(), m.end(), suggestion=match_case(m.group(0), t["prefer"]),
                            why=f"Approved wording is “{t['prefer']}” instead of “{t['avoid']}”.", source=src(t["doc"], t.get("source") or "Terminology"), conf=0.95))
    return out


def _tone(c, ctx):
    out = []
    for t in ctx["toneAvoid"]:
        for m in word_re(t["phrase"]).finditer(c):
            doc = f"{ctx['brandName']} brand profile"
            out.append(_raw("TONE", "Off-voice wording", "Language & tone", "suggestion", m.group(0), m.start(), m.end(), kind="replace" if t.get("prefer") else "advice",
                            suggestion=match_case(m.group(0), t["prefer"]) if t.get("prefer") else "Reword this passage to match the brand voice.",
                            why=t.get("reason") or "This wording is listed as off-voice in the brand profile.", source=src(doc, "Tone and voice"), conf=0.8))
    return out


def _restricted(c, ctx):
    out = []
    alts = [x["text"] for x in ctx["claims"][:2]]
    for r in ctx["restricted"]:
        for m in phrase_re(r["text"]).finditer(c):
            sug = "Remove this claim" + (f", or use an approved claim such as “{alts[0]}”." if alts else ".")
            out.append(_raw("CLAIM-RESTRICTED", "Restricted claim", "Facts & claims", "critical", m.group(0), m.start(), m.end(), kind="advice", suggestion=sug,
                            why=r.get("reason") or f"This claim is on the restricted list for {r['doc']}.", source=src(r["doc"], "Restricted claim"), conf=0.95, human=False))
    return out


NUM = r"\d[\d,]*(?:\.\d+)?"


def _specs(c, ctx):
    out = []
    for sp in ctx["specs"]:
        m0 = re.match(rf"\s*({NUM})\s*([A-Za-z%°/]+(?:\s?[A-Za-z]+)?)?", sp["value"])
        if not m0:
            continue
        want, unit = m0.group(1), (m0.group(2) or "").strip()
        for nm in word_re(sp["name"]).finditer(c):
            win_a, win_b = max(0, nm.start() - 60), min(len(c), nm.end() + 60)
            pat = re.compile(rf"(?<![\w.]){NUM}(?:\s*{re.escape(unit)})?(?![\w])", FL | re.IGNORECASE) if unit else re.compile(rf"(?<![\w.]){NUM}(?![\w])")
            cands = [(abs((m.start() + m.end()) // 2 - (nm.start() + nm.end()) // 2), m) for m in pat.finditer(c, win_a, win_b)
                     if unit.lower() in m.group(0).lower()]
            if not cands:
                continue
            m = min(cands, key=lambda x: x[0])[1]
            got = re.match(NUM, m.group(0)).group(0)
            if norm(got) != norm(want):
                fix = sp["value"] if not unit else f"{want} {unit}"
                out.append(_raw("SPEC-MISMATCH", "Contradicts approved specification", "Facts & claims", "critical", m.group(0), m.start(), m.end(), suggestion=fix,
                                why=f"The approved {sp['name']} is “{sp['value']}”, but the draft says “{m.group(0)}”.", source=src(sp["doc"], sp.get("source") or sp["name"]), conf=0.9, human=False))
    return out


def _spec_facets(c, ctx):
    """Facet-level comparison with the approved fact sheet (engine, power, acceleration, production run ...). See specs.py."""
    from . import specs
    who = ctx["productName"] or ctx["brandName"]
    out = []
    for i in specs.find(c, ctx):
        fact = i["fact"]
        source = src(fact["doc"], fact["ref"]) if fact else src(f"{who} approved facts", "No matching approved figure")
        out.append(_raw(i["rule"], i["label"], "Facts & claims", i["sev"], i["quote"], i["start"], i["end"], kind=i["kind"], suggestion=i["suggestion"],
                        why=i["why"], source=source, conf=i["conf"], human=i["human"], extra={"approvedFact": fact} if fact else None))
    return out


CLAIM_PATTERNS = [
    ("Unsupported superlative", r"(?<![\w-])(?:the\s+)?(?:best|fastest|cheapest|safest|leading|unbeatable|unmatched|world-class|most\s+(?:reliable|powerful|secure|popular|advanced|trusted|accurate)|#1|number[- ]one)(?![\w-])(?:[ \t]+(?:[A-Za-z]+[ \t]+){0,2}?(?:in|on|of)[ \t]+the[ \t]+(?:country|world|industry|market|planet))?"),
    ("Unsupported guarantee", r"(?<![\w-])(?:guaranteed?|100\s?%\s+(?:secure|safe|accurate|reliable|effective)|unhackable|risk[- ]free|never\s+fails?|always\s+works?|zero\s+(?:downtime|risk))(?![\w-])"),
    ("Misleading comparison", r"(?<![\w-])(?:(?:better|faster|cheaper|safer|smarter|stronger)\s+than\s+(?:any|all|other|the\s+competition|competitors?|alternatives?)|outperforms?\s+(?:any|all|other|competitors?)|unlike\s+(?:other|our\s+competitors|competitors))(?![\w-])"),
]
STAT = re.compile(rf"(?<![\w.]){NUM}(?:\s?(?:%|percent\b|x\b|×)|\+?\s*(?:customers|clients|users|businesses|teams|brands|downloads|installs|stores|reviews|countries|years|hours|minutes|days)\b)", FL | re.IGNORECASE)


def _approved_text(ctx):
    return [x["text"].lower() for x in ctx["claims"]]


def _unverified(c, ctx):
    out, claims = [], _approved_text(ctx)
    ex = f"for example “{ctx['claims'][0]['text']}”" if ctx["claims"] else None
    who = ctx["productName"] or ctx["brandName"]
    for label, pat in CLAIM_PATTERNS:
        for m in re.finditer(pat, c, FL | re.IGNORECASE):
            low, sent = m.group(0).lower(), sentence_at(c, m.start(), m.end()).lower()
            if any(low in a or a in sent for a in claims):
                continue
            sug = (f"This is not in the approved data for {who}. Remove it or use an approved claim, {ex}." if ex
                   else f"{who} has no approved claims that support this. Remove it, or ask the Owner to add it with a source.")
            out.append(_raw("CLAIM-UNVERIFIED", label, "Facts & claims", "warning", m.group(0), m.start(), m.end(), kind="advice", suggestion=sug,
                            why=f"{label}: nothing in the approved claims for {who} backs this up, so it is unverified.",
                            source=src(f"{who} approved claims", "No matching approved claim"), conf=0.8, human=True))
    known = " ".join(ctx["descriptions"] + [x["text"] for x in ctx["claims"]] + [x["value"] for x in ctx["specs"]])
    known_nums = {norm(n) for n in re.findall(NUM, known)}
    for m in STAT.finditer(c):
        n = norm(re.match(NUM, m.group(0)).group(0))
        if n in known_nums or any(m.group(0).lower() in a for a in claims):
            continue
        out.append(_raw("STAT-UNVERIFIED", "Unverified figure", "Facts & claims", "warning", m.group(0), m.start(), m.end(), kind="advice",
                        suggestion="This figure is not in the approved data. Verify it with the Owner, or remove it.",
                        why=f"“{m.group(0)}” does not appear in the approved facts for {who}.", source=src(f"{who} approved facts", "No matching approved figure"), conf=0.75, human=True))
    return out


def _names(c, ctx):
    out, known = [], " ".join(ctx["descriptions"] + [x["text"] for x in ctx["claims"]] + [x["value"] for x in ctx["specs"]]).lower()
    names = [(ctx["brandName"], f"{ctx['brandName']} brand profile")] + ([(ctx["productName"], f"{ctx['productName']} fact sheet")] if ctx["productName"] else [])
    olds = {o.lower() for o, _, _ in ctx["previousNames"]}
    for name, doc in names:
        if len(name) < 3:
            continue
        for m in word_re(name).finditer(c):
            if m.group(0) != name and any(ch.isupper() for ch in name):
                out.append(_raw("NAME-CASE", "Name written differently", "Terminology", "suggestion", m.group(0), m.start(), m.end(), suggestion=name,
                                why=f"The official name is written “{name}”.", source=src(doc, "Official name"), conf=0.9, human=False, strict="flexible"))
        if " " in name or len(name) < 5:
            continue
        for m in re.finditer(r"(?<![\w-])[A-Z][A-Za-z-]{3,}(?![\w-])", c):
            t = m.group(0)
            if t.lower() == name.lower() or t.lower() in olds or t.lower() in known:
                continue
            if difflib.SequenceMatcher(None, t.lower(), name.lower()).ratio() >= 0.82:
                out.append(_raw("NAME-TYPO", "Possible misspelt name", "Terminology", "suggestion", t, m.start(), m.end(), kind="advice",
                                suggestion=f"Did you mean “{name}”?", why=f"“{t}” is very close to the official name “{name}”.", source=src(doc, "Official name"), conf=0.6, human=True, strict="flexible"))
    return out


DETECTORS = (_previous_names, _terms, _restricted, _specs, _spec_facets, _tone, _unverified, _names)


def _finish(raws, content):
    raws.sort(key=lambda r: (r["start"], -SEV_RANK[r["severity"]]))
    kept = []
    for r in raws:
        if kept and r["start"] < kept[-1]["end"]:
            if SEV_RANK[r["severity"]] > SEV_RANK[kept[-1]["severity"]]:
                kept[-1] = r
            continue
        kept.append(r)
    groups, order = {}, []
    for r in kept:
        k = (r["ruleId"], r["quote"].lower(), r.get("suggestion"))
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(r)
    out = []
    for k in order:
        g = groups[k]
        f = dict(g[0])
        f["key"] = f"{f['ruleId']}|{f['quote'].lower()}" if len(g) > 1 or f["ruleId"] in ("TERM", "NAME-OLD") else f"{f['ruleId']}|{f['quote'].lower()}|{content[max(0, f['start'] - 20):f['end'] + 20].lower()}"
        f["id"] = f"{f['ruleId']}:{f['start']}"
        f["occurrences"] = len(g)
        if len(g) > 1:
            f["ranges"] = [{"start": x["start"], "end": x["end"]} for x in g]
        out.append(f)
    out.sort(key=lambda f: (-SEV_RANK[f["severity"]], f["start"]))
    return out


def image_findings(img, ctx):
    if not img:
        return []
    out, who = [], ctx["brandName"]

    def mk(rule, label, cat, sev, key, quote, sug, why, source, conf, strict=None, **extra):
        f = {"id": f"{rule}:{key}", "key": f"{rule}|{key}", "ruleId": rule, "label": label, "category": cat, "severity": sev,
             "strictness": strict or ("mandatory" if sev != "suggestion" else "flexible"), "kind": "advice", "scope": "image", "quote": quote,
             "suggestion": sug, "why": why, "source": source, "confidence": conf, "needsHuman": True, "occurrences": 1}
        f.update(extra)
        return f

    name = (img.get("name") or "").lower()
    if any(a.lower() in name for a in ctx["deprecatedAssets"]):
        out.append(mk("IMG-LOGO", "Possible retired logo", "Visual identity", "critical", img["name"], img["name"],
                      "Use the current approved logo. A person should confirm before publication.",
                      "The file name matches a retired asset. Only the file name is checked, the image itself is not analysed.", src(f"{who} brand assets", "Retired assets"), 0.7))
    if not (img.get("alt") or "").strip():
        out.append(mk("IMG-ALT", "Missing alt text", "Access & channel fit", "warning", "alt", "(image has no alt text)", "Describe what the image shows in one short sentence.",
                      "Images need alt text so screen-reader users get the same message.", src("Accessibility", "Alt text"), 0.95, fix={"type": "alt"}, needsHuman=False))
    fonts = [f.lower() for f in ctx["fonts"]]
    if fonts:
        for font in [s.strip() for s in (img.get("fonts") or "").split(",") if s.strip()]:
            if font.lower() not in fonts:
                out.append(mk("IMG-FONT", "Unapproved font", "Visual identity", "warning", font, font, f"Use an approved font: {', '.join(ctx['fonts'])}.",
                              f"“{font}” is not in the approved typography for {who}.", src(f"{who} brand profile", "Typography"), 0.9, needsHuman=False))
    a = img.get("analysis") or {}
    for c in a.get("offPalette") or []:
        out.append(mk("IMG-PALETTE", "Off-palette colour", "Visual identity", "suggestion", c["hex"], c["hex"],
                      f"Dominant colour {c['hex']} (about {int(c['share'] * 100 + 0.5)}% of the image) is far from the palette. Nearest: {c['nearest']['name']} {c['nearest']['hex']}.",
                      "Colour analysis is an estimate, so a person decides.", src(f"{who} brand profile", "Colours"), 0.58, swatch=c["hex"]))
    lc = a.get("lowContrast")
    if lc:
        r = f"{float(lc['ratio']):.1f}"
        out.append(mk("IMG-CONTRAST", "Possible low contrast", "Access & channel fit", "suggestion", "contrast", f"{r}:1",
                      f"The two main colours have a contrast ratio of {r}:1. Aim for at least 3:1 for large text and 4.5:1 for body text.",
                      "This is an estimate from dominant colours.", src("Accessibility", "Contrast"), 0.55))
    return out


def _review(content, meta, image, ctx):
    findings = []
    if ctx["hasApproved"]:
        raws = [r for d in DETECTORS for r in d(content, ctx)]
        findings = _finish(raws, content)
    img = image_findings(image, ctx)
    if image and (image.get("textInImage") or "").strip() and ctx["hasApproved"]:
        for f in _finish([r for d in DETECTORS for r in d(image["textInImage"], ctx)], image["textInImage"]):
            g = {k: v for k, v in f.items() if k not in ("start", "end", "ranges")}
            g.update(scope="image", kind="advice" if f["kind"] == "replace" else f["kind"], id=f"img-{f['id']}", key=f"img-{f['key']}",
                     label=f"{f['label']} (in image)", needsHuman=True,
                     suggestion=f"In the image text, change “{f['quote']}” to “{f['suggestion']}”." if f["kind"] == "replace" else f.get("suggestion"))
            img.append(g)
    return findings + img


BRIEF = ("key", "ruleId", "label", "category", "severity", "strictness", "kind", "scope", "quote", "suggestion", "why", "source", "needsHuman", "approvedFact", "options")


def brief(f):
    return {k: f[k] for k in BRIEF if k in f}


def _rewrite(content, meta, ctx, dismissed):
    findings = [f for f in _review(content, meta, None, ctx) if f["key"] not in dismissed]
    spans = []
    applied, left = [], []
    for f in findings:
        if f["scope"] != "text":
            continue
        if f["kind"] == "replace" and f.get("suggestion"):
            for r in f.get("ranges") or [{"start": f["start"], "end": f["end"]}]:
                spans.append((r["start"], r["end"], f["suggestion"]))
            applied.append({k: f[k] for k in ("key", "ruleId", "label", "quote", "suggestion", "strictness", "severity", "occurrences")} | {"why": f.get("why"), "source": f.get("source")})
        else:
            left.append({k: f.get(k) for k in ("key", "ruleId", "label", "quote", "kind", "severity", "suggestion", "options", "start", "end")})
    text = content
    for a, b, rep in sorted(spans, reverse=True):
        text = text[:a] + rep + text[b:]
    # Never assume the rewrite fixed everything: check the result again, with the same rules, and report what is left.
    return {"text": text, "applied": applied, "skipped": [x for x in left if x["kind"] == "conflict"],
            "needsPerson": [x for x in left if x["kind"] != "conflict"], **_recheck(text, meta, ctx, dismissed)}


def _recheck(text, meta, ctx, dismissed):
    remaining = [brief(f) for f in _review(text, meta, None, ctx) if f["key"] not in dismissed and f["scope"] == "text"]
    mandatory_left = [f for f in remaining if f["strictness"] == "mandatory"]
    return {"remaining": remaining, "compliant": not mandatory_left,
            "recheck": {"total": len(remaining), "mandatory": len(mandatory_left), "needsPerson": sum(1 for f in remaining if f.get("needsHuman"))}}


def review(content, meta, image, ctx):
    return _walk(_review(to_js(content or ""), meta, _walk(image, to_js), _walk(ctx, to_js)), from_js)


def rewrite(content, meta, ctx, dismissed=None):
    return _walk(_rewrite(to_js(content or ""), meta, _walk(ctx, to_js), {to_js(k) for k in (dismissed or set())}), from_js)


def recheck(content, meta, ctx, dismissed=None):
    """Run the rules over `content` again and report what is still unresolved (used on rewritten text)."""
    return _walk(_recheck(to_js(content or ""), meta, _walk(ctx, to_js), {to_js(k) for k in (dismissed or set())}), from_js)
