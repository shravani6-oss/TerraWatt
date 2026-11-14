"""Carbon calculator v2: exact arithmetic, disclosed assumptions, uncertainty, validation, persistence."""
import math

import pytest
from conftest import H

from backend.app.services import carbon

GRID = {"g_per_kwh": 700.0, "year": 2024, "from_data": True, "source": "test"}
SIMPLE = {"mode": "simple", "period": "2026-01", "country": "India", "household_size": 4,
          "electricity": {"bill_inr": 2100}, "cooking": {"type": "lpg_14kg", "per_month": 1},
          "vehicles": [{"type": "motorcycle", "km_per_month": 400}], "transit": {"metro_km": 100}, "flights": {"frequency": "occasionally"}}


def item(res, key):
    return next(i for i in res["items"] if i["key"] == key)


def test_advanced_exact_arithmetic():
    r = carbon.evaluate_advanced({"electricity_kwh": 100, "gas_m3": 10, "car_km": 100, "flight_km": 1000, "renewable_pct": 50,
                                  "household_size": 2}, {**GRID, "g_per_kwh": 500})
    assert r["parts"]["electricity"] == 25.0 and r["parts"]["cooking_heating"] == 20.0
    assert r["parts"]["vehicles"] == 17.0 and r["parts"]["flights"] == 150.0
    assert r["total_kg"] == 212.0 and r["per_person_kg"] == 106.0
    assert r["low_kg"] < r["total_kg"] < r["high_kg"]


def test_bill_conversion_uses_disclosed_tariff_and_is_flagged_estimated():
    r = carbon.evaluate_household({"household_size": 1, "electricity": {"bill_inr": 700}}, GRID)
    e = item(r, "electricity")
    assert e["basis"] == "estimated" and e["kg"] == round(700 / carbon.DEFAULT_TARIFF_INR * 0.7, 2)
    assert any("₹7/kWh" in a for a in r["assumptions"])
    custom = carbon.evaluate_household({"household_size": 1, "electricity": {"bill_inr": 700, "tariff_inr_per_kwh": 10}}, GRID)
    assert item(custom, "electricity")["kg"] < e["kg"]


def test_actual_kwh_beats_bill_and_is_flagged_actual():
    r = carbon.evaluate_household({"household_size": 1, "electricity": {"kwh": 200, "bill_inr": 99999}}, GRID)
    e = item(r, "electricity")
    assert e["basis"] == "actual" and e["kg"] == 140.0


def test_lpg_cylinders_and_two_wheelers():
    r = carbon.evaluate_household({"household_size": 1, "cooking": {"type": "lpg_14kg", "per_month": 1},
                                   "vehicles": [{"type": "scooter", "km_per_month": 450}, {"type": "ev_two_wheeler", "km_per_month": 100}]}, GRID)
    assert item(r, "lpg")["kg"] == round(14.2 * 2.98, 2)
    assert item(r, "vehicle0")["kg"] == round(450 / 45 * 2.31, 2)          # 10 L petrol
    assert item(r, "vehicle1")["kg"] == round(100 * 0.035 * 0.7, 2)        # EV uses grid intensity
    five = carbon.evaluate_household({"household_size": 1, "cooking": {"type": "lpg_5kg", "per_month": 2}}, GRID)
    assert item(five, "lpg")["kg"] == round(2 * 5 * 2.98, 2)


def test_skipped_questions_are_allowed_and_listed():
    r = carbon.evaluate_household({"household_size": 3, "electricity": {"kwh": 150}}, GRID)
    assert "cooking fuel" in r["skipped"] and "flights" in r["skipped"] and r["total_kg"] > 0
    with pytest.raises(ValueError):
        carbon.evaluate_household({"household_size": 3}, GRID)


def test_flight_bands_disclosed_and_ordered():
    never = carbon.evaluate_household({"household_size": 1, "electricity": {"kwh": 100}, "flights": "never"}, GRID)["parts"]["flights"]
    occ = carbon.evaluate_household({"household_size": 1, "electricity": {"kwh": 100}, "flights": {"frequency": "occasionally"}}, GRID)
    freq = carbon.evaluate_household({"household_size": 1, "electricity": {"kwh": 100}, "flights": {"frequency": "frequently"}}, GRID)
    assert never == 0 < occ["parts"]["flights"] < freq["parts"]["flights"]
    assert any("passenger-km/year" in a for a in occ["assumptions"])


def test_uncertainty_combines_in_quadrature():
    r = carbon.evaluate_household({k: v for k, v in SIMPLE.items() if k not in ("mode", "period", "country")}, GRID)
    expected = math.sqrt(sum(i["half_range_kg"] ** 2 for i in r["items"]))
    assert abs((r["high_kg"] - r["total_kg"]) - expected) < 0.02
    assert 0 < r["estimated_share"] <= 1


def test_estimate_endpoint_simple_and_benchmark(client):
    r = client.post("/api/footprint/estimate", json=SIMPLE, headers=H)
    assert r.status_code == 200
    j = r.json
    assert j["mode"] == "simple" and j["per_person_kg"] == round(j["total_kg"] / 4, 2)
    assert j["benchmark"]["country"] == "India" and "household operations only" in j["benchmark"]["caveat"]
    assert "operational" in j["scope"] and j["recommendations"] and j["factor_version"] == carbon.FACTOR_VERSION
    assert j["grid"]["from_data"] and j["grid"]["year"] == 2024


def test_norway_footprint_much_lower_electricity_than_india(client):
    kw = {"mode": "simple", "period": "2026-01", "household_size": 2, "electricity": {"kwh": 300}}
    i = client.post("/api/footprint/estimate", json={**kw, "country": "India"}, headers=H).json["parts"]["electricity"]
    n = client.post("/api/footprint/estimate", json={**kw, "country": "Norway"}, headers=H).json["parts"]["electricity"]
    assert i > 5 * n


@pytest.mark.parametrize("patch", [{"household_size": 0}, {"household_size": 50}, {"vehicles": [{"type": "hovercraft", "km_per_month": 5}]},
                                   {"electricity": {"bill_inr": -5}}, {"cooking": {"type": "coal", "per_month": 1}},
                                   {"period": "2026-13"}, {"unknown": 1}, {"country": "Atlantis"}])
def test_simple_validation(client, patch):
    assert client.post("/api/footprint/estimate", json={**SIMPLE, **patch}, headers=H).status_code in (404, 422)


def test_empty_simple_form_is_rejected(client):
    r = client.post("/api/footprint/estimate", json={"mode": "simple", "period": "2026-01", "household_size": 2}, headers=H)
    assert r.status_code == 422


def test_simple_entry_persists_raw_inputs_and_recomputes(user):
    r = user.post("/api/footprint/entries", json=SIMPLE, headers=H)
    assert r.status_code == 201
    e = user.get("/api/footprint/entries").json["entries"][0]
    assert e["mode"] == "simple" and e["household_size"] == 4 and e["inputs"]["electricity"]["bill_inr"] == 2100
    assert e["co2_low"] < e["co2_kg"] < e["co2_high"] and e["factor_version"] == carbon.FACTOR_VERSION
    s = user.get("/api/footprint/summary").json
    assert s["count"] == 1 and set(s["totals_by_category"]) == set(carbon.CATEGORIES) and s["benchmark"]
    assert b"kg_electricity" in user.get("/api/footprint/export.csv").data


def test_legacy_v1_rows_are_migrated_and_readable(tmp_path):
    """A database created by v1 (no new columns) must upgrade in place and still show its rows."""
    import sqlite3

    from backend.app import create_app
    db = tmp_path / "old.db"
    c = sqlite3.connect(db)
    c.executescript("""CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
        password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user', is_active INTEGER NOT NULL DEFAULT 1,
        home_country TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')), last_login_at TEXT);
        CREATE TABLE footprint_entries (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, period TEXT NOT NULL,
        country TEXT NOT NULL, electricity_kwh REAL NOT NULL DEFAULT 0, gas_m3 REAL NOT NULL DEFAULT 0, car_km REAL NOT NULL DEFAULT 0,
        flight_km REAL NOT NULL DEFAULT 0, renewable_pct REAL NOT NULL DEFAULT 0, co2_kg REAL NOT NULL, breakdown TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')), UNIQUE (user_id, period));
        INSERT INTO users (email, name, password_hash) VALUES ('old@x.io','Old','x');
        INSERT INTO footprint_entries (user_id, period, country, electricity_kwh, car_km, co2_kg, breakdown)
        VALUES (1, '2025-12', 'India', 300, 100, 9999, '{}');""")
    c.commit()
    c.close()
    app = create_app(TESTING=True, DATABASE_PATH=db, INSTANCE_DIR=tmp_path)
    with app.app_context():
        from backend.app.db import connect
        cols = {r["name"] for r in connect(db).execute("PRAGMA table_info(footprint_entries)")}
        assert {"mode", "inputs_json", "household_size", "factor_version"} <= cols
        from backend.app.services import entries
        row = connect(db).execute("SELECT * FROM footprint_entries").fetchone()
        res = entries.result_for(row, app.extensions["tw"].data)
        assert res["mode"] == "advanced" and res["total_kg"] > 200          # recomputed, not the stale stored 9999
