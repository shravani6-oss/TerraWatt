import csv
import io

from flask import Blueprint, Response, current_app, request

from ..services import recommendations as recs
from ..services import reports
from .energy import country_arg, int_arg, metric_arg

bp = Blueprint("exports", __name__, url_prefix="/api/export")


def tw():
    return current_app.extensions["tw"]


def _csv(rows, header, filename):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(header)
    w.writerows(rows)
    return Response(out.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})


@bp.get("/rankings.csv")
def rankings_csv():
    d = tw().data
    metric = metric_arg(request.args.get("metric", "renewable_share"))
    year = int_arg("year", None, d.first_year, d.last_year)
    res = d.ranking(metric, year, request.args.get("q", "")[:60], request.args.get("sort", "desc"))
    return _csv([[r["rank"], r["country"], r["value"], r["change"]] for r in res["rows"]],
                ["rank", "country", metric, "change_vs_previous_year"], f"terrawatt-{metric}-{res['year']}.csv")


@bp.get("/country/<path:name>.csv")
def country_csv(name):
    c = country_arg(name)
    df = tw().data.df
    sub = df[df["country"] == c]
    return _csv(sub.round(4).fillna("").values.tolist(), list(sub.columns), f"terrawatt-{c.replace(' ', '_')}.csv")


@bp.get("/country/<path:name>.pdf")
def country_pdf(name):
    t = tw()
    c = country_arg(name)
    history = t.data.series(c, "renewable_share")
    try:
        forecast = t.engine.forecast(c, "renewable_share", 2030)["forecast"]
    except ValueError:
        forecast = []
    pdf = reports.country_pdf(t.data.profile(c), history, forecast, recs.country_recommendations(t.data, c), t.data.provenance())
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=terrawatt-{c.replace(' ', '_')}.pdf"})
