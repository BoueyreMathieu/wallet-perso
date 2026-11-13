"""Vendeurs nommés d'après un libellé bancaire générique : recalculés (libellés inventés)."""

from datetime import date

TODAY = date.today().isoformat()


def test_generic_merchants_are_split_and_cleaned(auth_client):
    from app.connectors.enable_banking import to_statement
    from app.db import get_sessionmaker
    from app.services.importing import ingest
    from app.services.merchant_repair import fix_generic_merchants

    c = auth_client
    cats = {x["name"]: x["id"] for x in c.get("/api/categories").json()}
    acc = c.post("/api/accounts", json={"name": "Courant", "type": "courant"}).json()

    def op(label, merchant, amount):
        r = c.post("/api/transactions", json={"account_id": acc["id"], "booked_at": TODAY, "amount_cents": amount, "label": label, "merchant": merchant})
        assert r.status_code == 201, r.text

    # Comme avant le correctif : vendeur = libellé brut, et deux magasins mélangés dans un même vendeur.
    op("PAIEMENT PAR CARTE X1234 MAGASIN ZETA 01/11", "Paiement Par Carte X1234", -1100)
    op("PAIEMENT PAR CARTE X1234 EPICERIE OMEGA 02/11", "Paiement Par Carte X1234", -2200)
    op("PAIEMENT PAR CARTE X1234 MAGASIN ZETA 03/11", "Paiement Par Carte X1234 Magasin Zeta 03/11", -3300)
    merchants = {m["name"]: m for m in c.get("/api/merchants").json()}
    c.post(f"/api/merchants/{merchants['Paiement Par Carte X1234 Magasin Zeta 03/11']['id']}/category", json={"category_id": cats["Courses"]})

    with get_sessionmaker()() as db:
        assert fix_generic_merchants(db) == 3
        db.commit()
    items = c.get("/api/transactions", params={"account_id": acc["id"]}).json()["items"]
    by_amount = {t["amount_cents"]: t for t in items}
    assert by_amount[-1100]["merchant"] == by_amount[-3300]["merchant"] == "Magasin Zeta"
    assert by_amount[-2200]["merchant"] == "Epicerie Omega"
    assert by_amount[-1100]["category_id"] == cats["Courses"]  # catégorie choisie reportée sur le vrai vendeur
    names = {m["name"] for m in c.get("/api/merchants").json()}
    assert not any(n.startswith("Paiement Par Carte") for n in names)

    # Les synchros suivantes donnent directement le bon vendeur.
    synced = [{"entry_reference": "C1", "status": "BOOK", "credit_debit_indicator": "DBIT", "booking_date": TODAY,
               "transaction_amount": {"amount": "4.40", "currency": "EUR"}, "remittance_information": ["PAIEMENT PAR CARTE X1234 MAGASIN ZETA 04/11"]}]
    with get_sessionmaker()() as db:
        ingest(db, to_statement(synced, [], "Courant"), acc["id"], None, "Banque")
        db.commit()
    t = next(x for x in c.get("/api/transactions", params={"account_id": acc["id"]}).json()["items"] if x["amount_cents"] == -440)
    assert t["merchant"] == "Magasin Zeta" and t["category_id"] == cats["Courses"]
