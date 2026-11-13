"""Sécurité : blocage après échecs, sessions révocables, confirmation des actions destructrices, divers."""

from datetime import datetime, timedelta, timezone

from app.log_filters import mask_query
from app.passwords import hash_password, verify_password
from app.regex_safety import check_regex


def test_lockout_after_repeated_failures(client):
    for _ in range(5):
        assert client.post("/api/auth/login", json={"password": "faux"}).status_code == 401
    # Bloqué : même le bon mot de passe est refusé tant que le délai court.
    r = client.post("/api/auth/login", json={"password": "test-password"})
    assert r.status_code == 429 and "réessaie" in r.json()["detail"] and int(r.headers["retry-after"]) > 0
    assert client.post("/api/auth/device", json={"password": "test-password"}).status_code == 429


def test_success_resets_failure_count(client):
    for _ in range(4):
        client.post("/api/auth/login", json={"password": "faux"})
    assert client.post("/api/auth/login", json={"password": "test-password"}).status_code == 200
    for _ in range(4):
        client.post("/api/auth/login", json={"password": "faux"})
    assert client.post("/api/auth/login", json={"password": "test-password"}).status_code == 200


def test_logout_revokes_session_server_side(client):
    assert client.post("/api/auth/login", json={"password": "test-password"}).status_code == 200
    stolen = client.cookies.get("wallet_session")
    assert stolen.startswith("wps_")
    assert client.get("/api/auth/me", headers={"Cookie": f"wallet_session={stolen}"}).status_code == 200
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert client.get("/api/auth/me", headers={"Cookie": f"wallet_session={stolen}"}).status_code == 401


def test_old_signed_cookie_is_refused(client):
    client.cookies.clear()
    assert client.get("/api/auth/me", headers={"Cookie": "wallet_session=eyJ1c2VyIjoib3duZXIifQ.signature"}).status_code == 401


def test_idle_session_expires(client):
    from app.db import get_sessionmaker
    from app.models import DeviceToken

    client.post("/api/auth/login", json={"password": "test-password"})
    with get_sessionmaker()() as db:
        row = db.query(DeviceToken).one()
        old = datetime.now(timezone.utc) - timedelta(days=15)
        row.created_at, row.last_used_at = old, old
        db.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_destructive_actions_need_password(client):
    client.post("/api/auth/login", json={"password": "test-password"})
    assert client.post("/api/data/reset-categorization").status_code == 428
    r = client.post("/api/data/reset-categorization", headers={"X-Confirm-Password": "faux"})
    assert r.status_code == 403
    assert client.get("/api/auth/me").status_code == 200  # un mauvais mot de passe ne déconnecte pas
    ok = client.post("/api/data/reset-categorization", headers={"X-Confirm-Password": "test%2Dpassword"})  # encodé comme le front
    assert ok.status_code == 200
    kinds = [e["kind"] for e in client.get("/api/auth/security").json()["events"]]
    assert kinds[:2] == ["confirmation", "echec_mdp"] and "connexion" in kinds


def test_logout_others_keeps_current_session(client):
    token = client.post("/api/auth/device", json={"password": "test-password", "name": "Pixel"}).json()["token"]
    client.post("/api/auth/login", json={"password": "test-password"})
    devices = client.get("/api/auth/devices").json()
    assert sorted((d["kind"], d["current"]) for d in devices) == [("app", False), ("navigateur", True)]
    assert client.post("/api/auth/logout-others").json()["revoked"] == 1
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.get("/api/auth/me").status_code == 200


def test_security_overview_and_backup_warning(auth_client):
    from app.db import get_sessionmaker
    from app.models import AppMeta

    s = auth_client.get("/api/auth/security").json()
    assert s["password_hashed"] is False and "Aucune sauvegarde" in s["backup"]["warning"]
    with get_sessionmaker()() as db:
        db.add(AppMeta(key="backup_last_ok", value='{"at": "%s", "size": 1234, "offsite": "ok"}' % datetime.now(timezone.utc).isoformat()))
        db.commit()
    s = auth_client.get("/api/auth/security").json()
    assert s["backup"]["warning"] is None and s["backup"]["last_size_bytes"] == 1234


def test_api_docs_hidden_and_no_cache(auth_client):
    assert auth_client.get("/api/openapi.json").status_code in (401, 404)
    assert auth_client.get("/docs").status_code == 404
    assert auth_client.get("/api/auth/me").headers["cache-control"] == "no-store"


def test_password_hash_roundtrip():
    h = hash_password("une phrase de passe très longue")
    assert h.startswith("scrypt:") and "$" not in h
    assert verify_password("une phrase de passe très longue", h)
    assert not verify_password("autre", h) and not verify_password("x", "pas-une-empreinte")


def test_regex_guard_and_log_masking():
    assert check_regex("NETFLIX|SPOTIFY") is None
    assert "imbriquée" in check_regex("(a+)+$")
    assert "trop longue" in check_regex("a" * 300)
    assert mask_query("/api/connections/callback?code=abc&state=def") == "/api/connections/callback?code=***&state=***"
