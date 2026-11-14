from flask import Blueprint, current_app, jsonify, request

from ..db import audit, get_db
from ..errors import ApiError, not_found
from ..schemas import AdminUserPatch
from ..security import admin_required, current_user

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


@bp.get("/stats")
@admin_required
def stats():
    db = get_db()
    one = lambda q: db.execute(q).fetchone()[0]
    signups = db.execute("SELECT date(created_at) d, COUNT(*) n FROM users WHERE created_at >= date('now','-13 days') "
                         "GROUP BY d ORDER BY d").fetchall()
    t = current_app.extensions["tw"]
    return jsonify({
        "users": one("SELECT COUNT(*) FROM users"), "active_users": one("SELECT COUNT(*) FROM users WHERE is_active=1"),
        "admins": one("SELECT COUNT(*) FROM users WHERE role='admin'"),
        "footprint_entries": one("SELECT COUNT(*) FROM footprint_entries"), "alert_rules": one("SELECT COUNT(*) FROM alert_rules"),
        "notifications": one("SELECT COUNT(*) FROM notifications"), "signups_14d": [dict(r) for r in signups],
        "dataset": t.data.provenance(), "models_loaded": t.predictor.error is None,
        "models_trained_at": t.predictor.cards.get("trained_at"), "forecast_cache": list(t.engine._cache.keys())})


@bp.get("/users")
@admin_required
def users():
    q = f"%{request.args.get('q', '')[:60]}%"
    page = max(1, int(request.args.get("page", 1) or 1))
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM users WHERE email LIKE ? OR name LIKE ?", (q, q)).fetchone()[0]
    rows = db.execute("SELECT id, email, name, role, home_country, is_active, created_at, last_login_at FROM users "
                      "WHERE email LIKE ? OR name LIKE ? ORDER BY id DESC LIMIT 20 OFFSET ?", (q, q, (page - 1) * 20)).fetchall()
    return jsonify({"total": total, "page": page, "users": [dict(r) | {"is_active": bool(r["is_active"])} for r in rows]})


@bp.patch("/users/<int:uid>")
@admin_required
def patch_user(uid):
    body = AdminUserPatch.model_validate(request.get_json(silent=True) or {})
    me = current_user()
    if uid == me["id"]:
        raise ApiError(400, "self_modify", "You cannot change your own role or status.")
    db = get_db()
    fields = body.model_dump(exclude_unset=True)
    if "is_active" in fields:
        fields["is_active"] = int(fields["is_active"])
    if not fields:
        raise ApiError(400, "bad_request", "Nothing to update.")
    cur = db.execute(f"UPDATE users SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?", (*fields.values(), uid))
    db.commit()
    if not cur.rowcount:
        raise not_found("User not found.")
    audit("admin_update_user", f"user={uid} {fields}", me["id"])
    return jsonify({"ok": True})


@bp.get("/audit")
@admin_required
def audit_log():
    rows = get_db().execute("SELECT a.id, a.action, a.detail, a.ip, a.created_at, u.email FROM audit_log a "
                            "LEFT JOIN users u ON u.id = a.user_id ORDER BY a.id DESC LIMIT 100").fetchall()
    return jsonify({"events": [dict(r) for r in rows]})


@bp.post("/models/reload")
@admin_required
def reload_models():
    t = current_app.extensions["tw"]
    t.predictor.error = None
    t.predictor._load()
    audit("models_reload", t.predictor.error or "ok", current_user()["id"])
    return jsonify({"models_loaded": t.predictor.error is None, "error": t.predictor.error})
