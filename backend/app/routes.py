import base64
import time
from collections import defaultdict, deque

from flask import Blueprint, Response, current_app, g, jsonify, request

from .ai.gemini import Gemini
from .auth import ApiError, require
from .engine import review as engine
from .services import assets, assistant, demo, governance, insights, suggestions, workflow
from .services import brands as B

bp = Blueprint("api", __name__, url_prefix="/api")
_hits = defaultdict(deque)
store = lambda: current_app.config["STORE"]  # noqa: E731
cfg = lambda: current_app.config["CFG"]  # noqa: E731
ai = lambda: current_app.config["AI"]  # noqa: E731


def body():
    d = request.get_json(silent=True)
    if not isinstance(d, dict):
        raise ApiError(400, "Send a JSON object")
    return d


def throttle(limit=60, window=60):
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()
    q, t = _hits[ip], time.monotonic()
    while q and t - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        raise ApiError(429, "Too many requests. Try again in a minute.")
    q.append(t)


def with_products(b):
    return {**b, "products": B.list_products(store(), b["id"])}


def _ctx_for(d):
    ctx = B.build_context(store(), *workflow.scope_from(d))
    return ctx


@bp.get("/health")
def health():
    return jsonify({"ok": True, "store": cfg().store, "auth": cfg().auth_mode, "ai": ai().enabled})


@bp.get("/bootstrap")
@require()
def bootstrap():
    s = store()
    return jsonify({"user": g.user, "brands": [with_products(b) for b in B.list_brands(s)], "submissions": workflow.visible(s, g.user),
                    "suggestions": suggestions.visible(s, g.user), "ai": {"enabled": ai().enabled}, "config": {"auth": cfg().auth_mode, "store": cfg().store, "demo": cfg().demo_data}})


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
    return jsonify({"versions": [{k: v[k] for k in ("version", "updatedAt", "updatedBy", "changeNote")} for v in B.versions(store(), "brand", bid)]})


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
    return jsonify({"versions": [{k: v[k] for k in ("version", "updatedAt", "updatedBy", "changeNote")} for v in B.versions(store(), "product", pid)]})


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
    throttle(20)
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


# ----- review -----
@bp.post("/review")
@require()
def review():
    throttle()
    d = body()
    content = d.get("content")
    workflow.check_content(cfg(), content)
    meta, image = workflow.clean_meta(d), workflow.clean_image(d.get("image"))
    ctx = _ctx_for(d)
    findings = engine.review(content, meta, image, ctx)
    used_ai, notice = False, None
    if not ctx["hasApproved"]:
        notice = (f"{ctx['brand']['name']}{' / ' + ctx['product']['name'] if ctx['product'] else ''} has no approved facts, claims or rules yet, so no brand-specific "
                  "checks were run. Ask the Owner to add and approve them.")
    elif ai().enabled:
        extra = ai().suggest(content, meta, ctx, findings)
        if extra:
            used_ai = True
            findings = sorted(findings + extra, key=lambda f: (-engine.SEV_RANK[f["severity"]], f.get("start", 10 ** 9)))
    return jsonify({"findings": findings, "context": {"brand": ctx["brand"], "product": ctx["product"]}, "notice": notice,
                    "engine": "rules+ai" if used_ai else "rules"})


@bp.post("/rewrite")
@require()
def rewrite():
    throttle()
    d = body()
    content = d.get("content")
    workflow.check_content(cfg(), content)
    meta, ctx = workflow.clean_meta(d), _ctx_for(d)
    res = engine.rewrite(content, meta, ctx, {k for k in (d.get("dismissed") or []) if isinstance(k, str)})
    res["polished"] = False
    if ai().enabled and ctx["hasApproved"]:
        better = ai().polish(res["text"], meta, ctx)
        if better and better != res["text"]:
            res["text"], res["polished"] = better, True
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
    return jsonify(governance.drift(store().list("submission"), request.args.get("brandId")))


@bp.get("/governance/impact")
@require("reviewer", "owner")
def gov_impact():
    return jsonify(governance.impact(store(), request.args.get("brandId"), governance.impact_decisions(store())))


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
