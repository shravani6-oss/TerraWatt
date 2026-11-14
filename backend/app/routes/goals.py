from flask import Blueprint, current_app, jsonify, request

from ..db import get_db
from ..errors import ApiError
from ..schemas import GoalIn
from ..security import current_user, login_required
from ..services import goals

bp = Blueprint("goals", __name__, url_prefix="/api/goals")


def _data():
    return current_app.extensions["tw"].data


@bp.get("/progress")
@login_required
def progress():
    db, uid = get_db(), current_user()["id"]
    goals.evaluate(db, uid, _data())          # always re-evaluate with the current factors before showing anything
    return jsonify(goals.dashboard(db, uid, _data()))


@bp.post("")
@login_required
def create():
    body = GoalIn.model_validate(request.get_json(silent=True) or {})
    db, uid = get_db(), current_user()["id"]
    try:
        gid, new = goals.create_goal(db, uid, body, _data())
    except ValueError as exc:
        raise ApiError(422, "invalid_goal", str(exc))
    out = goals.dashboard(db, uid, _data())
    out["new_badges"] = [{"key": k, "name": next(b["name"] for b in goals.BADGES if b["key"] == k)} for k in new]
    return jsonify(out), 201


@bp.delete("/active")
@login_required
def archive():
    db, uid = get_db(), current_user()["id"]
    db.execute("UPDATE goals SET status='archived', ended_at=datetime('now') WHERE user_id=? AND status='active'", (uid,))
    db.commit()
    return jsonify({"ok": True})
