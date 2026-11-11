from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext


def test_migrations_match_models():
    """La migration écrite à la main doit produire exactement le schéma des modèles."""
    from app.db import Base, get_engine

    with get_engine().connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": False})
        diff = compare_metadata(ctx, Base.metadata)
    assert diff == [], diff


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_auth_required(client):
    client.cookies.clear()
    assert client.get("/api/accounts").status_code == 401


def test_bad_password(client):
    assert client.post("/api/auth/login", json={"password": "nope"}).status_code == 401


def test_categories_seeded(auth_client):
    cats = auth_client.get("/api/categories").json()
    names = {c["name"] for c in cats}
    assert {"Alimentation", "Courses", "Revenus", "Virement interne"} <= names


def test_accounts_and_net_worth(auth_client):
    r = auth_client.post(
        "/api/accounts",
        json={"name": "Compte courant", "type": "courant", "institution": "Crédit Agricole", "initial_balance_cents": 152_300},
    )
    assert r.status_code == 201, r.text
    courant = r.json()
    assert courant["balance_cents"] == 152_300
    assert courant["provider"] == "manuel"

    auth_client.post("/api/accounts", json={"name": "Crédit auto", "type": "credit", "initial_balance_cents": -500_000})
    tr = auth_client.post("/api/accounts", json={"name": "Trade Republic", "type": "investissement"}).json()
    r = auth_client.post(f"/api/accounts/{tr['id']}/balances", json={"date": "2026-11-01", "balance_cents": 1_000_000})
    assert r.json()["balance_cents"] == 1_000_000

    nw = auth_client.get("/api/accounts/net-worth").json()
    assert nw["by_type"]["courant"] == 152_300
    assert nw["total_cents"] == 152_300 - 500_000 + 1_000_000

    # Archiver retire le compte de la liste et du patrimoine.
    assert auth_client.delete(f"/api/accounts/{tr['id']}").status_code == 204
    assert all(a["id"] != tr["id"] for a in auth_client.get("/api/accounts").json())
    assert auth_client.get("/api/accounts/net-worth").json()["total_cents"] == 152_300 - 500_000


def test_invalid_account_type(auth_client):
    assert auth_client.post("/api/accounts", json={"name": "X", "type": "inconnu"}).status_code == 422


def test_secrets_roundtrip():
    from app.security import decrypt_secrets, encrypt_secrets

    token = encrypt_secrets({"access_token": "abc"})
    assert "abc" not in token
    assert decrypt_secrets(token) == {"access_token": "abc"}
