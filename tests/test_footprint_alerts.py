import pytest
from backend.app.services import carbon
from conftest import H

ENTRY = {"mode": "advanced", "period": "2026-01", "country": "India", "electricity_kwh": 300, "gas_m3": 10, "car_km": 200, "flight_km": 0, "renewable_pct": 0}


def test_estimate_is_public_and_uses_country_grid(client):
    india = client.post("/api/footprint/estimate", json={**ENTRY, "gas_m3": 0, "car_km": 0}, headers=H).json
    norway = client.post("/api/footprint/estimate", json={**ENTRY, "country": "Norway", "gas_m3": 0, "car_km": 0}, headers=H).json
    assert india["total_kg"] > 5 * norway["total_kg"] and india["grid_from_data"]
    assert india["recommendations"][0]["saving_kg_month"] > 0


@pytest.mark.parametrize("patch", [{"electricity_kwh": -5}, {"period": "2026-13"}, {"renewable_pct": 120}, {"electricity_kwh": 0, "gas_m3": 0, "car_km": 0}, {"country": "Atlantis"}])
def test_footprint_validation(client, patch):
    assert client.post("/api/footprint/estimate", json={**ENTRY, **patch}, headers=H).status_code in (404, 422)


def test_entry_crud_upsert_and_isolation(user, app):
    assert user.post("/api/footprint/entries", json=ENTRY, headers=H).status_code == 201
    user.post("/api/footprint/entries", json={**ENTRY, "car_km": 0}, headers=H)       # same month -> replace
    s = user.get("/api/footprint/summary").json
    assert s["count"] == 1 and s["entries"][0]["car_km"] == 0
    eid = s["entries"][0]["id"]
    other = app.test_client()
    other.post("/api/auth/register", json={"name": "Bob", "email": "bob@example.com", "password": "Secret123"}, headers=H)
    assert other.delete(f"/api/footprint/entries/{eid}", headers=H).status_code == 404     # cannot touch another user's row
    assert other.get("/api/footprint/summary").json["count"] == 0
    assert user.delete(f"/api/footprint/entries/{eid}", headers=H).status_code == 200
    assert b"period" in user.get("/api/footprint/export.csv").data


def test_alert_rule_fires_once_and_dedupes(user):
    r = user.post("/api/alerts/rules", json={"country": "India", "metric": "renewable_share", "condition": "below", "threshold": 60}, headers=H)
    assert r.status_code == 201 and r.json["notifications_created"] == 1
    assert user.post("/api/alerts/evaluate", headers=H).json["notifications_created"] == 0
    n = user.get("/api/notifications").json
    assert n["unread"] == 1
    user.post("/api/notifications/read", headers=H)
    assert user.get("/api/notifications").json["unread"] == 0


def test_alert_not_fired_when_condition_false(user):
    r = user.post("/api/alerts/rules", json={"country": "Norway", "metric": "renewable_share", "condition": "below", "threshold": 5}, headers=H)
    assert r.json["notifications_created"] == 0


def test_forecast_alert_requires_year_and_forecastable_metric(user):
    assert user.post("/api/alerts/rules", json={"country": "India", "metric": "renewable_share", "condition": "forecast_below", "threshold": 50}, headers=H).status_code == 422
    assert user.post("/api/alerts/rules", json={"country": "India", "metric": "gdp_per_capita", "condition": "forecast_below", "threshold": 50, "year": 2030}, headers=H).status_code == 422
    ok = user.post("/api/alerts/rules", json={"country": "India", "metric": "renewable_share", "condition": "forecast_below", "threshold": 50, "year": 2030}, headers=H)
    assert ok.status_code == 201 and ok.json["notifications_created"] == 1


def test_watchlist(user):
    user.post("/api/watchlist", json={"country": "brazil"}, headers=H)
    items = user.get("/api/watchlist").json["items"]
    assert items[0]["country"] == "Brazil" and items[0]["series"]
    user.delete("/api/watchlist/Brazil", headers=H)
    assert user.get("/api/watchlist").json["items"] == []
