from flask import Blueprint, current_app, jsonify, request

from ..errors import ApiError, bad_request, not_found
from ..services import recommendations as recs
from ..services import targets
from ..services.data_service import FORECASTABLE, METRICS, RENEWABLE_SOURCES

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


def d_first():
    return tw().data.first_year


def d_last():
    return tw().data.last_year


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
                     "description": m.description, "derived": m.derived, "forecastable": m.key in FORECASTABLE,
                     "latest_year": d.ind.get(m.key, {}).get("latest_year"), "default_year": d.ind.get(m.key, {}).get("broad_year"),
                     "source": d.ind.get(m.key, {}).get("source")}
                    for m in METRICS.values()],
        "provenance": d.provenance()})


@bp.get("/overview")
def overview():
    return jsonify(tw().data.overview(int_arg("year", None, d_first(), d_last())))


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
    year = int_arg("year", d.year_for(metric), d.first_year, d.last_year)
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
    prof["renewables"] = t.data.renewables_country(c)
    prof["recommendations"] = recs.country_recommendations(t.data, c)
    return jsonify(prof)


@bp.get("/compare")
def compare():
    t = tw()
    names = [country_arg(n) for n in request.args.get("countries", "").split(",") if n.strip()]
    if not 1 <= len(names) <= 5:
        raise bad_request("Provide 1 to 5 countries (comma separated).")
    metric = metric_arg(request.args.get("metric", "renewable_elec_share"))
    return jsonify({"metric": metric, "unit": METRICS[metric].unit, "series": t.data.compare(names, metric),
                    "world": t.data.world_average(metric) if metric in t.data.df.columns and METRICS[metric].unit != "TWh"
                    and metric != "co2_kt" else None,
                    "world_note": "population-weighted average of reporting countries, years with broad coverage only"})


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
        res = t.engine.forecast(c, metric, to, target)
        res["official_target"] = targets.official_target(c, metric, res["forecast"])
        return jsonify(res)
    except ValueError as exc:
        raise ApiError(422, "insufficient_data", str(exc))


@bp.get("/forecast-quality")
def forecast_quality():
    metric = metric_arg(request.args.get("metric", "renewable_share"), FORECASTABLE)
    return jsonify(tw().engine.backtest(metric))


# ---------------------------------------------------------------- renewables (source-wise)
@bp.get("/renewables/global")
def renewables_global():
    return jsonify(tw().data.renewables_global())


@bp.get("/renewables/ranking")
def renewables_ranking():
    d = tw().data
    src = request.args.get("source", "solar_twh")
    if src not in RENEWABLE_SOURCES and src != "elec_renewable_twh":
        raise bad_request("Unknown source.", {"allowed": RENEWABLE_SOURCES})
    by = request.args.get("by", "twh")
    if by not in ("twh", "share"):
        raise bad_request("'by' must be twh or share.")
    return jsonify(d.renewables_ranking(src, int_arg("year", None, d.first_year, d.last_year), by, int_arg("limit", 15, 1, 60)))


@bp.get("/renewables/dominant")
def renewables_dominant():
    d = tw().data
    return jsonify(d.dominant_by_country(int_arg("year", None, d.first_year, d.last_year)))


@bp.get("/renewables/country/<path:name>")
def renewables_country(name):
    return jsonify(tw().data.renewables_country(country_arg(name)))


@bp.get("/availability/<path:name>")
def availability(name):
    return jsonify({"country": country_arg(name), "indicators": tw().data.availability(country_arg(name))})


@bp.get("/targets")
def official_targets():
    return jsonify({"targets": targets.all_targets()})
