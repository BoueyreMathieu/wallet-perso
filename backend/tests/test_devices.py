"""Appli Android : connexion par jeton d'appareil, CORS, résumé des widgets."""

from datetime import date


def test_device_token_flow(client):
    assert client.post("/api/auth/device", json={"password": "faux", "name": "Pixel"}).status_code == 401
    token = client.post("/api/auth/device", json={"password": "test-password", "name": "Pixel"}).json()["token"]
    assert token.startswith("wpd_")
    h = {"Authorization": f"Bearer {token}"}

    client.cookies.clear()  # l'appli n'a pas de cookie : seulement le jeton
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers=h).status_code == 200
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer wpd_inconnu"}).status_code == 401

    devices = client.get("/api/auth/devices", headers=h).json()
    assert [d["name"] for d in devices] == ["Pixel"] and devices[0]["last_used_at"] is not None

    acc = client.post("/api/accounts", json={"name": "Espèces", "type": "especes", "initial_balance_cents": 5000}, headers=h).json()
    client.post("/api/transactions", headers=h, json={"account_id": acc["id"], "booked_at": date.today().isoformat(), "amount_cents": -1200, "label": "Café inventé"})
    s = client.get("/api/widgets/summary", headers=h).json()
    assert s["spent_cents"] == 1200 and s["net_worth_cents"] == 3800
    assert s["recent"][0]["label"] == "Café inventé" and s["accounts"][0]["name"] == "Espèces"

    # Déconnexion de l'appli : le jeton ne marche plus.
    assert client.post("/api/auth/device/logout", headers=h).status_code == 200
    assert client.get("/api/auth/me", headers=h).status_code == 401


def test_revoke_device_from_browser(auth_client):
    token = auth_client.post("/api/auth/device", json={"password": "test-password", "name": "Vieux téléphone"}).json()["token"]
    device = auth_client.get("/api/auth/devices").json()[0]
    assert auth_client.delete(f"/api/auth/devices/{device['id']}").status_code == 200
    assert auth_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_cors_for_android_app(client):
    r = client.options(
        "/api/auth/me",
        headers={"Origin": "https://localhost", "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"},
    )
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "https://localhost"
    r = client.options("/api/auth/me", headers={"Origin": "https://ailleurs.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in r.headers
