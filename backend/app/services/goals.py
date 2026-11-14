"""Personal sustainability goals, monthly progress and achievement badges.

Comparability rule: a month counts toward a goal only if it was recorded in the SAME mode, for the SAME country (grid)
and with the SAME household size as the goal's baseline month, and falls after the baseline month. Every month is
re-evaluated from its stored raw inputs with the CURRENT emission-factor version, so progress never mixes factors.
Non-comparable months are listed with the reason instead of being silently counted or dropped.
"""
from __future__ import annotations

from datetime import date

from . import entries

BADGES = [
    {"key": "green_beginner", "name": "Green Beginner", "icon": "seedling", "how": "Set your first sustainability goal."},
    {"key": "eco_warrior", "name": "Eco Warrior", "icon": "leaf", "how": "Achieve a monthly target for the first time."},
    {"key": "consistent_saver", "name": "Consistent Saver", "icon": "calendar",
     "how": "Achieve your target in three consecutive calendar months."},
    {"key": "planet_protector", "name": "Planet Protector", "icon": "globe", "how": "Reach a 20% reduction against your baseline month."},
]
EPS = 1e-6


def _next_period(p: str) -> str:
    y, m = int(p[:4]), int(p[5:])
    return f"{y + (m == 12)}-{1 if m == 12 else m + 1:02d}"


def _consecutive(periods: list[str]) -> int:
    best = run = 0
    prev = None
    for p in sorted(periods):
        run = run + 1 if prev and _next_period(prev) == p else 1
        best, prev = max(best, run), p
    return best


def _rows(db, uid):
    return db.execute("SELECT * FROM footprint_entries WHERE user_id = ? ORDER BY period", (uid,)).fetchall()


def active_goal(db, uid):
    return db.execute("SELECT * FROM goals WHERE user_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1", (uid,)).fetchone()


def baseline_for(db, uid, period, data):
    row = db.execute("SELECT * FROM footprint_entries WHERE user_id = ? AND period = ?", (uid, period)).fetchone()
    if not row:
        return None, None
    return row, entries.result_for(row, data)


def create_goal(db, uid, body, data) -> tuple[int, list[str]]:
    row, res = baseline_for(db, uid, body.baseline_period, data)
    if row is None:
        raise ValueError("Save a footprint entry for the baseline month first.")
    base = res["total_kg"]
    if body.kind == "percent":
        target = base * (1 - body.percent / 100)
    else:
        target = float(body.target_kg)
        if target >= base:
            raise ValueError(f"Your goal must be below the baseline month ({base:,.0f} kg CO₂e).")
    db.execute("UPDATE goals SET status='archived', ended_at=datetime('now') WHERE user_id=? AND status='active'", (uid,))
    cur = db.execute("""INSERT INTO goals (user_id, kind, percent, target_kg, baseline_period, baseline_kg, mode, country, household_size)
                        VALUES (?,?,?,?,?,?,?,?,?)""",
                     (uid, body.kind, body.percent, round(target, 2), body.baseline_period, base, res["mode"], row["country"],
                      res["household_size"]))
    db.commit()
    return cur.lastrowid, evaluate(db, uid, data)


def _comparable(goal, row, res):
    if row["period"] <= goal["baseline_period"]:
        return None
    if res["mode"] != goal["mode"]:
        return "different calculator mode than the baseline"
    if row["country"] != goal["country"]:
        return "different country (different grid) than the baseline"
    if res["household_size"] != goal["household_size"]:
        return "different household size than the baseline"
    return ""


def evaluate(db, uid, data) -> list[str]:
    """Recompute progress for the active goal and unlock badges. Returns badge keys unlocked by this call."""
    goal = active_goal(db, uid)
    if goal is None:
        return unlock(db, uid, None, [])
    _, base_res = baseline_for(db, uid, goal["baseline_period"], data)
    achieved_periods, best_pct = [], 0.0
    db.execute("DELETE FROM goal_progress WHERE goal_id = ?", (goal["id"],))
    if base_res is not None:
        base = base_res["total_kg"]
        target = base * (1 - goal["percent"] / 100) if goal["kind"] == "percent" else goal["target_kg"]
        db.execute("UPDATE goals SET baseline_kg=?, target_kg=? WHERE id=?", (base, round(target, 2), goal["id"]))
        for row in _rows(db, uid):
            res = entries.result_for(row, data)
            if _comparable(goal, row, res) != "":
                continue
            cur = res["total_kg"]
            red, pct = base - cur, (base - cur) / base * 100
            ok = cur <= round(target, 2) + EPS      # compare at the precision shown to the user
            db.execute("""INSERT INTO goal_progress (goal_id, user_id, period, footprint_kg, baseline_kg, target_kg, reduction_kg,
                          reduction_pct, achieved, factor_version) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                       (goal["id"], uid, row["period"], cur, base, round(target, 2), red, pct, int(ok), res["factor_version"]))
            if ok:
                achieved_periods.append(row["period"])
            best_pct = max(best_pct, pct)
        if achieved_periods and not goal["first_achieved_period"]:
            db.execute("UPDATE goals SET first_achieved_period=?, first_achieved_at=datetime('now') WHERE id=?",
                       (min(achieved_periods), goal["id"]))
    db.commit()
    return unlock(db, uid, goal, achieved_periods, best_pct)


def unlock(db, uid, goal, achieved_periods, best_pct=0.0) -> list[str]:
    have = {r["badge_key"] for r in db.execute("SELECT badge_key FROM badges WHERE user_id=?", (uid,))}
    ever_goal = db.execute("SELECT COUNT(*) FROM goals WHERE user_id=?", (uid,)).fetchone()[0] > 0
    ever_ach = db.execute("SELECT COUNT(*) FROM goal_progress WHERE user_id=? AND achieved=1", (uid,)).fetchone()[0] > 0
    ever_20 = db.execute("SELECT COUNT(*) FROM goal_progress WHERE user_id=? AND reduction_pct >= 20 - 1e-9", (uid,)).fetchone()[0] > 0
    streak = max((_consecutive([r["period"] for r in db.execute(
        "SELECT period FROM goal_progress WHERE goal_id=? AND achieved=1", (g["id"],))])
        for g in db.execute("SELECT id FROM goals WHERE user_id=?", (uid,)).fetchall()), default=0)
    earned = {"green_beginner": ever_goal, "eco_warrior": ever_ach, "consistent_saver": streak >= 3, "planet_protector": ever_20}
    new = []
    for b in BADGES:
        if earned[b["key"]] and b["key"] not in have:
            db.execute("INSERT INTO badges (user_id, badge_key, goal_id, detail) VALUES (?,?,?,?)",
                       (uid, b["key"], goal["id"] if goal else None, date.today().isoformat()))
            db.execute("INSERT OR IGNORE INTO notifications (user_id, severity, title, body, dedupe_key) VALUES (?,?,?,?,?)",
                       (uid, "success", f"Badge unlocked: {b['name']}", b["how"], f"badge:{b['key']}"))
            new.append(b["key"])
    if new:
        db.commit()
    return new


def dashboard(db, uid, data) -> dict:
    goal = active_goal(db, uid)
    badges = {r["badge_key"]: r for r in db.execute("SELECT * FROM badges WHERE user_id=?", (uid,))}
    out = {"goal": None, "dashboard": None, "history": [], "excluded": [],
           "badges": [{**b, "unlocked": b["key"] in badges, "unlocked_at": badges[b["key"]]["unlocked_at"] if b["key"] in badges else None}
                      for b in BADGES]}
    if goal is None:
        return out
    prog = db.execute("SELECT * FROM goal_progress WHERE goal_id=? ORDER BY period", (goal["id"],)).fetchall()
    out["goal"] = {k: goal[k] for k in ("id", "kind", "percent", "target_kg", "baseline_period", "baseline_kg", "mode", "country",
                                        "household_size", "first_achieved_period", "first_achieved_at", "created_at")}
    out["history"] = [{k: p[k] for k in ("period", "footprint_kg", "reduction_kg", "reduction_pct", "achieved", "target_kg")} for p in prog]
    for row in _rows(db, uid):
        res = entries.result_for(row, data)
        why = _comparable(goal, row, res)
        if why:
            out["excluded"].append({"period": row["period"], "reason": why})
    base, target = goal["baseline_kg"], goal["target_kg"]
    if prog:
        cur = prog[-1]
        need = base - target
        done = min(max(cur["reduction_kg"], 0), need)
        out["dashboard"] = {"period": cur["period"], "current_kg": cur["footprint_kg"], "baseline_kg": base, "target_kg": target,
                            "reduction_kg": round(cur["reduction_kg"], 2), "reduction_pct": round(cur["reduction_pct"], 1),
                            "remaining_kg": round(max(0.0, cur["footprint_kg"] - target), 2),
                            "progress_pct": round(done / need * 100, 1) if need > 0 else 100.0, "achieved": bool(cur["achieved"]),
                            "months_achieved": sum(p["achieved"] for p in prog), "months_tracked": len(prog)}
        row = db.execute("SELECT * FROM footprint_entries WHERE user_id=? AND period=?", (uid, cur["period"])).fetchone()
        from . import carbon
        out["recommendations"] = carbon.recommendations(entries.result_for(row, data))
    else:
        out["recommendations"] = []
    return out
