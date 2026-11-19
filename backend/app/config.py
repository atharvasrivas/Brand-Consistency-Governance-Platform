import os

from dotenv import load_dotenv

load_dotenv()


def _b(name, default="0"):
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


class Config:
    """Read from the environment on construction so tests can override with env vars."""

    def __init__(self, **over):
        e = os.getenv
        self.auth_mode = e("AUTH_MODE", "demo").lower()
        self.jwt_secret = e("SUPABASE_JWT_SECRET", "")
        self.store = e("STORE", "sqlite").lower()
        self.sqlite_path = e("SQLITE_PATH", "brandgov.db")
        self.supabase_url = e("SUPABASE_URL", "").rstrip("/")
        self.supabase_key = e("SUPABASE_SERVICE_KEY", "")
        self.gemini_key = e("GEMINI_API_KEY", "")
        self.gemini_model = e("GEMINI_MODEL", "gemini-2.5-flash")
        self.gemini_style = e("GEMINI_API_STYLE", "generate_content").lower()
        self.gemini_timeout = float(e("GEMINI_TIMEOUT", "20"))
        self.allowed_origins = [o.strip() for o in e("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",") if o.strip()]
        self.allow_reset = _b("ALLOW_RESET", "0")
        self.demo_data = _b("ALLOW_DEMO_DATA", "1")
        self.max_content_chars = 50_000
        self.max_asset_bytes = 1_500_000
        for k, v in over.items():
            setattr(self, k, v)
