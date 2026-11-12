"""Dataset access and analytics on the real Kaggle 'Global Data on Sustainable Energy' table.

All figures served by the API come from this CSV (World Bank / IEA-derived, 2000-2020).
Nothing here is simulated. Derived columns are explicitly marked `derived=True` in METRICS.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

RENAME = {
    "entity": "country", "year": "year",
    "access to electricity (% of population)": "electricity_access",
    "access to clean fuels for cooking": "clean_cooking_access",
    "renewable-electricity-generating-capacity-per-capita": "renew_capacity_per_capita",
    "financial flows to developing countries (us $)": "financial_flows_usd",
    "renewable energy share in the total final energy consumption (%)": "renewable_share",
    "electricity from fossil fuels (twh)": "elec_fossil_twh",
    "electricity from nuclear (twh)": "elec_nuclear_twh",
    "electricity from renewables (twh)": "elec_renewable_twh",
    "low-carbon electricity (% electricity)": "low_carbon_elec_pct",
    "primary energy consumption per capita (kwh/person)": "energy_per_capita_kwh",
    "energy intensity level of primary energy (mj/$2017 ppp gdp)": "energy_intensity",
    "value_co2_emissions_kt_by_country": "co2_kt",
    "renewables (% equivalent primary energy)": "renewables_primary_pct",
    "gdp_growth": "gdp_growth", "gdp_per_capita": "gdp_per_capita",
    "density (p/km2)": "density", "land area(km2)": "land_area_km2",
    "latitude": "latitude", "longitude": "longitude",
}

# Lifecycle emission factors, kg CO2e per kWh. Fossil is a *global-average blend*
# (~62% coal, ~33% gas, ~5% oil, using IPCC AR5 lifecycle medians 820/490/650 g/kWh).
# Nuclear and renewables are mid-range IPCC lifecycle medians. This is an ESTIMATE of grid
# carbon intensity from the generation mix; coal-heavy grids are understated, gas-heavy overstated.
EF_FOSSIL, EF_NUCLEAR, EF_RENEWABLE = 0.70, 0.012, 0.025


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
           "Renewable energy as a share of total final energy consumption (includes traditional biomass).", bounded_pct=True),
    Metric("renewable_elec_share", "Renewable share of electricity", "%", True,
           "Electricity from renewables ÷ total generation (fossil + nuclear + renewables).", derived=True, bounded_pct=True),
    Metric("low_carbon_elec_pct", "Low-carbon electricity", "%", True,
           "Share of electricity from renewables and nuclear.", bounded_pct=True),
    Metric("electricity_access", "Access to electricity", "% of population", True,
           "Population with access to electricity.", bounded_pct=True),
    Metric("clean_cooking_access", "Access to clean cooking fuels", "% of population", True,
           "Population relying primarily on clean fuels and technology for cooking.", bounded_pct=True),
    Metric("elec_renewable_twh", "Renewable electricity", "TWh", True, "Annual electricity generated from renewable sources."),
    Metric("elec_fossil_twh", "Fossil electricity", "TWh", False, "Annual electricity generated from fossil fuels."),
    Metric("co2_kt", "CO₂ emissions", "kt", False, "Total CO₂ emissions of the country."),
    Metric("co2_per_capita_t", "CO₂ per person", "t / person", False,
           "CO₂ emissions ÷ estimated population (density × land area). Approximate.", derived=True),
    Metric("grid_intensity", "Grid carbon intensity (est.)", "g CO₂e / kWh", False,
           "Estimated from the generation mix using lifecycle emission factors. Approximate.", derived=True),
    Metric("energy_per_capita_kwh", "Primary energy per person", "kWh", None, "Primary energy consumption per capita."),
    Metric("energy_intensity", "Energy intensity", "MJ / $2017 PPP", False, "Primary energy per unit of GDP; lower is more efficient."),
    Metric("gdp_per_capita", "GDP per capita", "US$", None, "Gross domestic product per person."),
]
METRICS: dict[str, Metric] = {m.key: m for m in _M}
FORECASTABLE = ["renewable_share", "electricity_access", "clean_cooking_access", "low_carbon_elec_pct",
                "renewable_elec_share", "co2_kt"]


class DatasetError(Exception):
    pass


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", str(name).replace("\\n", " ").replace("\n", " ")).strip().lower()


def load_frame(path: Path) -> pd.DataFrame:
    if not Path(path).exists():
        raise DatasetError(f"Dataset not found at {path}. See README for the download link.")
    raw = pd.read_csv(path)
    raw.columns = [RENAME.get(_norm(c), _norm(c)) for c in raw.columns]
    missing = [c for c in ("country", "year", "renewable_share") if c not in raw.columns]
    if missing:
        raise DatasetError(f"CSV is missing required columns: {missing}")
    df = raw.copy()
    df["country"] = df["country"].astype(str).str.strip()
    for col in df.columns.drop("country"):
        if not pd.api.types.is_numeric_dtype(df[col]):
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", "", regex=False), errors="coerce")
    df = df.dropna(subset=["year"]).drop_duplicates(["country", "year"]).copy()
    df["year"] = df["year"].astype(int)
    total = df[["elec_fossil_twh", "elec_nuclear_twh", "elec_renewable_twh"]].sum(axis=1, min_count=3)
    df["total_elec_twh"] = total
    df["renewable_elec_share"] = np.where(total > 0, df["elec_renewable_twh"] / total * 100, np.nan)
    df["grid_intensity"] = np.where(
        total > 0,
        (df["elec_fossil_twh"] * EF_FOSSIL + df["elec_nuclear_twh"] * EF_NUCLEAR
         + df["elec_renewable_twh"] * EF_RENEWABLE) / total * 1000, np.nan)
    df["population_est"] = df["density"] * df["land_area_km2"]
    df["co2_per_capita_t"] = np.where(df["population_est"] > 0, df["co2_kt"] * 1000 / df["population_est"], np.nan)
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
        self.coords = (self.df.groupby("country")[["latitude", "longitude"]].first()
                       .to_dict("index"))
        self._by_country = {c: g.set_index("year") for c, g in self.df.groupby("country")}
        # Latest year in which at least half of the countries report the headline metric.
        cov = self.df.groupby("year")["renewable_share"].apply(lambda s: s.notna().mean())
        self.headline_year = int(cov[cov >= 0.5].index.max())
        self.first_year = self.years[0]
        self.last_year = self.years[-1]

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
        """metric values by country for a year (NaN dropped)."""
        sub = self.df[self.df["year"] == year].set_index("country")[metric].dropna()
        return sub

    def latest_snapshot(self, metric: str) -> pd.DataFrame:
        """Most recent non-null value per country for a metric -> columns [value, year]."""
        sub = self.df.dropna(subset=[metric])
        last = sub.sort_values("year").groupby("country").tail(1)
        return last.set_index("country")[[metric, "year"]].rename(columns={metric: "value"})

    # ------------------------------------------------------------------ overview
    def overview(self, year: int | None = None) -> dict:
        year = year or self.headline_year
        if year not in self.years:
            raise DatasetError(f"Year {year} is not in the dataset ({self.first_year}-{self.last_year}).")
        df = self.df
        cur = df[df["year"] == year]
        prev = df[df["year"] == year - 1]

        def mean(frame, col):
            v = frame[col].dropna()
            return float(v.mean()) if len(v) else None

        def glob_elec(frame):
            r, t = frame["elec_renewable_twh"].sum(), frame["total_elec_twh"].sum()
            return float(r / t * 100) if t else None

        kpis = {
            "countries_reporting": int(cur["renewable_share"].notna().sum()),
            "avg_renewable_share": _clean(mean(cur, "renewable_share")),
            "avg_renewable_share_prev": _clean(mean(prev, "renewable_share")),
            "global_renewable_electricity_share": _clean(glob_elec(cur)),
            "global_renewable_electricity_share_prev": _clean(glob_elec(prev)),
            "renewable_twh": _clean(cur["elec_renewable_twh"].sum()),
            "renewable_twh_prev": _clean(prev["elec_renewable_twh"].sum()),
            "co2_mt": _clean(cur["co2_kt"].sum() / 1000),
            "co2_mt_prev": _clean(prev["co2_kt"].sum() / 1000),
            "avg_electricity_access": _clean(mean(cur, "electricity_access")),
            "avg_electricity_access_prev": _clean(mean(prev, "electricity_access")),
        }
        # CO2 is only reported for a subset of years; fall back to the last year with data
        if not kpis["co2_mt"]:
            y = int(df.dropna(subset=["co2_kt"])["year"].max())
            kpis["co2_mt"] = _clean(df[df["year"] == y]["co2_kt"].sum() / 1000)
            kpis["co2_mt_prev"] = _clean(df[df["year"] == y - 1]["co2_kt"].sum() / 1000)
            kpis["co2_year"] = y
        else:
            kpis["co2_year"] = year

        # Biggest movers over 5 years (percentage points of renewable share)
        past = year - 5
        a = self.snapshot("renewable_share", year)
        b = self.snapshot("renewable_share", past)
        delta = (a - b).dropna().sort_values()
        movers = {
            "gainers": [{"country": c, "delta": _clean(v), "value": _clean(a[c])} for c, v in delta.tail(8)[::-1].items()],
            "decliners": [{"country": c, "delta": _clean(v), "value": _clean(a[c])} for c, v in delta.head(8).items()],
            "window": [past, year],
        }
        top = a.sort_values(ascending=False).head(10)
        leaders = [{"country": c, "value": _clean(v)} for c, v in top.items()]
        return {"year": year, "kpis": kpis, "movers": movers, "leaders": leaders}

    def global_trend(self) -> list[dict]:
        out = []
        for y, g in self.df.groupby("year"):
            rs = g["renewable_share"].dropna()
            tot = g["total_elec_twh"].sum()
            out.append({
                "year": int(y),
                "mean_share": _clean(rs.mean()) if len(rs) >= 0.5 * g["country"].nunique() else None,
                "median_share": _clean(rs.median()) if len(rs) >= 0.5 * g["country"].nunique() else None,
                "renewable_elec_share": _clean(g["elec_renewable_twh"].sum() / tot * 100) if tot else None,
                "fossil_elec_share": _clean(g["elec_fossil_twh"].sum() / tot * 100) if tot else None,
                "nuclear_elec_share": _clean(g["elec_nuclear_twh"].sum() / tot * 100) if tot else None,
                "renewable_twh": _clean(g["elec_renewable_twh"].sum()),
                "fossil_twh": _clean(g["elec_fossil_twh"].sum()),
                "nuclear_twh": _clean(g["elec_nuclear_twh"].sum()),
                "electricity_access": _clean(g["electricity_access"].mean()),
                "co2_mt": _clean(g["co2_kt"].sum() / 1000) if g["co2_kt"].notna().sum() > 100 else None,
            })
        return out

    # ------------------------------------------------------------------ country views
    def ranking(self, metric: str, year: int | None = None, q: str = "", sort: str = "desc",
                limit: int = 500) -> dict:
        year = year or self.headline_year
        snap = self.snapshot(metric, year)
        prev = self.snapshot(metric, year - 1)
        rows = []
        for c, v in snap.items():
            if q and q.lower() not in c.lower():
                continue
            rows.append({"country": c, "value": _clean(v),
                         "change": _clean(v - prev[c]) if c in prev.index else None})
        rows.sort(key=lambda r: r["value"], reverse=(sort != "asc"))
        for i, r in enumerate(rows, 1):
            r["rank"] = i
        return {"metric": metric, "year": year, "total": len(rows), "rows": rows[:limit]}

    def map_points(self, metric: str, year: int) -> list[dict]:
        snap = self.snapshot(metric, year)
        return [{"country": c, "value": _clean(v), "lat": _clean(self.coords[c]["latitude"]),
                 "lon": _clean(self.coords[c]["longitude"])} for c, v in snap.items()]

    def profile(self, country: str) -> dict:
        key_metrics = ["renewable_share", "renewable_elec_share", "low_carbon_elec_pct", "electricity_access",
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
            rank = int((snap > val).sum() + 1)
            s = self._by_country[country][m].dropna()
            prev = float(s.loc[year - 1]) if (year - 1) in s.index else None
            five = float(s.loc[year - 5]) if (year - 5) in s.index else None
            cards.append({"metric": m, "value": _clean(val), "year": year, "rank": rank, "of": int(len(snap)),
                          "percentile": _clean((snap < val).mean() * 100),
                          "change_1y": _clean(val - prev) if prev is not None else None,
                          "change_5y": _clean(val - five) if five is not None else None})
        c = self._by_country[country]
        mix = [{"year": int(y), "fossil": _clean(r["elec_fossil_twh"]), "nuclear": _clean(r["elec_nuclear_twh"]),
                "renewable": _clean(r["elec_renewable_twh"])} for y, r in c.iterrows()
               if pd.notna(r["elec_fossil_twh"]) or pd.notna(r["elec_renewable_twh"])]
        info = {"country": country, "latitude": _clean(self.coords[country]["latitude"]),
                "longitude": _clean(self.coords[country]["longitude"]),
                "land_area_km2": _clean(c["land_area_km2"].iloc[-1]), "density": _clean(c["density"].iloc[-1]),
                "population_est": _clean(c["population_est"].iloc[-1]),
                "first_year": int(c.index.min()), "last_year": int(c.index.max())}
        return {"info": info, "cards": cards, "mix": mix}

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
        columns = columns or ["country", "year", "renewable_share", "renewable_elec_share", "electricity_access",
                              "clean_cooking_access", "elec_renewable_twh", "elec_fossil_twh", "co2_kt",
                              "gdp_per_capita", "energy_per_capita_kwh"]
        if metric_sort not in df.columns:
            metric_sort = "country"
        df = df.sort_values([metric_sort, "country", "year"], ascending=(order != "desc"), na_position="last")
        total = len(df)
        start = (page - 1) * per_page
        page_df = df.iloc[start:start + per_page][columns]
        rows = [{k: (_clean(v) if k not in ("country",) else v) for k, v in r.items()} for r in page_df.to_dict("records")]
        return {"total": total, "page": page, "per_page": per_page, "columns": columns, "rows": rows}

    def percentile_in(self, metric: str, country: str) -> float | None:
        lat = self.latest(country, metric)
        if lat is None:
            return None
        snap = self.latest_snapshot(metric)["value"]
        return float((snap < lat[1]).mean() * 100)

    def provenance(self) -> dict:
        return {
            "source": "Kaggle - Global Data on Sustainable Energy (World Bank / IEA-derived)",
            "url": "https://www.kaggle.com/datasets/anshtanwar/global-data-on-sustainable-energy",
            "rows": int(len(self.df)), "countries": len(self.countries),
            "years": [self.first_year, self.last_year], "headline_year": self.headline_year,
            "type": "historical",
            "note": ("Historical annual data, not a live feed. The renewable-share series ends in "
                     f"{self.df.dropna(subset=['renewable_share'])['year'].max()}. Derived metrics (marked ~) "
                     "are computed by TerraWatt from this table; forecasts are model output."),
        }


@lru_cache(maxsize=2)
def get_dataset(path: str) -> EnergyData:
    return EnergyData(Path(path))
