"""What-if lab API, model loading/prediction and Model Lab endpoints."""
import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
from conftest import H

from backend.app.ml.pipeline import FEATURES, SCENARIO_FEATURES
from backend.app.services.predictor import Predictor

ROOT = Path(__file__).resolve().parents[1]


def predict(client, country="India", **body):
    return client.post("/api/ml/predict", json={"country": country, **body}, headers=H)


# ---------------------------------------------------------------- Model Lab endpoints
def test_model_endpoints_and_status(client):
    s = client.get("/api/ml/status").json
    assert s["ok"] and s["env"]["sklearn"]
    m = client.get("/api/ml/models").json
    assert {"regression", "classification", "clustering", "gmm"} <= set(m)
    assert m["regression"]["examples"] and m["classification"]["examples"]
    sel = next(r for r in m["regression"]["table"] if r["selected"])
    assert sel["RMSE"] < next(r for r in m["regression"]["table"] if r["model"].startswith("Baseline"))["RMSE"]
    c = client.get("/api/ml/clusters").json
    assert c["k"] >= 3 and c["gmm"]["k"] >= 3
    some = next(iter(c["gmm"]["countries"].values()))
    assert abs(sum(some["probs"]) - 1) < 1e-6                      # soft membership sums to one
    assert -1 <= m["clustering"]["silhouette_chosen"] <= 1


def test_forecast_quality_and_all_forecastable_metrics(client):
    from backend.app.services.data_service import FORECASTABLE
    for metric in FORECASTABLE:
        assert client.get(f"/api/forecast-quality?metric={metric}").status_code == 200, metric
        r = client.get(f"/api/forecast/India?metric={metric}&to=2030")
        assert r.status_code == 200, (metric, r.json)


# ---------------------------------------------------------------- scenario config
def test_scenario_config_has_usable_slider_ranges(client):
    j = client.get("/api/ml/scenario-config?country=India").json
    assert j["reference_year"] <= 2020 and {f["key"] for f in j["features"]} == set(SCENARIO_FEATURES)
    for f in j["features"]:
        assert f["min"] <= f["max"] and f["step"] > 0
        if f["baseline"] is not None:
            assert f["min"] <= f["baseline"] <= f["max"]
    assert set(j["presets"]) == {"high_solar", "high_wind", "reduced_fossil", "improved_access"}
    assert j["electricity_mix"]["year"] >= 2024


def test_scenario_config_unknown_country_and_missing_models(client):
    assert client.get("/api/ml/scenario-config?country=Atlantis").status_code == 404


# ---------------------------------------------------------------- predictions
def test_no_change_gives_zero_delta_and_matches_direct_model_call(client, app):
    r = predict(client, "Kenya").json
    assert r["delta"] == 0 and r["baseline"]["share"] == r["scenario"]["share"] and r["effects"] == []
    p = app.extensions["tw"].predictor
    row, _, _ = p.baseline_row("Kenya")
    X = pd.DataFrame([row])[p.cards["regression"]["columns"]]            # exact stored column order
    assert abs(float(p.reg.predict(X)[0]) - r["baseline"]["share"]) < 0.01


def test_regression_columns_are_exact_feature_order(app):
    cols = app.extensions["tw"].predictor.cards["regression"]["columns"]
    assert cols[:len(FEATURES)] == FEATURES and "year" in cols


def test_electricity_access_override_changes_prediction_and_is_reported(client):
    r = predict(client, "Kenya", overrides={"electricity_access": 100}).json
    assert r["changed_inputs"][0]["feature"] == "electricity_access" and r["effects"]
    assert 0 <= r["scenario"]["share"] <= 100 and "causal" in r["disclaimer"]


def test_presets_move_the_electricity_mix_in_the_expected_direction(client):
    base = predict(client).json["electricity_mix"]
    assert base is None                                                  # no mix inputs -> no accounting block
    solar = predict(client, mix={"solar_mult": 3}).json["electricity_mix"]
    assert solar["delta"]["renewable_share_pp"] > 0 and solar["delta"]["grid_intensity"] < 0 and solar["delta"]["emissions_mt"] < 0
    wind = predict(client, mix={"wind_mult": 3}).json["electricity_mix"]
    assert wind["delta"]["renewable_share_pp"] > 0
    fossil = predict(client, mix={"fossil_reduction_pct": 30}).json["electricity_mix"]
    assert fossil["scenario"]["fossil_share"] < fossil["baseline"]["fossil_share"]
    acc = predict(client, "Kenya", access_gap_pct=50).json
    assert acc["changed_inputs"][0]["feature"] == "electricity_access"
    cur, new = acc["changed_inputs"][0]["from"], acc["changed_inputs"][0]["to"]
    assert abs(new - (cur + (100 - cur) / 2)) < 1e-6


def test_mix_accounting_is_exact_and_calibrated_to_ember(client, app):
    j = predict(client, mix={"solar_mult": 3}).json["electricity_mix"]
    d = app.extensions["tw"].data
    ember = d.latest("India", "grid_intensity")
    assert j["year"] == ember[0] and abs(j["baseline"]["grid_intensity"] - ember[1]) < 1.0          # reproduces reported intensity
    b, s = j["baseline"], j["scenario"]
    assert abs(sum(x["twh"] for x in b["by_source"]) - b["total_twh"]) < 0.1
    assert abs(s["total_twh"] - b["total_twh"]) < 0.1                                                # constant demand
    solar_b = next(x["twh"] for x in b["by_source"] if x["key"] == "solar_twh")
    solar_s = next(x["twh"] for x in s["by_source"] if x["key"] == "solar_twh")
    assert abs(solar_s - 3 * solar_b) < 0.1
    assert j["assumptions"] and not j["surplus_twh"]


def test_surplus_is_reported_not_hidden(client):
    j = predict(client, "Norway", mix={"solar_mult": 10, "wind_mult": 10, "fossil_reduction_pct": 100}).json["electricity_mix"]
    assert j["surplus_twh"] > 0 and j["scenario"]["fossil_share"] == 0


@pytest.mark.parametrize("body", [
    {"overrides": {"latitude": 5}}, {"overrides": {"electricity_access": 140}}, {"overrides": {"electricity_access": -1}},
    {"overrides": {"elec_fossil_twh": -3}}, {"overrides": {"gdp_per_capita": 1e12}}, {"mix": {"solar_mult": 99}},
    {"mix": {"solar_mult": -1}}, {"mix": {"bogus": 1}}, {"mix": {"fossil_reduction_pct": 101}}, {"access_gap_pct": 140}])
def test_invalid_scenarios_are_422_with_a_message(client, body):
    r = predict(client, "Kenya", **body)
    assert r.status_code == 422 and r.json["error"]["message"]


def test_nan_and_non_numbers_rejected(client):
    assert client.post("/api/ml/predict", json={"country": "India", "overrides": {"electricity_access": "high"}}, headers=H).status_code == 422
    assert client.post("/api/ml/predict", data='{"country":"India","overrides":{"electricity_access":NaN}}',
                       content_type="application/json", headers=H).status_code in (400, 422)
    assert predict(client, "Atlantis").status_code == 404


def test_low_reliability_flag_for_countries_without_inputs(client):
    r = predict(client, "Bolivia").json
    assert r["reliability"] == "low" and r["reliability_note"] and r["has_labelled_history"] is False


def test_every_country_predicts_without_server_errors(client, app):
    """Regression guard for the original 'What-if is broken' report: no country may produce a 5xx or invalid JSON."""
    for c in app.extensions["tw"].data.countries:
        r = predict(client, c, overrides={"electricity_access": 90}, mix={"wind_mult": 2})
        assert r.status_code in (200, 422), (c, r.status_code, r.data[:200])
        if r.status_code == 200:
            json.loads(r.data.decode())                      # strictly valid JSON (no NaN tokens)
            assert b"NaN" not in r.data
        cfg = client.get(f"/api/ml/scenario-config?country={c}")
        assert cfg.status_code in (200, 422) and b"NaN" not in cfg.data


def test_scenario_report_pdf(client):
    r = client.post("/api/ml/scenario-report", json={"country": "India", "overrides": {"electricity_access": 100}, "mix": {"solar_mult": 3}}, headers=H)
    assert r.status_code == 200 and r.data[:4] == b"%PDF" and "attachment" in r.headers["Content-Disposition"]
    assert client.post("/api/ml/scenario-report", json={"country": "India", "overrides": {"latitude": 1}}, headers=H).status_code == 422


# ---------------------------------------------------------------- model loading robustness
@pytest.fixture()
def models_copy(tmp_path):
    dst = tmp_path / "models"
    shutil.copytree(ROOT / "models", dst)
    return dst


def test_corrupt_model_file_triggers_automatic_retrain(app, models_copy):
    (models_copy / "regressor.joblib").write_bytes(b"not a pickle")
    p = Predictor(models_copy, app.extensions["tw"].data, auto_retrain=True)
    assert p.error is None and p.retrained
    assert 0 <= p.predict("India", {})["baseline"]["share"] <= 100


def test_sklearn_version_mismatch_triggers_retrain(app, models_copy):
    card = json.loads((models_copy / "model_cards.json").read_text())
    card["env"]["sklearn"] = "0.20.0"
    (models_copy / "model_cards.json").write_text(json.dumps(card))
    p = Predictor(models_copy, app.extensions["tw"].data, auto_retrain=True)
    assert p.retrained and p.error is None
    assert json.loads((models_copy / "model_cards.json").read_text())["env"]["sklearn"] != "0.20.0"


def test_unrecoverable_models_give_clear_503_not_a_crash(tmp_path):
    from backend.app import create_app
    app = create_app(TESTING=True, DATABASE_PATH=tmp_path / "t.db", INSTANCE_DIR=tmp_path, MODELS_DIR=tmp_path / "nomodels",
                     AUTO_RETRAIN=False)
    c = app.test_client()
    for url in ("/api/ml/models", "/api/ml/clusters", "/api/ml/scenario-config?country=India"):
        r = c.get(url)
        assert r.status_code == 503 and "python -m backend.manage train" in r.json["error"]["message"], url
    assert c.post("/api/ml/predict", json={"country": "India"}, headers=H).status_code == 503
    assert c.get("/api/ml/status").json["ok"] is False
    assert c.get("/api/overview").status_code == 200                   # the rest of the app keeps working
    assert c.get("/api/health").json["models_loaded"] is False
