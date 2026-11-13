"""Opérations « à venir » (pas encore comptabilisées) reçues par la synchro bancaire (données inventées)."""

from datetime import date, timedelta

TODAY = date.today()


def _tx(ref, status, amount, label, day=TODAY):
    return {"entry_reference": ref, "status": status, "credit_debit_indicator": "DBIT", "booking_date": day.isoformat(),
            "transaction_date": day.isoformat(), "transaction_amount": {"amount": amount, "currency": "EUR"},
            "remittance_information": [label]}


def _sync(acc_id, txs):
    from app.connectors.enable_banking import to_statement
    from app.db import get_sessionmaker
    from app.services.importing import ingest

    with get_sessionmaker()() as db:
        ingest(db, to_statement(txs, [], "Courant"), acc_id, None, "Banque")
        db.commit()


def test_pending_operations_shown_apart_and_replaced(auth_client):
    c = auth_client
    acc = c.post("/api/accounts", json={"name": "Courant", "type": "courant", "initial_balance_cents": 100000}).json()

    _sync(acc["id"], [
        _tx("B1", "BOOK", "10.00", "PAIEMENT PAR CARTE X1234 BOULANGERIE ZETA 01/11"),
        _tx("P1", "PDNG", "25.50", "PAIEMENT PAR CARTE X1234 MAGASIN OMEGA"),
        _tx("P2", "PDNG", "4.00", "PAIEMENT PAR CARTE X1234 CAFE SIGMA"),
    ])
    pending = c.get("/api/pending", params={"account_id": acc["id"]}).json()
    assert {p["label"] for p in pending} == {"Magasin Omega", "Cafe Sigma"}
    assert sum(p["amount_cents"] for p in pending) == -2950
    # Hors opérations et hors statistiques…
    items = c.get("/api/transactions", params={"account_id": acc["id"]}).json()["items"]
    assert len(items) == 1
    assert c.get("/api/dashboard").json()["spent_cents"] == 1000
    # …mais visibles dans le compte (solde prévisionnel) et sur l'accueil.
    a = next(x for x in c.get("/api/accounts").json() if x["id"] == acc["id"])
    assert a["pending_cents"] == -2950 and a["pending_count"] == 2
    assert c.get("/api/dashboard").json()["pending_spent_cents"] == 2950

    # Synchro suivante : P1 est comptabilisée (nouvel identifiant), P2 toujours à venir.
    _sync(acc["id"], [
        _tx("B1", "BOOK", "10.00", "PAIEMENT PAR CARTE X1234 BOULANGERIE ZETA 01/11"),
        _tx("B2", "BOOK", "25.50", "PAIEMENT PAR CARTE X1234 MAGASIN OMEGA", TODAY - timedelta(days=1)),
        _tx("P2", "PDNG", "4.00", "PAIEMENT PAR CARTE X1234 CAFE SIGMA"),
    ])
    pending = c.get("/api/pending", params={"account_id": acc["id"]}).json()
    assert [p["label"] for p in pending] == ["Cafe Sigma"]
    assert len(c.get("/api/transactions", params={"account_id": acc["id"]}).json()["items"]) == 2


def test_csv_import_keeps_pending(auth_client):
    from tests.test_import_ca import ROWS, make_csv

    c = auth_client
    acc = c.post("/api/accounts", json={"name": "CA", "type": "courant"}).json()
    _sync(acc["id"], [_tx("P9", "PDNG", "7.00", "PAIEMENT PAR CARTE X1234 KIOSQUE TAU")])
    c.post("/api/imports/credit-agricole", files={"file": ("x.csv", make_csv(ROWS, number="55550000111"), "text/csv")}, data={"account_id": str(acc["id"])})
    assert len(c.get("/api/pending", params={"account_id": acc["id"]}).json()) == 1  # un export CSV ne sait rien des opérations à venir
