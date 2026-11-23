from fastapi.testclient import TestClient

from tests.conftest import Api


def test_login_me_logout(client):
    a = Api(client)
    assert a.login(password="wrong-password-here").status_code == 401
    r = a.login()
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "admin"
    assert a.get("/api/auth/me").json()["user"]["username"] == "admin"
    # Unsafe methods need the CSRF header.
    assert client.post("/api/auth/logout").status_code == 403
    assert a.post("/api/auth/logout").status_code == 200
    assert a.get("/api/auth/me").status_code == 401


def test_rate_limit(client):
    a = Api(client)
    for _ in range(5):
        assert a.login(password="nope-nope-nope").status_code == 401
    assert a.login().status_code == 429


def test_admin_created_user_must_change_password(api):
    r = api.post("/api/users", json={"username": "molly", "display_name": "Molly"})
    assert r.status_code == 201
    temp = r.json()["temporary_password"]
    m = Api(TestClient(api.c.app))
    assert m.login("molly", temp).status_code == 200
    assert m.get("/api/occasions").json()["detail"] == "password_change_required"
    assert m.post("/api/auth/password", json={"current_password": temp, "new_password": "short"}).status_code == 422
    r = m.post("/api/auth/password", json={"current_password": temp, "new_password": "a-much-better-password"})
    assert r.status_code == 200
    assert m.get("/api/occasions").status_code == 200


def test_non_admin_cannot_admin(second):
    assert second.get("/api/users").status_code == 403
    assert second.post("/api/invites", json={}).status_code == 403
    assert second.post("/api/categories", json={"name": "Kids"}).status_code == 403
    assert second.get("/api/occasions").status_code == 200
    assert second.get("/api/users/directory").status_code == 200


def test_invite_flow(api):
    r = api.post("/api/invites", json={"note": "For Jo"})
    assert r.status_code == 201
    token = r.json()["token"]
    assert r.json()["path"] == f"/#/invite/{token}"

    guest = Api(TestClient(api.c.app))
    assert guest.get(f"/api/auth/invite/{token}").status_code == 200
    assert guest.get("/api/auth/invite/not-a-real-token").status_code == 404
    bad = guest.post(f"/api/auth/invite/{token}", json={"username": "jo", "password": "short"})
    assert bad.status_code == 422
    r = guest.post(
        f"/api/auth/invite/{token}", json={"username": "jo", "display_name": "Jo", "password": "jo-has-a-long-password"}
    )
    assert r.status_code == 200
    guest.csrf = r.json()["csrf_token"]
    me = guest.get("/api/auth/me").json()["user"]
    assert me["name"] == "Jo" and me["role"] == "user"
    # Single use.
    again = Api(TestClient(api.c.app))
    assert (
        again.post(
            f"/api/auth/invite/{token}", json={"username": "jo2", "password": "jo-has-a-long-password"}
        ).status_code
        == 404
    )
    invites = api.get("/api/invites").json()["invites"]
    assert invites[0]["state"] == "used" and invites[0]["used_by"] == "Jo"


def test_invite_username_taken_and_revoke(api):
    token = api.post("/api/invites", json={}).json()["token"]
    guest = Api(TestClient(api.c.app))
    r = guest.post(f"/api/auth/invite/{token}", json={"username": "ADMIN", "password": "long-enough-password"})
    assert r.status_code == 409
    inv_id = api.get("/api/invites").json()["invites"][0]["id"]
    assert api.delete(f"/api/invites/{inv_id}").status_code == 200
    assert guest.get(f"/api/auth/invite/{token}").status_code == 404


def test_healthz_and_spa(client):
    assert client.get("/healthz").json()["ok"] is True
    r = client.get("/some/where")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert client.get("/api/nope").status_code == 404
