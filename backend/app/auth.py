"""Identity and permissions.

PROTOTYPE IDENTITY: in AUTH_MODE=demo the browser sends the identity the person typed on the welcome screen
(X-User-Id / Name / Designation / Role, URL-encoded). This is NOT secure authentication: anyone can claim any role.
AUTH_MODE=jwt requires a Supabase access token and reads the role from app_metadata.brand_role.
"""
import re
from functools import wraps
from urllib.parse import unquote

import jwt
from flask import current_app, g, jsonify, request
from werkzeug.exceptions import HTTPException

ROLES = ("creator", "reviewer", "owner")


class ApiError(Exception):
    def __init__(self, status, message, **extra):
        super().__init__(message)
        self.status, self.message, self.extra = status, message, extra


def _clean(v, lo, hi, what):
    v = re.sub(r"\s+", " ", unquote(v or "")).strip()
    if not (lo <= len(v) <= hi):
        raise ApiError(401, f"Your {what} is missing or invalid. Complete the welcome screen first.")
    return v


def current_user():
    cfg = current_app.config["CFG"]
    if cfg.auth_mode == "jwt":
        h = request.headers.get("Authorization", "")
        if not h.startswith("Bearer "):
            raise ApiError(401, "Sign in required")
        try:
            claims = jwt.decode(h[7:], cfg.jwt_secret, algorithms=["HS256"], audience="authenticated")
        except jwt.PyJWTError:
            raise ApiError(401, "Invalid or expired token")
        role = (claims.get("app_metadata") or {}).get("brand_role")
        meta = claims.get("user_metadata") or {}
        if role not in ROLES:
            raise ApiError(403, "Your account has no brand role assigned")
        return {"id": claims.get("sub"), "role": role, "name": meta.get("full_name") or meta.get("name") or claims.get("email"),
                "designation": meta.get("designation", "")}
    role = unquote(request.headers.get("X-User-Role", "")).lower()
    if role not in ROLES:
        raise ApiError(401, "Choose a role on the welcome screen first.")
    uid = unquote(request.headers.get("X-User-Id", ""))
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", uid):
        raise ApiError(401, "Your identity is missing. Complete the welcome screen first.")
    return {"id": uid, "role": role, "name": _clean(request.headers.get("X-User-Name"), 2, 80, "name"),
            "designation": (unquote(request.headers.get("X-User-Designation", "")).strip()[:80])}


def require(*roles):
    def deco(fn):
        @wraps(fn)
        def inner(*a, **kw):
            g.user = current_user()
            if roles and g.user["role"] not in roles:
                raise ApiError(403, f"The {g.user['role']} role cannot do this. Allowed: {', '.join(roles)}.")
            return fn(*a, **kw)
        return inner
    return deco


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def _api(e):
        return jsonify({"error": e.message, **e.extra}), e.status

    @app.errorhandler(Exception)
    def _any(e):
        if isinstance(e, HTTPException):
            return jsonify({"error": e.description}), e.code
        current_app.logger.exception("Unhandled error")
        return jsonify({"error": "Something went wrong on the server"}), 500
