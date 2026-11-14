"""Password hashing, JWT session cookies, role guards, CSRF guard and login throttling."""
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import current_app, g, request
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db
from .errors import ApiError

COOKIE_NAME = "tw_session"
CSRF_HEADER = ("X-Requested-With", "TerraWatt")

_PASSWORD_RE_LETTER = re.compile(r"[A-Za-z]")
_PASSWORD_RE_DIGIT = re.compile(r"\d")


def validate_password_strength(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if len(password) > 128:
        raise ValueError("Password must be at most 128 characters.")
    if not (_PASSWORD_RE_LETTER.search(password) and _PASSWORD_RE_DIGIT.search(password)):
        raise ValueError("Password must contain at least one letter and one digit.")
    return password


def hash_password(password: str) -> str:
    return generate_password_hash(password)  # scrypt with per-password salt


def verify_password(password_hash: str, password: str) -> bool:
    return check_password_hash(password_hash, password)


def issue_token(user_id: int, role: str) -> str:
    cfg = current_app.config
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "role": role, "iat": now,
               "exp": now + timedelta(hours=cfg["JWT_TTL_HOURS"])}
    return jwt.encode(payload, cfg["SECRET_KEY"], algorithm="HS256")


def set_session_cookie(response, token: str):
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="Lax",
                        secure=current_app.config["COOKIE_SECURE"],
                        max_age=current_app.config["JWT_TTL_HOURS"] * 3600, path="/")
    return response


def clear_session_cookie(response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


def _load_user():
    """Resolve the session cookie to a user row (re-checked in the DB so revocation is immediate)."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        data = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
        user = get_db().execute("SELECT * FROM users WHERE id = ? AND is_active = 1",
                                (int(data["sub"]),)).fetchone()
    except (jwt.PyJWTError, ValueError, KeyError):
        return None
    return user


def current_user():
    if "user" not in g:
        g.user = _load_user()
    return g.user


def csrf_protect():
    """State-changing API calls must carry a custom header, which cross-site forms cannot send."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.path.startswith("/api/"):
        if request.headers.get(CSRF_HEADER[0]) != CSRF_HEADER[1]:
            raise ApiError(403, "csrf_failed", "Missing or invalid request header.")


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            raise ApiError(401, "unauthorized", "Please sign in to continue.")
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if current_user()["role"] != "admin":
            raise ApiError(403, "forbidden", "Administrator access required.")
        return fn(*args, **kwargs)
    return wrapper


class LoginThrottle:
    """In-memory sliding-window limiter keyed by (ip, email). Fine for a single process;
    swap for Redis when running several workers (documented in the README)."""
    def __init__(self):
        self._lock = threading.Lock()
        self._fails: dict[str, list[float]] = {}

    def _recent(self, key, window):
        now = time.time()
        hits = [t for t in self._fails.get(key, []) if now - t < window]
        self._fails[key] = hits
        return hits

    def blocked(self, key, max_attempts, window) -> int:
        """Return seconds until retry is allowed (0 if not blocked)."""
        with self._lock:
            hits = self._recent(key, window)
            if len(hits) >= max_attempts:
                return int(window - (time.time() - hits[0])) + 1
            return 0

    def fail(self, key, window):
        with self._lock:
            self._recent(key, window).append(time.time())

    def reset(self, key):
        with self._lock:
            self._fails.pop(key, None)

