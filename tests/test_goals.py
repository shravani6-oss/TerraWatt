"""My Sustainability: goals, comparable-record rules, progress maths, badge unlocking, persistence, isolation."""
from conftest import H

GRID_INDIA = 0.7054          # 2024 Ember intensity, kg/kWh (pinned by the dataset)


def adv(period, kwh, **kw):
    return {"mode": "advanced", "period": period, "country": "India", "electricity_kwh": kwh, **kw}


def save(c, body):
    r = c.post("/api/footprint/entries", json=body, headers=H)
    assert r.status_code == 201, r.json
    return r.json


def set_goal(c, **kw):
    r = c.post("/api/goals", json={"kind": "percent", "percent": 10, "baseline_period": "2026-01", **kw}, headers=H)
    assert r.status_code == 201, r.json
    return r.json


def progress(c):
    return c.get("/api/goals/progress", headers=H).json


def badge_state(c):
    return {b["key"]: b["unlocked"] for b in progress(c)["badges"]}


def test_requires_login(client):
    assert client.get("/api/goals/progress").status_code == 401
    assert client.post("/api/goals", json={"kind": "percent", "percent": 10, "baseline_period": "2026-01"}, headers=H).status_code == 401


def test_goal_needs_a_baseline_entry(user):
    r = user.post("/api/goals", json={"kind": "percent", "percent": 10, "baseline_period": "2026-01"}, headers=H)
    assert r.status_code == 422 and "baseline" in r.json["error"]["message"].lower()


def test_goal_validation(user):
    save(user, adv("2026-01", 300))
    for bad in ({"kind": "percent"}, {"kind": "percent", "percent": 0}, {"kind": "percent", "percent": 95},
                {"kind": "absolute"}, {"kind": "absolute", "target_kg": 99999}, {"kind": "wat", "percent": 5}):
        assert user.post("/api/goals", json={"baseline_period": "2026-01", **bad}, headers=H).status_code == 422


def test_green_beginner_unlocks_on_first_goal_only(user):
    save(user, adv("2026-01", 300))
    assert not any(badge_state(user).values())
    r = set_goal(user)
    assert [b["key"] for b in r["new_badges"]] == ["green_beginner"]
    assert badge_state(user) == {"green_beginner": True, "eco_warrior": False, "consistent_saver": False, "planet_protector": False}
    assert user.get("/api/notifications").json["unread"] >= 1


def test_progress_dashboard_numbers(user):
    save(user, adv("2026-01", 300))
    g = set_goal(user, percent=10)
    base = round(300 * GRID_INDIA, 2)
    assert abs(g["goal"]["baseline_kg"] - base) < 0.01 and abs(g["goal"]["target_kg"] - base * 0.9) < 0.02
    save(user, adv("2026-02", 270))                          # 10% less electricity -> exactly at target
    d = progress(user)["dashboard"]
    assert d["period"] == "2026-02" and abs(d["reduction_pct"] - 10) < 0.1
    assert d["achieved"] and d["remaining_kg"] == 0 and d["progress_pct"] >= 99.9
    save(user, adv("2026-03", 285))                          # only 5% -> not achieved, half way
    d = progress(user)["dashboard"]
    assert not d["achieved"] and 45 < d["progress_pct"] < 55 and d["remaining_kg"] > 0
    assert d["months_tracked"] == 2 and d["months_achieved"] == 1


def test_eco_warrior_after_first_achieved_month_and_completion_date(user):
    save(user, adv("2026-01", 300))
    set_goal(user, percent=10)
    save(user, adv("2026-02", 295))
    assert not badge_state(user)["eco_warrior"]
    r = save(user, adv("2026-03", 250))
    assert "eco_warrior" in [b["key"] for b in r["new_badges"]]
    g = progress(user)["goal"]
    assert g["first_achieved_period"] == "2026-03" and g["first_achieved_at"]


def test_consistent_saver_needs_three_consecutive_months(user):
    save(user, adv("2026-01", 300))
    set_goal(user, percent=10)
    save(user, adv("2026-02", 250))
    save(user, adv("2026-03", 250))
    save(user, adv("2026-05", 250))                         # April is missing -> NOT consecutive
    assert not badge_state(user)["consistent_saver"]
    save(user, adv("2026-04", 250))                         # now Feb-Mar-Apr-May
    assert badge_state(user)["consistent_saver"]


def test_planet_protector_at_twenty_percent(user):
    save(user, adv("2026-01", 300))
    set_goal(user, percent=5)
    save(user, adv("2026-02", 250))                         # -16.7%
    assert not badge_state(user)["planet_protector"]
    save(user, adv("2026-03", 235))                         # -21.7%
    assert badge_state(user)["planet_protector"]


def test_absolute_goal(user):
    save(user, adv("2026-01", 300))
    g = set_goal(user, kind="absolute", percent=None, target_kg=150)
    assert g["goal"]["target_kg"] == 150
    save(user, adv("2026-02", 200))                         # 141 kg
    assert progress(user)["dashboard"]["achieved"]


def test_non_comparable_months_are_excluded_with_reason(user):
    save(user, adv("2026-01", 300, household_size=2))
    set_goal(user)
    save(user, adv("2026-02", 100, household_size=4))       # different household size
    save(user, {**adv("2026-03", 100, household_size=2), "country": "Norway"})
    save(user, {"mode": "simple", "period": "2026-04", "country": "India", "household_size": 2, "electricity": {"kwh": 50}})
    p = progress(user)
    assert p["dashboard"] is None and p["history"] == []
    reasons = {e["period"]: e["reason"] for e in p["excluded"]}
    assert "household size" in reasons["2026-02"] and "country" in reasons["2026-03"] and "mode" in reasons["2026-04"]
    assert not badge_state(user)["eco_warrior"]             # a "reduction" from a different household must not unlock badges


def test_months_before_baseline_do_not_count(user):
    save(user, adv("2025-12", 100))
    save(user, adv("2026-01", 300))
    set_goal(user)
    assert progress(user)["history"] == []


def test_progress_uses_current_factors_not_stored_values(user, app):
    """Rows are re-evaluated from raw inputs, so a stale stored co2_kg cannot change progress."""
    save(user, adv("2026-01", 300))
    set_goal(user)
    save(user, adv("2026-02", 250))
    from backend.app.db import connect
    c = connect(app.config["DATABASE_PATH"])
    c.execute("UPDATE footprint_entries SET co2_kg = 99999")
    c.commit()
    d = progress(user)["dashboard"]
    assert d["current_kg"] < 200 and d["achieved"]


def test_deleting_the_achieving_month_updates_progress(user):
    save(user, adv("2026-01", 300))
    set_goal(user)
    save(user, adv("2026-02", 250))
    eid = next(e["id"] for e in user.get("/api/footprint/entries").json["entries"] if e["period"] == "2026-02")
    assert user.delete(f"/api/footprint/entries/{eid}", headers=H).status_code == 200
    assert progress(user)["dashboard"] is None


def test_new_goal_archives_previous_and_badges_persist(user):
    save(user, adv("2026-01", 300))
    set_goal(user, percent=10)
    save(user, adv("2026-02", 250))
    assert badge_state(user)["eco_warrior"]
    set_goal(user, percent=20)
    p = progress(user)
    assert p["goal"]["percent"] == 20 and badge_state(user)["eco_warrior"]       # badges are never revoked


def test_recommendations_reflect_user_categories(user):
    save(user, adv("2026-01", 300, car_km=400))
    set_goal(user)
    save(user, adv("2026-02", 290, car_km=400))
    recs = progress(user)["recommendations"]
    assert recs and all(r["saving_kg_month"] > 0 for r in recs)
    assert {"electricity", "vehicles"} <= {r["category"] for r in recs}


def test_goals_are_private_per_user(user, app):
    save(user, adv("2026-01", 300))
    set_goal(user)
    other = app.test_client()
    other.post("/api/auth/register", json={"name": "Bob", "email": "bob@example.com", "password": "Secret123"}, headers=H)
    p = progress(other)
    assert p["goal"] is None and not any(b["unlocked"] for b in p["badges"])


def test_persistence_across_app_restart(tmp_path):
    from backend.app import create_app
    kw = dict(TESTING=True, DATABASE_PATH=tmp_path / "p.db", INSTANCE_DIR=tmp_path)
    a = create_app(**kw).test_client()
    a.post("/api/auth/register", json={"name": "Ada Lovelace", "email": "ada@example.com", "password": "Secret123"}, headers=H)
    save(a, adv("2026-01", 300))
    set_goal(a)
    save(a, adv("2026-02", 250))
    b = create_app(**kw).test_client()                     # "restart"
    assert b.post("/api/auth/login", json={"email": "ada@example.com", "password": "Secret123"}, headers=H).status_code == 200
    p = progress(b)
    assert p["goal"]["percent"] == 10 and p["dashboard"]["achieved"] and badge_state(b)["eco_warrior"]
