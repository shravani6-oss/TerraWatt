from flask import Blueprint, current_app, jsonify, request

from ..errors import ApiError, bad_request, not_found
from ..services import recommendations as recs
from ..services.data_service import FORECASTABLE, METRICS

bp = Blueprint("energy", __name__, url_prefix="/api")


def tw():
    return current_app.extensions["tw"]


def country_arg(name: str) -> str:
    c = tw().data.canonical(name or "")
    if not c:
        raise not_found(f"Unknown country '{name}'.")
    return c


def metric_arg(name: str, allowed=None) -> str:
    if name not in METRICS or (allowed is not None and name not in allowed):
        raise bad_request(f"Unknown or unsupported metric '{name}'.", {"allowed": list(allowed or METRICS)})
    return name


def int_arg(name, default=None, lo=None, hi=None):
    raw = request.args.get(name)
    if raw in (None, ""):
        return default
    try:
        v = int(raw)
    except ValueError:
        raise bad_request(f"'{name}' must be an integer.")
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        raise bad_request(f"'{name}' must be between {lo} and {hi}.")
    return v


@bp.get("/health")
def health():
    t = tw()
    return jsonify({"status": "ok", "dataset_rows": len(t.data.df), "models_loaded": t.predictor.error is None})


@bp.get("/meta")
def meta():
    d = tw().data
    return jsonify({
        "countries": d.countries, "years": [d.first_year, d.last_year], "headline_year": d.headline_year,
        "metrics": [{"key": m.key, "label": m.label, "unit": m.unit, "higher_is_better": m.higher_is_better,
                     "description": m.description, "derived": m.derived, "forecastable": m.key in FORECASTABLE}
                    for m in METRICS.values()],
        "provenance": d.provenance()})


@bp.get("/overview")
def overview():
    return jsonify(tw().data.overview(int_arg("year", None, 2001, 2020)))


@bp.get("/trend/global")
def trend():
    return jsonify({"series": tw().data.global_trend()})


@bp.get("/rankings")
def rankings():
    d = tw().data
    metric = metric_arg(request.args.get("metric", "renewable_share"))
    year = int_arg("year", None, d.first_year, d.last_year)
    return jsonify(d.ranking(metric, year, request.args.get("q", "")[:60], request.args.get("sort", "desc"),
                             int_arg("limit", 500, 1, 500)))


@bp.get("/map")
def map_points():
    d = tw().data
    metric = metric_arg(request.args.get("metric", "renewable_share"))
    year = int_arg("year", d.headline_year, d.first_year, d.last_year)
    pts = d.map_points(metric, year)
    vals = [p["value"] for p in pts]
    return jsonify({"metric": metric, "year": year, "points": pts,
                    "min": min(vals) if vals else None, "max": max(vals) if vals else None})


@bp.get("/countries/<path:name>")
def country(name):
    t = tw()
    c = country_arg(name)
    prof = t.data.profile(c)
    prof["cluster"] = t.predictor.cluster_of(c)
    prof["peers"] = t.predictor.peers(c)
    prof["series"] = {m: t.data.series(c, m) for m in ("renewable_share", "renewable_elec_share", "electricity_access",
                                                      "clean_cooking_access", "co2_per_capita_t", "grid_intensity")}
    prof["recommendations"] = recs.country_recommendations(t.data, c)
    return jsonify(prof)


@bp.get("/compare")
def compare():
    t = tw()
    names = [country_arg(n) for n in request.args.get("countries", "").split(",") if n.strip()]
    if not 1 <= len(names) <= 5:
        raise bad_request("Provide 1 to 5 countries (comma separated).")
    metric = metric_arg(request.args.get("metric", "renewable_share"))
    return jsonify({"metric": metric, "series": t.data.compare(names, metric)})


@bp.get("/records")
def records():
    d = tw().data
    return jsonify(d.records(
        q=request.args.get("q", "")[:60], year=int_arg("year", None, d.first_year, d.last_year),
        metric_sort=request.args.get("sort", "country"), order=request.args.get("order", "asc"),
        page=int_arg("page", 1, 1, 10000), per_page=int_arg("per_page", 25, 5, 100)))


@bp.get("/forecast/<path:name>")
def forecast(name):
    t = tw()
    c = country_arg(name)
    metric = metric_arg(request.args.get("metric", "renewable_share"), FORECASTABLE)
    to = int_arg("to", 2030, t.data.last_year + 1, 2040)
    target = request.args.get("target")
    try:
        target = float(target) if target not in (None, "") else None
        return jsonify(t.engine.forecast(c, metric, to, target))
    except ValueError as exc:
        raise ApiError(422, "insufficient_data", str(exc))


@bp.get("/forecast-quality")
def forecast_quality():
    metric = metric_arg(request.args.get("metric", "renewable_share"), FORECASTABLE)
    return jsonify(tw().engine.backtest(metric))
