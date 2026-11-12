"""SQLite access layer: one connection per request, WAL mode, foreign keys, versioned schema."""
import sqlite3
from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name          TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user','admin')),
    home_country  TEXT,
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    last_login_at TEXT
);
CREATE TABLE IF NOT EXISTS footprint_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    period      TEXT NOT NULL,                 -- YYYY-MM
    country     TEXT NOT NULL,
    electricity_kwh REAL NOT NULL DEFAULT 0,
    gas_m3      REAL NOT NULL DEFAULT 0,
    car_km      REAL NOT NULL DEFAULT 0,
    flight_km   REAL NOT NULL DEFAULT 0,
    renewable_pct REAL NOT NULL DEFAULT 0,     -- own solar / green tariff share of electricity
    co2_kg      REAL NOT NULL,                 -- computed at write time with the factors in force
    breakdown   TEXT NOT NULL,                 -- JSON
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, period)
);
CREATE INDEX IF NOT EXISTS idx_footprint_user_period ON footprint_entries(user_id, period);
CREATE TABLE IF NOT EXISTS watchlist (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    country TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, country)
);
CREATE TABLE IF NOT EXISTS alert_rules (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    country    TEXT NOT NULL,
    metric     TEXT NOT NULL,
    condition  TEXT NOT NULL CHECK (condition IN ('below','above','yoy_drop','forecast_below')),
    threshold  REAL NOT NULL,
    year       INTEGER,                         -- only for forecast_below
    enabled    INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_rules_user ON alert_rules(user_id);
CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rule_id    INTEGER REFERENCES alert_rules(id) ON DELETE CASCADE,
    severity   TEXT NOT NULL DEFAULT 'info' CHECK (severity IN ('info','warning','success')),
    title      TEXT NOT NULL,
    body       TEXT NOT NULL,
    is_read    INTEGER NOT NULL DEFAULT 0,
    dedupe_key TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, dedupe_key)
);
CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id, is_read);
CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER,
    action     TEXT NOT NULL,
    detail     TEXT,
    ip         TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at DESC);
"""


def connect(path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE_PATH"])
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(path) -> None:
    path = str(path)
    if path != ":memory:":
        import pathlib
        pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def audit(action: str, detail: str = "", user_id=None) -> None:
    """Append an audit record. Never raises: auditing must not break the request."""
    from flask import request
    try:
        db = get_db()
        db.execute("INSERT INTO audit_log (user_id, action, detail, ip) VALUES (?,?,?,?)",
                   (user_id, action, detail[:500], request.remote_addr))
        db.commit()
    except Exception:  # pragma: no cover
        current_app.logger.exception("audit failed")
