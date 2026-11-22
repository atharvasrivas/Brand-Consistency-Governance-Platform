"""Round 3: technical-spec contradictions, honest rewrite, Gemini diagnostics and the image-analysis path (mocked HTTP only)."""
import base64
import json

import requests

from app import create_app
from app.ai.gemini import Gemini, _red_png
from app.config import Config
from tests.conftest import CREATOR, OWNER, REV, mk_brand, mk_product

SP3 = ("The Ferrari Daytona SP3 features a hybrid powertrain with a twin-turbocharged V8 engine producing 700 horsepower. "
       "It sprints from 0–100 km/h in 3.5 seconds, with unlimited production for everyone.")
META = {"type": "ad", "audience": "collectors"}
PNG_B64 = base64.b64encode(_red_png()).decode()


def ferrari(c, **brand_kw):
    b = mk_brand(c, "Ferrari", terminology=[], restrictedClaims=[], approvedClaims=[{"text": "Limited production of 599 examples", "source": "Fact sheet"}], **brand_kw)
    p = mk_product(c, b["id"], "Daytona SP3", previousNames=[], specs=[
        {"name": "Engine", "value": "Naturally aspirated 6.5-litre V12", "source": "Fact sheet"}, {"name": "Power", "value": "840 cv", "source": "Fact sheet"},
        {"name": "0-100 km/h", "value": "2.85 seconds", "source": "Fact sheet"}, {"name": "Production", "value": "Limited to 599 examples", "source": "Fact sheet"}])
    return b, p


def review(c, b, p, text, headers=CREATOR, **extra):
    return c.post("/api/review", headers=headers, json={"brandId": b["id"], "productId": p["id"] if p else None, "content": text, "meta": META, **extra})


# ------------------------------------------------------------------ spec contradictions
def test_daytona_sp3_every_technical_contradiction_is_found_with_the_approved_fact(client):
    b, p = ferrari(client)
    fs = review(client, b, p, SP3).json["findings"]
    got = {f["quote"]: f for f in fs if f["ruleId"] in ("SPEC-CONTRADICTION", "SPEC-MISMATCH")}
    assert set(got) == {"hybrid powertrain", "twin-turbocharged", "V8", "700 horsepower", "3.5 seconds", "unlimited production"}
    assert all(f["severity"] == "critical" and f["strictness"] == "mandatory" and not f["needsHuman"] for f in got.values())
    assert got["700 horsepower"]["approvedFact"]["value"] == "840 cv" and got["700 horsepower"]["suggestion"] == "840 cv"
    assert got["3.5 seconds"]["suggestion"] == "2.85 seconds" and "2.85" in got["3.5 seconds"]["why"]
    assert got["V8"]["suggestion"] == "V12" and got["twin-turbocharged"]["suggestion"] == "naturally aspirated"
    assert "599" in got["unlimited production"]["suggestion"]
    assert all(f["source"]["doc"] == "Daytona SP3 fact sheet" for f in got.values())


def test_specs_are_only_contradicted_when_the_fact_sheet_states_them(client):
    b = mk_brand(client, "Plain", terminology=[], restrictedClaims=[])
    p = mk_product(client, b["id"], "Gadget", previousNames=[], specs=[{"name": "Colour", "value": "Black", "source": "s"}])
    fs = review(client, b, p, "A hybrid V8 with 700 horsepower in 3.5 seconds, unlimited production.").json["findings"]
    assert not [f for f in fs if f["ruleId"] in ("SPEC-CONTRADICTION", "SPEC-MISMATCH")]


def test_equivalent_units_and_correct_figures_are_not_flagged(client):
    b, p = ferrari(client)
    ok = "A naturally aspirated V12 of 828 hp (618 kW), 0-100 km/h in 2.85 s, limited to 599 examples."
    assert not [f for f in review(client, b, p, ok).json["findings"] if f["ruleId"].startswith("SPEC-")]


def test_unsupported_technical_figure_goes_to_a_person_without_an_invented_source(client):
    b, p = ferrari(client)
    f = [x for x in review(client, b, p, "It develops 780 Nm of torque.").json["findings"] if x["ruleId"] == "SPEC-UNSUPPORTED"]
    assert f and f[0]["needsHuman"] and f[0]["source"]["ref"] == "No matching approved figure" and "approvedFact" not in f[0]


def test_rule_rewrite_fixes_specs_and_rechecks_itself(client):
    b, p = ferrari(client)
    r = client.post("/api/rewrite", headers=CREATOR, json={"brandId": b["id"], "productId": p["id"], "content": SP3, "meta": META}).json
    for wrong in ("hybrid", "V8", "700", "3.5 seconds", "unlimited"):
        assert wrong not in r["text"]
    assert "840 cv" in r["text"] and "2.85 seconds" in r["text"] and "599" in r["text"] and "V12" in r["text"]
    assert r["compliant"] is True and r["recheck"]["mandatory"] == 0 and r["status"] == "compliant"
    again = review(client, b, p, r["text"]).json["findings"]
    assert not [f for f in again if f["ruleId"].startswith("SPEC-")]


def test_rewrite_never_claims_compliance_while_a_mandatory_finding_remains(client):
    b, p = ferrari(client)
    r = client.post("/api/rewrite", headers=CREATOR, json={"brandId": b["id"], "productId": p["id"], "meta": META,
                                                           "content": "Daytona SP3 is the fastest car in the world, guaranteed."}).json
    assert r["compliant"] is False and r["status"] == "needs_attention" and r["recheck"]["mandatory"] >= 2
    assert {f["ruleId"] for f in r["remaining"]} >= {"CLAIM-UNVERIFIED"} and "not configured" in r["aiNotice"]


# ------------------------------------------------------------------ fake Gemini transport
class Net:
    """Routes by capability. handlers: fn(url, body) -> (status, data)."""
    def __init__(self, text=None, image=None, rewrite=None, get=None, fail=None):
        self.text, self.image, self.rewrite_, self.get_, self.fail, self.calls = text, image, rewrite, get, fail, []

    def _gen(self, obj):
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(obj)}]}, "finishReason": "STOP"}]}

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "body": json, "timeout": timeout})
        if self.fail:
            status, data = self.fail
        else:
            parts = json["contents"][0]["parts"]
            has_img = any("inlineData" in x for x in parts)
            sys_text = json["systemInstruction"]["parts"][0]["text"]
            if has_img:
                status, data = 200, self._gen(self.image(parts) if callable(self.image) else self.image)
            elif sys_text.startswith("You are a brand copy editor"):
                status, data = 200, self._gen(self.rewrite_ or {"text": "x"})
            else:
                status, data = 200, self._gen(self.text or {"findings": []})
        return _Resp(status, data)

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "body": None, "timeout": timeout})
        return _Resp(*(self.get_ or (200, {"supportedGenerationMethods": ["generateContent"]})))


class _Resp:
    def __init__(self, status, data):
        self.status_code, self.data, self.text = status, data, ""

    def json(self):
        return self.data


def app_with(net, **cfg):
    c = Config(sqlite_path=":memory:", gemini_key="SECRET-KEY", gemini_backoff=0, **cfg)
    return create_app(c, ai=Gemini(c, net)).test_client()


def branded(c):
    up = c.post("/api/assets", headers=OWNER, json={"name": "logo.png", "mime": "image/png", "data": PNG_B64, "kind": "logo"}).json
    b = mk_brand(c, "Ferrari", terminology=[], restrictedClaims=[], approvedClaims=[{"text": "Limited production of 599 examples"}], fonts=["Ferrari Sans"],
                 colours=[{"name": "Rosso Corsa", "hex": "#D40000", "role": "primary"}], logoAssetId=up["assetId"],
                 assets=[{"assetId": up["assetId"], "name": "logo.png", "kind": "logo", "mime": "image/png", "size": 100}],
                 guidelines=[{"text": "Never place the logo on a busy background."}])
    return b


IMG = {"name": "ad.png", "alt": "A red car", "data": PNG_B64, "mime": "image/png"}


def img_result(basis):
    return {"summary": "A yellow car on a busy background.", "matchesBrand": "no",
            "detected": {"subject": "car", "logoPresent": True, "dominantColours": ["yellow"], "fonts": ["Comic Sans"], "textInImage": "Daytona SP3 with 700 horsepower"},
            "findings": [{"aspect": "colour", "issue": "Dominant yellow instead of Rosso Corsa", "why": "Brand red is the primary colour", "change": "Re-grade to Rosso Corsa #D40000",
                          "basisId": basis, "severity": "warning", "confidence": 0.9},
                         {"aspect": "style", "issue": "Looks like a discount flyer", "why": "off brand", "change": "Use a calmer layout", "basisId": "made-up", "severity": "warning", "confidence": 0.95}],
            "concept": {"headline": "Rosso-led hero", "steps": ["Re-grade to Rosso Corsa", "Move logo to a plain area"]}}


# ------------------------------------------------------------------ image analysis
def test_image_is_sent_to_the_vision_model_with_brand_visuals_and_reference_logo(client):
    c0 = app_with(Net())
    b = branded(c0)
    colour_id = c0.get(f"/api/brands/{b['id']}", headers=OWNER).json["brand"]["colours"][0]["id"]
    net = Net(image=lambda parts: img_result(colour_id))
    c = app_with(net)
    b = branded(c)
    colour_id = c.get(f"/api/brands/{b['id']}", headers=OWNER).json["brand"]["colours"][0]["id"]
    net.image = lambda parts: img_result(colour_id)
    r = review(c, b, None, "Ferrari. Drive the Daytona SP3.", image=IMG).json
    sent = [x for x in net.calls if x["body"] and any("inlineData" in p for p in x["body"]["contents"][0]["parts"])][0]
    parts = sent["body"]["contents"][0]["parts"]
    assert sent["url"].endswith(":generateContent") and sent["timeout"] >= 30
    inl = [p["inlineData"] for p in parts if "inlineData" in p]
    assert len(inl) == 2 and all(i["mimeType"] == "image/png" and i["data"] == PNG_B64 for i in inl)  # approved logo reference + uploaded image
    labels = [p["text"] for p in parts if "text" in p]
    assert any("APPROVED REFERENCE: approved logo" in t for t in labels) and any("UPLOADED IMAGE TO ASSESS" in t for t in labels)
    ctx = json.loads(parts[0]["text"])["context"]
    assert ctx["colours"][0]["hex"] == "#D40000" and ctx["fonts"][0]["name"] == "Ferrari Sans" and ctx["visualGuidelines"]
    a = r["imageAnalysis"]
    assert a["status"] == "ok" and a["matchesBrand"] == "no" and a["concept"]["steps"] and a["references"]
    fs = {f["key"]: f for f in r["findings"] if f["ruleId"] == "IMG-AI"}
    assert len(fs) == 2 and all(f["strictness"] == "flexible" and f["needsHuman"] and f["scope"] == "image" for f in fs.values())
    cited = [f for f in fs.values() if f["source"]["ref"].startswith("Colour Rosso Corsa")]
    unverified = [f for f in fs.values() if f["source"]["doc"].startswith("Unverified")]
    assert len(cited) == 1 and len(unverified) == 1 and unverified[0]["severity"] == "suggestion" and unverified[0]["confidence"] <= 0.6
    assert "SECRET-KEY" not in json.dumps(r)


def test_text_read_from_the_image_is_checked_against_the_product_facts(client):
    net = Net(image=lambda parts: img_result("x"))
    c = app_with(net)
    b = branded(c)
    p = mk_product(c, b["id"], "Daytona SP3", previousNames=[], specs=[{"name": "Power", "value": "840 cv", "source": "Fact sheet"}])
    fs = review(c, b, p, "Daytona SP3.", image=IMG).json["findings"]
    hit = [f for f in fs if f["scope"] == "image" and f["ruleId"] == "SPEC-MISMATCH"]
    assert hit and "read from the image" in hit[0]["label"] and hit[0]["quote"] == "700 horsepower"


def test_image_is_never_silently_accepted(client):
    # no key at all
    b = mk_brand(client, "Plain")
    r = review(client, b, None, "Hello there.", image=IMG).json
    f = [x for x in r["findings"] if x["ruleId"] == "IMG-UNANALYSED"]
    assert f and f[0]["needsHuman"] and "not configured" in f[0]["why"] and r["imageAnalysis"]["status"] == "unavailable"
    # key set but no visual identity defined
    c = app_with(Net())
    r = review(c, mk_brand(c, "Bare"), None, "Hello there.", image=IMG).json
    assert r["imageAnalysis"]["status"] == "no_identity" and any(x["ruleId"] == "IMG-UNANALYSED" for x in r["findings"])
    # unsupported type and pixels not sent
    r = review(c, mk_brand(c, "Bare2"), None, "Hello there.", image={"name": "a.svg", "data": PNG_B64, "mime": "image/svg+xml"}).json
    assert r["imageAnalysis"]["status"] == "unsupported"
    r = review(c, mk_brand(c, "Bare3"), None, "Hello there.", image={"name": "a.png"}).json
    assert r["imageAnalysis"]["status"] == "not_sent"


def test_vision_failure_is_reported_with_the_real_reason(client):
    c = app_with(Net(fail=(429, {"error": {"message": "Quota exceeded for SECRET-KEY"}})))
    b = branded(c)
    r = review(c, b, None, "Ferrari.", image=IMG).json
    assert r["imageAnalysis"]["status"] == "failed" and "quota" in r["imageAnalysis"]["reason"].lower()
    assert any(f["ruleId"] == "IMG-UNANALYSED" for f in r["findings"]) and r["aiNotes"]
    assert "SECRET-KEY" not in json.dumps(r) and "SECRET-KEY" not in json.dumps(c.get("/api/ai/status", headers=CREATOR).json)


def test_image_validation_and_persistence(client):
    b = mk_brand(client, "Plain")
    big = base64.b64encode(b"0" * 1_500_000).decode()
    assert review(client, b, None, "Hi.", image={"name": "x.png", "data": big, "mime": "image/png"}).status_code == 413
    assert review(client, b, None, "Hi.", image={"name": "x.png", "data": "!!!", "mime": "image/png"}).status_code == 422
    r = client.post("/api/submissions", headers=CREATOR, json={"brandId": b["id"], "productId": None, "title": "T", "content": "A calm hello.", "meta": META,
                                                               "image": {**IMG, "alt": "red"}, "findings": []})
    assert r.status_code == 201
    img = r.json["submission"]["image"]
    assert "data" not in img and img["assetId"] and img["mime"] == "image/png"
    g = client.get(f"/api/assets/{img['assetId']}")
    assert g.status_code == 200 and g.mimetype == "image/png"


def test_forged_advisory_image_findings_cannot_block_or_be_mandatory(client):
    b = mk_brand(client, "Plain")
    forged = [{"key": "IMG-AI|x|y", "ruleId": "IMG-AI", "label": "x", "category": "Visual identity", "severity": "critical", "strictness": "mandatory", "quote": "q", "needsHuman": False}]
    r = client.post("/api/submissions", headers=CREATOR, json={"brandId": b["id"], "productId": None, "title": "T", "content": "A calm hello.", "meta": META, "findings": forged})
    f = r.json["submission"]["findings"][0]
    assert r.status_code == 201 and f["strictness"] == "flexible" and f["needsHuman"] is True


# ------------------------------------------------------------------ rewrite with AI
def test_ai_rewrite_resolves_remaining_findings_and_is_rechecked(client):
    net = Net(rewrite={"text": "Daytona SP3 is a remarkable car.", "changes": ["Removed the unsupported superlative"]})
    c = app_with(net)
    b, p = ferrari(c)
    r = c.post("/api/rewrite", headers=CREATOR, json={"brandId": b["id"], "productId": p["id"], "meta": META, "content": "Daytona SP3 is the fastest car in the world, guaranteed."}).json
    assert r["polished"] and r["compliant"] and r["status"] == "compliant" and r["aiChanges"] and r["recheck"]["mandatory"] == 0
    sent = [x for x in net.calls if x["body"] and x["body"]["systemInstruction"]["parts"][0]["text"].startswith("You are a brand copy editor")][0]
    payload = json.loads(sent["body"]["contents"][0]["parts"][0]["text"])
    assert {i["problem"] for i in payload["issues"]} >= {"Unsupported superlative", "Unsupported guarantee"} and payload["context"]["specs"]


def test_ai_rewrite_that_invents_numbers_or_keeps_violations_is_discarded(client):
    for bad in ("Daytona SP3 reaches 400 km/h.", "Daytona SP3 is the fastest car in the world, guaranteed, with unlimited production."):
        c = app_with(Net(rewrite={"text": bad}))
        b, p = ferrari(c)
        r = c.post("/api/rewrite", headers=CREATOR, json={"brandId": b["id"], "productId": p["id"], "meta": META, "content": "Daytona SP3 is the fastest car in the world, guaranteed."}).json
        assert not r["polished"] and r["compliant"] is False and "discarded" in r["aiNotice"] and "400" not in r["text"]


# ------------------------------------------------------------------ status & diagnostics
def test_status_levels_and_error_classification():
    def level(net, calls=None):
        c = app_with(net)
        b = mk_brand(c, "Plain", terminology=[{"avoid": "cheap", "prefer": "affordable"}])
        review(c, b, None, "A cheap kettle.")
        return c.get("/api/ai/status", headers=CREATOR).json
    off = create_app(Config(sqlite_path=":memory:", gemini_key="")).test_client().get("/api/ai/status", headers=CREATOR).json
    assert off["level"] == "off" and off["configured"] is False
    ok = level(Net(text={"findings": []}))
    assert ok["level"] == "text" and ok["capabilities"]["text"]["ok"] is True and ok["capabilities"]["text"]["status"] is None
    for status, kind in ((401, "auth"), (404, "model"), (429, "quota"), (503, "server"), (400, "bad_request")):
        s = level(Net(fail=(status, {"error": {"message": "nope"}})))
        assert s["level"] == "failing" and s["capabilities"]["text"]["kind"] == kind and s["capabilities"]["text"]["status"] == status, (status, s)
    assert level(Net(text="not json at all")) is not None


def test_gemini_empty_blocked_and_timeout_are_distinguished():
    cfg = Config(gemini_key="k", gemini_backoff=0)

    class Odd:
        def __init__(self, data=None, exc=None):
            self.data, self.exc = data, exc

        def post(self, *a, **k):
            if self.exc:
                raise self.exc
            return _Resp(200, self.data)
    for data, exc, kind in (({"promptFeedback": {"blockReason": "SAFETY"}}, None, "blocked"), ({"candidates": []}, None, "empty"),
                            ({"candidates": [{"content": {"parts": [{"text": " "}]}, "finishReason": "MAX_TOKENS"}]}, None, "empty"),
                            (None, requests.Timeout(), "timeout"), (None, requests.ConnectionError(), "unreachable")):
        g = Gemini(cfg, Odd(data, exc))
        assert g.suggest("some draft text", {}, {"claims": [], "specs": [], "restricted": [], "terms": [], "brandName": "B", "productName": None, "voice": {}}, []) == []
        assert g.last["text"]["kind"] == kind and g.last["text"]["ok"] is False


def test_gemini_retries_only_rate_limits_once():
    cfg = Config(gemini_key="k", gemini_backoff=0)
    net = Net(fail=(429, {}))
    Gemini(cfg, net).suggest("x y z", {}, {"claims": [], "specs": [], "restricted": [], "terms": [], "brandName": "B", "productName": None, "voice": {}}, [])
    assert len([c for c in net.calls if c.get('body') is not None]) == 2
    net = Net(fail=(500, {}))
    Gemini(cfg, net).suggest("x y z", {}, {"claims": [], "specs": [], "restricted": [], "terms": [], "brandName": "B", "productName": None, "voice": {}}, [])
    assert len([c for c in net.calls if c.get("body") is not None]) == 1


def test_diagnose_verifies_each_layer_for_real(client):
    net = Net(text={"findings": [{"quote": "cheap", "label": "w", "category": "Terminology", "why": "x", "confidence": 0.9}]}, image={"dominantColour": "Bright red"})
    c = app_with(net)
    assert c.post("/api/ai/diagnose", headers=CREATOR).status_code == 403
    d = c.post("/api/ai/diagnose", headers=OWNER).json
    assert d["overall"] == "full" and [s["id"] for s in d["stages"]] == ["key", "reachable", "model", "plain", "text", "image"] and all(s["ok"] for s in d["stages"])
    assert any(x["url"].endswith("/models/gemini-3.8-flash") and x["headers"]["x-goog-api-key"] == "SECRET-KEY" for x in net.calls if x["body"] is None)
    sent_img = [x for x in net.calls if x["body"] and any("inlineData" in p for p in x["body"]["contents"][0]["parts"])][0]
    assert base64.b64decode(sent_img["body"]["contents"][0]["parts"][2]["inlineData"]["data"]).startswith(b"\x89PNG")
    assert c.get("/api/ai/status", headers=CREATOR).json["level"] == "full" and "SECRET-KEY" not in json.dumps(d)


def test_diagnose_catches_a_model_that_ignores_the_image_and_a_missing_model():
    c = app_with(Net(text={"findings": []}, image={"dominantColour": "I cannot see an image"}))
    d = c.post("/api/ai/diagnose", headers=OWNER).json
    by = {s["id"]: s for s in d["stages"]}
    assert d["overall"] == "text" and by["text"]["ok"] and by["image"]["ok"] is False and "not reading the pixels" in by["image"]["detail"]
    c = app_with(Net(get=(404, {"error": {"message": "models/x is not found"}}), fail=(404, {"error": {"message": "models/x is not found"}})))
    d = c.post("/api/ai/diagnose", headers=OWNER).json
    by = {s["id"]: s for s in d["stages"]}
    assert d["overall"] == "failing" and by["model"]["ok"] is False and "not found" in by["model"]["detail"].lower()
    off = create_app(Config(sqlite_path=":memory:", gemini_key="")).test_client().post("/api/ai/diagnose", headers=OWNER).json
    assert off["overall"] == "off" and off["stages"][0]["ok"] is False


def test_text_review_uses_richer_context_for_the_model():
    net = Net(text={"findings": []})
    c = app_with(net)
    b, p = ferrari(c)
    review(c, b, p, "Daytona SP3 is thrilling.", headers=REV)
    sent = [x for x in net.calls if x["body"]][0]
    ctx = json.loads(sent["body"]["contents"][0]["parts"][0]["text"])["context"]
    assert any(s["name"] == "Engine" for s in ctx["specs"]) and "system" not in sent["body"]
    assert "specification" in sent["body"]["systemInstruction"]["parts"][0]["text"].lower()


def test_unavailable_model_switches_to_one_the_key_can_use():
    class N(Net):
        def post(self, url, headers=None, json=None, timeout=None):
            if "gemini-2.5-flash:" in url:
                self.calls.append({"url": url})
                return _Resp(404, {"error": {"message": "models/gemini-2.5-flash is no longer available to new users"}})
            return super().post(url, headers, json, timeout)

        def get(self, url, headers=None, timeout=None):
            self.calls.append({"url": url})
            return _Resp(200, {"models": [
                {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-3.0-flash-lite", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-3.0-flash", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-3.5-flash-preview-05", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/text-embedding-9", "supportedGenerationMethods": ["embedContent"]}]})
    net = N(text={"findings": []})
    ai = Gemini(Config(sqlite_path=":memory:", gemini_key="SECRET-KEY", gemini_backoff=0, gemini_model="gemini-2.5-flash"), net)
    ai._json("suggest", "sys", "prompt", {"type": "object", "properties": {"findings": {"type": "array", "items": {"type": "string"}}}})
    assert ai.model == "gemini-3.0-flash"
    assert ai.last["suggest"]["ok"] is True and "SECRET-KEY" not in str(ai.status())


def test_gemini_3_request_has_room_to_think_and_no_forced_temperature():
    net = Net(text={"findings": []})
    ai = Gemini(Config(sqlite_path=":memory:", gemini_key="SECRET-KEY", gemini_backoff=0, gemini_model="gemini-3.8-flash"), net)
    ai._json("suggest", "sys", "prompt", {"type": "object", "properties": {}})
    cfg = net.calls[-1]["body"]["generationConfig"]
    assert "temperature" not in cfg and cfg["maxOutputTokens"] >= 4096 and net.calls[-1]["url"].endswith("gemini-3.8-flash:generateContent")


def test_overloaded_model_is_answered_by_another_model():
    class N(Net):
        def post(self, url, headers=None, json=None, timeout=None):
            if "gemini-3.8-flash:" in url:
                self.calls.append({"url": url, "body": json})
                return _Resp(503, {"error": {"message": "This model is currently experiencing high demand."}})
            return super().post(url, headers, json, timeout)

        def get(self, url, headers=None, timeout=None):
            self.calls.append({"url": url, "body": None})
            return _Resp(200, {"models": [
                {"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-3.8-flash-lite", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-3.1-flash", "supportedGenerationMethods": ["generateContent"]}]})
    net = N(text={"findings": []})
    ai = Gemini(Config(sqlite_path=":memory:", gemini_key="SECRET-KEY", gemini_backoff=0, gemini_model="gemini-3.8-flash"), net)
    out = ai._json("suggest", "sys", "prompt", {"type": "object", "properties": {"findings": {"type": "array", "items": {"type": "string"}}}})
    assert out == {"findings": []} and ai.answered_by == "gemini-3.1-flash" and ai.model == "gemini-3.8-flash"


def test_fallback_provider_answers_when_gemini_is_down():
    from app.ai.gemini import Gemini
    from app.config import Config

    class R:
        def __init__(self, code, data): self.status_code, self._d = code, data
        def json(self): return self._d

    class S:
        def post(self, url, **kw):
            if "generativelanguage" in url:
                return R(503, {"error": {"message": "high demand", "status": "UNAVAILABLE"}})
            return R(200, {"choices": [{"message": {"content": '{"ok": true}'}}]})

    g = Gemini(Config(sqlite_path=":memory:", gemini_key="k", fallback_key="f", store="sqlite", gemini_retries=0), session=S())
    g._alternates = lambda *a, **k: []
    assert g._json("text", "sys", "p", {"type": "object"}) == {"ok": True}
    assert g.answered_by == g.fb_model
