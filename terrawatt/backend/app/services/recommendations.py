"""Rule-based, evidence-quoting country recommendations. Every item cites the numbers that triggered it."""
from __future__ import annotations

from .data_service import EnergyData


def country_recommendations(data: EnergyData, country: str) -> list[dict]:
    def val(m):
        lat = data.latest(country, m)
        return lat[1] if lat else None

    def pct(m):
        return data.percentile_in(m, country)

    recs = []
    rs, rs_p = val("renewable_elec_share"), pct("renewable_elec_share")
    if rs is not None and rs < 30:
        recs.append(("high", "Scale up grid-connected renewables",
                     f"Only {rs:.0f}% of electricity is renewable (lower than {100 - rs_p:.0f}% of countries). "
                     "Competitive auctions for solar and wind, plus grid upgrades, are the usual first levers.", "supply"))
    low_c = val("low_carbon_elec_pct")
    fossil_share = None
    f, n, r = val("elec_fossil_twh"), val("elec_nuclear_twh"), val("elec_renewable_twh")
    if f is not None and r is not None:
        tot = f + (n or 0) + r
        fossil_share = f / tot * 100 if tot else None
    if fossil_share is not None and fossil_share > 70:
        recs.append(("high", "Plan a fossil-generation phase-down",
                     f"{fossil_share:.0f}% of generation is fossil-fired. Retiring the oldest, least efficient plants first "
                     "cuts emissions fastest.", "supply"))
    ei, ei_p = val("energy_intensity"), pct("energy_intensity")
    if ei is not None and ei_p is not None and ei_p > 66:
        recs.append(("medium", "Invest in energy efficiency",
                     f"Energy intensity is {ei:.1f} MJ per $ of GDP, higher than {ei_p:.0f}% of countries. Efficiency standards "
                     "for buildings, motors and appliances reduce demand before any new supply is needed.", "demand"))
    cc = val("clean_cooking_access")
    if cc is not None and cc < 70:
        recs.append(("high", "Expand clean cooking access",
                     f"{100 - cc:.0f}% of the population still cooks with polluting fuels. LPG, electric and improved "
                     "biomass stoves cut indoor air pollution and deforestation.", "access"))
    ea = val("electricity_access")
    if ea is not None and ea < 95:
        recs.append(("high", "Close the electricity access gap",
                     f"{100 - ea:.1f}% of people have no electricity. Solar mini-grids and home systems are typically the "
                     "cheapest route to remote households.", "access"))
    cpc = val("co2_per_capita_t")
    if cpc is not None and cpc > 8:
        recs.append(("medium", "Target high per-person emissions",
                     f"Estimated {cpc:.1f} t CO₂ per person. Electrifying transport and heating while decarbonising the grid "
                     "addresses the largest sources together.", "demand"))
    slope = None
    yrs, vals = data.series_array(country, "renewable_share")
    if len(yrs) >= 6:
        slope = float(vals[-1] - vals[-6]) / (yrs[-1] - yrs[-6])
        if slope < -0.3:
            recs.append(("medium", "Reverse the declining renewable share",
                         f"Renewable share fell about {abs(slope):.1f} points a year recently, often because total demand "
                         "outgrows new clean supply or biomass use is falling without replacement.", "trend"))
        elif slope > 0.5:
            recs.append(("low", "Keep the momentum",
                         f"Renewable share is rising about {slope:.1f} points a year. Protect it with grid-flexibility "
                         "investment (storage, interconnection) as variable renewables grow.", "trend"))
    if not recs:
        recs.append(("low", "Maintain and diversify",
                     "Indicators are healthy against peers. Focus on storage, grid flexibility and demand response.", "supply"))
    order = {"high": 0, "medium": 1, "low": 2}
    recs.sort(key=lambda x: order[x[0]])
    return [{"priority": p, "title": t, "evidence": e, "category": c} for p, t, e, c in recs]
