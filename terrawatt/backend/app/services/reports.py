"""PDF country report built with ReportLab (vector line chart drawn natively)."""
from __future__ import annotations

import io
from datetime import date

from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .data_service import METRICS

GREEN = colors.HexColor("#0f7a4d")


def _chart(history, forecast):
    d = Drawing(170 * mm, 62 * mm)
    lp = LinePlot()
    lp.x, lp.y, lp.width, lp.height = 12 * mm, 10 * mm, 150 * mm, 46 * mm
    lp.data = [[(p["year"], p["value"]) for p in history]] + ([[(history[-1]["year"], history[-1]["value"])] +
                                                              [(r["year"], r["value"]) for r in forecast]] if forecast else [])
    lp.lines[0].strokeColor, lp.lines[0].strokeWidth = GREEN, 1.8
    if forecast:
        lp.lines[1].strokeColor, lp.lines[1].strokeDashArray, lp.lines[1].strokeWidth = colors.HexColor("#d98a00"), (3, 2), 1.6
    lp.xValueAxis.labelTextFormat = "%d"
    lp.xValueAxis.valueSteps = list(range(history[0]["year"], (forecast[-1]["year"] if forecast else history[-1]["year"]) + 1, 5))
    lp.yValueAxis.labels.fontSize = lp.xValueAxis.labels.fontSize = 7
    d.add(lp)
    d.add(String(12 * mm, 58 * mm, "Renewable share of final energy (%) — solid: observed, dashed: model forecast", fontSize=7))
    return d


def country_pdf(profile: dict, history: list, forecast: list, recs: list, provenance: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"TerraWatt report — {profile['info']['country']}")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=GREEN, alignment=0, fontSize=22)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=GREEN)
    small = ParagraphStyle("small", parent=ss["BodyText"], fontSize=8, textColor=colors.grey)
    story = [Paragraph(f"{profile['info']['country']} — energy transition report", h1),
             Paragraph(f"Generated {date.today().isoformat()} by TerraWatt", small), Spacer(1, 6 * mm),
             Paragraph("Key indicators (latest available year)", h2)]
    rows = [["Indicator", "Value", "Year", "Rank"]]
    for c in profile["cards"]:
        if c.get("value") is None:
            continue
        m = METRICS[c["metric"]]
        rows.append([m.label, f"{c['value']:,.1f} {m.unit}", str(c["year"]), f"{c['rank']} of {c['of']}"])
    t = Table(rows, colWidths=[78 * mm, 48 * mm, 18 * mm, 26 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), GREEN), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f7f4")])]))
    story += [t, Spacer(1, 6 * mm)]
    if history:
        story += [Paragraph("Renewable share trend and forecast", h2), _chart(history, forecast)]
    story += [Paragraph("Recommendations", h2)]
    for r in recs:
        story.append(Paragraph(f"<b>{r['title']}</b> ({r['priority']} priority) — {r['evidence']}", ss["BodyText"]))
        story.append(Spacer(1, 2 * mm))
    story += [Spacer(1, 4 * mm), Paragraph(
        f"Data: {provenance['source']}. {provenance['note']} Forecasts are statistical extrapolations validated by a "
        "rolling-origin backtest; they are not guarantees.", small)]
    doc.build(story)
    return buf.getvalue()
