"""Bilan du mois et export CSV (données inventées)."""

from datetime import date, timedelta

from app.api.reports import safe


def test_formula_neutralized():
    assert safe("=HYPERLINK(1)") == "'=HYPERLINK(1)" and safe("+33") == "'+33" and safe("Boulangerie") == "Boulangerie" and safe(None) == ""


def test_recap_and_export(auth_client):
    c = auth_client
    acc = c.post("/api/accounts", json={"name": "Courant inventé", "type": "courant"}).json()
    cats = {x["name"]: x["id"] for x in c.get("/api/categories").json()}
    first = date.today().replace(day=1)
    last_month = (first - timedelta(days=1)).replace(day=1)

    def op(d, cents, label, merchant=None, cat=None):
        r = c.post("/api/transactions", json={"account_id": acc["id"], "booked_at": d.isoformat(), "amount_cents": cents, "label": label,
                                               "merchant": merchant, "category_id": cats.get(cat) if cat else None})
        assert r.status_code == 201, r.text

    op(last_month + timedelta(days=1), 200000, "VIR SALAIRE INVENTE", None, "Salaire")
    op(last_month + timedelta(days=4), -80000, "PRLV LOYER INVENTE", "Propriétaire inventé", "Loyer / crédit")
    op(last_month + timedelta(days=9), -6000, "=FORMULE DANGEREUSE", "Nouveau vendeur inventé", "Courses")
    r = c.get("/api/recap").json()  # par défaut : le mois précédent
    assert r["month"] == last_month.strftime("%Y-%m") and r["complete"]
    assert r["income_cents"] == 200000 and r["spending_cents"] == 86000 and r["net_cents"] == 114000
    assert r["layers"]["fixe"] == 80000 and r["savings_rate"] == 0.57
    assert r["biggest"][0]["amount_cents"] == -80000
    assert {m["name"] for m in r["new_merchants"]} == {"Propriétaire inventé", "Nouveau vendeur inventé"}
    assert c.get("/api/recap", params={"month": "2999-01"}).status_code == 422

    res = c.get("/api/export/transactions.csv")
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/csv")
    text = res.content.decode("utf-8-sig")
    lines = text.strip().split("\r\n")
    assert lines[0].startswith("Date;Compte;Libellé") and len(lines) == 4
    assert "'=FORMULE DANGEREUSE" in text and "-800,00" in text and "Logement › Loyer / crédit" in text
