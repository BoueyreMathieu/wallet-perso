"""Virements entre mes comptes : appariement automatique et manuel (données inventées)."""


def _accounts(c):
    cur = c.post("/api/accounts", json={"name": "Courant", "type": "courant"}).json()
    sav = c.post("/api/accounts", json={"name": "Livret", "type": "epargne"}).json()
    return cur, sav


def _op(c, account_id, day, amount, label):
    r = c.post("/api/transactions", json={"account_id": account_id, "booked_at": day, "amount_cents": amount, "label": label})
    assert r.status_code == 201, r.text
    return r.json()


def _get(c, tx):
    return next(t for t in c.get("/api/transactions", params={"account_id": tx["account_id"]}).json()["items"] if t["id"] == tx["id"])


def test_detect_and_unpair(auth_client):
    c = auth_client
    cur, sav = _accounts(c)
    out = _op(c, cur["id"], "2026-10-05", -20000, "VIREMENT VERS LIVRET")
    inc = _op(c, sav["id"], "2026-10-06", 20000, "VIR RECU DE COMPTE")
    # Même montant mais pas un virement (paiement carte) : jamais apparié.
    _op(c, cur["id"], "2026-10-05", -4500, "PAIEMENT CARTE BOUTIQUE")
    _op(c, sav["id"], "2026-10-05", 4500, "REMBOURSEMENT")

    assert c.post("/api/transfers/detect").json()["updated"] == 1
    a, b = _get(c, out), _get(c, inc)
    assert a["transfer_pair_id"] == b["id"] and b["transfer_pair_id"] == a["id"]
    assert a["is_transfer"] and b["is_transfer"]
    assert a["pair_account"] == "Livret" and b["pair_account"] == "Courant"
    assert a["category_id"] == b["category_id"] is not None

    # Réappliquer les règles ne casse pas l'appariement.
    c.post("/api/rules/reapply")
    assert _get(c, out)["is_transfer"]

    # Dissocier : les deux lignes redeviennent normales et ne sont pas ré-appariées automatiquement.
    assert c.post(f"/api/transactions/{out['id']}/unlink").status_code == 200
    a, b = _get(c, out), _get(c, inc)
    assert a["transfer_pair_id"] is None and b["transfer_pair_id"] is None and b["pair_account"] is None
    assert c.post("/api/transfers/detect").json()["updated"] == 0


def test_ambiguous_transfers_are_not_guessed(auth_client):
    c = auth_client
    cur, sav = _accounts(c)
    other = c.post("/api/accounts", json={"name": "Autre livret", "type": "epargne"}).json()
    _op(c, cur["id"], "2026-10-10", -5000, "VIREMENT EPARGNE")
    _op(c, sav["id"], "2026-10-11", 5000, "VIREMENT RECU")
    _op(c, other["id"], "2026-10-09", 5000, "VIREMENT RECU")
    assert c.post("/api/transfers/detect").json()["updated"] == 0


def test_manual_pair(auth_client):
    c = auth_client
    cur, sav = _accounts(c)
    a = _op(c, cur["id"], "2026-10-01", -3000, "Retrait pour tirelire")
    b = _op(c, sav["id"], "2026-10-03", 3000, "Dépôt tirelire")
    wrong = _op(c, sav["id"], "2026-10-03", 2999, "Autre")
    assert c.post("/api/transactions/pair", json={"ids": [a["id"], wrong["id"]]}).status_code == 422
    assert c.post("/api/transactions/pair", json={"ids": [a["id"], b["id"]]}).status_code == 200
    assert _get(c, a)["pair_account"] == "Livret" and _get(c, b)["is_transfer"]

    # Ranger un côté en dépense = ce n'était pas un virement entre mes comptes.
    food = next(x for x in c.get("/api/categories").json() if x["name"] == "Courses")
    c.patch(f"/api/transactions/{a['id']}", json={"category_id": food["id"]})
    assert _get(c, a)["transfer_pair_id"] is None and _get(c, b)["transfer_pair_id"] is None
