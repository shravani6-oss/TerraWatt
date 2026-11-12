import sqlite3

from flask import Blueprint, current_app, jsonify, request

from ..db import audit, get_db
from ..errors import ApiError
from ..schemas import LoginIn, PasswordIn, ProfileIn, RegisterIn
from ..security import (clear_session_cookie, current_user, hash_password, issue_token, login_required,
                        set_session_cookie, verify_password)

bp = Blueprint("auth", __name__, url_prefix="/api")


def public_user(u) -> dict:
    return {"id": u["id"], "name": u["name"], "email": u["email"], "role": u["role"],
            "home_country": u["home_country"], "created_at": u["created_at"]}


def _check_country(name):
    if name is None or name == "":
        return None
    c = current_app.extensions["tw"].data.canonical(name)
    if not c:
        raise ApiError(422, "validation_error", "Unknown country.", [{"field": "home_country", "message": "Unknown country."}])
    return c


@bp.post("/auth/register")
def register():
    body = RegisterIn.model_validate(request.get_json(silent=True) or {})
    db = get_db()
    try:
        cur = db.execute("INSERT INTO users (email, name, password_hash, home_country) VALUES (?,?,?,?)",
                         (body.email, body.name, hash_password(body.password), _check_country(body.home_country)))
        db.commit()
    except sqlite3.IntegrityError:
        raise ApiError(409, "email_taken", "An account with this email already exists.")
    user = db.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    audit("register", user["email"], user["id"])
    resp = jsonify({"user": public_user(user)})
    resp.status_code = 201
    return set_session_cookie(resp, issue_token(user["id"], user["role"]))


@bp.post("/auth/login")
def login():
    body = LoginIn.model_validate(request.get_json(silent=True) or {})
    cfg = current_app.config
    key = f"{request.remote_addr}|{body.email}"
    throttle = current_app.extensions["throttle"]
    wait = throttle.blocked(key, cfg["LOGIN_MAX_ATTEMPTS"], cfg["LOGIN_WINDOW_SECONDS"])
    if wait:
        raise ApiError(429, "too_many_attempts", f"Too many failed attempts. Try again in {wait // 60 + 1} minute(s).")
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email = ?", (body.email,)).fetchone()
    if not user or not user["is_active"] or not verify_password(user["password_hash"], body.password):
        throttle.fail(key, cfg["LOGIN_WINDOW_SECONDS"])
        audit("login_failed", body.email)
        raise ApiError(401, "invalid_credentials", "Incorrect email or password.")
    throttle.reset(key)
    db.execute("UPDATE users SET last_login_at = datetime('now') WHERE id = ?", (user["id"],))
    db.commit()
    audit("login", "", user["id"])
    return set_session_cookie(jsonify({"user": public_user(user)}), issue_token(user["id"], user["role"]))


@bp.post("/auth/logout")
def logout():
    return clear_session_cookie(jsonify({"ok": True}))


@bp.get("/auth/me")
def me():
    u = current_user()
    return jsonify({"user": public_user(u) if u else None})


@bp.put("/auth/password")
@login_required
def change_password():
    body = PasswordIn.model_validate(request.get_json(silent=True) or {})
    u = current_user()
    if not verify_password(u["password_hash"], body.current_password):
        raise ApiError(400, "wrong_password", "Current password is incorrect.")
    db = get_db()
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(body.new_password), u["id"]))
    db.commit()
    audit("password_change", "", u["id"])
    return jsonify({"ok": True})


@bp.patch("/users/me")
@login_required
def update_profile():
    body = ProfileIn.model_validate(request.get_json(silent=True) or {})
    u = current_user()
    fields = body.model_dump(exclude_unset=True)
    if "home_country" in fields:
        fields["home_country"] = _check_country(fields["home_country"])
    if fields:
        sets = ", ".join(f"{k} = ?" for k in fields)
        db = get_db()
        db.execute(f"UPDATE users SET {sets} WHERE id = ?", (*fields.values(), u["id"]))
        db.commit()
    return jsonify({"user": public_user(get_db().execute("SELECT * FROM users WHERE id = ?", (u["id"],)).fetchone())})


@bp.delete("/users/me")
@login_required
def delete_account():
    u = current_user()
    db = get_db()
    db.execute("DELETE FROM users WHERE id = ?", (u["id"],))
    db.commit()
    audit("account_deleted", u["email"])
    return clear_session_cookie(jsonify({"ok": True}))
