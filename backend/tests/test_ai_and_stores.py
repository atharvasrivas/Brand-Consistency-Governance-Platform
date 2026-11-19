import json

from app import create_app
from app.ai.gemini import Gemini, polish_is_safe, validate_ai_findings
from app.config import Config
from app.engine.review import review
from app.store.supabase_store import SupabaseStore
from tests.conftest import CREATOR, OWNER, mk_brand

CTX = {"brand": {"id": "b", "name": "Acme", "version": 1}, "product": None, "brandName": "Acme", "productName": None, "previousNames": [],
       "claims": [{"id": "c1", "text": "Boils fast", "doc": "Acme brand profile", "source": "lab"}], "restricted": [], "terms": [], "toneAvoid": [],
       "specs": [], "colours": [], "fonts": [], "deprecatedAssets": [], "approvedAssetNames": [], "voice": {"personality": ["warm"], "toneGuidance": "plain"},
       "descriptions": [], "hasApproved": True}
TXT = "Our revolutionary synergy boils fast for everyone."


def test_ai_findings_are_validated():
    raw = {"findings": [
        {"quote": "revolutionary synergy", "label": "Buzzwords", "category": "Language & tone", "suggestion": "simple tools", "why": "voice", "basisId": "made-up", "confidence": 0.95},
        {"quote": "NOT IN THE DRAFT", "label": "x", "category": "Language & tone", "why": "x", "confidence": 0.9},
        {"quote": "boils fast", "label": "m", "category": "Facts & claims", "why": "x", "confidence": 0.9, "severity": "warning", "basisId": "c1"},
    ]}
    out = validate_ai_findings(raw, TXT, CTX, [])
    assert len(out) == 2
    a, b = out
    assert a["needsHuman"] and a["confidence"] <= 0.6 and a["source"]["doc"].startswith("Unverified") and a["severity"] == "suggestion"
    assert TXT[a["start"]:a["end"]] == a["quote"]
    assert b["source"]["doc"] == "Acme brand profile" and b["strictness"] == "flexible"  # never mandatory


def test_ai_overlap_with_rule_finding_dropped():
    ctx = {**CTX, "terms": [{"id": "t", "avoid": "synergy", "prefer": "teamwork", "doc": "d"}]}
    existing = review(TXT, {"type": "blog"}, None, ctx)
    assert existing
    raw = {"findings": [{"quote": "synergy", "label": "x", "category": "Terminology", "why": "x", "confidence": 0.9}]}
    assert validate_ai_findings(raw, TXT, ctx, existing) == []


def test_polish_guardrails():
    m = {"type": "blog"}
    assert polish_is_safe("It boils fast.", "It boils fast, simply.", m, CTX)
    assert not polish_is_safe("It boils fast.", "It boils fast, 99% of the time.", m, CTX)
    assert not polish_is_safe("It boils fast.", "", m, CTX)


class FakeResp:
    def __init__(self, data, status=200):
        self.data, self.status_code, self.text = data, status, json.dumps(data)

    def json(self):
        return self.data


class FakeSession:
    def __init__(self, data, status=200):
        self.data, self.status, self.calls = data, status, []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append((url, headers, json))
        r = FakeResp(self.data, self.status)
        r.raise_for_status = lambda: (_ for _ in ()).throw(RuntimeError("http")) if self.status >= 400 else None
        return r


def gen(t):
    return {"candidates": [{"content": {"parts": [{"text": t}]}}]}


FIND = {"findings": [{"quote": "revolutionary synergy", "label": "B", "category": "Language & tone", "why": "w", "confidence": 0.8}]}


def test_gemini_client_request_and_failsoft():
    cfg = Config(gemini_key="k", gemini_model="m1", gemini_style="generate_content")
    fs = FakeSession(gen(json.dumps(FIND)))
    out = Gemini(cfg, fs).suggest(TXT, {"audience": "a"}, CTX, [])
    url, headers, body = fs.calls[0]
    assert url.endswith("/models/m1:generateContent") and headers["x-goog-api-key"] == "k"
    assert body["generationConfig"]["responseMimeType"] == "application/json" and len(out) == 1
    assert Gemini(cfg, FakeSession({}, 500)).suggest(TXT, {}, CTX, []) == []
    assert Gemini(cfg, FakeSession(gen("not json"))).suggest(TXT, {}, CTX, []) == []
    assert Gemini(Config(gemini_key=""), fs).suggest(TXT, {}, CTX, []) == []


def test_gemini_interactions_style_parse():
    cfg = Config(gemini_key="k", gemini_style="interactions")
    data = {"steps": [{"type": "model_output", "content": [{"type": "text", "text": json.dumps({"text": "It boils fast, simply."})}]}]}
    fs = FakeSession(data)
    assert Gemini(cfg, fs).polish("It boils fast.", {"type": "blog"}, CTX) == "It boils fast, simply."
    assert fs.calls[0][0].endswith("/interactions")


def test_ai_wired_into_review_endpoint():
    cfg = Config(sqlite_path=":memory:", gemini_key="k")
    c = create_app(cfg, ai=Gemini(cfg, FakeSession(gen(json.dumps(FIND))))).test_client()
    b = mk_brand(c)
    r = c.post("/api/review", headers=CREATOR, json={"brandId": b["id"], "productId": None, "content": TXT, "meta": {"type": "blog"}}).json
    assert r["engine"] == "rules+ai" and any(f["ruleId"] == "AI-ASSIST" for f in r["findings"])


def test_assistant_uses_ai_but_marks_drafts():
    cfg = Config(sqlite_path=":memory:", gemini_key="k")
    ai = Gemini(cfg, FakeSession(gen(json.dumps({"description": "Kettles", "approvedClaims": [{"text": "Boils fast"}]}))))
    c = create_app(cfg, ai=ai).test_client()
    d = c.post("/api/assistant/factsheet", headers=OWNER, json={"scope": "brand", "name": "B", "answers": {}, "documentText": "Boils fast."}).json
    assert d["usedAI"] and d["draft"]["approvedClaims"][0]["status"] == "draft" and "unverified" in d["draft"]["approvedClaims"][0]["source"]


class FakePostgrest:
    """In-memory PostgREST for the bg_docs table."""
    def __init__(self):
        self.rows = []

    def request(self, method, url, params=None, json=None, headers=None, timeout=None):
        p = params or {}
        assert url.endswith("/rest/v1/bg_docs")
        match = lambda r: all(r[k] == p[k][3:] for k in ("kind", "id") if k in p)  # noqa: E731
        if method == "GET":
            out = [{"data": r["data"]} for r in self.rows if match(r)]
            return FakeResp(out[:int(p["limit"])] if "limit" in p else out)
        if method == "POST":
            assert headers["Prefer"] == "resolution=merge-duplicates" and p["on_conflict"] == "kind,id"
            self.rows = [r for r in self.rows if not (r["kind"] == json["kind"] and r["id"] == json["id"])] + [json]
            return FakeResp([])
        if method == "DELETE":
            self.rows = [r for r in self.rows if not match(r)]
            return FakeResp([])


def test_supabase_store_full_flow_with_fake_http():
    fake = FakePostgrest()
    store = SupabaseStore("https://x.supabase.co", "svc", session=fake)
    c = create_app(Config(store="supabase", gemini_key=""), store=store).test_client()
    b = mk_brand(c)
    r = c.post("/api/submissions", headers=CREATOR, json={"brandId": b["id"], "productId": None, "title": "T", "content": "It is affordable.", "meta": {"type": "blog"}, "findings": []})
    assert r.status_code == 201
    assert {x["kind"] for x in fake.rows} >= {"brand", "brand_version", "submission"}
    assert c.get("/api/brands", headers=CREATOR).json["brands"][0]["id"] == b["id"]
    store.delete("submission", r.json["submission"]["id"])
    assert store.get("submission", r.json["submission"]["id"]) is None
