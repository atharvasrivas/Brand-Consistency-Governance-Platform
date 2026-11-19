"""Optional Gemini layer, used only from the backend. The rule engine is the source of truth; the model adds to it.

Guarantees enforced in code, not by prompting:
  * the API key never leaves the server
  * only the selected brand/product approved context (plus the draft) is sent; nothing from other brands
  * the model cannot create mandatory findings, and cannot invent a source: a finding is "verified" only if it cites the id
    of a real approved item in the context, otherwise it is downgraded to an unverified suggestion routed to a person
  * every quote must appear verbatim in the draft; offsets are computed here
  * rewrites are accepted only if they add no numbers and no new rule violations
  * any failure returns nothing, and the rule engine result stands

Request/response handling is covered by tests with mocked HTTP. It has not been run against the live Gemini API.
"""
import json
import re

import requests

from ..engine.review import from_js, review, to_js

HOST = "https://generativelanguage.googleapis.com/v1beta"
CATS = ["Facts & claims", "Terminology", "Language & tone", "Audience fit"]

FINDINGS_SCHEMA = {
    "type": "object",
    "properties": {"findings": {"type": "array", "items": {"type": "object", "properties": {
        "quote": {"type": "string"}, "label": {"type": "string"}, "category": {"type": "string", "enum": CATS},
        "severity": {"type": "string", "enum": ["warning", "suggestion"]}, "suggestion": {"type": "string"},
        "why": {"type": "string"}, "basisId": {"type": "string"}, "confidence": {"type": "number"}},
        "required": ["quote", "label", "category", "why", "confidence"]}}},
    "required": ["findings"],
}
REWRITE_SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string"}, "heritage": {"type": "string"}, "personality": {"type": "array", "items": {"type": "string"}},
        "toneGuidance": {"type": "string"}, "previousNames": {"type": "array", "items": {"type": "string"}},
        "approvedClaims": {"type": "array", "items": {"type": "object", "properties": {"text": {"type": "string"}, "source": {"type": "string"}}, "required": ["text"]}},
        "restrictedClaims": {"type": "array", "items": {"type": "object", "properties": {"text": {"type": "string"}, "reason": {"type": "string"}}, "required": ["text"]}},
        "terminology": {"type": "array", "items": {"type": "object", "properties": {"avoid": {"type": "string"}, "prefer": {"type": "string"}}, "required": ["avoid", "prefer"]}},
        "specs": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "value": {"type": "string"}, "source": {"type": "string"}}, "required": ["name", "value"]}},
    },
}


class Gemini:
    def __init__(self, cfg, session=None):
        self.key, self.model, self.style, self.timeout = cfg.gemini_key, cfg.gemini_model, cfg.gemini_style, cfg.gemini_timeout
        self.s = session or requests.Session()

    @property
    def enabled(self):
        return bool(self.key)

    def _json(self, system, prompt, schema):
        h = {"x-goog-api-key": self.key, "Content-Type": "application/json"}
        if self.style == "interactions":
            body = {"model": self.model, "input": f"{system}\n\n{prompt}", "response_format": {"type": "json_schema", "schema": schema}}
            r = self.s.post(f"{HOST}/interactions", headers=h, json=body, timeout=self.timeout)
            r.raise_for_status()
            text = "".join(c.get("text", "") for st in r.json().get("steps", []) if st.get("type") == "model_output"
                           for c in st.get("content", []) if c.get("type") == "text")
        else:
            body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json", "responseSchema": _gs(schema), "temperature": 0.2}}
            r = self.s.post(f"{HOST}/models/{self.model}:generateContent", headers=h, json=body, timeout=self.timeout)
            r.raise_for_status()
            text = "".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"])
        return json.loads(text)

    # ---------- extra findings ----------
    def suggest(self, content, meta, ctx, existing):
        if not self.enabled or not content.strip():
            return []
        system = ("You are a brand-compliance reviewer. Using ONLY the approved context provided, find statements in the DRAFT that contradict "
                  "an approved fact, make an unsupported promotional claim, clash with the brand voice, or do not suit the audience. "
                  "Quote the exact words. Cite the id of the approved item you rely on as basisId; if none applies leave basisId empty. "
                  "Never invent facts, numbers or sources. Return JSON only.")
        prompt = json.dumps({"context": context_for_model(ctx), "audience": meta.get("audience"), "purpose": meta.get("purpose"), "draft": content}, ensure_ascii=False)
        try:
            raw = self._json(system, prompt, FINDINGS_SCHEMA)
        except Exception:
            return []
        return validate_ai_findings(raw, content, ctx, existing)

    def polish(self, text, meta, ctx):
        if not self.enabled or not text.strip():
            return None
        voice = ctx["voice"]
        system = ("Rewrite the text to match this brand voice: " + "; ".join([*voice.get("personality", []), voice.get("toneGuidance", "")]) +
                  ". Keep the meaning, audience, call to action and every fact. Do not add any number, statistic, guarantee or claim. Return JSON only.")
        try:
            new = self._json(system, json.dumps({"audience": meta.get("audience"), "text": text}, ensure_ascii=False), REWRITE_SCHEMA)["text"]
        except Exception:
            return None
        return new if polish_is_safe(text, new, meta, ctx) else None

    # ---------- fact-sheet assistant ----------
    def draft_factsheet(self, scope, name, answers, document_text):
        if not self.enabled:
            return None
        system = (f"You turn the owner's answers and pasted document text into a draft {scope} fact sheet. Use ONLY information that is stated in the input. "
                  "Do not add claims, numbers or sources that are not in the input. Leave fields empty when the input does not say. Return JSON only.")
        try:
            return self._json(system, json.dumps({"name": name, "answers": answers, "documentText": (document_text or "")[:12000]}, ensure_ascii=False), DRAFT_SCHEMA)
        except Exception:
            return None


def _gs(schema):
    if isinstance(schema, dict):
        return {k: _gs(v) for k, v in schema.items() if k != "additionalProperties"}
    if isinstance(schema, list):
        return [_gs(x) for x in schema]
    return schema


def context_for_model(ctx):
    return {"brand": ctx["brandName"], "product": ctx["productName"], "voice": ctx["voice"],
            "approvedClaims": [{"id": c["id"], "text": c["text"]} for c in ctx["claims"]],
            "specs": [{"id": s["id"], "name": s["name"], "value": s["value"]} for s in ctx["specs"]],
            "restrictedClaims": [{"id": r["id"], "text": r["text"]} for r in ctx["restricted"]],
            "terminology": [{"id": t["id"], "avoid": t["avoid"], "prefer": t["prefer"]} for t in ctx["terms"]]}


def _basis(ctx):
    m = {}
    for c in ctx["claims"]:
        m[c["id"]] = {"doc": c["doc"], "ref": c.get("source") or "Approved claim"}
    for s in ctx["specs"]:
        m[s["id"]] = {"doc": s["doc"], "ref": s.get("source") or s["name"]}
    for r in ctx["restricted"]:
        m[r["id"]] = {"doc": r["doc"], "ref": "Restricted claim"}
    for t in ctx["terms"]:
        m[t["id"]] = {"doc": t["doc"], "ref": t.get("source") or "Terminology"}
    return m


def validate_ai_findings(raw, content, ctx, existing):
    if not isinstance(raw, dict) or not isinstance(raw.get("findings"), list):
        return []
    js, basis = to_js(content), _basis(ctx)
    taken = [(f["start"], f["end"]) for f in existing if f.get("scope") == "text" and "start" in f]
    for f in existing:
        taken += [(r["start"], r["end"]) for r in f.get("ranges", [])]
    out = []
    for i, r in enumerate(raw["findings"][:12]):
        if not isinstance(r, dict) or not isinstance(r.get("quote"), str) or not r["quote"].strip():
            continue
        q = to_js(r["quote"])
        start = js.find(q)
        if start < 0:
            continue
        end = start + len(q)
        if any(start < e and end > s for s, e in taken):
            continue
        conf = r.get("confidence") if isinstance(r.get("confidence"), (int, float)) else 0.5
        conf = max(0.0, min(1.0, float(conf)))
        source = basis.get(r.get("basisId"))
        verified = source is not None
        if not verified:
            conf, source = min(conf, 0.6), {"doc": "Unverified AI suggestion", "ref": "Not backed by an approved source"}
        sug = r.get("suggestion") if isinstance(r.get("suggestion"), str) and r["suggestion"].strip() else None
        f = {"id": f"AI-{i}:{start}", "key": f"AI|{q.lower()}", "ruleId": "AI-ASSIST", "label": str(r.get("label") or "AI suggestion")[:80],
             "category": r.get("category") if r.get("category") in CATS else "Language & tone",
             "severity": "warning" if (verified and r.get("severity") == "warning") else "suggestion", "strictness": "flexible",
             "kind": "advice", "scope": "text", "start": start, "end": end, "quote": q,
             "suggestion": sug or "Consider rewording this passage.", "why": str(r.get("why") or "")[:400], "source": source,
             "confidence": conf, "needsHuman": (not verified) or conf < 0.7, "ai": True, "occurrences": 1}
        taken.append((start, end))
        out.append(f)
    return [{k: (from_js(v) if isinstance(v, str) else (_fix(v) if isinstance(v, dict) else v)) for k, v in f.items()} for f in out]


def _fix(d):
    return {k: from_js(v) if isinstance(v, str) else v for k, v in d.items()}


NUMS = re.compile(r"\d[\d,.]*%?")


def polish_is_safe(before, after, meta, ctx):
    if not isinstance(after, str) or not after.strip() or len(after) > max(200, len(before) * 1.6):
        return False
    if {n.rstrip(",.") for n in NUMS.findall(after)} - {n.rstrip(",.") for n in NUMS.findall(before)}:
        return False
    crit = lambda t: {f["key"] for f in review(t, meta, None, ctx) if f["severity"] == "critical"}  # noqa: E731
    return crit(after) <= crit(before)
