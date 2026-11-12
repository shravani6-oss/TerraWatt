"""Evaluate user alert rules against the dataset and forecasts, writing de-duplicated notifications."""
from __future__ import annotations

import sqlite3

from .data_service import FORECASTABLE, METRICS, EnergyData
from .forecast import ForecastEngine

CONDITIONS = {
    "below": "is below", "above": "is above",
    "yoy_drop": "fell year-on-year by at least", "forecast_below": "is forecast to be below",
}


def describe(rule) -> str:
    m = METRICS[rule["metric"]]
    extra = f" in {rule['year']}" if rule["condition"] == "forecast_below" else ""
    return f"{rule['country']} · {m.label} {CONDITIONS[rule['condition']]} {rule['threshold']:g} {m.unit}{extra}"


def evaluate_rule(rule, data: EnergyData, engine: ForecastEngine) -> dict | None:
    """Return {severity,title,body,key} when the rule fires, else None."""
    country, metric = rule["country"], rule["metric"]
    m = METRICS[metric]
    lat = data.latest(country, metric)
    if lat is None:
        return None
    year, value = lat
    cond, thr = rule["condition"], rule["threshold"]
    if cond == "below" and value < thr:
        return {"severity": "warning", "key": f"{rule['id']}:{year}",
                "title": f"{country}: {m.label} below {thr:g}",
                "body": f"Latest value is {value:.1f} {m.unit} ({year}), under your threshold of {thr:g}."}
    if cond == "above" and value > thr:
        return {"severity": "success", "key": f"{rule['id']}:{year}",
                "title": f"{country}: {m.label} above {thr:g}",
                "body": f"Latest value is {value:.1f} {m.unit} ({year}), over your threshold of {thr:g}."}
    if cond == "yoy_drop":
        yrs, vals = data.series_array(country, metric)
        if len(yrs) >= 2 and yrs[-1] - yrs[-2] == 1 and vals[-2] - vals[-1] >= thr:
            drop = vals[-2] - vals[-1]
            return {"severity": "warning", "key": f"{rule['id']}:{yrs[-1]}",
                    "title": f"{country}: {m.label} dropped {drop:.1f}",
                    "body": f"Fell from {vals[-2]:.1f} to {vals[-1]:.1f} {m.unit} between {yrs[-2]} and {yrs[-1]}."}
    if cond == "forecast_below" and metric in FORECASTABLE and rule["year"]:
        fc = engine.forecast(country, metric, rule["year"])
        row = next((r for r in fc["forecast"] if r["year"] == rule["year"]), None)
        if row and row["value"] < thr:
            return {"severity": "warning", "key": f"{rule['id']}:{rule['year']}:{fc['last_observed_year']}",
                    "title": f"{country}: {m.label} forecast below {thr:g} in {rule['year']}",
                    "body": (f"Model forecast {row['value']:.1f} {m.unit} (80% range {row['lo']:.1f}–{row['hi']:.1f}) "
                             f"for {rule['year']}. This is a statistical projection, not a certainty.")}
    return None


def evaluate_user(db: sqlite3.Connection, user_id: int, data: EnergyData, engine: ForecastEngine) -> int:
    rules = db.execute("SELECT * FROM alert_rules WHERE user_id = ? AND enabled = 1", (user_id,)).fetchall()
    created = 0
    for rule in rules:
        hit = evaluate_rule(rule, data, engine)
        if not hit:
            continue
        cur = db.execute("INSERT OR IGNORE INTO notifications (user_id, rule_id, severity, title, body, dedupe_key) "
                         "VALUES (?,?,?,?,?,?)", (user_id, rule["id"], hit["severity"], hit["title"], hit["body"], hit["key"]))
        created += cur.rowcount
    db.commit()
    return created
