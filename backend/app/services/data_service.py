"""Dataset access and analytics on the validated TerraWatt dataset (data/processed/terrawatt_dataset.csv).

Built by `python -m backend.manage build-data` from World Bank/IEA indicators (to 2020), Ember + Energy Institute
electricity data and Global Carbon Project CO2 (to 2025). Nothing is simulated, carried forward or extrapolated:
every indicator has its OWN latest reporting year (see `EnergyData.ind`) and that year is disclosed with each figure.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

RENEWABLE_SOURCES = ["solar_twh", "wind_twh", "hydro_twh", "bioenergy_twh", "other_renew_twh"]
SOURCE_LABELS = {"solar_twh": "Solar", "wind_twh": "Wind", "hydro_twh": "Hydropower", "bioenergy_twh": "Bioenergy",
                 "other_renew_twh": "Geothermal & other"}


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    unit: str
    higher_is_better: bool | None   # None = neutral
    description: str
    derived: bool = False
    bounded_pct: bool = False


_M = [
    Metric("renewable_share", "Renewable share of final energy", "%", True,
           "Renewables in total FINAL energy consumption (SDG 7.2.1, incl. traditional biomass). World Bank; ends 2020.", bounded_pct=True),
    Metric("renewable_elec_share", "Renewable share of electricity", "%", True,
           "Renewable generation ÷ total electricity generation (Ember).", bounded_pct=True),
    Metric("renewables_share_primary", "Renewables share of primary energy", "%", True,
           "Renewables in PRIMARY energy, substitution method (Energy Institute; ~78 countries). Not comparable with final-energy share.", bounded_pct=True),
    Metric("low_carbon_elec_pct", "Low-carbon electricity", "%", True, "Renewables + nuclear share of electricity (Ember).", bounded_pct=True),
    Metric("electricity_access", "Access to electricity", "% of population", True, "Population with access to electricity (World Bank; ends 2020).", bounded_pct=True),
    Metric("clean_cooking_access", "Access to clean cooking fuels", "% of population", True, "Population primarily using clean cooking fuels (World Bank; ends 2020).", bounded_pct=True),
    Metric("total_elec_twh", "Electricity generation", "TWh", None, "Total annual electricity generation (Ember)."),
    Metric("elec_renewable_twh", "Renewable electricity", "TWh", True, "Solar + wind + hydro + bioenergy + other renewables."),
    Metric("solar_twh", "Solar electricity", "TWh", True, "Generation from solar."),
    Metric("wind_twh", "Wind electricity", "TWh", True, "Generation from wind."),
    Metric("hydro_twh", "Hydropower electricity", "TWh", True, "Generation from hydropower."),
    Metric("bioenergy_twh", "Bioenergy electricity", "TWh", True, "Generation from bioenergy."),
    Metric("other_renew_twh", "Geothermal & other renewables", "TWh", True, "Geothermal, wave and tidal (reported together by Ember)."),
    Metric("elec_fossil_twh", "Fossil electricity", "TWh", False, "Generation from fossil fuels."),
    Metric("elec_nuclear_twh", "Nuclear electricity", "TWh", None, "Generation from nuclear."),
    Metric("co2_kt", "CO₂ emissions", "kt", False, "Territorial fossil CO₂ (Global Carbon Project)."),
    Metric("co2_per_capita_t", "CO₂ per person", "t / person", False, "Territorial CO₂ ÷ population (Global Carbon Project)."),
    Metric("grid_intensity", "Grid carbon intensity", "g CO₂e / kWh", False, "Lifecycle emissions per kWh generated (Ember)."),
    Metric("power_ghg_mt", "Power-sector emissions", "Mt CO₂e", False, "Lifecycle emissions from electricity generation (Ember)."),
    Metric("energy_per_capita_kwh", "Primary energy per person", "kWh", None, "Primary energy per capita (World Bank/IEA; ends 2020)."),
    Metric("energy_intensity", "Energy intensity", "MJ / $2017 PPP", False, "Primary energy per unit GDP; lower is more efficient."),
    Metric("gdp_per_capita", "GDP per capita", "US$", None, "GDP per person (World Bank; ends 2020)."),
]
METRICS: dict[str, Metric] = {m.key: m for m in _M}
FORECASTABLE = ["renewable_share", "electricity_access", "clean_cooking_access", "low_carbon_elec_pct",
                "renewable_elec_share", "co2_kt", "solar_twh", "wind_twh"]


class DatasetError(Exception):
    pass


def load_frame(path: Path) -> pd.DataFrame:
    if not Path(path).exists():
        raise DatasetError(f"Dataset not found at {path}. Run: python -m backend.manage build-data")
    df = pd.read_csv(path)
    missing = [c for c in ("country", "year", "renewable_share", "renewable_elec_share") if c not in df.columns]
    if missing:
        raise DatasetError(f"Dataset is missing required columns: {missing}")
    df["country"] = df["country"].astype(str).str.strip()
    df = df.dropna(subset=["year"]).copy()
    df["year"] = df["year"].astype(int)
    if df.duplicated(["country", "year"]).any():
        raise DatasetError("Dataset contains duplicate country-year rows.")
    return df.sort_values(["country", "year"]).reset_index(drop=True)


def _clean(v):
    """JSON-safe scalar: NaN/inf -> None, numpy -> python, rounded."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    if not np.isfinite(f):
        return None
    return round(f, 4)


class EnergyData:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.df = load_frame(self.path)
        self.countries = sorted(self.df["country"].unique())
        self.years = sorted(int(y) for y in self.df["year"].unique())
        self.first_year, self.last_year = self.years[0], self.years[-1]
        self.coords = self.df.groupby("country")[["latitude", "longitude"]].first().to_dict("index")
        self.iso3 = self.df.groupby("country")["iso3"].first().to_dict()
        self._by_country = {c: g.set_index("year") for c, g in self.df.groupby("country")}
        cat_path = self.path.parent / "indicator_catalog.json"
        self.catalog = json.loads(cat_path.read_text()) if cat_path.exists() else {}
        self.ind = {k: self._indicator_years(k) for k in METRICS if k in self.df.columns}
        # headline year = latest year in which >=50% of reporting countries have the electricity indicators
        self.headline_year = self.ind["renewable_elec_share"]["broad_year"]

    def _indicator_years(self, metric: str) -> dict:
        s = self.df.dropna(subset=[metric])
        by_year = s.groupby("year")["country"].nunique()
        broad = by_year[by_year >= 0.5 * by_year.max()]
        meta = self.catalog.get("indicators", {}).get(metric, {})
        return {"first_year": int(by_year.index.min()), "latest_year": int(by_year.index.max()),
                "broad_year": int(broad.index.max()), "n_latest": int(by_year.iloc[-1]),
                "n_broad": int(by_year.get(broad.index.max(), 0)), "n_countries": int(s.country.nunique()),
                "source": meta.get("source"), "definition": meta.get("definition")}

    def year_for(self, metric: str) -> int:
        """Indicator-specific default reporting year (latest year with broad country coverage)."""
        return self.ind[metric]["broad_year"]

    # ------------------------------------------------------------------ basics
    def has_country(self, country: str) -> bool:
        return country in self._by_country

    def canonical(self, country: str) -> str | None:
        low = country.strip().lower()
        for c in self.countries:
            if c.lower() == low:
                return c
        return None

    def series(self, country: str, metric: str) -> list[dict]:
        s = self._by_country[country][metric].dropna()
        return [{"year": int(y), "value": _clean(v)} for y, v in s.items()]

    def series_array(self, country: str, metric: str) -> tuple[np.ndarray, np.ndarray]:
        s = self._by_country[country][metric].dropna()
        return s.index.to_numpy(dtype=int), s.to_numpy(dtype=float)

    def latest(self, country: str, metric: str) -> tuple[int, float] | None:
        s = self._by_country[country][metric].dropna()
        if s.empty:
            return None
        return int(s.index[-1]), float(s.iloc[-1])

    def snapshot(self, metric: str, year: int) -> pd.Series:
        return self.df[self.df["year"] == year].set_index("country")[metric].dropna()

    def latest_snapshot(self, metric: str) -> pd.DataFrame:
        sub = self.df.dropna(subset=[metric])
        last = sub.sort_values("year").groupby("country").tail(1)
        return last.set_index("country")[[metric, "year"]].rename(columns={metric: "value"})

    def availability(self, country: str) -> list[dict]:
        """Per indicator: first/latest year and number of observed years for one country (data-availability view)."""
        c = self._by_country[country]
        out = []
        for k, m in METRICS.items():
            if k not in c.columns:
                continue
            s = c[k].dropna()
            out.append({"metric": k, "label": m.label, "unit": m.unit, "n_years": int(len(s)),
                        "first_year": int(s.index.min()) if len(s) else None,
                        "latest_year": int(s.index.max()) if len(s) else None,
                        "source": self.ind.get(k, {}).get("source")})
        return out

    # ------------------------------------------------------------------ overview
    def _like_for_like(self, metric_cols: list[str], year: int, prev_year: int):
        """Frames for `year` and `prev_year` restricted to countries observed in both (so deltas are comparable)."""
        a = self.df[self.df["year"] == year].dropna(subset=metric_cols).set_index("country")
        b = self.df[self.df["year"] == prev_year].dropna(subset=metric_cols).set_index("country")
        common = a.index.intersection(b.index)
        return a.loc[common], b.loc[common]

    def overview(self, year: int | None = None) -> dict:
        """Global KPIs. Each KPI carries its own reporting year; the optional `year` only moves the electricity block."""
        ey = year or self.year_for("renewable_elec_share")
        if ey not in self.years:
            raise DatasetError(f"Year {year} is not in the dataset ({self.first_year}-{self.last_year}).")
        cur = self.df[self.df["year"] == ey]
        a, b = self._like_for_like(["total_elec_twh", "elec_renewable_twh"], ey, ey - 1)
        share = lambda f: float(f["elec_renewable_twh"].sum() / f["total_elec_twh"].sum() * 100) if f["total_elec_twh"].sum() else None
        total_n = int(cur["total_elec_twh"].notna().sum())

        def kpi(value, prev, year_, n, unit, label, extra=None):
            d = {"label": label, "value": _clean(value), "prev": _clean(prev), "year": year_, "n": n, "unit": unit}
            if value is not None and prev is not None:
                d["change"] = _clean(value - prev)
            return {**d, **(extra or {})}

        kp = {"renewable_elec_share": kpi(share(a), share(b), ey, len(a), "%", "Renewable share of electricity",
              {"note": "world total over reporting countries; change is like-for-like vs previous year"}),
              "renewable_twh": kpi(a["elec_renewable_twh"].sum(), b["elec_renewable_twh"].sum(), ey, len(a), "TWh", "Renewable electricity")}
        for key in ("solar_twh", "wind_twh", "hydro_twh"):
            x, y = self._like_for_like([key], ey, ey - 1)
            kp[key] = kpi(x[key].sum(), y[key].sum(), ey, len(x), "TWh", METRICS[key].label)
        cy = self.year_for("co2_kt")
        x, y = self._like_for_like(["co2_mt"], cy, cy - 1)
        kp["co2_mt"] = kpi(x["co2_mt"].sum(), y["co2_mt"].sum(), cy, len(x), "Mt", "Global CO₂ (fossil)")
        gi = self._like_for_like(["grid_intensity", "total_elec_twh"], ey, ey - 1)
        w = lambda f: float((f["grid_intensity"] * f["total_elec_twh"]).sum() / f["total_elec_twh"].sum())
        kp["grid_intensity"] = kpi(w(gi[0]), w(gi[1]), ey, len(gi[0]), "g CO₂e/kWh", "Grid carbon intensity (generation-weighted)")
        ay = self.year_for("electricity_access")
        x, y = self._like_for_like(["electricity_access", "population"], ay, ay - 1)
        pw = lambda f: float((f["electricity_access"] * f["population"]).sum() / f["population"].sum())
        kp["electricity_access"] = kpi(pw(x), pw(y), ay, len(x), "%", "Electricity access (population-weighted)")
        ry = self.year_for("renewable_share")
        rs, rp = self.snapshot("renewable_share", ry), self.snapshot("renewable_share", ry - 1)
        kp["renewable_share"] = kpi(rs.median(), rp.median(), ry, len(rs), "%", "Renewable share of final energy (median country)")

        # movers over 5 years on the current-year electricity share (percentage points)
        past = ey - 5
        sa, sb = self.snapshot("renewable_elec_share", ey), self.snapshot("renewable_elec_share", past)
        delta = (sa - sb).dropna().sort_values()
        movers = {"metric": "renewable_elec_share", "window": [past, ey],
                  "gainers": [{"country": c, "delta": _clean(v), "value": _clean(sa[c])} for c, v in delta.tail(8)[::-1].items()],
                  "decliners": [{"country": c, "delta": _clean(v), "value": _clean(sa[c])} for c, v in delta.head(8).items()]}
        top = sa.sort_values(ascending=False).head(10)
        leaders = [{"country": c, "value": _clean(v)} for c, v in top.items()]
        mix = self.global_mix(ey)
        partial = self.ind["renewable_elec_share"]["latest_year"] > ey or total_n < 0.8 * self.ind["total_elec_twh"]["n_broad"]
        return {"year": ey, "kpis": kp, "movers": movers, "leaders": leaders, "mix": mix,
                "latest_electricity_year": self.ind["renewable_elec_share"]["latest_year"],
                "latest_electricity_year_n": self.ind["renewable_elec_share"]["n_latest"],
                "partial_year_note": self._partial_note(), "partial": bool(partial)}

    def _partial_note(self) -> str | None:
        ly = self.ind["renewable_elec_share"]["latest_year"]
        by = self.ind["renewable_elec_share"]["broad_year"]
        if ly <= by:
            return None
        n = self.ind["renewable_elec_share"]["n_latest"]
        cov = self.df[(self.df.year == ly) & self.df.total_elec_twh.notna()].set_index("country").total_elec_twh
        prev = self.df[(self.df.year == by)].set_index("country").total_elec_twh
        share = float(cov.sum() / prev.sum() * 100)
        return (f"{ly} electricity data covers {n} countries (≈{share:.0f}% of {by} global generation) and is shown "
                f"as partial; {by} is the latest year with broad coverage.")

    def global_mix(self, year: int) -> dict:
        cur = self.df[self.df["year"] == year]
        tot = cur["total_elec_twh"].sum()
        parts = {"Fossil": cur["elec_fossil_twh"].sum(), "Nuclear": cur["elec_nuclear_twh"].sum(),
                 **{SOURCE_LABELS[k]: cur[k].sum() for k in RENEWABLE_SOURCES}}
        return {"year": year, "total_twh": _clean(tot),
                "parts": [{"label": k, "twh": _clean(v), "share": _clean(v / tot * 100)} for k, v in parts.items()]}

    def global_trend(self) -> list[dict]:
        out = []
        n_ref = self.ind["total_elec_twh"]["n_broad"]
        for y, g in self.df.groupby("year"):
            tot = g["total_elec_twh"].sum()
            n = int(g["total_elec_twh"].notna().sum())
            rs = g["renewable_share"].dropna()
            row = {"year": int(y), "n_electricity": n, "partial": n < 0.8 * n_ref,
                   "renewable_elec_share": _clean(g["elec_renewable_twh"].sum() / tot * 100) if tot else None,
                   "fossil_elec_share": _clean(g["elec_fossil_twh"].sum() / tot * 100) if tot else None,
                   "nuclear_elec_share": _clean(g["elec_nuclear_twh"].sum() / tot * 100) if tot else None,
                   "median_share": _clean(rs.median()) if len(rs) >= 0.5 * g["country"].nunique() else None,
                   "co2_mt": _clean(g["co2_mt"].sum()) if g["co2_mt"].notna().sum() > 100 else None}
            for k in ["elec_renewable_twh", "elec_fossil_twh", "elec_nuclear_twh", *RENEWABLE_SOURCES]:
                row[k] = _clean(g[k].sum()) if n else None
            out.append(row)
        return out

    # ------------------------------------------------------------------ renewables (source-wise)
    def renewables_global(self) -> dict:
        trend = [r for r in self.global_trend() if r["n_electricity"] > 0 and r["year"] >= 2000]
        ey = self.year_for("renewable_elec_share")
        base = next(r for r in trend if r["year"] == ey)
        first = trend[0]
        sources = []
        for k in RENEWABLE_SOURCES:
            v, v0 = base[k], first[k]
            yrs = ey - first["year"]
            sources.append({"key": k, "label": SOURCE_LABELS[k], "twh": v,
                            "share_of_renewables": _clean(v / base["elec_renewable_twh"] * 100),
                            "share_of_electricity": _clean(v / self.global_mix(ey)["total_twh"] * 100),
                            "twh_first": v0, "first_year": first["year"],
                            "cagr": _clean(((v / v0) ** (1 / yrs) - 1) * 100) if v0 and v0 > 0 and v else None,
                            "growth_5y": _clean(v - next(r for r in trend if r["year"] == ey - 5)[k])})
        return {"year": ey, "trend": trend, "sources": sources, "mix": self.global_mix(ey),
                "partial_year_note": self._partial_note(),
                "note": "Generation (TWh) from Ember. This is electricity generation, not the renewable share of final energy."}

    def renewables_ranking(self, source: str, year: int | None = None, by: str = "twh", limit: int = 15) -> dict:
        if source not in RENEWABLE_SOURCES and source != "elec_renewable_twh":
            raise DatasetError(f"Unknown source '{source}'.")
        year = year or self.year_for(source)
        d = self.df[self.df["year"] == year].set_index("country")
        if by == "share":
            val = (d[source] / d["total_elec_twh"] * 100).where(d["total_elec_twh"] > 1)
        else:
            val = d[source]
        val = val.dropna().sort_values(ascending=False)
        gl = d[source].sum()
        rows = [{"country": c, "value": _clean(v), "twh": _clean(d.loc[c, source]),
                 "share_of_global": _clean(d.loc[c, source] / gl * 100) if gl else None} for c, v in val.head(limit).items()]
        return {"source": source, "label": SOURCE_LABELS.get(source, "Renewable"), "year": year, "by": by,
                "n": int(len(val)), "global_twh": _clean(gl), "rows": rows}

    def renewables_country(self, country: str) -> dict:
        c = self._by_country[country]
        cols = RENEWABLE_SOURCES + ["elec_renewable_twh", "total_elec_twh", "elec_fossil_twh", "elec_nuclear_twh"]
        hist = []
        for y, r in c[cols].iterrows():
            if pd.isna(r["total_elec_twh"]):
                continue
            hist.append({"year": int(y), **{k: _clean(r[k]) for k in cols}})
        avail = self.availability(country)
        out = {"country": country, "history": hist, "latest_year": hist[-1]["year"] if hist else None,
               "sources_without_data": [SOURCE_LABELS[k] for k in RENEWABLE_SOURCES if c[k].dropna().empty]}
        if hist:
            last = hist[-1]
            tot, ren = last["total_elec_twh"], last["elec_renewable_twh"]
            out["latest"] = [{"key": k, "label": SOURCE_LABELS[k], "twh": last[k],
                              "share_of_electricity": _clean(last[k] / tot * 100) if (tot and last[k] is not None) else None,
                              "share_of_renewables": _clean(last[k] / ren * 100) if (ren and last[k] is not None) else None}
                             for k in RENEWABLE_SOURCES]
            ranked = [r for r in out["latest"] if r["twh"]]
            out["dominant"] = max(ranked, key=lambda r: r["twh"])["label"] if ranked and ren else None
            first = next((h for h in hist if h["year"] >= self.first_year), hist[0])
            out["window"] = [first["year"], last["year"]]
        out["availability"] = [a for a in avail if a["metric"] in RENEWABLE_SOURCES]
        return out

    def dominant_by_country(self, year: int | None = None) -> dict:
        year = year or self.year_for("elec_renewable_twh")
        d = self.df[self.df["year"] == year].set_index("country")
        d = d[d["elec_renewable_twh"] > 0.05]
        parts = d[RENEWABLE_SOURCES]
        dom = parts.idxmax(axis=1)
        rows = [{"country": c, "source": SOURCE_LABELS[dom[c]], "key": dom[c],
                 "share_of_renewables": _clean(parts.loc[c, dom[c]] / d.loc[c, "elec_renewable_twh"] * 100),
                 "renewable_twh": _clean(d.loc[c, "elec_renewable_twh"]),
                 "lat": _clean(self.coords[c]["latitude"]), "lon": _clean(self.coords[c]["longitude"])} for c in d.index]
        counts = pd.Series([r["source"] for r in rows]).value_counts().to_dict()
        return {"year": year, "rows": rows, "counts": counts}

    # ------------------------------------------------------------------ country views
    def ranking(self, metric: str, year: int | None = None, q: str = "", sort: str = "desc", limit: int = 500) -> dict:
        year = year or self.year_for(metric)
        snap = self.snapshot(metric, year)
        prev = self.snapshot(metric, year - 1)
        rows = []
        for c, v in snap.items():
            if q and q.lower() not in c.lower():
                continue
            rows.append({"country": c, "value": _clean(v), "change": _clean(v - prev[c]) if c in prev.index else None})
        rows.sort(key=lambda r: r["value"], reverse=(sort != "asc"))
        for i, r in enumerate(rows, 1):
            r["rank"] = i
        return {"metric": metric, "year": year, "total": len(rows), "rows": rows[:limit]}

    def map_points(self, metric: str, year: int) -> list[dict]:
        snap = self.snapshot(metric, year)
        return [{"country": c, "value": _clean(v), "lat": _clean(self.coords[c]["latitude"]),
                 "lon": _clean(self.coords[c]["longitude"])} for c, v in snap.items()]

    def profile(self, country: str) -> dict:
        key_metrics = ["renewable_elec_share", "renewable_share", "low_carbon_elec_pct", "electricity_access",
                       "clean_cooking_access", "co2_per_capita_t", "grid_intensity", "energy_intensity",
                       "energy_per_capita_kwh", "gdp_per_capita", "co2_kt", "elec_renewable_twh"]
        cards = []
        for m in key_metrics:
            lat = self.latest(country, m)
            if lat is None:
                cards.append({"metric": m, "value": None})
                continue
            year, val = lat
            snap = self.snapshot(m, year)
            s = self._by_country[country][m].dropna()
            prev = float(s.loc[year - 1]) if (year - 1) in s.index else None
            five = float(s.loc[year - 5]) if (year - 5) in s.index else None
            cards.append({"metric": m, "value": _clean(val), "year": year, "rank": int((snap > val).sum() + 1),
                          "of": int(len(snap)), "percentile": _clean((snap < val).mean() * 100),
                          "change_1y": _clean(val - prev) if prev is not None else None,
                          "change_5y": _clean(val - five) if five is not None else None})
        c = self._by_country[country]
        mix = [{"year": int(y), "fossil": _clean(r["elec_fossil_twh"]), "nuclear": _clean(r["elec_nuclear_twh"]),
                "renewable": _clean(r["elec_renewable_twh"])} for y, r in c.iterrows()
               if pd.notna(r["elec_fossil_twh"]) or pd.notna(r["elec_renewable_twh"])]
        pop = self.latest(country, "population")
        info = {"country": country, "iso3": self.iso3.get(country), "latitude": _clean(self.coords[country]["latitude"]),
                "longitude": _clean(self.coords[country]["longitude"]),
                "land_area_km2": _clean(c["land_area_km2"].iloc[-1]), "density": _clean(c["density"].iloc[-1]),
                "population": _clean(pop[1]) if pop else None, "population_year": pop[0] if pop else None,
                "first_year": int(c.index.min()), "last_year": int(c.index.max())}
        return {"info": info, "cards": cards, "mix": mix, "availability": self.availability(country)}

    def world_average(self, metric: str) -> list[dict]:
        """Per-year world benchmark: population-weighted for per-capita / % indicators, only where coverage is broad."""
        d = self.df.dropna(subset=[metric, "population"])
        n_ref = self.ind[metric]["n_broad"]
        out = []
        for y, g in d.groupby("year"):
            if len(g) < 0.8 * n_ref:
                continue
            out.append({"year": int(y), "value": _clean((g[metric] * g["population"]).sum() / g["population"].sum())})
        return out

    def compare(self, countries: list[str], metric: str) -> list[dict]:
        return [{"country": c, "series": self.series(c, metric)} for c in countries]

    def records(self, q="", year=None, metric_sort="country", order="asc", page=1, per_page=25,
                year_from=None, year_to=None, columns=None) -> dict:
        df = self.df
        if q:
            df = df[df["country"].str.contains(q, case=False, regex=False)]
        if year:
            df = df[df["year"] == year]
        if year_from:
            df = df[df["year"] >= year_from]
        if year_to:
            df = df[df["year"] <= year_to]
        columns = columns or ["country", "year", "renewable_share", "renewable_elec_share", "solar_twh", "wind_twh",
                              "hydro_twh", "electricity_access", "clean_cooking_access", "co2_per_capita_t", "grid_intensity"]
        if metric_sort not in df.columns:
            metric_sort = "country"
        df = df.sort_values([metric_sort, "country", "year"], ascending=(order != "desc"), na_position="last")
        total = len(df)
        start = (page - 1) * per_page
        page_df = df.iloc[start:start + per_page][columns]
        rows = [{k: (_clean(v) if k != "country" else v) for k, v in r.items()} for r in page_df.to_dict("records")]
        return {"total": total, "page": page, "per_page": per_page, "columns": columns, "rows": rows}

    def percentile_in(self, metric: str, country: str) -> float | None:
        lat = self.latest(country, metric)
        if lat is None:
            return None
        snap = self.latest_snapshot(metric)["value"]
        return float((snap < lat[1]).mean() * 100)

    def provenance(self) -> dict:
        return {
            "sources": self.catalog.get("sources", {}), "built_at": self.catalog.get("built_at"),
            "rows": int(len(self.df)), "countries": len(self.countries), "years": [self.first_year, self.last_year],
            "headline_year": self.headline_year,
            "indicators": {k: {x: v[x] for x in ("first_year", "latest_year", "broad_year", "n_latest", "n_broad", "n_countries", "source")}
                           for k, v in self.ind.items()},
            "type": "historical",
            "note": ("Annual data from public sources, not a live feed. Every indicator keeps its own latest year; "
                     "nothing is carried forward. World Bank access/cooking/final-energy-share series end in 2020. "
                     "Forecasts are model output.")}


@lru_cache(maxsize=2)
def get_dataset(path: str) -> EnergyData:
    return EnergyData(Path(path))
