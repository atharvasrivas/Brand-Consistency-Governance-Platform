import base64
import time
from collections import defaultdict, deque

from flask import Blueprint, Response, current_app, g, jsonify, request

from .ai.gemini import Gemini, polish_is_safe
from .auth import ApiError, require
from .engine import review as engine
from .services import assets, assistant, demo, governance, insights, suggestions, versions, visual, workflow
from .services import brands as B

bp = Blueprint("api", __name__, url_prefix="/api")
store = lambda: current_app.config["STORE"]  # noqa: E731
cfg = lambda: current_app.config["CFG"]  # noqa: E731
ai = lambda: current_app.config["AI"]  # noqa: E731


def body():
    d = request.get_json(silent=True)
    if not isinstance(d, dict):
        raise ApiError(400, "Send a JSON object")
    return d


def throttle(limit=60, window=60, bucket="default"):
    """Per-client, per-bucket sliding window. Counters live on the app, so each endpoint family has its own limit."""
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()
    q, t = current_app.config.setdefault("HITS", defaultdict(deque))[(ip, bucket)], time.monotonic()
    while q and t - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        raise ApiError(429, "Too many requests. Try again in a minute.")
    q.append(t)


def _int(name):
    try:
        return int(request.args.get(name, ""))
    except ValueError:
        raise ApiError(422, f"Give the version numbers to compare as ?from=<n>&to=<n> ('{name}' is missing or not a number)")


def with_products(b):
    return {**b, "products": B.list_products(store(), b["id"])}


def _ctx_for(d):
    ctx = B.build_context(store(), *workflow.scope_from(d))
    return ctx


@bp.get("/health")
def health():
    return jsonify({"ok": True, "store": cfg().store, "auth": cfg().auth_mode, "ai": ai().enabled, "aiLevel": ai().status()["level"]})


@bp.get("/bootstrap")
@require()
def bootstrap():
    s = store()
    return jsonify({"user": g.user, "brands": [with_products(b) for b in B.list_brands(s)], "submissions": workflow.visible(s, g.user),
                    "suggestions": suggestions.visible(s, g.user), "ai": {"enabled": ai().enabled, "level": ai().status()["level"]}, "config": {"auth": cfg().auth_mode, "store": cfg().store, "demo": cfg().demo_data}})


# ----- brands & products -----
@bp.get("/brands")
@require()
def brands():
    return jsonify({"brands": [with_products(b) for b in B.list_brands(store())]})


@bp.post("/brands")
@require("owner")
def create_brand():
    return jsonify({"brand": with_products(B.save_brand(store(), g.user, body()))}), 201


@bp.get("/brands/<bid>")
@require()
def get_brand(bid):
    return jsonify({"brand": with_products(B.get_brand(store(), bid))})


@bp.put("/brands/<bid>")
@require("owner")
def put_brand(bid):
    return jsonify({"brand": with_products(B.save_brand(store(), g.user, body(), bid))})


@bp.get("/brands/<bid>/versions")
@require()
def brand_versions(bid):
    B.get_brand(store(), bid)
    return jsonify({"versions": versions.history(store(), "brand", bid)})


@bp.get("/brands/<bid>/versions/compare")
@require()
def brand_compare(bid):
    B.get_brand(store(), bid)
    return jsonify(versions.compare(store(), "brand", bid, _int("from"), _int("to")))


@bp.get("/brands/<bid>/versions/<int:n>")
@require()
def brand_version(bid, n):
    B.get_brand(store(), bid)
    return jsonify(versions.snapshot(store(), "brand", bid, n))


@bp.post("/brands/<bid>/versions/<int:n>/restore")
@require("owner")
def brand_restore(bid, n):
    return jsonify({"brand": with_products(versions.restore(store(), g.user, "brand", bid, n, body()))}), 201


@bp.post("/brands/<bid>/products")
@require("owner")
def create_product(bid):
    return jsonify({"product": B.save_product(store(), g.user, bid, body())}), 201


@bp.put("/brands/<bid>/products/<pid>")
@require("owner")
def put_product(bid, pid):
    return jsonify({"product": B.save_product(store(), g.user, bid, body(), pid)})


@bp.get("/brands/<bid>/products/<pid>/versions")
@require()
def product_versions(bid, pid):
    B.get_product(store(), pid, bid)
    return jsonify({"versions": versions.history(store(), "product", pid)})


@bp.get("/brands/<bid>/products/<pid>/versions/compare")
@require()
def product_compare(bid, pid):
    B.get_product(store(), pid, bid)
    return jsonify(versions.compare(store(), "product", pid, _int("from"), _int("to")))


@bp.get("/brands/<bid>/products/<pid>/versions/<int:n>")
@require()
def product_version(bid, pid, n):
    B.get_product(store(), pid, bid)
    return jsonify(versions.snapshot(store(), "product", pid, n))


@bp.post("/brands/<bid>/products/<pid>/versions/<int:n>/restore")
@require("owner")
def product_restore(bid, pid, n):
    return jsonify({"product": versions.restore(store(), g.user, "product", pid, n, body(), brand_id=bid)}), 201


# ----- assets -----
@bp.post("/assets")
@require("owner")
def upload_asset():
    return jsonify(assets.upload(store(), cfg(), g.user, body())), 201


@bp.get("/assets/<aid>")
def get_asset(aid):  # ids are random and unguessable, so <img> tags can load them without headers
    mime, raw, name = assets.fetch(store(), aid)
    r = Response(raw, mimetype=mime)
    r.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
    r.headers["Cache-Control"] = "private, max-age=3600"
    r.headers["Content-Disposition"] = "inline"
    return r


# ----- fact-sheet assistant -----
@bp.get("/assistant/questions")
@require("owner")
def assistant_questions():
    return jsonify({"questions": assistant.questions(request.args.get("scope", "brand"))})


@bp.post("/assistant/factsheet")
@require("owner")
def assistant_draft():
    throttle(20, bucket="assistant")
    d = body()
    return jsonify(assistant.make_draft(ai(), d.get("scope"), B.s(d.get("name"), 100), d.get("answers"), d.get("documentText")))


# ----- suggestions -----
@bp.get("/suggestions")
@require()
def list_suggestions():
    return jsonify({"suggestions": suggestions.visible(store(), g.user)})


@bp.post("/suggestions")
@require("creator", "reviewer")
def create_suggestion():
    return jsonify({"suggestion": suggestions.create(store(), g.user, body())}), 201


@bp.post("/suggestions/<sid>/resolve")
@require("owner")
def resolve_suggestion(sid):
    return jsonify({"suggestion": suggestions.resolve(store(), g.user, sid, body())})


# ----- AI status & diagnostics -----
@bp.get("/ai/status")
@require()
def ai_status():
    """What is known without spending quota: key configured? what did the last real calls do? (No secrets.)"""
    return jsonify(ai().status())


@bp.post("/ai/diagnose")
@require("owner")
def ai_diagnose():
    """Actively verify key, service, model, text and image with real (small) requests."""
    throttle(6, bucket="diagnose")
    return jsonify(ai().diagnose())


# ----- review -----
@bp.post("/review")
@require()
def review():
    throttle()
    d = body()
    content = d.get("content")
    workflow.check_content(cfg(), content)
    meta, image = workflow.clean_meta(d), workflow.clean_image(d.get("image"), cfg().max_image_bytes)
    ctx = _ctx_for(d)
    engine_image = {k: v for k, v in image.items() if k != "data"} if image else None  # pixels are for the vision model only
    findings = engine.review(content, meta, engine_image, ctx)
    used_ai, notice, ai_notes = False, None, []
    if not ctx["hasApproved"]:
        notice = (f"{ctx['brand']['name']}{' / ' + ctx['product']['name'] if ctx['product'] else ''} has no approved facts, claims or rules yet, so no brand-specific "
                  "checks were run. Ask the Owner to add and approve them.")
    elif ai().enabled:
        extra = ai().suggest(content, meta, ctx, findings)
        if extra:
            used_ai = True
            findings = findings + extra
        err = ai().last_error("text")
        if err:
            ai_notes.append(f"AI text analysis did not run: {err}. The rule-based checks above still apply.")
    img_findings, analysis = visual.review_image(ai(), store(), image, ctx, content, meta)
    findings = sorted(findings + img_findings, key=lambda f: (-engine.SEV_RANK[f["severity"]], f.get("start", 10 ** 9)))
    if analysis and analysis.get("status") == "failed":
        ai_notes.append(analysis["reason"])
    return jsonify({"findings": findings, "context": {"brand": ctx["brand"], "product": ctx["product"]}, "notice": notice,
                    "engine": "rules+ai" if used_ai or (analysis and analysis.get("status") == "ok") else "rules",
                    "imageAnalysis": analysis, "aiNotes": ai_notes, "aiLevel": ai().status()["level"]})


@bp.post("/rewrite")
@require()
def rewrite():
    """Deterministic corrections first (exact approved wording), then - if Gemini is available - a full rewrite that has to resolve every
    remaining finding and follow the brand voice. Whatever the result, it is checked again by the rules and the outcome is reported
    honestly: `compliant` is true only if no mandatory finding is left."""
    throttle()
    d = body()
    content = d.get("content")
    workflow.check_content(cfg(), content)
    meta, ctx = workflow.clean_meta(d), _ctx_for(d)
    dismissed = {k for k in (d.get("dismissed") or []) if isinstance(k, str)}
    res = engine.rewrite(content, meta, ctx, dismissed)
    res.update(polished=False, aiChanges=[], aiNotice=None, notice=None)
    if not ctx["hasApproved"]:
        res["notice"] = "This brand has no approved facts or rules yet, so there is nothing to rewrite against."
    elif not ai().enabled:
        res["aiNotice"] = ("Only the exact corrections from approved facts and wording were applied. Tone, marketing language and unsupported claims need the "
                           "Gemini AI service, which is not configured on the server.") if res["remaining"] else None
    else:
        out = ai().rewrite(res["text"], meta, ctx, res["remaining"])
        if out and out["text"].strip() and out["text"] != res["text"]:
            if polish_is_safe(res["text"], out["text"], meta, ctx):
                res.update(text=out["text"], polished=True, aiChanges=out["changes"], **engine.recheck(out["text"], meta, ctx, dismissed))
            else:
                res["aiNotice"] = "An AI rewrite was produced but discarded: it added figures or claims that are not approved, or introduced new rule violations."
        elif not out:
            res["aiNotice"] = f"The AI rewrite did not run: {ai().last_error('rewrite') or 'no result'}. Only the exact corrections were applied."
    # never "compliant" while a mandatory finding is left; "unchanged" only when there was nothing to correct
    res["status"] = "needs_attention" if not res["compliant"] else "unchanged" if res["text"] == content else "compliant"
    return jsonify(res)


# ----- submissions -----
@bp.get("/submissions")
@require()
def list_submissions():
    return jsonify({"submissions": workflow.visible(store(), g.user)})


@bp.get("/submissions/<sid>")
@require()
def get_submission(sid):
    return jsonify({"submission": workflow.get(store(), g.user, sid)})


@bp.post("/submissions")
@require()
def create_submission():
    return jsonify({"submission": workflow.create(store(), cfg(), g.user, body())}), 201


@bp.post("/submissions/<sid>/versions")
@require()
def new_version(sid):
    return jsonify({"submission": workflow.resubmit(store(), cfg(), g.user, sid, body())})


@bp.post("/submissions/<sid>/submit")
@require()
def submit_draft(sid):
    return jsonify({"submission": workflow.submit_draft(store(), cfg(), g.user, sid, body())})


@bp.post("/submissions/<sid>/start-review")
@require()
def start_review(sid):
    return jsonify({"submission": workflow.start_review(store(), g.user, sid)})


@bp.post("/submissions/<sid>/decision")
@require()
def decision(sid):
    return jsonify({"submission": workflow.decide(store(), g.user, sid, body())})


@bp.post("/submissions/<sid>/comments")
@require()
def comment(sid):
    return jsonify({"submission": workflow.comment(store(), g.user, sid, body())}), 201


@bp.post("/submissions/<sid>/recheck")
@require()
def recheck(sid):
    return jsonify({"submission": workflow.recheck(store(), g.user, sid)})


# ----- governance tools (drift, change impact, guideline conflicts) -----
@bp.get("/governance/drift")
@require("reviewer", "owner")
def gov_drift():
    return jsonify(governance.drift(store().list("submission"), request.args.get("brandId"), request.args.get("productId")))


@bp.get("/governance/impact")
@require("reviewer", "owner")
def gov_impact():
    return jsonify(governance.impact(store(), request.args.get("brandId"), governance.impact_decisions(store())))


@bp.get("/governance/impact/history")
@require("reviewer", "owner")
def gov_impact_history():
    return jsonify({"history": governance.impact_history(store(), request.args.get("key"))})


@bp.post("/governance/impact/decision")
@require("reviewer", "owner")
def gov_impact_decide():
    return jsonify({"decision": governance.decide_impact(store(), g.user, body())}), 201


@bp.get("/governance/conflicts")
@require("reviewer", "owner")
def gov_conflicts():
    return jsonify(governance.conflicts(store(), request.args.get("brandId"), governance.conflict_decisions(store())))


@bp.post("/governance/conflicts/resolve")
@require("owner")
def gov_conflict_resolve():
    return jsonify({"decision": governance.resolve_conflict(store(), g.user, body())}), 201


# ----- insights & demo -----
@bp.get("/insights")
@require("reviewer", "owner")
def get_insights():
    return jsonify(insights.compute(store().list("submission"), request.args.get("brandId"), request.args.get("productId")))


@bp.post("/demo/load")
@require("owner")
def load_demo():
    if not cfg().demo_data:
        raise ApiError(403, "Demo data is disabled")
    return jsonify({"brand": with_products(demo.load(store(), g.user))}), 201
