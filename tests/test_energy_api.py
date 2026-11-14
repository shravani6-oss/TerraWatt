import pytest
from conftest import H


def test_meta_and_provenance(client):
    r = client.get("/api/meta").json
    assert len(r["countries"]) == 194 and r["years"] == [2000, 2025]
    assert r["headline_year"] == 2024                                # latest year with broad electricity coverage
    ind = {m["key"]: m for m in r["metrics"]}
    assert ind["renewable_share"]["latest_year"] == 2020             # World Bank series is NOT extended
    assert ind["solar_twh"]["latest_year"] == 2025 and ind["solar_twh"]["default_year"] == 2024
    assert r["provenance"]["type"] == "historical"


def test_overview_matches_known_magnitudes(client):
    o = client.get("/api/overview").json
    k = o["kpis"]
    assert 28 < k["renewable_elec_share"]["value"] < 36              # Ember: ~32% in 2024
    assert 30 < k["co2_mt"]["value"] / 1000 < 45                     # ~37 Gt
    assert k["renewable_elec_share"]["year"] == 2024 and k["co2_mt"]["year"] == 2025
    assert k["electricity_access"]["year"] == 2020 and k["renewable_share"]["year"] == 2019   # indicator-specific years
    assert o["partial_year_note"] and "2025" in o["partial_year_note"]
    assert abs(sum(p["share"] for p in o["mix"]["parts"]) - 100) < 0.5


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


def test_official_targets_are_verified_and_matched_only_when_comparable(client):
    t = client.get("/api/targets").json["targets"]
    assert {x["country"] for x in t} == {"Spain", "Germany", "Ireland"}
    assert all(x["source"].startswith("https://") and x["wording"] and x["comparability"] in ("like-for-like", "approximate") for x in t)
    f = client.get("/api/forecast/Spain?metric=renewable_elec_share&to=2030").json
    assert f["official_target"]["value"] == 81 and f["official_target"]["gap_pp"] == round(81 - f["forecast"][-1]["value"], 2)
    assert client.get("/api/forecast/Germany?metric=renewable_elec_share").json["official_target"]["comparability"] == "approximate"
    assert client.get("/api/forecast/Spain?metric=co2_kt").json["official_target"] is None          # different indicator: never compared
    assert client.get("/api/forecast/India?metric=renewable_elec_share").json["official_target"] is None


def test_renewables_endpoints(client):
    g = client.get("/api/renewables/global").json
    keys = {s["key"] for s in g["sources"]}
    assert keys == {"solar_twh", "wind_twh", "hydro_twh", "bioenergy_twh", "other_renew_twh"}
    assert abs(sum(s["share_of_renewables"] for s in g["sources"]) - 100) < 0.1
    assert next(s for s in g["sources"] if s["key"] == "hydro_twh")["share_of_renewables"] > 35
    solar = client.get("/api/renewables/ranking?source=solar_twh").json
    assert solar["rows"][0]["country"] == "China" and solar["year"] == 2024
    assert solar["rows"] == sorted(solar["rows"], key=lambda r: -r["value"])
    share = client.get("/api/renewables/ranking?source=wind_twh&by=share&limit=5").json["rows"]
    assert len(share) == 5 and all(r["value"] <= 100 for r in share)
    dom = client.get("/api/renewables/dominant").json
    assert dom["counts"].get("Hydropower", 0) > dom["counts"].get("Wind", 0)
    c = client.get("/api/renewables/country/Norway").json
    assert c["dominant"] == "Hydropower" and c["history"] and c["latest"][0]["share_of_electricity"] is not None
    assert "Solar" not in c["sources_without_data"]
    assert client.get("/api/renewables/country/Atlantis").status_code == 404
    assert client.get("/api/renewables/ranking?source=coal").status_code == 400


def test_compare_includes_world_average_and_up_to_five_countries(client):
    r = client.get("/api/compare?countries=India,China,Brazil,Norway,Germany&metric=solar_twh").json
    assert len(r["series"]) == 5 and r["world"] is None                 # absolute TWh has no per-capita world average
    r = client.get("/api/compare?countries=India,China&metric=electricity_access").json
    assert r["world"] and r["world"][-1]["year"] == 2020
    r = client.get("/api/compare?countries=India,China&metric=co2_per_capita_t").json
    assert r["world"] and r["world"][-1]["year"] >= 2024
    assert client.get("/api/compare?countries=A,B,C,D,E,F").status_code in (400, 404)


def test_country_profile_has_availability_and_renewables(client):
    j = client.get("/api/countries/India").json
    assert j["renewables"]["history"] and j["availability"]
    sol = next(a for a in j["availability"] if a["metric"] == "solar_twh")
    assert sol["latest_year"] == 2025 and sol["n_years"] >= 20
    assert client.get("/api/availability/India").json["indicators"]
