"""Application configuration, driven entirely by environment variables (see .env.example)."""
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    """Load a local .env file if python-dotenv is installed (optional dependency)."""
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:  # pragma: no cover - dotenv is optional
        pass


def _secret_key(instance_dir: Path, env: str) -> str:
    """SECRET_KEY from env. In development, generate one and persist it so sessions survive restarts."""
    key = os.getenv("SECRET_KEY")
    if key:
        return key
    if env == "production":
        raise RuntimeError("SECRET_KEY must be set when TERRAWATT_ENV=production")
    instance_dir.mkdir(parents=True, exist_ok=True)
    path = instance_dir / ".secret_key"
    if path.exists():
        return path.read_text().strip()
    key = secrets.token_urlsafe(48)
    path.write_text(key)
    return key


class Config:
    def __init__(self, **overrides):
        _load_dotenv()
        self.ENV = os.getenv("TERRAWATT_ENV", "development")
        self.INSTANCE_DIR = Path(os.getenv("INSTANCE_DIR", ROOT / "instance"))
        self.SECRET_KEY = _secret_key(self.INSTANCE_DIR, self.ENV)
        self.DATABASE_PATH = Path(os.getenv("DATABASE_PATH", self.INSTANCE_DIR / "terrawatt.db"))
        self.DATA_CSV = Path(os.getenv("DATA_CSV", ROOT / "data" / "global-data-on-sustainable-energy.csv"))
        self.MODELS_DIR = Path(os.getenv("MODELS_DIR", ROOT / "models"))
        self.FRONTEND_DIR = ROOT / "frontend"
        self.JWT_TTL_HOURS = int(os.getenv("JWT_TTL_HOURS", "12"))
        self.COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true" if self.ENV == "production" else "false").lower() == "true"
        self.LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
        self.LOGIN_WINDOW_SECONDS = int(os.getenv("LOGIN_WINDOW_SECONDS", "900"))
        self.ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip().lower()
        self.ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.TESTING = False
        for key, value in overrides.items():
            setattr(self, key, value)
