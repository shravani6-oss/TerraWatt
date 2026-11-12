import pytest
from conftest import H


def test_meta_and_provenance(client):
    r = client.get("/api/meta").json
    assert len(r["countries"]) == 176 and r["headline_year"] == 2019
    assert r["provenance"]["type"] == "historical"


def test_overview_matches_known_magnitudes(client):
    k = client.get("/api/overview").json["kpis"]
    assert 25 < k["global_renewable_electricity_share"] < 32       # ~27-29% in 2019 (sanity vs public stats)
    assert 25 < k["co2_mt"] / 1000 < 40                            # ~30-37 Gt


def test_country_profile_and_unknown_country(client):
    r = client.get("/api/countries/india")                         # case-insensitive
    assert r.status_code == 200 and r.json["info"]["country"] == "India" and r.json["recommendations"]
    assert client.get("/api/countries/Atlantis").status_code == 404


@pytest.mark.parametrize("url", ["/api/rankings?metric=bogus", "/api/rankings?year=abc", "/api/compare?countries=", "/api/compare?countries=A,B,C,D,E,F"])
def test_bad_params_are_400_or_404(client, url):
    assert client.get(url).status_code in (400, 404)


def test_rankings_sorted_and_ranked(client):
    rows = client.get("/api/rankings?metric=renewable_elec_share&year=2019").json["rows"]
    vals = [r["value"] for r in rows]
    assert vals == sorted(vals, reverse=True) and rows[0]["rank"] == 1


def test_records_pagination_filter(client):
    r = client.get("/api/records?q=nor&per_page=5&sort=year&order=desc").json
    assert r["per_page"] == 5 and all("nor" in x["country"].lower() for x in r["rows"])


def test_sql_injection_like_input_is_harmless(client):
    assert client.get("/api/records?q=' OR 1=1 --").json["total"] == 0


def test_forecast_shape_and_monotone_interval(client):
    f = client.get("/api/forecast/India?metric=renewable_share&to=2030&target=40").json
    assert f["forecast"][0]["year"] == 2020 and f["forecast"][-1]["year"] == 2030
    for r in f["forecast"]:
        assert 0 <= r["lo"] <= r["value"] <= r["hi"] <= 100
    assert f["forecast"][4]["validated"] and not f["forecast"][5]["validated"]
    assert f["model"]["interval_coverage_validation"] > 0.6
    assert f["target_crossing"]["status"] in ("forecast", "not_within_horizon", "already_reached")


def test_forecast_rejects_unforecastable_metric(client):
    assert client.get("/api/forecast/India?metric=gdp_per_capita").status_code == 400


def test_backtest_selection_does_not_use_validation(client):
    q = client.get("/api/forecast-quality?metric=renewable_share").json
    assert q["origins"]["calibration"][1] < q["origins"]["validation"][0]
    assert q["mae_validation"][q["method"]] <= q["mae_validation"]["naive"] * 1.15


def test_ml_predict_what_if(client):
    r = client.post("/api/ml/predict", json={"country": "Kenya", "overrides": {"electricity_access": 100}}, headers=H)
    assert r.status_code == 200 and 0 <= r.json["scenario"]["share"] <= 100 and r.json["effects"]
    bad = client.post("/api/ml/predict", json={"country": "Kenya", "overrides": {"latitude": 5}}, headers=H)
    assert bad.status_code == 422


def test_model_cards_report_held_out_metrics(client):
    c = client.get("/api/ml/models").json
    assert any(r["selected"] for r in c["regression"]["table"])
    assert c["classification"]["n_test_countries"] > 20


def test_exports(client):
    csv = client.get("/api/export/country/India.csv")
    assert csv.mimetype == "text/csv" and b"renewable_share" in csv.data
    pdf = client.get("/api/export/country/India.pdf")
    assert pdf.data[:4] == b"%PDF"
    assert client.get("/api/export/rankings.csv?metric=co2_kt").status_code == 200


def test_unknown_api_route_json_404(client):
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.json["error"]["code"] == "not_found"


def test_security_headers(client):
    h = client.get("/api/health").headers
    assert h["X-Content-Type-Options"] == "nosniff" and "frame-ancestors 'none'" in h["Content-Security-Policy"]
