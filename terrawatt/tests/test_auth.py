from conftest import H


def test_register_login_logout(client):
    r = client.post("/api/auth/register", json={"name": "Ada", "email": "A@Example.com", "password": "Secret123"}, headers=H)
    assert r.status_code == 201 and r.json["user"]["email"] == "a@example.com"
    assert "HttpOnly" in r.headers["Set-Cookie"] and "SameSite=Lax" in r.headers["Set-Cookie"]
    assert client.get("/api/auth/me").json["user"]["name"] == "Ada"
    client.post("/api/auth/logout", headers=H)
    assert client.get("/api/auth/me").json["user"] is None


def test_duplicate_email_conflict(user, client):
    r = client.post("/api/auth/register", json={"name": "Other", "email": "ADA@example.com", "password": "Secret123"}, headers=H)
    assert r.status_code == 409 and r.json["error"]["code"] == "email_taken"


def test_password_policy_and_validation_errors(client):
    r = client.post("/api/auth/register", json={"name": "A", "email": "nope", "password": "short"}, headers=H)
    assert r.status_code == 422
    fields = {d["field"] for d in r.json["error"]["details"]}
    assert {"name", "email", "password"} <= fields


def test_extra_fields_rejected(client):
    r = client.post("/api/auth/register", json={"name": "Ada", "email": "a@b.co", "password": "Secret123", "role": "admin"}, headers=H)
    assert r.status_code == 422      # mass-assignment of `role` is impossible


def test_csrf_header_required(client):
    r = client.post("/api/auth/register", json={"name": "Ada", "email": "a@b.co", "password": "Secret123"})
    assert r.status_code == 403 and r.json["error"]["code"] == "csrf_failed"


def test_login_wrong_password_and_throttle(user, app):
    c = app.test_client()
    for _ in range(5):
        assert c.post("/api/auth/login", json={"email": "ada@example.com", "password": "bad"}, headers=H).status_code == 401
    r = c.post("/api/auth/login", json={"email": "ada@example.com", "password": "Secret123"}, headers=H)
    assert r.status_code == 429          # even the right password is blocked while throttled


def test_protected_routes_need_session(client):
    for path in ("/api/footprint/entries", "/api/alerts/rules", "/api/notifications", "/api/watchlist"):
        assert client.get(path).status_code == 401


def test_admin_forbidden_for_user_allowed_for_admin(user, admin):
    assert user.get("/api/admin/stats").status_code == 403
    assert admin.get("/api/admin/stats").json["users"] >= 2


def test_admin_cannot_modify_self_and_can_disable_user(user, admin):
    uid = [u for u in admin.get("/api/admin/users").json["users"] if u["email"] == "ada@example.com"][0]["id"]
    assert admin.patch(f"/api/admin/users/{uid}", json={"is_active": False}, headers=H).status_code == 200
    assert user.get("/api/auth/me").json["user"] is None        # revocation is immediate
    me = [u for u in admin.get("/api/admin/users").json["users"] if u["role"] == "admin"][0]["id"]
    assert admin.patch(f"/api/admin/users/{me}", json={"role": "user"}, headers=H).status_code == 400


def test_change_password_and_delete_account(user, app):
    assert user.put("/api/auth/password", json={"current_password": "wrong1234", "new_password": "NewPass123"}, headers=H).status_code == 400
    assert user.put("/api/auth/password", json={"current_password": "Secret123", "new_password": "NewPass123"}, headers=H).status_code == 200
    assert user.delete("/api/users/me", headers=H).status_code == 200
    assert app.test_client().post("/api/auth/login", json={"email": "ada@example.com", "password": "NewPass123"}, headers=H).status_code == 401


def test_tampered_cookie_rejected(client):
    client.set_cookie("tw_session", "not.a.jwt")
    assert client.get("/api/auth/me").json["user"] is None
