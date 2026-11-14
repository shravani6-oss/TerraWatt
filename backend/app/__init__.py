"""TerraWatt application factory."""
import logging
import threading
from types import SimpleNamespace

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config
from .db import close_db, init_db
from .errors import register_error_handlers
from .security import LoginThrottle, csrf_protect
from .services.data_service import get_dataset
from .services.forecast import ForecastEngine
from .services.predictor import Predictor


def _seed_admin(app):
    from .db import connect
    from .security import hash_password
    email, pw = app.config["ADMIN_EMAIL"], app.config["ADMIN_PASSWORD"]
    if not email or not pw:
        return
    conn = connect(app.config["DATABASE_PATH"])
    if not conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        conn.execute("INSERT INTO users (email, name, password_hash, role) VALUES (?,?,?, 'admin')",
                     (email, "Administrator", hash_password(pw)))
        conn.commit()
        app.logger.info("Seeded admin account %s", email)
    conn.close()


def create_app(**overrides) -> Flask:
    cfg = Config(**overrides)
    logging.basicConfig(level=cfg.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = Flask(__name__, static_folder=None)
    app.config.from_mapping({k: v for k, v in vars(cfg).items()})
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
    if cfg.ENV == "production":
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

    init_db(cfg.DATABASE_PATH)
    _seed_admin(app)
    data = get_dataset(str(cfg.DATA_CSV))
    engine = ForecastEngine(data)
    app.extensions["throttle"] = LoginThrottle()   # per-app instance (no cross-app/test leakage)
    app.extensions["tw"] = SimpleNamespace(data=data, engine=engine, predictor=Predictor(cfg.MODELS_DIR, data, cfg.DATA_CSV, cfg.AUTO_RETRAIN))
    if not cfg.TESTING:  # warm the headline backtest off the request path (others compute lazily, ~3 s)
        threading.Thread(target=lambda: engine.backtest("renewable_share"), daemon=True).start()

    register_error_handlers(app)
    app.before_request(csrf_protect)
    app.teardown_appcontext(close_db)

    from .routes import admin, alerts, auth, energy, exports, footprint, goals, ml
    for mod in (auth, energy, ml, footprint, goals, alerts, exports, admin):
        app.register_blueprint(mod.bp)

    @app.after_request
    def headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("Content-Security-Policy",
                                "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                                "font-src 'self' data:; img-src 'self' data:; "
                                "script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        if request.path.startswith("/api/"):
            private = ("/api/auth", "/api/notifications", "/api/watchlist", "/api/alerts", "/api/footprint", "/api/goals", "/api/admin", "/api/users")
            resp.headers["Cache-Control"] = ("no-store" if request.method != "GET" or request.path.startswith(private)
                                             else "public, max-age=60")
        return resp

    @app.get("/")
    def index():
        return send_from_directory(cfg.FRONTEND_DIR, "index.html")

    @app.get("/<path:path>")
    def static_files(path):
        if path.startswith("api/"):
            return jsonify({"error": {"code": "not_found", "message": "Unknown API route."}}), 404
        full = cfg.FRONTEND_DIR / path
        if full.is_file():
            return send_from_directory(cfg.FRONTEND_DIR, path)
        return send_from_directory(cfg.FRONTEND_DIR, "index.html")   # SPA fallback

    return app
