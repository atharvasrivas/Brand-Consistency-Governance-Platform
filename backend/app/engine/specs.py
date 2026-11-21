"""Technical-specification contradiction detection.

The generic spec check in review.py only fires when the spec NAME appears next to a number with the same unit. Real marketing
copy rarely does that ("700 horsepower", "twin-turbocharged V8", "unlimited production"). This module compares the draft with the
approved facts by *facet* instead:

  engine layout (V12, flat-6 ...), aspiration (naturally aspirated / turbocharged / supercharged), electrification (hybrid / electric),
  engine displacement, power output (cv / hp / kW, converted before comparing), acceleration (0-100 ...), top speed,
  production run (limited / unlimited / unit count), and any other technical figure the approved data does not contain.

Rules that keep it honest:
  * a facet is only compared when the approved facts actually state that facet; silence in the fact sheet is never a contradiction
  * every issue carries the approved fact it was compared with, so the UI can show exactly what the draft contradicts
  * figures that cannot be compared (not in the approved data at all) are "unsupported technical claims" and are routed to a person
  * all regexes work on text with the same length as the original, so offsets stay valid
"""
from __future__ import annotations

import re

NUM = r"\d[\d,]*(?:\.\d+)?"
_DASH = str.maketrans({"–": "-", "—": "-", "‑": "-", "−": "-"})  # 1:1 characters, so offsets do not move


def _f(s) -> float:
    return float(str(s).replace(",", ""))


def _norm_num(s) -> str:
    return re.sub(r"[\s,]+", "", str(s).lower())


def _fix(num_text: str, approved_num: str) -> str:
    """Swap the number inside the draft's own wording for the approved one: '3.5-second' -> '2.85-second'."""
    return re.sub(NUM, approved_num, num_text, count=1)


def _cap_like(orig: str, text: str) -> str:
    return text[:1].upper() + text[1:] if orig[:1].isupper() else text[:1].lower() + text[1:]


# ------------------------------------------------------------------ approved facts
def facts(ctx) -> list[dict]:
    out = []
    for sp in ctx.get("specs", []):
        out.append({"name": sp["name"], "value": sp["value"], "text": f"{sp['name']} {sp['value']}".translate(_DASH), "doc": sp["doc"],
                    "ref": sp.get("source") or sp["name"], "kind": "spec"})
    for c in ctx.get("claims", []):
        out.append({"name": "Approved claim", "value": c["text"], "text": c["text"].translate(_DASH), "doc": c["doc"],
                    "ref": c.get("source") or "Approved claim", "kind": "claim"})
    return out


def _fact(f):
    return {"name": f["name"], "value": f["value"], "doc": f["doc"], "ref": f["ref"]}


def _issue(rule, label, quote, start, end, *, kind, suggestion, why, fact, conf=0.92, sev="critical", human=False):
    return {"rule": rule, "label": label, "sev": sev, "quote": quote, "start": start, "end": end, "kind": kind, "suggestion": suggestion,
            "why": why, "fact": fact, "conf": conf, "human": human}


def _say(f):
    return f"The approved {f['name']} is “{f['value']}”" if f["kind"] == "spec" else f"The approved claim says “{f['value']}”"


# ------------------------------------------------------------------ facets: engine layout, aspiration, electrification, displacement
LAYOUT = re.compile(r"(?<![\w-])(?:[VW]\s?-?(?:1[0-6]|[2-9])|(?i:flat|inline|straight)[- ](?:[2-9]|1[0-2]))(?![\w-])")
NATURAL = re.compile(r"(?<![\w-])(?i:(?:naturally|normally)[- ]aspirated|atmospheric(?:\s+engine)?)(?![\w-])")
FORCED = re.compile(r"(?<![\w-])(?i:(?:(?:twin|bi|quad|tri|single)[- ]?)?(?:turbo(?:charged|chargers?)?|supercharged|superchargers?|forced[- ]induction))(?![\w-])")
HYBRID = re.compile(r"(?<![\w-])(?i:plug-in\s+hybrid|mild[- ]hybrid|hybrid|PHEV)(?![\w-])")
ELECTRIC = re.compile(r"(?<![\w-])(?i:all[- ]electric|fully[- ]electric|battery[- ]electric|electric\s+(?:motor|powertrain|drivetrain|vehicle|car))(?![\w-])|(?<![\w-])EV(?![\w-])")
COMBUSTION = re.compile(r"(?<![\w-])(?i:petrol|gasoline|diesel|combustion|ICE)(?![\w-])")
DISPLACEMENT = re.compile(rf"(?<![\w.])({NUM})[\s-]*(?i:litres?|liters?)(?![\w])|(?<![\w.])({NUM})\s?L(?![\w])")
ENGINEISH = re.compile(r"(?i)engine|powertrain|power\s?train|motor|drivetrain|power\s?unit|displacement|cylinder|aspirat|turbo|supercharg")


def _layout_key(t: str) -> str:
    k = re.sub(r"[\s-]", "", t).upper()
    return k.replace("STRAIGHT", "INLINE")


def _approved_matches(fs, rx):
    return [(m, f) for f in fs for m in rx.finditer(f["text"])]


def _facets(c, fs):
    out, checked = [], []

    # engine layout
    approved = _approved_matches(fs, LAYOUT)
    if approved:
        keys = {_layout_key(m.group(0)) for m, _ in approved}
        pm, pf = approved[0]
        for m in LAYOUT.finditer(c):
            if _layout_key(m.group(0)) in keys:
                checked.append((m.start(), m.end()))
                continue
            out.append(_issue("SPEC-CONTRADICTION", "Contradicts approved engine layout", m.group(0), m.start(), m.end(), kind="replace",
                              suggestion=pm.group(0), why=f"{_say(pf)}, but the draft says “{m.group(0)}”.", fact=_fact(pf)))

    # aspiration
    nat, forced = _approved_matches(fs, NATURAL), _approved_matches(fs, FORCED)
    if nat or forced:
        allow_nat, allow_forced = bool(nat), bool(forced)
        pm, pf = (nat or forced)[0]
        for rx, ok in ((NATURAL, allow_nat), (FORCED, allow_forced)):
            for m in rx.finditer(c):
                if ok:
                    checked.append((m.start(), m.end()))
                    continue
                out.append(_issue("SPEC-CONTRADICTION", "Contradicts approved engine aspiration", m.group(0), m.start(), m.end(), kind="replace",
                                  suggestion=_cap_like(m.group(0), pm.group(0)), why=f"{_say(pf)}, but the draft says “{m.group(0)}”.", fact=_fact(pf)))

    # electrification: only contradicted when the approved facts clearly describe a combustion-only powertrain
    approved_text = " ".join(f["text"] for f in fs)
    has_hybrid, has_electric = bool(HYBRID.search(approved_text)), bool(ELECTRIC.search(approved_text))
    engine_facts = [f for f in fs if f["kind"] == "spec" and ENGINEISH.search(f["name"] + " " + f["value"])]
    combustion = bool(approved) or bool(nat or forced) or bool(COMBUSTION.search(approved_text))
    if engine_facts and combustion:
        ef = next((f for f in engine_facts if LAYOUT.search(f["text"]) or NATURAL.search(f["text"]) or FORCED.search(f["text"])), engine_facts[0])
        desc = re.sub(r"(?i)\s+engine$", "", ef["value"].strip())
        for rx, ok, word in ((HYBRID, has_hybrid, "hybrid"), (ELECTRIC, has_electric, "electric")):
            if ok:
                continue
            for m in rx.finditer(c):
                start, end, quote, sug = m.start(), m.end(), m.group(0), _cap_like(m.group(0), desc)
                noun = re.match(r"\s+(powertrain|power\s?train|drivetrain|power\s?unit|engine)(?![\w-])", c[end:], re.I)
                # when the approved engine is already stated next to it ("hybrid powertrain with a V8 ..."), dropping the word reads better
                # than repeating the whole engine description
                if noun and any(abs(i["start"] - start) < 150 for i in out if i["label"].startswith(("Contradicts approved engine", "Contradicts approved engine aspiration"))):
                    end, quote, sug = end + noun.end(), c[start:end + noun.end()], noun.group(1)
                out.append(_issue("SPEC-CONTRADICTION", f"Contradicts approved powertrain ({word} not approved)", quote, start, end, kind="replace",
                                  suggestion=sug, why=f"{_say(ef)}. Nothing in the approved facts says the powertrain is {word}, but the draft says “{quote}”.", fact=_fact(ef)))

    # displacement: only when an approved ENGINE spec states it (a kettle's litre capacity is not an engine size)
    disp = []
    for f in engine_facts:
        for m in DISPLACEMENT.finditer(f["text"]):
            disp.append((m.group(1) or m.group(2), m, f))
    if disp:
        wanted = {_norm_num(n) for n, _, _ in disp}
        _, pm, pf = disp[0]
        for m in DISPLACEMENT.finditer(c):
            n = m.group(1) or m.group(2)
            if _norm_num(n) in wanted:
                checked.append((m.start(), m.end()))
                continue
            out.append(_issue("SPEC-MISMATCH", "Contradicts approved engine size", m.group(0), m.start(), m.end(), kind="replace",
                              suggestion=_fix(m.group(0), disp[0][0]), why=f"{_say(pf)}, but the draft says “{m.group(0)}”.", fact=_fact(pf)))
    return out, checked


# ------------------------------------------------------------------ power
POWER = re.compile(rf"(?<![\w.])({NUM})\s*(cv|hp|bhp|ps|pk|kw|horse[\s-]?power)(?![\w])", re.I)
TO_CV = {"cv": 1.0, "ps": 1.0, "pk": 1.0, "hp": 1.01387, "bhp": 1.01387, "horsepower": 1.01387, "kw": 1.35962}


def _cv(num, unit):
    return _f(num) * TO_CV[re.sub(r"[\s-]", "", unit.lower())]


def _power(c, fs):
    out, checked = [], []
    approved = [(m, f) for f in fs for m in POWER.finditer(f["text"])]
    if not approved:
        return out, checked
    values = [(_cv(m.group(1), m.group(2)), m, f) for m, f in approved]
    for m in POWER.finditer(c):
        v = _cv(m.group(1), m.group(2))
        if any(abs(v - a) <= 0.025 * a for a, _, _ in values):
            checked.append((m.start(), m.end()))
            continue
        same = [(a, am, f) for a, am, f in values if re.sub(r"[\s-]", "", am.group(2).lower()) == re.sub(r"[\s-]", "", m.group(2).lower())]
        _, am, f = (same or values)[0]
        out.append(_issue("SPEC-MISMATCH", "Contradicts approved power output", m.group(0), m.start(), m.end(), kind="replace", suggestion=am.group(0),
                          why=f"{_say(f)}, but the draft says “{m.group(0)}”.", fact=_fact(f)))
    return out, checked


# ------------------------------------------------------------------ acceleration
TIME = re.compile(rf"(?<![\w.])({NUM})[\s-]*(?:seconds?|secs?|s)(?![\w/])", re.I)
REF = re.compile(r"(?<![\w.])0\s?(?:-|to)\s?(\d{2,3})(?:\s?(?:km/h|kph|mph))?", re.I)


def _ref_near(text, pos, span=70):
    best = None
    for r in REF.finditer(text, max(0, pos - span), min(len(text), pos + span)):
        d = abs((r.start() + r.end()) // 2 - pos)
        if best is None or d < best[0]:
            best = (d, f"0-{r.group(1)}")
    return best[1] if best else None


def _acceleration(c, fs):
    out, checked, approved = [], [], {}
    for f in fs:
        for m in TIME.finditer(f["text"]):
            ref = _ref_near(f["text"], (m.start() + m.end()) // 2)
            if ref:
                approved.setdefault(ref, []).append((_f(m.group(1)), m, f))
    if not approved:
        return out, checked
    for m in TIME.finditer(c):
        ref = _ref_near(c, (m.start() + m.end()) // 2)
        if ref not in approved:
            continue
        v = _f(m.group(1))
        if any(abs(v - a) <= 0.06 for a, _, _ in approved[ref]):
            checked.append((m.start(), m.end()))
            continue
        a, am, f = approved[ref][0]
        out.append(_issue("SPEC-MISMATCH", f"Contradicts approved {ref.replace('-', '–')} acceleration", m.group(0), m.start(), m.end(), kind="replace",
                          suggestion=_fix(m.group(0), am.group(1)), why=f"{_say(f)}, but the draft says “{m.group(0)}” for the same {ref.replace('-', '–')} sprint.", fact=_fact(f)))
    return out, checked


# ------------------------------------------------------------------ top speed
SPEED = re.compile(rf"(?<![\w.])({NUM})\s*(km/h|kph|kmh|mph)(?![\w])", re.I)
TOPCTX = re.compile(r"(?i)top\s+speed|max(?:imum)?\.?\s+speed|v-?max|tops\s+out")


def _kmh(num, unit):
    return _f(num) * (1.609344 if unit.lower() == "mph" else 1.0)


def _top_speed(c, fs):
    out, checked = [], []
    approved = []
    for f in fs:
        for m in SPEED.finditer(f["text"]):
            if TOPCTX.search(f["text"][max(0, m.start() - 40):m.end() + 10]) or TOPCTX.search(f["name"]):
                approved.append((_kmh(m.group(1), m.group(2)), m, f))
    if not approved:
        return out, checked
    for m in SPEED.finditer(c):
        if not TOPCTX.search(c[max(0, m.start() - 40):m.end() + 10]):
            continue
        v = _kmh(m.group(1), m.group(2))
        if any(abs(v - a) <= 0.02 * a for a, _, _ in approved):
            checked.append((m.start(), m.end()))
            continue
        a, am, f = approved[0]
        out.append(_issue("SPEC-MISMATCH", "Contradicts approved top speed", m.group(0), m.start(), m.end(), kind="replace", suggestion=am.group(0),
                          why=f"{_say(f)}, but the draft says “{m.group(0)}”.", fact=_fact(f)))
    return out, checked


# ------------------------------------------------------------------ production run
UNLIMITED = re.compile(r"(?<![\w-])(?i:unlimited\s+(?:production|run|numbers|availability|supply|quantit(?:y|ies))|mass[- ](?:produced|production)|"
                       r"produced\s+in\s+(?:large|high)\s+(?:numbers|volumes?)|widely\s+available)(?![\w-])")
COUNT = re.compile(rf"(?<![\w.])({NUM})\s*(units|examples|cars|pieces|vehicles|copies)(?![\w])", re.I)
LIMITED = re.compile(r"(?<![\w-])(?i:limited|exclusive|numbered)(?![\w-])")
PRODCTX = re.compile(r"(?i)production|produced|built|build|limited|run of|only|worldwide|available|made|exclusive|numbered|units|examples")


def _production(c, fs):
    out, checked = [], []
    prod = [f for f in fs if re.search(r"(?i)production|limited|run\b|units|examples|numbered|built", f["text"])]
    counts = [(m, f) for f in prod for m in COUNT.finditer(f["text"])]
    limited = [f for f in prod if LIMITED.search(f["text"])] or [f for _, f in counts]
    if not counts and not limited:
        return out, checked
    pf = (counts or [(None, limited[0])])[0][1]
    word = counts[0][0].group(2).lower() if counts else "units"
    num = counts[0][0].group(1) if counts else None
    for m in UNLIMITED.finditer(c):
        fix = f"limited production of {num} {word}" if num else "limited production"
        out.append(_issue("SPEC-CONTRADICTION", "Contradicts approved production run", m.group(0), m.start(), m.end(), kind="replace",
                          suggestion=_cap_like(m.group(0), fix), why=f"{_say(pf)}, so “{m.group(0)}” is not accurate.", fact=_fact(pf)))
    wanted = {_norm_num(m.group(1)) for m, _ in counts}
    for m in COUNT.finditer(c):
        if not wanted or not PRODCTX.search(c[max(0, m.start() - 60):m.end() + 40]):
            continue
        if _norm_num(m.group(1)) in wanted:
            checked.append((m.start(), m.end()))
            continue
        out.append(_issue("SPEC-MISMATCH", "Contradicts approved production number", m.group(0), m.start(), m.end(), kind="replace",
                          suggestion=_fix(m.group(0), num), why=f"{_say(pf)}, but the draft says “{m.group(0)}”.", fact=_fact(pf)))
    return out, checked


# ------------------------------------------------------------------ unsupported technical figures
TECH = re.compile(rf"(?<![\w.]){NUM}[\s-]?(?:Nm|kg|lbs?|mm|cm|km/h|kph|mph|litres?|liters?|kW|cv|hp|bhp|rpm|mAh|Wh|kWh|GB|TB|dB|lumens?|seconds?|secs?)(?![\w/])", re.I)
NUMBER = re.compile(NUM)


def _unsupported(c, fs, ctx, checked):
    out = []
    known = {_norm_num(n) for n in NUMBER.findall(" ".join([f["text"] for f in fs] + list(ctx.get("descriptions", []))))}
    who = ctx.get("productName") or ctx.get("brandName")
    for m in TECH.finditer(c):
        if any(m.start() < e and m.end() > s for s, e in checked):
            continue
        n = NUMBER.search(m.group(0)).group(0)
        if _norm_num(n) in known:
            continue
        out.append(_issue("SPEC-UNSUPPORTED", "Unsupported technical figure", m.group(0), m.start(), m.end(), kind="advice",
                          suggestion="This technical figure is not in the approved fact sheet. Verify it with the Owner, or remove it.",
                          why=f"“{m.group(0)}” cannot be found in the approved data for {who}, so it is unverified.",
                          fact=None, conf=0.7, sev="warning", human=True))
    return out


def find(c: str, ctx) -> list[dict]:
    """All specification issues in `c` (a UTF-16-safe string; offsets index into it)."""
    fs = facts(ctx)
    if not fs:
        return []
    t = c.translate(_DASH)
    out, checked = [], []
    for fn in (_facets, _power, _acceleration, _top_speed, _production):
        o, k = fn(t, fs)
        out += o
        checked += k
    out += _unsupported(t, fs, ctx, checked + [(i["start"], i["end"]) for i in out])
    for i in out:  # quote the draft's own characters (the dash translation only changed lookups)
        i["quote"] = c[i["start"]:i["end"]]
    return out
