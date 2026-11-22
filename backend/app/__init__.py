from flask import Flask, request

from .ai.gemini import Gemini
from .auth import register_error_handlers
from .config import Config
from .routes import bp
from .store.sqlite_store import SQLiteStore


def build_store(cfg):
    if cfg.store == "supabase":
        from .store.supabase_store import SupabaseStore
        if not (cfg.supabase_url and cfg.supabase_key):
            raise RuntimeError("STORE=supabase needs SUPABASE_URL and SUPABASE_SERVICE_KEY")
        return SupabaseStore(cfg.supabase_url, cfg.supabase_key)
    return SQLiteStore(cfg.sqlite_path)


def create_app(cfg=None, store=None, ai=None):
    app = Flask(__name__)
    cfg = cfg or Config()
    if cfg.auth_mode == "jwt" and not cfg.jwt_secret:
        raise RuntimeError("AUTH_MODE=jwt needs SUPABASE_JWT_SECRET")
    app.config.update(CFG=cfg, MAX_CONTENT_LENGTH=3_200_000, STORE=store or build_store(cfg), AI=ai or Gemini(cfg))
    register_error_handlers(app)
    app.register_blueprint(bp)

    @app.after_request
    def cors(resp):
        origin, allowed = request.headers.get("Origin"), cfg.allowed_origins
        if origin and ("*" in allowed or origin in allowed):
            resp.headers["Access-Control-Allow-Origin"] = "*" if "*" in allowed else origin
            resp.headers["Vary"] = "Origin"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-User-Id, X-User-Role, X-User-Name, X-User-Designation"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, OPTIONS"
            resp.headers["Access-Control-Max-Age"] = "600"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    @app.route("/api/<path:_>", methods=["OPTIONS"])
    def preflight(_):
        return "", 204

    @app.get("/favicon.ico")
    def favicon():
        return "", 204

    @app.get("/")
    def root():
        return {"service": "Brand Consistency and Governance Platform API", "health": "/api/health"}

    return app
