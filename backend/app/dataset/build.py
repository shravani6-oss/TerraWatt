"""Build and validate the unified TerraWatt dataset (2000-2025).

    python -m backend.manage build-data --owid-energy <owid-energy-data.csv> --owid-co2 <owid-co2-data.csv>

Sources (all public):
  * World Bank / IEA indicators via the Kaggle "Global Data on Sustainable Energy" table (2000-2020):
    electricity access, clean-cooking access, renewable share of FINAL energy (SDG 7.2.1), energy intensity,
    GDP per capita / growth, country coordinates.
  * Ember yearly electricity data + Energy Institute Statistical Review via Our World in Data (energy-data repo):
    generation by source (solar, wind, hydro, bioenergy, other), shares, grid carbon intensity.
  * Global Carbon Project via Our World in Data (co2-data repo): territorial CO2 and per-person CO2.

Rules enforced here:
  * No value is ever carried forward or extrapolated: a year with no source observation stays empty.
  * Each indicator keeps its own source; indicators with different definitions are NEVER merged into one series
    (e.g. renewable share of final energy [World Bank] vs share of primary energy [Energy Institute]).
  * Exactly one row per (country, year); countries are matched by exact standardised name.
  * Source-vs-source overlap is compared and reported rather than silently trusted.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

FIRST_YEAR, LAST_YEAR = 2000, 2025

# Sovereign states present in OWID but absent from the Kaggle table. Coordinates are approximate
# geographic centres used ONLY to place map dots (not a data source for any analysis).
EXTRA_COUNTRIES = {
    "Bolivia": (-16.29, -63.59), "Brunei": (4.54, 114.73), "Cape Verde": (16.0, -24.01), "Cote d'Ivoire": (7.54, -5.55),
    "Democratic Republic of Congo": (-4.04, 21.76), "East Timor": (-8.87, 125.73), "Iran": (32.43, 53.69),
    "Laos": (19.86, 102.5), "Micronesia (country)": (7.43, 150.55), "Moldova": (47.41, 28.37),
    "North Korea": (40.34, 127.51), "Palestine": (31.95, 35.23), "Russia": (61.52, 105.32),
    "South Korea": (35.91, 127.77), "Syria": (34.8, 38.99), "Taiwan": (23.7, 120.96), "Tanzania": (-6.37, 34.89),
    "Venezuela": (6.42, -66.59), "Vietnam": (14.06, 108.28),
}

KAGGLE_RENAME = {
    "access to electricity (% of population)": "electricity_access",
    "access to clean fuels for cooking": "clean_cooking_access",
    "renewable energy share in the total final energy consumption (%)": "renewable_share",
    "primary energy consumption per capita (kwh/person)": "energy_per_capita_kwh",
    "energy intensity level of primary energy (mj/$2017 ppp gdp)": "energy_intensity",
    "gdp_growth": "gdp_growth", "gdp_per_capita": "gdp_per_capita",
    "density (p/km2)": "density", "land area(km2)": "land_area_km2", "latitude": "latitude", "longitude": "longitude",
    # kept only to cross-validate against OWID, never published:
    "electricity from fossil fuels (twh)": "_k_fossil", "electricity from nuclear (twh)": "_k_nuclear",
    "electricity from renewables (twh)": "_k_renew", "value_co2_emissions_kt_by_country": "_k_co2_kt",
}
OWID_ENERGY_MAP = {
    "population": "population", "electricity_generation": "total_elec_twh", "fossil_electricity": "elec_fossil_twh",
    "nuclear_electricity": "elec_nuclear_twh", "renewables_electricity": "elec_renewable_twh",
    "solar_electricity": "solar_twh", "wind_electricity": "wind_twh", "hydro_electricity": "hydro_twh",
    "biofuel_electricity": "bioenergy_twh", "other_renewable_exc_biofuel_electricity": "other_renew_twh",
    "renewables_share_elec": "renewable_elec_share", "low_carbon_share_elec": "low_carbon_elec_pct",
    "carbon_intensity_elec": "grid_intensity", "greenhouse_gas_emissions": "power_ghg_mt",
    "renewables_share_energy": "renewables_share_primary",
}
OWID_CO2_MAP = {"co2": "co2_mt", "co2_per_capita": "co2_per_capita_t"}

# indicator -> (label, unit, source key, definition, higher_is_better)
SOURCES = {
    "wb": "World Bank / IEA indicators (Kaggle: Global Data on Sustainable Energy, 2000-2020)",
    "ember": "Ember Yearly Electricity Data (2026) & Energy Institute Statistical Review (2025), via Our World in Data",
    "ei": "Energy Institute Statistical Review of World Energy (2025), via Our World in Data",
    "gcp": "Global Carbon Project (Global Carbon Budget), via Our World in Data",
}
INDICATORS = {
    "renewable_share": ("Renewable share of final energy", "%", "wb", "Renewables in total FINAL energy consumption (SDG 7.2.1, incl. traditional biomass)."),
    "renewables_share_primary": ("Renewables share of primary energy", "%", "ei", "Renewables in PRIMARY energy (substitution method). Different definition from SDG 7.2.1."),
    "renewable_elec_share": ("Renewable share of electricity", "%", "ember", "Renewable generation ÷ total electricity generation."),
    "low_carbon_elec_pct": ("Low-carbon electricity", "%", "ember", "Renewables + nuclear share of electricity generation."),
    "total_elec_twh": ("Electricity generation", "TWh", "ember", "Total annual electricity generation."),
    "elec_fossil_twh": ("Fossil electricity", "TWh", "ember", "Generation from coal, gas, oil and other fossil sources."),
    "elec_nuclear_twh": ("Nuclear electricity", "TWh", "ember", "Generation from nuclear power."),
    "elec_renewable_twh": ("Renewable electricity", "TWh", "ember", "Sum of solar, wind, hydro, bioenergy and other renewables."),
    "solar_twh": ("Solar electricity", "TWh", "ember", "Generation from solar PV and solar thermal."),
    "wind_twh": ("Wind electricity", "TWh", "ember", "Generation from onshore and offshore wind."),
    "hydro_twh": ("Hydropower electricity", "TWh", "ember", "Generation from hydropower (excl. pumped storage)."),
    "bioenergy_twh": ("Bioenergy electricity", "TWh", "ember", "Generation from biomass, biogas and other bioenergy."),
    "other_renew_twh": ("Geothermal & other renewables", "TWh", "ember", "Other renewables excluding bioenergy: geothermal, wave and tidal (not reported separately)."),
    "grid_intensity": ("Grid carbon intensity", "g CO₂e / kWh", "ember", "Lifecycle greenhouse gases per kWh of generated electricity (excludes grid losses)."),
    "power_ghg_mt": ("Power-sector emissions", "Mt CO₂e", "ember", "Lifecycle emissions from electricity generation."),
    "co2_mt": ("CO₂ emissions", "Mt", "gcp", "Territorial fossil-fuel and industry CO₂ (+ cement)."),
    "co2_per_capita_t": ("CO₂ per person", "t / person", "gcp", "Territorial CO₂ divided by population."),
    "population": ("Population", "people", "ember", "Population (OWID, from UN WPP / Gapminder / HYDE)."),
    "electricity_access": ("Access to electricity", "% of population", "wb", "Population with access to electricity (SDG 7.1.1)."),
    "clean_cooking_access": ("Access to clean cooking fuels", "% of population", "wb", "Population primarily using clean fuels for cooking (SDG 7.1.2)."),
    "energy_intensity": ("Energy intensity", "MJ / $2017 PPP", "wb", "Primary energy per unit of GDP (SDG 7.3.1)."),
    "energy_per_capita_kwh": ("Primary energy per person", "kWh", "wb", "Primary energy consumption per capita."),
    "gdp_per_capita": ("GDP per capita", "US$", "wb", "GDP per person."),
    "gdp_growth": ("GDP growth", "% / year", "wb", "Annual GDP growth."),
}
# Kaggle rows that are not countries/territories with usable data (reported in validation_report.json)
EXCLUDED = {"French Guiana": "single 2000 row, no coordinates, no indicators (overseas department of France)"}
STATIC = ["density", "land_area_km2", "latitude", "longitude"]


def _norm(c: str) -> str:
    return " ".join(str(c).replace("\\n", " ").replace("\n", " ").split()).lower()


def _read_owid(path: Path, mapping: dict, universe: set[str]) -> pd.DataFrame:
    df = pd.read_csv(path, usecols=lambda c: c in {"country", "year", "iso_code", *mapping})
    df = df[df["country"].isin(universe) & df["year"].between(FIRST_YEAR, LAST_YEAR)].copy()
    return df.rename(columns=mapping)


def build(kaggle_csv: Path, owid_energy_csv: Path, owid_co2_csv: Path, out_dir: Path, source_info: dict | None = None) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    k = pd.read_csv(kaggle_csv)
    k.columns = [KAGGLE_RENAME.get(_norm(c), c if c in ("Entity", "Year") else _norm(c)) for c in k.columns]
    k = k.rename(columns={"Entity": "country", "Year": "year"})
    k["country"] = k["country"].astype(str).str.strip()
    if "density" in k:
        k["density"] = pd.to_numeric(k["density"].astype(str).str.replace(",", ""), errors="coerce")
    k = k[~k["country"].isin(EXCLUDED)]
    universe = set(k["country"].unique()) | set(EXTRA_COUNTRIES)

    en = _read_owid(owid_energy_csv, {**OWID_ENERGY_MAP}, universe)
    co = _read_owid(owid_co2_csv, {**OWID_CO2_MAP}, universe)
    iso = pd.concat([en[["country", "iso_code"]], co[["country", "iso_code"]]]).dropna().drop_duplicates("country").set_index("country")["iso_code"]

    # ---- skeleton: one row per universe country x year (guarantees no duplicates, no accidental extension)
    grid = pd.MultiIndex.from_product([sorted(universe), range(FIRST_YEAR, LAST_YEAR + 1)], names=["country", "year"]).to_frame(index=False)
    keep_k = ["country", "year", *[c for c in ("electricity_access", "clean_cooking_access", "renewable_share", "energy_per_capita_kwh",
              "energy_intensity", "gdp_per_capita", "gdp_growth", "_k_fossil", "_k_nuclear", "_k_renew", "_k_co2_kt") if c in k]]
    kk = k[keep_k].drop_duplicates(["country", "year"])
    df = grid.merge(kk, on=["country", "year"], how="left")
    df = df.merge(en.drop(columns=["iso_code"]).drop_duplicates(["country", "year"]), on=["country", "year"], how="left")
    df = df.merge(co.drop(columns=["iso_code", "population"], errors="ignore").drop_duplicates(["country", "year"]), on=["country", "year"], how="left")
    static = k.groupby("country")[[c for c in STATIC if c in k]].first()
    for name, (lat, lon) in EXTRA_COUNTRIES.items():
        static.loc[name, ["latitude", "longitude"]] = [lat, lon]
    df = df.merge(static.reset_index(), on="country", how="left")
    df["iso3"] = df["country"].map(iso)
    df["co2_kt"] = df["co2_mt"] * 1000
    df["gdp_per_capita"] = df["gdp_per_capita"]  # World Bank only; OWID gdp (Maddison) is a different series and not merged

    # ---- validation ------------------------------------------------------------------------
    report: dict = {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "errors": [], "warnings": [], "checks": {}, "excluded_entities": EXCLUDED, "added_countries": sorted(EXTRA_COUNTRIES)}
    err, warn = report["errors"], report["warnings"]
    if df.duplicated(["country", "year"]).any():
        err.append("duplicate country-year rows")
    if df["iso3"].isna().any():
        err.append(f"countries without ISO code: {sorted(df[df.iso3.isna()].country.unique())}")
    if df[["latitude", "longitude"]].isna().any().any():
        err.append("countries without coordinates")
    pct_cols = ["renewable_share", "renewables_share_primary", "renewable_elec_share", "low_carbon_elec_pct", "electricity_access", "clean_cooking_access"]
    for c in pct_cols:
        bad = df[(df[c] < -0.01) | (df[c] > 100.01)]
        if len(bad):
            err.append(f"{c}: {len(bad)} values outside 0-100")
    for c in ["total_elec_twh", "elec_fossil_twh", "elec_renewable_twh", "solar_twh", "wind_twh", "hydro_twh", "bioenergy_twh", "co2_mt", "population"]:
        if (df[c] < -1e-9).any():
            err.append(f"{c}: negative values")
    parts = df[["solar_twh", "wind_twh", "hydro_twh", "bioenergy_twh", "other_renew_twh"]].sum(axis=1, min_count=1)
    resid = (parts - df["elec_renewable_twh"]).abs()
    report["checks"]["renewable_components_sum_to_total_max_abs_diff_twh"] = float(np.nanmax(resid)) if resid.notna().any() else None
    if np.nanmax(resid) > 0.05:
        err.append("renewable sources do not add up to renewable total")
    gen = df[["elec_fossil_twh", "elec_nuclear_twh", "elec_renewable_twh"]].sum(axis=1, min_count=3)
    over = (gen - df["total_elec_twh"]).abs() / df["total_elec_twh"].where(df["total_elec_twh"] > 0)
    report["checks"]["fossil+nuclear+renewable_vs_total_share_of_rows_off_by_over_2pct"] = float((over > 0.02).mean())
    # cross-source agreement on overlapping years (Kaggle vs OWID): reported, not hidden
    ov = {}
    for kc, oc_ in (("_k_renew", "elec_renewable_twh"), ("_k_fossil", "elec_fossil_twh"), ("_k_nuclear", "elec_nuclear_twh")):
        m = df[[kc, oc_]].dropna()
        m = m[(m[kc].abs() + m[oc_].abs()) > 1]
        rel = ((m[kc] - m[oc_]).abs() / np.maximum(m[kc].abs(), m[oc_].abs()))
        ov[oc_] = {"overlap_rows": int(len(m)), "median_rel_diff": float(rel.median()), "share_rows_within_5pct": float((rel <= 0.05).mean())}
    m = df[["_k_co2_kt", "co2_kt"]].dropna()
    rel = (m["_k_co2_kt"] - m["co2_kt"]).abs() / np.maximum(m["_k_co2_kt"].abs(), m["co2_kt"].abs())
    ov["co2_kt"] = {"overlap_rows": int(len(m)), "median_rel_diff": float(rel.median()), "share_rows_within_5pct": float((rel <= 0.05).mean())}
    report["checks"]["kaggle_vs_owid_overlap"] = ov
    for k_, v in ov.items():
        if v["share_rows_within_5pct"] < 0.8:
            warn.append(f"{k_}: only {v['share_rows_within_5pct']:.0%} of overlapping rows agree within 5% (OWID values are used)")
    df = df.drop(columns=[c for c in df if c.startswith("_k_")])
    # world-level sanity vs well-known magnitudes
    w = df[df.year == 2023]
    gen23 = w["total_elec_twh"].sum()
    report["checks"]["world_2023_generation_twh_covered_countries"] = float(gen23)
    report["checks"]["world_2023_renewable_share_pct"] = float(w["elec_renewable_twh"].sum() / gen23 * 100)
    report["checks"]["world_2023_co2_gt_covered_countries"] = float(w["co2_mt"].sum() / 1000)

    # ---- catalog: per-indicator provenance + coverage ----------------------------------------
    cat = {}
    for key, (label, unit, src, definition) in INDICATORS.items():
        s = df.dropna(subset=[key])
        by_year = s.groupby("year")["country"].nunique()
        n_all = df["country"].nunique()
        full = by_year[by_year >= 0.5 * by_year.max()]
        cat[key] = {"label": label, "unit": unit, "source": SOURCES[src], "definition": definition,
                    "first_year": int(s.year.min()), "latest_year": int(s.year.max()),
                    "latest_year_broad_coverage": int(full.index.max()) if len(full) else None,
                    "countries_with_data": int(s.country.nunique()), "countries_total": int(n_all),
                    "countries_in_latest_year": int(by_year.get(s.year.max(), 0)),
                    "coverage_by_year": {int(y): int(n) for y, n in by_year.items()}}
    # sanity: no indicator may report beyond what its source holds
    for key in ("renewable_share", "electricity_access", "clean_cooking_access"):
        if cat[key]["latest_year"] > 2020:
            err.append(f"{key} extends beyond the World Bank/Kaggle table (possible fabricated extension)")
    report["checks"]["rows"] = int(len(df))
    report["checks"]["countries"] = int(df.country.nunique())
    report["checks"]["years"] = [FIRST_YEAR, LAST_YEAR]
    report["ok"] = not err

    cols = ["country", "iso3", "year", *INDICATORS, "co2_kt", *STATIC]
    cols = [c for c in dict.fromkeys(cols) if c in df]
    out_csv = out_dir / "terrawatt_dataset.csv"
    if report["ok"]:
        df[cols].sort_values(["country", "year"]).round(6).to_csv(out_csv, index=False)
        meta = {"built_at": report["built_at"], "indicators": cat, "sources": SOURCES, "inputs": source_info or {},
                "sha256": hashlib.sha256(out_csv.read_bytes()).hexdigest(), "policy": [
                    "Missing values stay missing: no forward-fill, interpolation across source gaps, or extension past a source's last year.",
                    "Indicators with different definitions are kept as separate series.",
                    "One row per country-year; country names standardised to Our World in Data names (Kaggle names are a subset)."]}
        (out_dir / "indicator_catalog.json").write_text(json.dumps(meta, indent=1))
    (out_dir / "validation_report.json").write_text(json.dumps(report, indent=1))
    return report
