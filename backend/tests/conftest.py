import os
import tempfile
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

# Configuration de test, posée avant tout import de l'appli.
# On écrase toujours les valeurs : les tests ne doivent jamais toucher la vraie base.
os.environ["APP_PASSWORD"] = "test-password"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()
# Dans /tmp : le conteneur de l'API a un système de fichiers en lecture seule (sauf /tmp).
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{Path(tempfile.gettempdir()) / 'wallet_test.db'}")
os.environ["SYNC_INTERVAL_HOURS"] = "0"  # pas de synchro automatique pendant les tests
os.environ["ENABLE_BANKING_APP_ID"] = ""
os.environ["SECRETS_DIR"] = "/nonexistent"
os.environ["COOKIE_SECURE"] = "false"  # le client de test parle en HTTP : un cookie « Secure » ne serait pas renvoyé
os.environ.pop("APP_PASSWORD_HASH", None)

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def database():
    """Base de test neuve, créée via les migrations Alembic (comme en prod)."""
    from alembic import command
    from alembic.config import Config

    from app.db import get_engine

    url = os.environ["DATABASE_URL"]
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).unlink(missing_ok=True)
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    command.upgrade(cfg, "head")
    yield cfg
    get_engine().dispose()


# Tables vidées après chaque test (ordre compatible avec les clés étrangères).
# Les catégories et règles par défaut sont conservées.
_USER_TABLES = (
    "DELETE FROM transaction_tag",
    "DELETE FROM merchant_tag",
    "DELETE FROM rule_tag",
    "DELETE FROM tag",
    'DELETE FROM "transaction"',
    "DELETE FROM import_batch",
    "DELETE FROM rule WHERE from_correction",
    "DELETE FROM recurring_series",
    "DELETE FROM budget",
    "DELETE FROM merchant",
    "DELETE FROM balance_snapshot",
    "DELETE FROM pending_transaction",
    "DELETE FROM holding",
    "DELETE FROM goal",
    "DELETE FROM account",
    "DELETE FROM connection",
    "DELETE FROM device_token",
    "DELETE FROM security_event",
    "DELETE FROM app_meta WHERE key IN ('owner_signatures', 'hidden_default_categories', 'category_aliases', 'backup_last_ok', 'backup_last_error', 'advice_dismissed', 'global_budget_cents', 'payday', 'home_layout_web', 'home_layout_mobile')",
)


@pytest.fixture(autouse=True)
def clean_tables(database):
    """Chaque test démarre avec une base sans comptes ni opérations."""
    yield
    from sqlalchemy import text

    from app.db import get_engine

    with get_engine().begin() as conn:
        for stmt in _USER_TABLES:
            conn.execute(text(stmt))


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def fast_password_failures(monkeypatch):
    """Pas d'attente d'une seconde après chaque mauvais mot de passe pendant les tests."""
    monkeypatch.setattr("app.security.time.sleep", lambda _s: None)


@pytest.fixture
def auth_client(client):
    r = client.post("/api/auth/login", json={"password": "test-password"})
    assert r.status_code == 200
    # Les actions destructrices redemandent le mot de passe : on le joint à toutes les requêtes des tests.
    client.headers["X-Confirm-Password"] = "test-password"
    return client
