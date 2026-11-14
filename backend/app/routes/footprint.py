import csv
import io
import json

from flask import Blueprint, Response, current_app, jsonify, request

from ..db import get_db
from ..errors import ApiError, not_found
from ..schemas import FootprintIn, HouseholdIn
from ..security import current_user, login_required
from ..services import carbon, entries, goals
from .energy import country_arg

bp = Blueprint("footprint", __name__, url_prefix="/api/footprint")
BADGE_NAMES = {b["key"]: b["name"] for b in goals.BADGES}


def tw():
    return current_app.extensions["tw"]


def _parse(raw: dict):
    model = HouseholdIn if (raw or {}).get("mode") == "simple" else FootprintIn
    return model.model_validate(raw or {})


def _calc(body):
    c = country_arg(body.country)
    grid = carbon.grid_factor(tw().data, c)
    inp = body.model_dump(exclude_none=True, exclude={"period", "country", "mode"})
    try:
        res = carbon.evaluate(body.mode, inp, grid)
    except ValueError as exc:
        raise ApiError(422, "validation_error", str(exc))
    res["country"] = c
    res["grid_from_data"] = grid["from_data"]
    return c, inp, res


@bp.get("/factors")
def factors():
    return jsonify({"version": carbon.FACTOR_VERSION, "factors": carbon.F, "default_tariff_inr_per_kwh": carbon.DEFAULT_TARIFF_INR,
                    "tariff_presets": carbon.TARIFF_PRESETS,
                    "vehicles": {k: {"label": v[0], "km_per_litre": v[1]} for k, v in carbon.VEHICLES.items()},
                    "flight_bands_pkm_per_year": {k: v[0] for k, v in carbon.FLIGHT_BANDS.items()},
                    "categories": carbon.CATEGORIES,
                    "note": "Typical published averages; approximate. Electricity uses the selected country's Ember lifecycle grid "
                            "intensity (pinned to one reporting year) and excludes transmission and distribution losses."})


@bp.post("/estimate")
def estimate():
    body = _parse(request.get_json(silent=True))
    c, _, res = _calc(body)
    res["recommendations"] = carbon.recommendations(res)
    res["benchmark"] = carbon.benchmark(tw().data, c, res["household_size"], res["total_kg"])
    return jsonify(res)


def _row(r):
    res = entries.result_for(r, tw().data)
    return {"id": r["id"], "period": r["period"], "country": r["country"], "mode": res["mode"],
            "household_size": res["household_size"], "electricity_kwh": r["electricity_kwh"], "gas_m3": r["gas_m3"],
            "car_km": r["car_km"], "flight_km": r["flight_km"], "renewable_pct": r["renewable_pct"],
            "co2_kg": res["total_kg"], "co2_low": res["low_kg"], "co2_high": res["high_kg"], "per_person_kg": res["per_person_kg"],
            "breakdown": res["parts"], "estimated_share": res["estimated_share"], "factor_version": res["factor_version"],
            "stored_co2_kg": r["co2_kg"], "inputs": entries.inputs_of(r)[1]}


@bp.get("/entries")
@login_required
def list_entries():
    rows = get_db().execute("SELECT * FROM footprint_entries WHERE user_id = ? ORDER BY period DESC", (current_user()["id"],)).fetchall()
    return jsonify({"entries": [_row(r) for r in rows]})


@bp.post("/entries")
@login_required
def upsert():
    body = _parse(request.get_json(silent=True))
    c, inp, res = _calc(body)
    db, uid = get_db(), current_user()["id"]
    inp_store = {**inp, "household_size": res["household_size"]}
    db.execute("""INSERT INTO footprint_entries (user_id, period, country, electricity_kwh, gas_m3, car_km, flight_km,
                  renewable_pct, co2_kg, breakdown, mode, household_size, inputs_json, factor_version, co2_low, co2_high)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                  ON CONFLICT(user_id, period) DO UPDATE SET country=excluded.country, electricity_kwh=excluded.electricity_kwh,
                  gas_m3=excluded.gas_m3, car_km=excluded.car_km, flight_km=excluded.flight_km,
                  renewable_pct=excluded.renewable_pct, co2_kg=excluded.co2_kg, breakdown=excluded.breakdown, mode=excluded.mode,
                  household_size=excluded.household_size, inputs_json=excluded.inputs_json,
                  factor_version=excluded.factor_version, co2_low=excluded.co2_low, co2_high=excluded.co2_high""",
               (uid, body.period, c, round(res.get("derived_kwh") or 0, 2), inp.get("gas_m3", 0), inp.get("car_km", 0),
                inp.get("flight_km", 0), (inp.get("electricity") or {}).get("renewable_pct", inp.get("renewable_pct", 0)),
                res["total_kg"], json.dumps(res["parts"]), res["mode"], res["household_size"], json.dumps(inp_store),
                res["factor_version"], res["low_kg"], res["high_kg"]))
    db.commit()
    new = goals.evaluate(db, uid, tw().data)
    row = db.execute("SELECT * FROM footprint_entries WHERE user_id = ? AND period = ?", (uid, body.period)).fetchone()
    return jsonify({"entry": _row(row), "new_badges": [{"key": k, "name": BADGE_NAMES[k]} for k in new]}), 201


@bp.delete("/entries/<int:entry_id>")
@login_required
def delete(entry_id):
    db = get_db()
    cur = db.execute("DELETE FROM footprint_entries WHERE id = ? AND user_id = ?", (entry_id, current_user()["id"]))
    db.commit()
    if not cur.rowcount:
        raise not_found("Entry not found.")
    goals.evaluate(db, current_user()["id"], tw().data)
    return jsonify({"ok": True})


@bp.get("/summary")
@login_required
def summary():
    rows = [_row(r) for r in get_db().execute(
        "SELECT * FROM footprint_entries WHERE user_id = ? ORDER BY period", (current_user()["id"],)).fetchall()]
    if not rows:
        return jsonify({"count": 0, "entries": []})
    totals = {k: round(sum(r["breakdown"].get(k, 0) for r in rows), 1) for k in carbon.CATEGORIES}
    avg_month = sum(r["co2_kg"] for r in rows) / len(rows)
    last = rows[-1]
    d = tw().data
    prev = rows[-2]["co2_kg"] if len(rows) > 1 else None
    last_row = get_db().execute("SELECT * FROM footprint_entries WHERE id = ?", (last["id"],)).fetchone()
    last_res = entries.result_for(last_row, d)
    return jsonify({
        "count": len(rows), "entries": rows, "totals_by_category": totals, "total_kg": round(sum(r["co2_kg"] for r in rows), 1),
        "avg_month_kg": round(avg_month, 1), "annualised_t": round(avg_month * 12 / 1000, 2),
        "last_period": last["period"], "change_vs_previous_pct": round((last["co2_kg"] / prev - 1) * 100, 1) if prev else None,
        "benchmark": carbon.benchmark(d, last["country"], last["household_size"], last["co2_kg"]),
        "recommendations": carbon.recommendations(last_res), "factor_version": carbon.FACTOR_VERSION})


@bp.get("/export.csv")
@login_required
def export():
    rows = [_row(r) for r in get_db().execute("SELECT * FROM footprint_entries WHERE user_id = ? ORDER BY period",
                                              (current_user()["id"],)).fetchall()]
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["period", "country", "mode", "household_size", "co2_kg", "co2_low", "co2_high", "per_person_kg",
                *[f"kg_{c}" for c in carbon.CATEGORIES], "factor_version"])
    for r in rows:
        w.writerow([r["period"], r["country"], r["mode"], r["household_size"], r["co2_kg"], r["co2_low"], r["co2_high"],
                    r["per_person_kg"], *[r["breakdown"].get(c, 0) for c in carbon.CATEGORIES], r["factor_version"]])
    return Response(out.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=terrawatt-footprint.csv"})
