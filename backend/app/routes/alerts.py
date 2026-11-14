from flask import Blueprint, current_app, jsonify, request

from ..db import get_db
from ..errors import ApiError, not_found
from ..schemas import AlertRuleIn, WatchIn
from ..security import current_user, login_required
from ..services import alerts as svc
from ..services.data_service import FORECASTABLE, METRICS
from .energy import country_arg

bp = Blueprint("alerts", __name__, url_prefix="/api")


def tw():
    return current_app.extensions["tw"]


def _rule(r):
    return {"id": r["id"], "country": r["country"], "metric": r["metric"], "condition": r["condition"],
            "threshold": r["threshold"], "year": r["year"], "enabled": bool(r["enabled"]), "description": svc.describe(r)}


@bp.get("/alerts/rules")
@login_required
def rules():
    rows = get_db().execute("SELECT * FROM alert_rules WHERE user_id = ? ORDER BY id DESC", (current_user()["id"],)).fetchall()
    return jsonify({"rules": [_rule(r) for r in rows]})


@bp.post("/alerts/rules")
@login_required
def create_rule():
    body = AlertRuleIn.model_validate(request.get_json(silent=True) or {})
    c = country_arg(body.country)
    if body.metric not in METRICS:
        raise ApiError(422, "validation_error", "Unknown metric.")
    if body.condition == "forecast_below" and body.metric not in FORECASTABLE:
        raise ApiError(422, "validation_error", "That metric cannot be forecast.")
    db = get_db()
    cur = db.execute("INSERT INTO alert_rules (user_id, country, metric, condition, threshold, year) VALUES (?,?,?,?,?,?)",
                     (current_user()["id"], c, body.metric, body.condition, body.threshold, body.year))
    db.commit()
    fired = svc.evaluate_user(db, current_user()["id"], tw().data, tw().engine)
    row = db.execute("SELECT * FROM alert_rules WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify({"rule": _rule(row), "notifications_created": fired}), 201


@bp.patch("/alerts/rules/<int:rid>")
@login_required
def toggle_rule(rid):
    db = get_db()
    enabled = 1 if (request.get_json(silent=True) or {}).get("enabled", True) else 0
    cur = db.execute("UPDATE alert_rules SET enabled = ? WHERE id = ? AND user_id = ?", (enabled, rid, current_user()["id"]))
    db.commit()
    if not cur.rowcount:
        raise not_found("Rule not found.")
    return jsonify({"ok": True})


@bp.delete("/alerts/rules/<int:rid>")
@login_required
def delete_rule(rid):
    db = get_db()
    cur = db.execute("DELETE FROM alert_rules WHERE id = ? AND user_id = ?", (rid, current_user()["id"]))
    db.commit()
    if not cur.rowcount:
        raise not_found("Rule not found.")
    return jsonify({"ok": True})


@bp.post("/alerts/evaluate")
@login_required
def evaluate():
    n = svc.evaluate_user(get_db(), current_user()["id"], tw().data, tw().engine)
    return jsonify({"notifications_created": n})


@bp.get("/notifications")
@login_required
def notifications():
    db = get_db()
    uid = current_user()["id"]
    rows = db.execute("SELECT id, severity, title, body, is_read, created_at FROM notifications WHERE user_id = ? "
                      "ORDER BY id DESC LIMIT 50", (uid,)).fetchall()
    unread = db.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0", (uid,)).fetchone()[0]
    return jsonify({"notifications": [dict(r) | {"is_read": bool(r["is_read"])} for r in rows], "unread": unread})


@bp.post("/notifications/read")
@login_required
def mark_read():
    db = get_db()
    db.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (current_user()["id"],))
    db.commit()
    return jsonify({"ok": True})


@bp.delete("/notifications")
@login_required
def clear_notifications():
    db = get_db()
    db.execute("DELETE FROM notifications WHERE user_id = ?", (current_user()["id"],))
    db.commit()
    return jsonify({"ok": True})


@bp.get("/watchlist")
@login_required
def watchlist():
    d = tw().data
    rows = get_db().execute("SELECT country FROM watchlist WHERE user_id = ? ORDER BY created_at", (current_user()["id"],)).fetchall()
    items = []
    for r in rows:
        c = r["country"]
        lat = d.latest(c, "renewable_elec_share")
        items.append({"country": c, "value": lat[1] if lat else None, "year": lat[0] if lat else None,
                      "series": d.series(c, "renewable_elec_share")[-10:]})
    return jsonify({"items": items})


@bp.post("/watchlist")
@login_required
def watch_add():
    body = WatchIn.model_validate(request.get_json(silent=True) or {})
    c = country_arg(body.country)
    db = get_db()
    db.execute("INSERT OR IGNORE INTO watchlist (user_id, country) VALUES (?,?)", (current_user()["id"], c))
    db.commit()
    return jsonify({"ok": True, "country": c}), 201


@bp.delete("/watchlist/<path:name>")
@login_required
def watch_remove(name):
    c = country_arg(name)
    db = get_db()
    db.execute("DELETE FROM watchlist WHERE user_id = ? AND country = ?", (current_user()["id"], c))
    db.commit()
    return jsonify({"ok": True})
