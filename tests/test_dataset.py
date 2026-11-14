"""Dataset validation: the processed CSV, its catalog, and the build pipeline's own guards."""
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.app.dataset import build as B

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data/processed/terrawatt_dataset.csv"
CAT = json.loads((ROOT / "data/processed/indicator_catalog.json").read_text())["indicators"]


@pytest.fixture(scope="module")
def df():
    return pd.read_csv(CSV)


def test_one_row_per_country_year_and_expected_span(df):
    assert not df.duplicated(["country", "year"]).any()
    assert df.year.min() == 2000 and df.year.max() == 2025 and df.country.nunique() == 194
    assert df.groupby("country").year.nunique().eq(26).all()          # full skeleton, no accidental gaps in the grid


def test_countries_are_standardised_and_have_codes_and_coordinates(df):
    assert df.iso3.notna().all() and df.groupby("country").iso3.nunique().max() == 1
    assert df.latitude.between(-90, 90).all() and df.longitude.between(-180, 180).all()
    assert "French Guiana" not in set(df.country) and {"Russia", "Vietnam", "South Korea"} <= set(df.country)
    assert (df.country == df.country.str.strip()).all()


def test_value_ranges(df):
    for c in ["renewable_share", "renewables_share_primary", "renewable_elec_share", "low_carbon_elec_pct", "electricity_access", "clean_cooking_access"]:
        v = df[c].dropna()
        assert v.between(-0.01, 100.01).all(), c
    for c in ["total_elec_twh", "elec_fossil_twh", "elec_renewable_twh", "solar_twh", "wind_twh", "hydro_twh", "bioenergy_twh", "co2_mt", "population"]:
        assert (df[c].dropna() >= 0).all(), c


def test_renewable_sources_add_up_and_mix_is_consistent(df):
    parts = df[["solar_twh", "wind_twh", "hydro_twh", "bioenergy_twh", "other_renew_twh"]].sum(axis=1, min_count=1)
    assert (parts - df.elec_renewable_twh).abs().max() < 0.05
    tot = df[["elec_fossil_twh", "elec_nuclear_twh", "elec_renewable_twh"]].sum(axis=1, min_count=3)
    ok = df.total_elec_twh > 1
    assert ((tot[ok] - df.total_elec_twh[ok]).abs() / df.total_elec_twh[ok]).max() < 0.02


def test_no_values_extended_beyond_their_source(df):
    """World Bank/Kaggle indicators end in 2020; nothing may be carried forward into 2021-2025."""
    for c in ["renewable_share", "electricity_access", "clean_cooking_access", "energy_intensity", "energy_per_capita_kwh", "gdp_per_capita", "gdp_growth"]:
        assert df.loc[df.year > 2020, c].isna().all(), c
    assert df.loc[df.year > 2024, "renewables_share_primary"].isna().all()
    # a carried-forward series would show identical consecutive values for many countries
    d = df.sort_values(["country", "year"])
    for c in ["solar_twh", "wind_twh", "co2_mt"]:
        same = (d.groupby("country")[c].diff() == 0) & d[c].notna() & (d[c] > 1)
        assert same.mean() < 0.01, c
    # no country ends with a flat run of the same CO2 value (the signature of a forward-fill into 2021-2025)
    tail = d[d.year >= 2021].groupby("country")["co2_mt"].agg(lambda s: s.dropna().nunique() == 1 and s.notna().sum() >= 4)
    assert not tail.any()


def test_catalog_matches_data_and_records_provenance(df):
    for k, v in CAT.items():
        s = df.dropna(subset=[k])
        assert v["latest_year"] == s.year.max() and v["first_year"] == s.year.min() and v["countries_with_data"] == s.country.nunique()
        assert v["source"] and v["unit"] and v["definition"]
    assert CAT["renewable_share"]["latest_year"] == 2020 and CAT["solar_twh"]["latest_year"] == 2025
    assert CAT["solar_twh"]["countries_in_latest_year"] < CAT["solar_twh"]["countries_with_data"]       # 2025 is partial, and says so
    assert "FINAL" in CAT["renewable_share"]["definition"] and "PRIMARY" in CAT["renewables_share_primary"]["definition"]


def test_validation_report_is_clean_and_reproducible(tmp_path):
    rep = json.loads((ROOT / "data/processed/validation_report.json").read_text())
    assert rep["ok"] and rep["errors"] == []
    assert rep["checks"]["renewable_components_sum_to_total_max_abs_diff_twh"] < 0.05
    assert 28 < rep["checks"]["world_2023_renewable_share_pct"] < 34           # public figure ~30%
    assert "French Guiana" in rep["excluded_entities"]
    out = tmp_path / "rebuilt"
    again = B.build(ROOT / "data/global-data-on-sustainable-energy.csv", ROOT / "data/raw/owid-energy-extract.csv",
                    ROOT / "data/raw/owid-co2-extract.csv", out)
    assert again["ok"]
    a = pd.read_csv(CSV).sort_values(["country", "year"]).reset_index(drop=True)
    b = pd.read_csv(out / "terrawatt_dataset.csv").sort_values(["country", "year"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)                                          # the committed dataset is exactly what the pipeline produces


def _tamper_energy(tmp_path, fn):
    e = pd.read_csv(ROOT / "data/raw/owid-energy-extract.csv")
    fn(e)
    p = tmp_path / "energy.csv"
    e.to_csv(p, index=False)
    return p


def test_build_refuses_out_of_range_percentages(tmp_path):
    p = _tamper_energy(tmp_path, lambda e: e.__setitem__("renewables_share_elec", e["renewables_share_elec"].where(e.index != 5, 250.0)))
    rep = B.build(ROOT / "data/global-data-on-sustainable-energy.csv", p, ROOT / "data/raw/owid-co2-extract.csv", tmp_path / "o")
    assert not rep["ok"] and any("outside 0-100" in x for x in rep["errors"]) and not (tmp_path / "o/terrawatt_dataset.csv").exists()


def test_build_refuses_sources_that_do_not_add_up(tmp_path):
    p = _tamper_energy(tmp_path, lambda e: e.__setitem__("solar_electricity", e["solar_electricity"].where(e.index != 400, 9999.0)))
    rep = B.build(ROOT / "data/global-data-on-sustainable-energy.csv", p, ROOT / "data/raw/owid-co2-extract.csv", tmp_path / "o")
    assert not rep["ok"] and any("add up" in x for x in rep["errors"])


def test_build_refuses_negative_generation(tmp_path):
    def f(e):
        i = e.index[e["fossil_electricity"].notna()][0]
        e.loc[i, "fossil_electricity"] = -5
    p = _tamper_energy(tmp_path, f)
    rep = B.build(ROOT / "data/global-data-on-sustainable-energy.csv", p, ROOT / "data/raw/owid-co2-extract.csv", tmp_path / "o")
    assert not rep["ok"] and any("negative" in x for x in rep["errors"])


def test_build_flags_world_bank_values_past_2020(tmp_path):
    k = pd.read_csv(ROOT / "data/global-data-on-sustainable-energy.csv")
    extra = k[k.Year == 2020].copy()
    extra["Year"] = 2023
    pd.concat([k, extra]).to_csv(tmp_path / "k.csv", index=False)
    rep = B.build(tmp_path / "k.csv", ROOT / "data/raw/owid-energy-extract.csv", ROOT / "data/raw/owid-co2-extract.csv", tmp_path / "o")
    assert not rep["ok"] and any("beyond" in x for x in rep["errors"])


def test_indicator_specific_latest_year_in_service():
    from backend.app.services.data_service import EnergyData
    d = EnergyData(CSV)
    assert d.year_for("renewable_share") == 2019 and d.year_for("renewable_elec_share") == 2024 and d.year_for("co2_kt") == 2025
    assert d.ind["renewable_share"]["latest_year"] == 2020 and d.ind["renewable_share"]["n_latest"] < 5
    a = d.availability("India")
    assert next(x for x in a if x["metric"] == "solar_twh")["latest_year"] == 2025
    assert next(x for x in a if x["metric"] == "electricity_access")["latest_year"] == 2020


def test_like_for_like_kpi_change_not_distorted_by_partial_year():
    from backend.app.services.data_service import EnergyData
    d = EnergyData(CSV)
    k = d.overview(2025)["kpis"]["renewable_elec_share"]            # 2025 only has 90 countries
    assert k["n"] <= 90 and abs(k["change"]) < 6                    # compared on the same countries, so no artificial jump
    naive = d.df[d.df.year == 2025].elec_renewable_twh.sum() / d.df[d.df.year == 2025].total_elec_twh.sum() * 100
    assert abs(naive - k["value"]) < 1e-3
