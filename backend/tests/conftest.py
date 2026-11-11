import os
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

# Configuration de test, posée avant tout import de l'appli.
# On écrase toujours les valeurs : les tests ne doivent jamais toucher la vraie base.
os.environ["APP_PASSWORD"] = "test-password"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "sqlite:///./test_wallet.db")

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


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_client(client):
    r = client.post("/api/auth/login", json={"password": "test-password"})
    assert r.status_code == 200
    return client
