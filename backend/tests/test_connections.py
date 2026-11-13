"""Connexion Enable Banking avec un faux client (aucun appel réseau, données inventées)."""

import base64
import json
from datetime import date

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.connectors import enable_banking as eb
from app.services import sync
from tests.test_import_ca import ROWS, make_csv

NUMBER = "77778888999"


def _pad(s):
    return s + "=" * (-len(s) % 4)


def test_jwt_is_signed_with_the_private_key():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    token = eb.make_jwt("app-1", pem, now=1_700_000_000)
    h, b, sig = token.split(".")
    assert json.loads(base64.urlsafe_b64decode(_pad(h))) == {"typ": "JWT", "alg": "RS256", "kid": "app-1"}
    body = json.loads(base64.urlsafe_b64decode(_pad(b)))
    assert body["aud"] == "api.enablebanking.com" and body["exp"] - body["iat"] <= 86400
    key.public_key().verify(base64.urlsafe_b64decode(_pad(sig)), f"{h}.{b}".encode(), padding.PKCS1v15(), hashes.SHA256())


def _tx(day, cents, label, ref=None, status="BOOK"):
    return {
        "entry_reference": ref,
        "transaction_amount": {"amount": f"{abs(cents) / 100:.2f}", "currency": "EUR"},
        "credit_debit_indicator": "DBIT" if cents < 0 else "CRDT",
        "status": status,
        "booking_date": day,
        "remittance_information": [label],
    }


# Les mêmes opérations que l'export CSV de test (une avec un jour d'écart), plus une nouvelle et une en attente.
BANK_TXS = [
    _tx("2026-11-10", -1230, "CB MONOP", "R1"),
    _tx("2026-11-09", -450, "CB MONOP", "R2"),
    _tx("2026-11-09", -500, "CB BAR DU COIN", "R3"),
    _tx("2026-11-09", -500, "CB BAR DU COIN", "R4"),
    _tx("2026-11-06", -3599, "PRLV ORANGE", "R5"),  # 05/11 dans le CSV : rattrapé à ±2 jours
    _tx("2026-11-04", -4699, "PRLV ORANGE", "R6"),
    _tx("2026-11-03", 202582, "VIR ACME CORP", "R7"),
    _tx("2026-11-02", -10000, "VIR EPARGNE", "R8"),
    _tx("2026-11-02", -68978, "VIR LOYER", "R9"),
    _tx("2026-11-01", -820, "COTISATION OFFRE", "R10"),
    _tx("2026-11-11", -999, "CB NOUVEAU COMMERCE", "R11"),
    _tx("2026-11-11", -2000, "CB EN COURS", "R12", status="PDNG"),
]


class FakeClient:
    def __init__(self):
        self.state = None
        self.deleted = []

    def aspsps(self, country="FR"):
        return [{"name": "Banque Test", "country": country, "logo": None, "maximum_consent_validity": 7776000}]

    def start_auth(self, aspsp_name, country, state, redirect_url, valid_seconds):
        self.state = state
        self.valid_seconds = valid_seconds
        return {"url": f"https://banque.example/auth?state={state}"}

    def create_session(self, code):
        assert code == "CODE"
        return {
            "session_id": "S1",
            "access": {"valid_until": "2027-05-10T00:00:00+00:00"},
            "accounts": [
                {"uid": "U1", "identification_hash": "H1", "account_id": {"iban": f"FR7612345000{NUMBER}12"}, "name": "Compte courant"},
                {"uid": "U2", "identification_hash": "H2", "account_id": {"iban": "FR7600000000000000000000099"}, "name": "Livret"},
            ],
        }

    def delete_session(self, sid):
        self.deleted.append(sid)

    def transactions(self, uid, date_from):
        return BANK_TXS if uid == "U1" else [_tx("2026-11-05", 5000, "VIR INTERNE", "L1")]

    def balances(self, uid):
        amount = "1300.00" if uid == "U1" else "50.00"
        return [{"balance_type": "CLBD", "balance_amount": {"amount": amount}, "reference_date": "2026-11-11"}]


@pytest.fixture
def fake(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(sync, "get_client", lambda: client)
    return client


def test_config_reports_missing_setup(auth_client):
    cfg = auth_client.get("/api/connections/config").json()
    assert cfg["configured"] is False and cfg["app_id_set"] is False


def test_full_connection_flow(auth_client, fake):
    c = auth_client
    acc = c.post("/api/accounts", json={"name": "CA", "type": "courant"}).json()
    c.post("/api/imports/credit-agricole", files={"file": ("x.csv", make_csv(ROWS, number=NUMBER), "text/csv")}, data={"account_id": str(acc["id"])})
    assert c.get("/api/transactions", params={"account_id": acc["id"]}).json()["total"] == 10

    assert c.get("/api/connections/aspsps").json()[0]["name"] == "Banque Test"
    c.post("/api/connections/start", json={"aspsp_name": "Banque Test"})  # tentative abandonnée…
    url = c.post("/api/connections/start", json={"aspsp_name": "Banque Test"}).json()["url"]  # …puis relancée
    assert len(c.get("/api/connections").json()) == 1  # pas de doublon « en attente »
    assert url.startswith("https://banque.example/") and fake.state
    assert fake.valid_seconds == 7776000 - 3600  # maximum annoncé par la banque, moins une marge

    # Mauvais « state » : refusé.
    r = c.get("/api/connections/callback", params={"code": "CODE", "state": "faux"}, follow_redirects=False)
    assert r.status_code == 303 and "erreur" in r.headers["location"]

    r = c.get("/api/connections/callback", params={"code": "CODE", "state": fake.state}, follow_redirects=False)
    assert r.status_code == 303 and "ok=" in r.headers["location"]

    conns = c.get("/api/connections").json()
    assert len(conns) == 1 and conns[0]["status"] == "actif"
    accounts = {a["uid"]: a for a in conns[0]["accounts"]}
    assert accounts["U1"]["account_id"] == acc["id"]  # reconnu grâce au n° de compte dans l'IBAN
    assert accounts["U2"]["account_id"] is None and accounts["U1"]["iban_end"]
    assert "iban" not in accounts["U1"]  # l'IBAN complet ne sort pas de l'API

    # La synchro faite au retour a ajouté uniquement la nouvelle opération comptabilisée (pas de doublon avec le CSV).
    items = c.get("/api/transactions", params={"account_id": acc["id"]}).json()["items"]
    assert len(items) == 11 and any(t["amount_cents"] == -999 for t in items)
    assert not any(t["amount_cents"] == -2000 for t in items)  # « en attente » : ignorée
    bal = next(a for a in c.get("/api/accounts").json() if a["id"] == acc["id"])
    assert bal["balance_cents"] == 130000

    # Associer le livret à un nouveau compte, puis synchroniser.
    c.post(f"/api/connections/{conns[0]['id']}/accounts", json={"mapping": {"U2": "new"}})
    res = c.post(f"/api/connections/{conns[0]['id']}/sync").json()
    assert {r["account_name"]: r["imported"] for r in res} == {"CA": 0, "Livret": 1}
    # Une nouvelle synchro ne crée rien.
    assert all(r["imported"] == 0 for r in c.post(f"/api/connections/{conns[0]['id']}/sync").json())

    # Un réimport CSV après la synchro ne crée pas de doublons non plus.
    res = c.post("/api/imports/credit-agricole", files={"file": ("x.csv", make_csv(ROWS, number=NUMBER), "text/csv")}).json()
    assert res["imported"] == 0

    # Supprimer la connexion garde les comptes et les opérations.
    c.delete(f"/api/connections/{conns[0]['id']}")
    assert fake.deleted == ["S1"]
    assert c.get("/api/transactions", params={"account_id": acc["id"]}).json()["total"] == 11


def test_statement_conversion_without_reference():
    st = eb.to_statement(
        [_tx("2026-11-01", -250, "CAFE"), _tx("2026-11-01", -250, "CAFE")],
        [{"balance_type": "ITAV", "balance_amount": {"amount": "-12.5"}}],
        "Test",
    )
    assert len({t.dedup_key for t in st.transactions}) == 2  # deux cafés identiques restent distincts
    assert st.balance_cents == -1250 and st.balance_date == date.today()


def test_sync_stale_on_app_open_and_error_kept(auth_client, fake, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from app.db import get_sessionmaker
    from app.models import Connection

    c = auth_client
    acc = c.post("/api/accounts", json={"name": "CA", "type": "courant"}).json()
    c.post("/api/connections/start", json={"aspsp_name": "Banque Test"})
    c.get("/api/connections/callback", params={"code": "CODE", "state": fake.state}, follow_redirects=False)
    conn = c.get("/api/connections").json()[0]
    assert conn["status"] == "actif" and conn["last_error"] is None
    c.post(f"/api/connections/{conn['id']}/accounts", json={"mapping": {"U1": acc["id"]}})

    # Synchronisée à l'instant : rien à faire à l'ouverture de l'appli.
    r = c.post("/api/connections/sync-stale").json()
    assert r["synced"] == [] and r["errors"] == []
    assert c.post("/api/connections/sync-stale", params={"max_age_minutes": 5}).status_code == 422  # pas plus d'une fois par demi-heure

    def age(hours):
        with get_sessionmaker()() as db:
            db.get(Connection, conn["id"]).last_sync_at = datetime.now(timezone.utc) - timedelta(hours=hours)
            db.commit()

    age(2)
    r = c.post("/api/connections/sync-stale").json()
    assert r["synced"] == [conn["label"]] and r["imported"] == 0

    # La banque refuse (quota du jour) : l'erreur est gardée, la connexion reste active, puis effacée au succès suivant.
    def quota(*_a, **_k):
        raise eb.EnableBankingError("Too many requests", 429)

    monkeypatch.setattr(fake, "transactions", quota)
    age(2)
    r = c.post("/api/connections/sync-stale").json()
    assert r["synced"] == [] and len(r["errors"]) == 1 and "limite" in r["errors"][0]["error"]
    conn2 = c.get("/api/connections").json()[0]
    assert conn2["status"] == "actif" and "limite" in conn2["last_error"]
    monkeypatch.setattr(fake, "transactions", FakeClient.transactions.__get__(fake))
    assert c.post(f"/api/connections/{conn['id']}/sync").status_code == 200
    assert c.get("/api/connections").json()[0]["last_error"] is None
