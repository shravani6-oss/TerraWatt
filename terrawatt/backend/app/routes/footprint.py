import csv
import io
import json

from flask import Blueprint, Response, current_app, jsonify, request

from ..db import get_db
from ..errors import ApiError, not_found
from ..schemas import FootprintIn
from ..security import current_user, login_required
from ..services import carbon
from .energy import country_arg

bp = Blueprint("footprint", __name__, url_prefix="/api/footprint")


def grid_for(country: str) -> tuple[float, bool]:
    d = current_app.extensions["tw"].data
    lat = d.latest(country, "grid_intensity")
    return (lat[1], True) if lat else (carbon.FALLBACK_GRID_G_PER_KWH, False)


def _calc(body: FootprintIn):
    c = country_arg(body.country)
    grid, from_data = grid_for(c)
    res = carbon.compute(body.electricity_kwh, body.gas_m3, body.car_km, body.flight_km, body.renewable_pct, grid)
    res.update(country=c, grid_from_data=from_data)
    return c, res


@bp.get("/factors")
def factors():
    return jsonify({**carbon.FACTORS, "note": "Typical published averages; approximate. Electricity uses the selected "
                    "country's estimated grid intensity (generation-mix based)."})


@bp.post("/estimate")
def estimate():
    body = FootprintIn.model_validate(request.get_json(silent=True) or {})
    c, res = _calc(body)
    res["recommendations"] = carbon.recommendations(body.model_dump(), res["grid_g_per_kwh"])
    return jsonify(res)


def _row(r):
    return {"id": r["id"], "period": r["period"], "country": r["country"], "electricity_kwh": r["electricity_kwh"],
            "gas_m3": r["gas_m3"], "car_km": r["car_km"], "flight_km": r["flight_km"],
            "renewable_pct": r["renewable_pct"], "co2_kg": r["co2_kg"], "breakdown": json.loads(r["breakdown"])}


@bp.get("/entries")
@login_required
def entries():
    rows = get_db().execute("SELECT * FROM footprint_entries WHERE user_id = ? ORDER BY period DESC",
                            (current_user()["id"],)).fetchall()
    return jsonify({"entries": [_row(r) for r in rows]})


@bp.post("/entries")
@login_required
def upsert():
    body = FootprintIn.model_validate(request.get_json(silent=True) or {})
    c, res = _calc(body)
    db = get_db()
    uid = current_user()["id"]
    db.execute("""INSERT INTO footprint_entries (user_id, period, country, electricity_kwh, gas_m3, car_km, flight_km,
                  renewable_pct, co2_kg, breakdown) VALUES (?,?,?,?,?,?,?,?,?,?)
                  ON CONFLICT(user_id, period) DO UPDATE SET country=excluded.country,
                  electricity_kwh=excluded.electricity_kwh, gas_m3=excluded.gas_m3, car_km=excluded.car_km,
                  flight_km=excluded.flight_km, renewable_pct=excluded.renewable_pct, co2_kg=excluded.co2_kg,
                  breakdown=excluded.breakdown""",
               (uid, body.period, c, body.electricity_kwh, body.gas_m3, body.car_km, body.flight_km,
                body.renewable_pct, res["total_kg"], json.dumps(res["parts"])))
    db.commit()
    row = db.execute("SELECT * FROM footprint_entries WHERE user_id = ? AND period = ?", (uid, body.period)).fetchone()
    return jsonify({"entry": _row(row)}), 201


@bp.delete("/entries/<int:entry_id>")
@login_required
def delete(entry_id):
    db = get_db()
    cur = db.execute("DELETE FROM footprint_entries WHERE id = ? AND user_id = ?", (entry_id, current_user()["id"]))
    db.commit()
    if not cur.rowcount:
        raise not_found("Entry not found.")
    return jsonify({"ok": True})


@bp.get("/summary")
@login_required
def summary():
    rows = [_row(r) for r in get_db().execute(
        "SELECT * FROM footprint_entries WHERE user_id = ? ORDER BY period", (current_user()["id"],)).fetchall()]
    if not rows:
        return jsonify({"count": 0, "entries": []})
    totals = {k: round(sum(r["breakdown"][k] for r in rows), 1) for k in ("electricity", "gas", "car", "flights")}
    avg_month = sum(r["co2_kg"] for r in rows) / len(rows)
    last = rows[-1]
    d = current_app.extensions["tw"].data
    per_cap = d.latest(last["country"], "co2_per_capita_t")
    grid, _ = grid_for(last["country"])
    prev = rows[-2]["co2_kg"] if len(rows) > 1 else None
    return jsonify({
        "count": len(rows), "entries": rows, "totals_by_category": totals, "total_kg": round(sum(r["co2_kg"] for r in rows), 1),
        "avg_month_kg": round(avg_month, 1), "annualised_t": round(avg_month * 12 / 1000, 2),
        "last_period": last["period"], "change_vs_previous_pct": round((last["co2_kg"] / prev - 1) * 100, 1) if prev else None,
        "country_per_capita_t": {"value": per_cap[1], "year": per_cap[0], "country": last["country"]} if per_cap else None,
        "recommendations": carbon.recommendations(last, grid)})


@bp.get("/export.csv")
@login_required
def export():
    rows = get_db().execute("SELECT * FROM footprint_entries WHERE user_id = ? ORDER BY period",
                            (current_user()["id"],)).fetchall()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["period", "country", "electricity_kwh", "gas_m3", "car_km", "flight_km", "renewable_pct", "co2_kg"])
    for r in rows:
        w.writerow([r["period"], r["country"], r["electricity_kwh"], r["gas_m3"], r["car_km"], r["flight_km"],
                    r["renewable_pct"], r["co2_kg"]])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=terrawatt-footprint.csv"})
