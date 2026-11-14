"""Exact electricity-mix scenario accounting (no machine learning involved).

Given a country's reported generation by source in its latest electricity year, apply multipliers to each
renewable source (and nuclear) and recompute the generation mix, renewable share of electricity, grid carbon
intensity and power-sector emissions.

Assumptions (all disclosed in the API response):
  * Demand is held constant: extra low-carbon generation displaces fossil generation 1:1, down to zero fossil.
    Anything beyond that is reported as `surplus_twh` (exports / storage / curtailment), not silently dropped.
  * `fossil_reduction_pct` retires that share of the remaining fossil generation and replaces it with renewables in
    proportion to the country's current renewable mix (solar/wind 50:50 if it has no renewables).
  * Lifecycle intensities for non-fossil sources are IPCC AR5 median values (g CO2e/kWh). The country's fossil
    intensity is CALIBRATED so that the baseline reproduces Ember's reported power-sector emissions exactly.
"""
from __future__ import annotations

import math

from .data_service import RENEWABLE_SOURCES, SOURCE_LABELS, EnergyData

LIFECYCLE_G_PER_KWH = {"solar_twh": 48.0, "wind_twh": 11.0, "hydro_twh": 24.0, "bioenergy_twh": 230.0,
                       "other_renew_twh": 38.0, "elec_nuclear_twh": 12.0}
MIX_KEYS = ["solar_mult", "wind_mult", "hydro_mult", "bio_mult", "other_mult", "nuclear_mult", "fossil_reduction_pct"]
MULT_TO_SOURCE = {"solar_mult": "solar_twh", "wind_mult": "wind_twh", "hydro_mult": "hydro_twh",
                  "bio_mult": "bioenergy_twh", "other_mult": "other_renew_twh", "nuclear_mult": "elec_nuclear_twh"}

PRESETS = {
    "high_solar": {"label": "High solar adoption", "mix": {"solar_mult": 3.0},
                   "text": "Triples solar generation; the extra electricity displaces fossil generation."},
    "high_wind": {"label": "High wind adoption", "mix": {"wind_mult": 3.0},
                  "text": "Triples wind generation; the extra electricity displaces fossil generation."},
    "reduced_fossil": {"label": "Reduced fossil dependence", "mix": {"fossil_reduction_pct": 30.0},
                       "text": "Retires 30% of fossil generation, replaced by renewables in today's renewable mix."},
    "improved_access": {"label": "Improved electricity access", "access_close_gap_pct": 50.0,
                        "text": "Closes half of the remaining gap to universal electricity access (model input, not the mix)."},
}


def baseline(data: EnergyData, country: str) -> dict | None:
    year = data.year_for("elec_renewable_twh")
    s = data._by_country[country]
    # latest year (<= broad year... or later if the country reports it) where generation by source is observed
    ok = s.dropna(subset=["total_elec_twh", "elec_fossil_twh", "elec_renewable_twh"])
    if ok.empty:
        return None
    y = int(ok.index.max())
    r = ok.loc[y]
    return {"year": y, "row": r}


def run(data: EnergyData, country: str, mix: dict) -> dict:
    b = baseline(data, country)
    if b is None:
        raise ValueError("No electricity generation data for this country.")
    r, year = b["row"], b["year"]
    g = lambda k: float(r[k]) if k in r and r[k] == r[k] else 0.0
    base = {k: g(k) for k in [*RENEWABLE_SOURCES, "elec_nuclear_twh", "elec_fossil_twh"]}
    for k in mix:
        if k not in MIX_KEYS:
            raise ValueError(f"Unknown mix input '{k}'.")
    mults = {k: float(mix.get(k, 1.0)) for k in MULT_TO_SOURCE}
    for k, v in mults.items():
        if not (0 <= v <= 10) or not math.isfinite(v):
            raise ValueError(f"{k} must be between 0 and 10.")
    red = float(mix.get("fossil_reduction_pct", 0.0))
    if not (0 <= red <= 100) or not math.isfinite(red):
        raise ValueError("fossil_reduction_pct must be between 0 and 100.")

    new = dict(base)
    for m, src in MULT_TO_SOURCE.items():
        new[src] = base[src] * mults[m]
    extra = sum(new[k] - base[k] for k in new if k != "elec_fossil_twh")
    fossil = base["elec_fossil_twh"] - extra               # constant demand: displace (or backfill) fossil
    surplus = 0.0
    if fossil < 0:
        surplus, fossil = -fossil, 0.0
    shift = fossil * red / 100
    fossil -= shift
    if shift > 0:
        ren_total = sum(new[k] for k in RENEWABLE_SOURCES)
        weights = ({k: new[k] / ren_total for k in RENEWABLE_SOURCES} if ren_total > 0
                   else {"solar_twh": 0.5, "wind_twh": 0.5})
        for k, w in weights.items():
            new[k] += shift * w
    new["elec_fossil_twh"] = fossil

    def totals(d):
        ren = sum(d[k] for k in RENEWABLE_SOURCES)
        tot = ren + d["elec_nuclear_twh"] + d["elec_fossil_twh"]
        return ren, tot

    # calibrate fossil intensity on the baseline (g/kWh == Mt per TWh)
    non_fossil_base = sum(base[k] * LIFECYCLE_G_PER_KWH[k] for k in LIFECYCLE_G_PER_KWH) / 1000   # Mt
    reported = r.get("power_ghg_mt")
    calibrated = True
    if reported == reported and reported is not None and base["elec_fossil_twh"] > 0:
        ef_fossil = (float(reported) - non_fossil_base) / base["elec_fossil_twh"] * 1000
        if not 250 <= ef_fossil <= 1300:        # implausible -> use the generic gas/coal blend instead of a wild value
            ef_fossil, calibrated = 700.0, False
    else:
        ef_fossil, calibrated = 700.0, False

    def emissions(d):
        return (d["elec_fossil_twh"] * ef_fossil + sum(d[k] * LIFECYCLE_G_PER_KWH[k] for k in LIFECYCLE_G_PER_KWH)) / 1000

    def summary(d):
        ren, tot = totals(d)
        em = emissions(d)
        return {"renewable_twh": round(ren, 2), "total_twh": round(tot, 2),
                "renewable_share": round(ren / tot * 100, 2) if tot else None,
                "fossil_share": round(d["elec_fossil_twh"] / tot * 100, 2) if tot else None,
                "grid_intensity": round(em / tot * 1000, 1) if tot else None,
                "emissions_mt": round(em, 2),
                "by_source": [{"key": k, "label": SOURCE_LABELS.get(k, "Nuclear" if k == "elec_nuclear_twh" else "Fossil"),
                               "twh": round(d[k], 2)} for k in [*RENEWABLE_SOURCES, "elec_nuclear_twh", "elec_fossil_twh"]]}

    if totals(base)[1] <= 0:
        raise ValueError("This country reports zero electricity generation, so no mix scenario can be computed.")
    b_sum, s_sum = summary(base), summary(new)
    changed = []
    for m, src in MULT_TO_SOURCE.items():
        if abs(mults[m] - 1) > 1e-9:
            changed.append({"input": m, "label": f"{SOURCE_LABELS.get(src, 'Nuclear')} generation × {mults[m]:g}",
                            "from_twh": round(base[src], 2), "to_twh": round(new[src], 2)})
    if red:
        changed.append({"input": "fossil_reduction_pct", "label": f"{red:g}% of fossil generation replaced by renewables",
                        "from_twh": round(base["elec_fossil_twh"], 2), "to_twh": round(new["elec_fossil_twh"], 2)})
    d_em = s_sum["emissions_mt"] - b_sum["emissions_mt"]
    return {"year": year, "baseline": b_sum, "scenario": s_sum, "changed": changed,
            "delta": {"renewable_share_pp": round(s_sum["renewable_share"] - b_sum["renewable_share"], 2),
                      "grid_intensity": round(s_sum["grid_intensity"] - b_sum["grid_intensity"], 1),
                      "emissions_mt": round(d_em, 2),
                      "emissions_pct": round(d_em / b_sum["emissions_mt"] * 100, 1) if b_sum["emissions_mt"] else None},
            "surplus_twh": round(surplus, 2), "fossil_intensity_g_per_kwh": round(ef_fossil, 0),
            "fossil_intensity_calibrated": calibrated,
            "assumptions": ["Electricity demand held constant; extra low-carbon generation displaces fossil generation.",
                            "Non-fossil lifecycle intensities are IPCC AR5 medians; fossil intensity is calibrated to Ember's reported "
                            "power-sector emissions for the baseline year." if calibrated else
                            "Reported emissions were unusable for calibration, so a generic fossil intensity (700 g/kWh) was assumed.",
                            "Accounting arithmetic only: no grid-stability, cost, build-time or policy feasibility is modelled."]}


def baseline_summary(data: EnergyData, country: str) -> dict | None:
    """Neutral (no-change) scenario: what the UI shows as the electricity baseline."""
    try:
        r = run(data, country, {})
    except ValueError:
        return None
    return {"year": r["year"], **r["baseline"]}
