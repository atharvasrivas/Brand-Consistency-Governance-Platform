"""Optional Gemini layer, used only from the backend. The rule engine is the source of truth; the model adds to it.

Guarantees enforced in code, not by prompting:
  * the API key never leaves the server (and is scrubbed from anything recorded or returned)
  * only the selected brand/product approved context (plus the draft) is sent; nothing from other brands
  * the model cannot create mandatory findings, and cannot invent a source: a finding is "verified" only if it cites the id
    of a real approved item in the context, otherwise it is downgraded to an unverified suggestion routed to a person
  * every quote must appear verbatim in the draft; offsets are computed here
  * rewrites are accepted only if they add no numbers outside the approved facts and no new rule violations
  * any failure returns nothing, and the rule engine result stands

Nothing fails silently any more: every call records success/failure, HTTP status, latency and a classified error per capability
("text", "image", "rewrite", "diagnose"). `status()` and `diagnose()` expose that so "API Connected" can mean something.

Request/response handling is covered by tests with mocked HTTP. It has not been run against the live Gemini API from here:
run POST /api/ai/diagnose on the deployed server to verify the key, model, text and image paths for real.
"""
import base64
import json
import re
import struct
import time
import zlib
from collections import deque
from datetime import datetime, timezone

import requests

from ..engine.review import from_js, review, to_js

HOST = "https://generativelanguage.googleapis.com/v1beta"
CATS = ["Facts & claims", "Terminology", "Language & tone", "Audience fit"]
IMAGE_MIMES = ("image/png", "image/jpeg", "image/webp", "image/gif")

FINDINGS_SCHEMA = {
    "type": "object",
    "properties": {"findings": {"type": "array", "items": {"type": "object", "properties": {
        "quote": {"type": "string"}, "label": {"type": "string"}, "category": {"type": "string", "enum": CATS},
        "severity": {"type": "string", "enum": ["warning", "suggestion"]}, "suggestion": {"type": "string"},
        "why": {"type": "string"}, "basisId": {"type": "string"}, "confidence": {"type": "number"}},
        "required": ["quote", "label", "category", "why", "confidence"]}}},
    "required": ["findings"],
}
REWRITE_SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}, "changes": {"type": "array", "items": {"type": "string"}}}, "required": ["text"]}
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
ASPECTS = ["logo", "colour", "typography", "composition", "product", "style", "text", "other"]
IMAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "matchesBrand": {"type": "string", "enum": ["yes", "partly", "no", "unclear"]},
        "detected": {"type": "object", "properties": {
            "subject": {"type": "string"}, "logoPresent": {"type": "boolean"}, "dominantColours": {"type": "array", "items": {"type": "string"}},
            "fonts": {"type": "array", "items": {"type": "string"}}, "textInImage": {"type": "string"}}},
        "findings": {"type": "array", "items": {"type": "object", "properties": {
            "aspect": {"type": "string", "enum": ASPECTS}, "issue": {"type": "string"}, "why": {"type": "string"}, "change": {"type": "string"},
            "guideline": {"type": "string"}, "basisId": {"type": "string"}, "severity": {"type": "string", "enum": ["warning", "suggestion"]},
            "confidence": {"type": "number"}}, "required": ["aspect", "issue", "why", "change", "confidence"]}},
        "concept": {"type": "object", "properties": {"headline": {"type": "string"}, "steps": {"type": "array", "items": {"type": "string"}}}},
    },
    "required": ["summary", "matchesBrand", "findings"],
}
THEMES_SCHEMA = {"type": "object", "properties": {"themes": {"type": "array", "items": {"type": "object", "properties": {
    "theme": {"type": "string"}, "domain": {"type": "string", "enum": ["text", "visual"]}, "description": {"type": "string"},
    "submissionIds": {"type": "array", "items": {"type": "string"}}, "quotes": {"type": "array", "items": {"type": "object", "properties": {
        "submissionId": {"type": "string"}, "quote": {"type": "string"}}, "required": ["submissionId", "quote"]}},
    "recommendation": {"type": "string"}, "consistentWording": {"type": "string"}}, "required": ["theme", "domain", "description", "recommendation"]}}},
    "required": ["themes"]}


class GeminiError(Exception):
    """kind: no_key | timeout | unreachable | auth | quota | model | bad_request | server | blocked | empty | parse | unknown"""

    def __init__(self, kind, message, status=None):
        super().__init__(message)
        self.kind, self.message, self.status = kind, message, status


def _api_error(status, data):
    msg = ""
    if isinstance(data, dict) and isinstance(data.get("error"), dict):
        msg = str(data["error"].get("message") or data["error"].get("status") or "")
    msg = re.sub(r"\s+", " ", msg)[:240]
    if status in (401, 403) or (status == 400 and "api key" in msg.lower()):
        return GeminiError("auth", f"API key rejected or not allowed to use this model (HTTP {status}). {msg}".strip(), status)
    if status == 404:
        return GeminiError("model", f"Model not found or not available for this key (HTTP 404). {msg}".strip(), status)
    if status == 429:
        return GeminiError("quota", f"Rate limit or quota exceeded (HTTP 429). {msg}".strip(), status)
    if status == 400:
        return GeminiError("bad_request", f"Gemini rejected the request (HTTP 400). {msg}".strip(), status)
    if status >= 500:
        return GeminiError("server", f"Gemini service error (HTTP {status}). {msg}".strip(), status)
    return GeminiError("unknown", f"Unexpected response (HTTP {status}). {msg}".strip(), status)


def _extract_text(data):
    if not isinstance(data, dict):
        raise GeminiError("parse", "Gemini returned an unreadable response")
    block = (data.get("promptFeedback") or {}).get("blockReason")
    if block:
        raise GeminiError("blocked", f"Gemini blocked the request ({block})")
    cands = data.get("candidates") or []
    if not cands:
        raise GeminiError("empty", "Gemini returned no candidates")
    c = cands[0]
    text = "".join(p.get("text", "") for p in ((c.get("content") or {}).get("parts") or []) if isinstance(p, dict))
    if not text.strip():
        raise GeminiError("empty", f"Gemini returned no text (finishReason={c.get('finishReason') or 'unknown'})")
    return text, c.get("finishReason")


def _parse_json(text, finish=None):
    try:
        return json.loads(text)
    except ValueError:
        pass
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    for cand in (t, t[t.find("{"):t.rfind("}") + 1] if "{" in t else ""):
        try:
            return json.loads(cand)
        except ValueError:
            continue
    why = " (the response was cut off: MAX_TOKENS)" if finish == "MAX_TOKENS" else ""
    raise GeminiError("parse", f"Gemini did not return valid JSON{why}")


def _red_png(n=32):
    row = b"\x00" + b"\xff\x00\x00" * n

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(row * n)) + chunk(b"IEND", b""))


class Gemini:
    def __init__(self, cfg, session=None):
        self.key, self.model, self.style, self.timeout = cfg.gemini_key, cfg.gemini_model, cfg.gemini_style, cfg.gemini_timeout
        self.image_timeout = max(self.timeout, getattr(cfg, "gemini_image_timeout", 45.0))
        self.retries, self.backoff = getattr(cfg, "gemini_retries", 1), getattr(cfg, "gemini_backoff", 0.8)
        self.thinking = getattr(cfg, "gemini_thinking", "low")
        self.s = session or requests.Session()
        self.last = {}                 # capability -> most recent outcome
        self.log = deque(maxlen=40)    # recent outcomes, newest last

    @property
    def enabled(self):
        return bool(self.key)

    # ---------- bookkeeping ----------
    def _scrub(self, text):
        t = str(text or "")
        return t.replace(self.key, "***") if self.key else t

    def _record(self, cap, ok, ms, err=None):
        rec = {"capability": cap, "ok": ok, "at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"), "ms": int(ms),
               "model": self.model, "status": getattr(err, "status", None), "kind": getattr(err, "kind", None),
               "error": self._scrub(getattr(err, "message", None) or (str(err) if err else None))}
        self.last[cap] = rec
        self.log.append(rec)

    def last_error(self, cap):
        r = self.last.get(cap)
        return r["error"] if r and not r["ok"] else None

    # ---------- transport ----------
    def _post(self, url, body, timeout):
        h = {"x-goog-api-key": self.key, "Content-Type": "application/json"}
        err = None
        for i in range(1 + max(0, self.retries)):
            try:
                r = self.s.post(url, headers=h, json=body, timeout=timeout)
            except requests.Timeout:
                err = GeminiError("timeout", f"Gemini did not answer within {timeout:.0f}s")
            except requests.RequestException as e:
                err = GeminiError("unreachable", f"Could not reach the Gemini API ({type(e).__name__})")
            else:
                try:
                    data = r.json()
                except ValueError:
                    data = None
                if r.status_code == 200:
                    if data is None:
                        err = GeminiError("parse", "Gemini returned a non-JSON HTTP response", 200)
                    else:
                        return data
                else:
                    err = _api_error(r.status_code, data)
            if err.status in (429, 503) and i < self.retries:
                time.sleep(self.backoff * (i + 1))
                continue
            break
        raise err

    def _pick_model(self, avoid):
        """Ask Google which models this key can use and choose the newest stable Flash model that supports generateContent."""
        try:
            r = self.s.get(f"{HOST}/models?pageSize=200", headers={"x-goog-api-key": self.key}, timeout=10)
            models = (r.json() or {}).get("models", []) if r.status_code == 200 else []
        except Exception:  # noqa: BLE001
            return None
        best, best_score = None, None
        for m in models:
            name = str(m.get("name", "")).replace("models/", "")
            if name == avoid or "generateContent" not in (m.get("supportedGenerationMethods") or []):
                continue
            g = re.match(r"gemini-(\d+(?:\.\d+)?)-flash(.*)$", name)
            if not g or re.search(r"lite|image|tts|live|audio|embed|thinking|exp|8b", g.group(2)):
                continue
            score = (0 if "preview" in g.group(2) or re.search(r"\d{3,}", g.group(2)) else 1, float(g.group(1)))
            if best_score is None or score > best_score:
                best, best_score = name, score
        if not best:
            for fallback in ("gemini-3.8-flash", "gemini-2.0-flash", "gemini-1.5-flash"):
                if fallback != avoid:
                    return fallback
        return best

    def _gen_cfg(self, schema):
        """Gemini 3.x models are reasoning models: they need room for thinking in the output budget, and Google advises leaving
        temperature at its default for them. Older models keep the low temperature that makes the JSON steadier."""
        cfg = {"responseMimeType": "application/json", "responseSchema": _gs(schema), "maxOutputTokens": 8192}
        if not re.match(r"gemini-([3-9]|\d{2,})", self.model):
            cfg["temperature"] = 0.2
        elif self.thinking:
            cfg["thinkingConfig"] = {"thinkingLevel": self.thinking}  # these requests are short extraction tasks, not puzzles
        return cfg

    def _call(self, path_for, body, timeout):
        """POST with self-healing: if the configured model is gone (404), switch to one the key can use and retry once."""
        try:
            return self._post(path_for(self.model), body, timeout)
        except GeminiError as e:
            if e.kind == "bad_request" and "thinking" in e.message.lower() and "thinkingConfig" in (body.get("generationConfig") or {}):
                self.thinking = ""   # this model does not accept the setting: stop sending it
                body["generationConfig"].pop("thinkingConfig", None)
                return self._post(path_for(self.model), body, timeout)
            if e.kind != "model":
                raise
            new = self._pick_model(self.model)
            if not new:
                raise
            old, self.model = self.model, new
            self.log.append({"capability": "model", "ok": True, "at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"), "ms": 0,
                             "model": new, "status": 404, "kind": "model", "error": None, "note": f"{old} was not available; switched to {new}"})
            if "model" in body:
                body["model"] = new
            return self._post(path_for(new), body, timeout)

    def _json(self, cap, system, prompt, schema, images=None):
        """One structured request. `images` = [(bytes_or_b64, mime, label)]. Raises GeminiError and records the outcome."""
        t0 = time.monotonic()
        try:
            if not self.enabled:
                raise GeminiError("no_key", "GEMINI_API_KEY is not set")
            if images:  # vision is only sent through generateContent
                parts = [{"text": prompt}]
                for raw, mime, label in images:
                    b64 = raw if isinstance(raw, str) else base64.b64encode(raw).decode()
                    parts += [{"text": f"[{label}]"}, {"inlineData": {"mimeType": mime, "data": b64}}]
                body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": parts}],
                        "generationConfig": self._gen_cfg(schema)}
                data = self._call(lambda m: f"{HOST}/models/{m}:generateContent", body, self.image_timeout)
                text, finish = _extract_text(data)
            elif self.style == "interactions":
                body = {"model": self.model, "input": f"{system}\n\n{prompt}", "response_format": {"type": "json_schema", "schema": schema}}
                data = self._call(lambda m: f"{HOST}/interactions", body, self.timeout)
                text = "".join(c.get("text", "") for st in data.get("steps", []) if st.get("type") == "model_output" for c in st.get("content", []) if c.get("type") == "text")
                if not text.strip():
                    raise GeminiError("empty", "Gemini returned no model output")
                finish = None
            else:
                body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                        "generationConfig": self._gen_cfg(schema)}
                data = self._call(lambda m: f"{HOST}/models/{m}:generateContent", body, self.timeout)
                text, finish = _extract_text(data)
            out = _parse_json(text, finish)
        except GeminiError as e:
            e.message = self._scrub(e.message)  # whatever the upstream said, the key must never travel further than this
            self._record(cap, False, (time.monotonic() - t0) * 1000, e)
            raise
        except Exception as e:  # unexpected shape of a response: still never silent
            err = GeminiError("unknown", f"Unexpected error handling the Gemini response ({type(e).__name__})")
            self._record(cap, False, (time.monotonic() - t0) * 1000, err)
            raise err
        self._record(cap, True, (time.monotonic() - t0) * 1000)
        return out

    # ---------- extra findings (text) ----------
    def suggest(self, content, meta, ctx, existing):
        if not self.enabled or not content.strip():
            return []
        system = ("You are a brand-compliance reviewer. Using ONLY the approved context provided, review the DRAFT and report: "
                  "(1) statements that contradict an approved fact or technical specification (engine or powertrain type, power, performance figures, "
                  "dimensions, production numbers, availability), (2) unsupported promotional or comparative claims, (3) wording that clashes with the brand "
                  "voice, personality or tone guidance, (4) terminology that differs from the approved terminology, (5) messaging that is inconsistent with the "
                  "approved brand description, and (6) wording that does not suit the audience. Use category 'Facts & claims' for specification problems. "
                  "Quote the exact words from the draft. Cite the id of the approved item you rely on as basisId; if none applies leave basisId empty. "
                  "Never invent facts, numbers or sources. Return JSON only.")
        prompt = json.dumps({"context": context_for_model(ctx), "audience": meta.get("audience"), "purpose": meta.get("purpose"), "contentType": meta.get("type"), "draft": content}, ensure_ascii=False)
        try:
            raw = self._json("text", system, prompt, FINDINGS_SCHEMA)
        except GeminiError:
            return []
        return validate_ai_findings(raw, content, ctx, existing)

    # ---------- rewrite ----------
    def rewrite(self, text, meta, ctx, findings):
        """Rewrite the text so it resolves EVERY listed finding and follows the brand voice. Returns the new text or None."""
        if not self.enabled or not text.strip():
            return None
        voice = ctx["voice"]
        system = ("You are a brand copy editor. Rewrite the TEXT so that it (a) fixes every issue in ISSUES, (b) follows the brand voice and terminology, "
                  "(c) keeps the original purpose, audience, structure and call to action, and (d) stays natural marketing copy, not a list of corrections. "
                  "Use ONLY the facts in CONTEXT. Never add a number, statistic, guarantee, comparison or claim that is not in CONTEXT or in the original text. "
                  "If an unsupported claim cannot be replaced by an approved fact, remove or soften it. If ISSUES is empty, only improve tone and clarity. "
                  "Never say the text is compliant. Return JSON: text, and changes (one short line per change).")
        issues = [{"quote": f.get("quote"), "problem": f.get("label"), "why": f.get("why"), "fix": f.get("suggestion"), "mandatory": f.get("strictness") == "mandatory"}
                  for f in findings[:30]]
        prompt = json.dumps({"context": context_for_model(ctx), "voice": [*voice.get("personality", []), voice.get("toneGuidance", "")], "contentType": meta.get("type"),
                             "audience": meta.get("audience"), "purpose": meta.get("purpose"), "issues": issues, "text": text}, ensure_ascii=False)
        try:
            new = self._json("rewrite", system, prompt, REWRITE_SCHEMA)
        except GeminiError:
            return None
        new_text = new.get("text") if isinstance(new, dict) else None
        if not isinstance(new_text, str):
            return None
        changes = [str(c)[:200] for c in (new.get("changes") or []) if isinstance(c, str)][:12]
        return {"text": new_text, "changes": changes}

    def polish(self, text, meta, ctx):
        """Tone-only polish (kept for callers that have no findings)."""
        out = self.rewrite(text, meta, ctx, [])
        return out["text"] if out and polish_is_safe(text, out["text"], meta, ctx) else None

    # ---------- image analysis ----------
    def analyse_image(self, image_b64, mime, ctx, content, meta, references=()):
        """Send the uploaded image (plus approved reference images) and the approved visual guidelines to the vision model.
        Returns validated {"analysis":..., "findings":[...]} or raises GeminiError."""
        if mime not in IMAGE_MIMES:
            raise GeminiError("bad_request", f"Images of type {mime or 'unknown'} cannot be analysed. Use PNG, JPEG, WebP or GIF.")
        system = ("You are a brand visual-compliance reviewer. You are given the approved visual identity (colours with hex codes, fonts, logo rules, retired "
                  "assets, written guidelines, product description) and, when available, approved REFERENCE images, followed by the UPLOADED image to assess. "
                  "Judge ONLY what you can actually see in the uploaded image. Check: logo (present, correct, distorted, retired), colour palette (hex distance "
                  "from approved colours), typography (against approved fonts), composition and layout, product representation (is it the right product, "
                  "is it accurate), and overall advertising style versus the brand identity and voice. For each problem say what is inconsistent, why, which "
                  "approved item it conflicts with (basisId from the context), and the specific change needed. Read any text visible in the image into "
                  "detected.textInImage. If you cannot tell, use matchesBrand 'unclear' and a low confidence; never invent guidelines. Finally give a concept: "
                  "a short headline and numbered steps describing how to correct the asset to match the brand (a brief, not an image). Return JSON only.")
        prompt = json.dumps({"context": visual_context(ctx, [r[2] for r in references]), "contentType": meta.get("type"), "audience": meta.get("audience"),
                             "adCopy": (content or "")[:2000]}, ensure_ascii=False)
        imgs = [(raw, m, f"APPROVED REFERENCE: {label}") for raw, m, label in references] + [(image_b64, mime, "UPLOADED IMAGE TO ASSESS")]
        raw = self._json("image", system, prompt, IMAGE_SCHEMA, images=imgs)
        return validate_image_result(raw, ctx, [r[2] for r in references])

    # ---------- recurring themes across submissions ----------
    def themes(self, ctx, items):
        """items = [{"id","title","type","content","visual"}]. Returns validated themes (quotes must appear in the cited submission)."""
        system = ("You analyse several pieces of marketing content for ONE brand and find RECURRING patterns that break brand consistency: tone of voice, "
                  "messaging, headline and promotional style, terminology, product descriptions, and (from the visual notes) imagery, colour, logo and typography. "
                  "Only report a pattern seen in at least two submissions. Cite the submission ids and quote the exact words. Compare with the approved brand "
                  "voice and facts in CONTEXT; do not invent guidelines or facts. For each pattern give a clear recommendation and a consistent wording or "
                  "visual direction to use from now on. Return JSON only.")
        prompt = json.dumps({"context": context_for_model(ctx), "submissions": items}, ensure_ascii=False)
        raw = self._json("themes", system, prompt, THEMES_SCHEMA)
        return validate_themes(raw, items)

    # ---------- fact-sheet assistant ----------
    def draft_factsheet(self, scope, name, answers, document_text):
        if not self.enabled:
            return None
        system = (f"You turn the owner's answers and pasted document text into a draft {scope} fact sheet. Use ONLY information that is stated in the input. "
                  "Do not add claims, numbers or sources that are not in the input. Leave fields empty when the input does not say. Return JSON only.")
        try:
            return self._json("assistant", system, json.dumps({"name": name, "answers": answers, "documentText": (document_text or "")[:12000]}, ensure_ascii=False), DRAFT_SCHEMA)
        except GeminiError:
            return None

    # ---------- diagnostics ----------
    def status(self):
        """What is known WITHOUT spending quota: whether a key is set and how recent real calls went."""
        cap = lambda c: self.last.get(c)  # noqa: E731
        text_ok, image_ok = (cap("text") or {}).get("ok"), (cap("image") or {}).get("ok")
        diag = cap("diagnose:text")
        if not self.enabled:
            level = "off"
        elif (text_ok or (diag or {}).get("ok")) and (image_ok or (cap("diagnose:image") or {}).get("ok")):
            level = "full"
        elif text_ok or (diag or {}).get("ok"):
            level = "text"
        elif any(r["ok"] is False for r in self.last.values()):
            level = "failing"
        else:
            level = "unverified"
        return {"configured": self.enabled, "model": self.model, "style": self.style, "level": level,
                "capabilities": {k: v for k, v in self.last.items()}, "recent": list(self.log)[-10:]}

    def diagnose(self):
        """Actively verify each layer with real requests (costs a few small calls). Stages never raise."""
        stages = []

        def stage(sid, label, ok, detail="", status=None, ms=None):
            stages.append({"id": sid, "label": label, "ok": ok, "detail": self._scrub(detail)[:300], "status": status, "ms": None if ms is None else int(ms)})
            return ok

        if not stage("key", "API key configured", self.enabled, "GEMINI_API_KEY is set" if self.enabled else "GEMINI_API_KEY is not set on the server"):
            return {"overall": "off", "model": self.model, "stages": stages}

        # 1. service reachable + model available
        t0 = time.monotonic()
        getter = getattr(self.s, "get", None)
        if getter is None:
            stage("reachable", "Gemini service reachable", None, "not checked by this HTTP session")
            stage("model", f"Model “{self.model}” available", None, "not checked")
        else:
            try:
                r = getter(f"{HOST}/models/{self.model}", headers={"x-goog-api-key": self.key}, timeout=10)
                ms = (time.monotonic() - t0) * 1000
                try:
                    data = r.json()
                except ValueError:
                    data = None
                stage("reachable", "Gemini service reachable", r.status_code < 500, f"HTTP {r.status_code}", r.status_code, ms)
                if r.status_code == 200:
                    methods = (data or {}).get("supportedGenerationMethods") or []
                    ok = not methods or "generateContent" in methods
                    stage("model", f"Model “{self.model}” available", ok, "supports generateContent" if ok else "model does not support generateContent", 200)
                else:
                    e = _api_error(r.status_code, data)
                    stage("model", f"Model “{self.model}” available", False, e.message, r.status_code)
            except requests.RequestException as e:
                stage("reachable", "Gemini service reachable", False, f"{type(e).__name__}: could not connect")
                stage("model", f"Model “{self.model}” available", None, "not checked")

        # 2-4. real requests, run side by side so the whole check fits inside the server's time limit
        from concurrent.futures import ThreadPoolExecutor

        sample_ctx = {"brand": "Diagnostic", "product": None, "voice": {"personality": ["plain"], "toneGuidance": "Plain and factual."},
                      "approvedClaims": [], "specs": [{"id": "s1", "name": "Capacity", "value": "1.7 litres"}], "restrictedClaims": [], "terminology": [{"id": "t1", "avoid": "cheap", "prefer": "affordable"}]}

        def plain():
            t = time.monotonic()
            try:
                d = self._post(f"{HOST}/models/{self.model}:generateContent",
                               {"systemInstruction": {"parts": [{"text": "Answer as briefly as possible."}]}, "contents": [{"role": "user", "parts": [{"text": "Reply with the single word OK."}]}], "generationConfig": {"maxOutputTokens": 64}}, self.timeout)
                txt, _ = _extract_text(d)
                return ("plain", "Plain request answered (no JSON schema)", True, f"“{txt.strip()[:20]}” in {time.monotonic() - t:.1f}s", 200, (time.monotonic() - t) * 1000)
            except GeminiError as e:
                return ("plain", "Plain request answered (no JSON schema)", False, e.message, e.status, (time.monotonic() - t) * 1000)

        def text():
            t = time.monotonic()
            try:
                raw = self._json("diagnose:text", "You are a brand-compliance reviewer. Using ONLY the context, find problems in the draft. Return JSON only.",
                                 json.dumps({"context": sample_ctx, "draft": "This cheap kettle holds 2 litres."}), FINDINGS_SCHEMA)
                n = len(raw.get("findings", [])) if isinstance(raw, dict) else 0
                return ("text", "Successful AI request + text analysis", isinstance(raw, dict) and isinstance(raw.get("findings"), list),
                        f"structured JSON returned, {n} finding(s)", 200, (time.monotonic() - t) * 1000)
            except GeminiError as e:
                return ("text", "Successful AI request + text analysis", False, e.message, e.status, (time.monotonic() - t) * 1000)

        def image():
            t = time.monotonic()
            schema = {"type": "object", "properties": {"dominantColour": {"type": "string"}}, "required": ["dominantColour"]}
            try:
                raw = self._json("diagnose:image", "Describe the image. Return JSON only.", "What is the single dominant colour of this image? Answer in the field dominantColour.",
                                 schema, images=[(_red_png(), "image/png", "diagnostic image")])
                seen = str(raw.get("dominantColour", "")) if isinstance(raw, dict) else ""
                ok = "red" in seen.lower()
                return ("image", "Successful image analysis", ok, f"model saw: “{seen[:40]}”" if ok else f"model answered “{seen[:40]}” for a red image: it is not reading the pixels", 200, (time.monotonic() - t) * 1000)
            except GeminiError as e:
                return ("image", "Successful image analysis", False, e.message, e.status, (time.monotonic() - t) * 1000)

        with ThreadPoolExecutor(max_workers=3) as ex:
            futs = [ex.submit(f) for f in (plain, text, image)]
            for f in futs:
                sid, label, ok, detail, status, ms = f.result()
                if sid == "plain":
                    stages.append({"id": sid, "label": label, "ok": ok, "detail": self._scrub(detail)[:300], "status": status, "ms": int(ms)})
                else:
                    stage(sid, label, ok, detail, status, ms)

        by = {s["id"]: s["ok"] for s in stages}
        overall = "full" if by.get("text") and by.get("image") else "text" if by.get("text") else "failing"
        return {"overall": overall, "model": self.model, "style": self.style, "stages": stages}


def _gs(schema):
    if isinstance(schema, dict):
        return {k: _gs(v) for k, v in schema.items() if k != "additionalProperties"}
    if isinstance(schema, list):
        return [_gs(x) for x in schema]
    return schema


# ---------------------------------------------------------------------------------------------- context for the model
def context_for_model(ctx):
    out = {"brand": ctx["brandName"], "product": ctx["productName"], "voice": ctx["voice"],
           "approvedClaims": [{"id": c["id"], "text": c["text"]} for c in ctx["claims"]],
           "specs": [{"id": s["id"], "name": s["name"], "value": s["value"]} for s in ctx["specs"]],
           "restrictedClaims": [{"id": r["id"], "text": r["text"]} for r in ctx["restricted"]],
           "terminology": [{"id": t["id"], "avoid": t["avoid"], "prefer": t["prefer"]} for t in ctx["terms"]]}
    extra = {"description": " ".join(d for d in ctx.get("descriptions", []) if d)[:1500], "tagline": ctx.get("tagline"), "values": ctx.get("values"),
             "targetAudience": ctx.get("targetAudience"), "voiceNotes": ctx.get("voiceText"),
             "guidelines": [{"id": g["id"], "text": g["text"]} for g in ctx.get("guidelines", [])][:30],
             "avoidPhrases": [{"phrase": t["phrase"], "prefer": t.get("prefer")} for t in ctx.get("toneAvoid", [])][:30],
             "previousNames": [o for o, _, _ in ctx.get("previousNames", [])]}
    out.update({k: v for k, v in extra.items() if v})
    return out


def visual_context(ctx, reference_names=()):
    return {"brand": ctx["brandName"], "product": ctx["productName"],
            "colours": [{"id": c["id"], "name": c.get("name"), "hex": c["hex"], "role": c.get("role")} for c in ctx.get("colours", [])],
            "fonts": [{"id": f"font:{f}", "name": f} for f in ctx.get("fonts", [])],
            "logo": {"id": "logo", "approvedLogoFile": ctx.get("logoName")},
            "retiredAssets": [{"id": f"retired:{a}", "name": a} for a in ctx.get("deprecatedAssets", [])],
            "visualGuidelines": [{"id": g["id"], "text": g["text"]} for g in ctx.get("guidelines", [])][:30],
            "voice": ctx["voice"], "description": " ".join(d for d in ctx.get("descriptions", []) if d)[:1200],
            "approvedReferenceImages": list(reference_names)}


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
    for g in ctx.get("guidelines", []):
        m[g["id"]] = {"doc": g["doc"], "ref": g.get("source") or "Guideline"}
    return m


def _visual_basis(ctx):
    doc, m = f"{ctx['brandName']} brand profile", {}
    for c in ctx.get("colours", []):
        m[c["id"]] = {"doc": doc, "ref": f"Colour {c.get('name') or c['hex']} {c['hex']}"}
    for f in ctx.get("fonts", []):
        m[f"font:{f}"] = {"doc": doc, "ref": f"Typography: {f}"}
    for a in ctx.get("deprecatedAssets", []):
        m[f"retired:{a}"] = {"doc": f"{ctx['brandName']} brand assets", "ref": f"Retired asset: {a}"}
    for g in ctx.get("guidelines", []):
        m[g["id"]] = {"doc": g["doc"], "ref": g.get("source") or "Guideline"}
    m["logo"] = {"doc": doc, "ref": "Logo"}
    return m


# ---------------------------------------------------------------------------------------------- validation of model output
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


def validate_image_result(raw, ctx, reference_names=()):
    """Turn the model's image report into app findings. Never mandatory, always routed to a person; a finding only cites an
    approved source if its basisId is a real approved visual item."""
    if not isinstance(raw, dict):
        raise GeminiError("parse", "The image analysis was not an object")
    basis, brand = _visual_basis(ctx), ctx["brandName"]
    findings = []
    for i, r in enumerate((raw.get("findings") or [])[:12]):
        if not isinstance(r, dict) or not isinstance(r.get("issue"), str) or not r["issue"].strip():
            continue
        aspect = r.get("aspect") if r.get("aspect") in ASPECTS else "other"
        source = basis.get(r.get("basisId"))
        verified = source is not None
        conf = r.get("confidence") if isinstance(r.get("confidence"), (int, float)) else 0.5
        conf = max(0.0, min(1.0, float(conf)))
        if not verified:
            conf, source = min(conf, 0.6), {"doc": "Unverified AI observation", "ref": "Not backed by an approved guideline"}
        issue = re.sub(r"\s+", " ", r["issue"]).strip()[:200]
        findings.append({
            "id": f"IMG-AI:{i}", "key": f"IMG-AI|{aspect}|{re.sub(r'[^a-z0-9 ]+', '', issue.lower())[:60]}", "ruleId": "IMG-AI",
            "label": f"Visual: {aspect}", "category": "Visual identity", "severity": "warning" if (verified and r.get("severity") == "warning") else "suggestion",
            "strictness": "flexible", "kind": "advice", "scope": "image", "quote": issue,
            "suggestion": str(r.get("change") or "Review this visual element against the approved identity.")[:400], "why": str(r.get("why") or "")[:400],
            "source": source, "confidence": conf, "needsHuman": True, "occurrences": 1, "ai": True, "aspect": aspect})
    det = raw.get("detected") if isinstance(raw.get("detected"), dict) else {}
    concept = raw.get("concept") if isinstance(raw.get("concept"), dict) else {}
    analysis = {"status": "ok", "summary": str(raw.get("summary") or "")[:800],
                "matchesBrand": raw.get("matchesBrand") if raw.get("matchesBrand") in ("yes", "partly", "no", "unclear") else "unclear",
                "detected": {"subject": str(det.get("subject") or "")[:200], "logoPresent": det.get("logoPresent") if isinstance(det.get("logoPresent"), bool) else None,
                             "dominantColours": [str(c)[:40] for c in (det.get("dominantColours") or [])][:8], "fonts": [str(c)[:60] for c in (det.get("fonts") or [])][:8],
                             "textInImage": str(det.get("textInImage") or "")[:1000]},
                "concept": {"headline": str(concept.get("headline") or "")[:200], "steps": [str(s)[:300] for s in (concept.get("steps") or [])][:8]},
                "references": list(reference_names), "brand": brand}
    return {"analysis": analysis, "findings": findings}


def validate_themes(raw, items):
    if not isinstance(raw, dict) or not isinstance(raw.get("themes"), list):
        return []
    by_id = {i["id"]: i for i in items}
    out = []
    for t in raw["themes"][:10]:
        if not isinstance(t, dict) or not t.get("theme") or not t.get("recommendation"):
            continue
        ids = [i for i in (t.get("submissionIds") or []) if i in by_id]
        quotes = []
        for q in (t.get("quotes") or []):
            if isinstance(q, dict) and q.get("submissionId") in by_id and isinstance(q.get("quote"), str) and q["quote"].strip() \
                    and q["quote"].lower() in by_id[q["submissionId"]]["content"].lower():
                quotes.append({"submissionId": q["submissionId"], "title": by_id[q["submissionId"]]["title"], "quote": q["quote"][:240]})
        ids = sorted(set(ids) | {q["submissionId"] for q in quotes})
        if len(ids) < 2:  # a pattern needs at least two real submissions behind it
            continue
        out.append({"theme": str(t["theme"])[:120], "domain": "visual" if t.get("domain") == "visual" else "text", "description": str(t.get("description") or "")[:500],
                    "submissions": len(ids), "submissionIds": ids, "examples": quotes[:4], "recommendation": str(t["recommendation"])[:500],
                    "consistentWording": str(t.get("consistentWording") or "")[:300], "ai": True})
    return out


def _fix(d):
    return {k: from_js(v) if isinstance(v, str) else v for k, v in d.items()}


NUMS = re.compile(r"\d[\d,.]*%?")


def _nums(t):
    return {n.rstrip(",.") for n in NUMS.findall(t or "")}


def approved_numbers(ctx):
    texts = [c["text"] for c in ctx.get("claims", [])] + [s["value"] for s in ctx.get("specs", [])] + [s["name"] for s in ctx.get("specs", [])] + list(ctx.get("descriptions", []))
    return set().union(*[_nums(t) for t in texts]) if texts else set()


def polish_is_safe(before, after, meta, ctx):
    """A model rewrite is accepted only if it invents no numbers (beyond the original text and the approved facts), is not absurdly
    longer, and does not add any rule violation: every (rule, quote) problem left in it must already have existed."""
    if not isinstance(after, str) or not after.strip() or len(after) > max(200, len(before) * 1.6):
        return False
    if _nums(after) - _nums(before) - approved_numbers(ctx):
        return False
    problems = lambda t: [f for f in review(t, meta, None, ctx) if f["scope"] == "text" and f["strictness"] == "mandatory"]  # noqa: E731
    pa, pb = problems(after), problems(before)
    ident = lambda fs: {(f["ruleId"], f["quote"].lower()) for f in fs}  # noqa: E731
    return len(pa) <= len(pb) and ident(pa) <= ident(pb)
