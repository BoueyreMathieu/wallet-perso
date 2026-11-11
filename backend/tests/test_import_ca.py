"""Import Crédit Agricole : parser + API, sur un faux relevé au format réel."""

import pytest

from app.categorize import CompiledRule, find_category, normalize, owner_signatures
from app.default_rules import DEFAULT_RULES
from app.importers import credit_agricole as ca


def _row(day, lines, debit="", credit=""):
    lines = lines + [""] * (6 - len(lines))
    label = "\n".join(lines)
    return f'{day};"{label}";{debit};{credit};\n'


def make_csv(rows: list[str], balance="1 234,56", number="12345678901", label="Compte de Dépôt") -> bytes:
    header = (
        "\nTéléchargement du 11/11/2026;\n\n\nMONSIEUR DUPONT JEAN\n"
        f"{label} carte n° {number};\nSolde au 11/11/2026 {balance} €\n\n"
        "Liste des opérations du compte entre le 01/01/2026 et le 11/11/2026;\n\n"
        "Date d'opération;Libellé;Débit euros;Crédit euros;\n"
    )
    return (header + "".join(rows) + "\n\n").encode("cp1252")


ROWS = [
    _row("10/11/2026", ["Paiement par carte", "X1234 MONOP PARIS 11 08/11 - Monoprix"], "12,30"),
    _row("09/11/2026", ["Paiement par carte", "X1234 MONOP PARIS 11 07/11"], "4,50"),
    _row("09/11/2026", ["Paiement par carte", "X1234 BAR DU COIN PARIS 07/11"], "5,00"),
    _row("09/11/2026", ["Paiement par carte", "X1234 BAR DU COIN PARIS 07/11"], "5,00"),
    _row("05/11/2026", ["Prélèvement", "ORANGE SA - Orange - Votre abonnement mobile", "", "MANDAT1", "FR18ZZZ002305", "REF1"], "35,99"),
    _row("04/11/2026", ["Prélèvement", "ORANGE SA - Votre abonnement fibre", "", "MANDAT1", "FR18ZZZ002305", "REF2"], "46,99"),
    _row("03/11/2026", ["Virement en votre faveur", "ACME CORP 26340651", "", "", "", "26340651"], "", "2 025,82"),
    _row("02/11/2026", ["Virement émis", "WEB MONSIEUR DUPONT JEA Epargne", "", "", "", "Epargne"], "100,00"),
    _row("02/11/2026", ["Virement émis", "WEB REGIE IMMO Loyer - Loyer"], "689,78"),
    _row("01/11/2026", ["Cotisation", "Offre Compte à composer"], "8,20"),
]


# --- Parser (sans base) ---------------------------------------------------------


def test_parse_header_and_rows():
    st = ca.parse(make_csv(ROWS))
    assert st.account_label == "Compte de Dépôt"
    assert st.account_number == "12345678901"
    assert st.holder == "MONSIEUR DUPONT JEAN"
    assert st.balance_cents == 123456
    assert len(st.transactions) == 10
    first = st.transactions[0]
    assert first.amount_cents == -1230 and first.op_type == "Paiement par carte"
    assert st.transactions[6].amount_cents == 202582


def test_identical_rows_get_distinct_hashes():
    st = ca.parse(make_csv(ROWS))
    assert len({t.dedup_hash for t in st.transactions}) == len(st.transactions)
    # Et le même fichier donne les mêmes empreintes (réimport sans doublon).
    assert [t.dedup_hash for t in st.transactions] == [t.dedup_hash for t in ca.parse(make_csv(ROWS)).transactions]


def test_merchant_resolution():
    st = ca.parse(make_csv(ROWS))
    ca.resolve_merchants(st.transactions)
    names = [t.merchant_hint for t in st.transactions]
    assert names[0] == names[1] == "Monoprix"  # appris depuis la ligne enrichie
    assert names[2] == "Bar du Coin Paris"
    assert names[4] == names[5] == "Orange"  # même identifiant créancier
    assert names[6] == "Acme Corp"
    assert names[9] == "Crédit Agricole"


def test_amount_and_errors():
    assert ca.parse_amount("2 025,82") == 202582
    assert ca.parse_amount("-12,5") == -1250
    assert ca.parse_amount("") is None
    with pytest.raises(ca.CAParseError):
        ca.parse(b"pas un export")


def test_default_rules_point_to_existing_categories(auth_client):
    paths = set()
    cats = auth_client.get("/api/categories").json()
    by_id = {c["id"]: c for c in cats}
    for c in cats:
        parent = by_id.get(c["parent_id"])
        paths.add(f"{parent['name']}/{c['name']}" if parent else c["name"])
    missing = {p for p, _, _ in DEFAULT_RULES} - paths
    assert not missing, missing


def test_categorize_engine():
    rules = sorted(
        [CompiledRule(None, "contient", p, path, prio) for path, pats, prio in DEFAULT_RULES for p in pats],
        key=lambda r: r.priority,
    )
    sig = owner_signatures("MONSIEUR DUPONT JEAN")

    def cat(label, merchant=None):
        return find_category(rules, label, merchant, sig, "INTERNE")[0]

    assert normalize("Électricité  Générale") == "ELECTRICITE GENERALE"
    assert cat("Paiement par carte | X1234 MONOP PARIS", "Monoprix") == "Alimentation/Courses"
    assert cat("Virement émis | WEB MONSIEUR DUPONT JEA Epargne") == "INTERNE"
    assert cat("Prélèvement | ORANGE SA - Orange - Votre abonnement mobile") == "Logement/Internet / téléphone"
    assert cat("Cotisation | Offre Compte à composer") == "Banque & impôts/Frais bancaires"
    # Mot entier : « BAR » ne doit pas matcher « BARBARA ».
    assert cat("Virement émis | VIR INST vers BARBARA X") is None
    assert cat("Virement émis | Wero vers PAUL D - merci") == "Famille & amis/Remboursements à des proches"


# --- API -------------------------------------------------------------------------


@pytest.fixture
def ca_account(auth_client):
    return auth_client.post("/api/accounts", json={"name": "CA courant", "type": "courant"}).json()


def _upload(client, data: bytes, account_id=None):
    form = {"account_id": str(account_id)} if account_id else {}
    return client.post("/api/imports/credit-agricole", files={"file": ("export.csv", data, "text/csv")}, data=form)


def test_import_flow(auth_client, ca_account):
    data = make_csv(ROWS, number="99990000111")
    # Sans compte choisi et sans compte associé : on demande lequel.
    assert _upload(auth_client, data).status_code == 409

    r = _upload(auth_client, data, ca_account["id"])
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["imported"] == 10 and res["skipped"] == 0
    assert res["categorized"] >= 7
    assert res["balance_cents"] == 123456

    # Réimport du même fichier : rien de nouveau, et le compte est reconnu tout seul.
    res2 = _upload(auth_client, data).json()
    assert res2["imported"] == 0 and res2["skipped"] == 10 and res2["account_id"] == ca_account["id"]

    acc = next(a for a in auth_client.get("/api/accounts").json() if a["id"] == ca_account["id"])
    assert acc["balance_cents"] == 123456 and acc["institution"] == "Crédit Agricole"

    page = auth_client.get("/api/transactions", params={"account_id": ca_account["id"]}).json()
    assert page["total"] == 10
    transfer = next(t for t in page["items"] if "DUPONT" in t["raw_label"])
    assert transfer["is_transfer"] is True

    # Un fichier d'un autre compte est refusé pour ce compte.
    assert _upload(auth_client, make_csv(ROWS, number="11112222333"), ca_account["id"]).status_code == 422


def test_categorize_merchant_and_correction(auth_client, ca_account):
    _upload(auth_client, make_csv(ROWS, number="55554444333"), ca_account["id"])
    groups = auth_client.get("/api/transactions/to-categorize").json()
    acme = next(g for g in groups if g["merchant"] == "Acme Corp")
    cats = {c["name"]: c["id"] for c in auth_client.get("/api/categories").json()}

    r = auth_client.post(f"/api/merchants/{acme['merchant_id']}/category", json={"category_id": cats["Salaire"]})
    assert r.json()["updated"] >= 1
    assert all(g["merchant"] != "Acme Corp" for g in auth_client.get("/api/transactions/to-categorize").json())
    assert any(r["pattern"] == "Acme Corp" for r in auth_client.get("/api/rules").json())

    # Correction d'une seule opération : elle est verrouillée et survit à la réapplication des règles.
    tx = auth_client.get("/api/transactions", params={"q": "orange"}).json()["items"][0]
    auth_client.patch(f"/api/transactions/{tx['id']}", json={"category_id": cats["Streaming"]})
    auth_client.post("/api/rules/reapply")
    tx2 = next(t for t in auth_client.get("/api/transactions", params={"q": "orange"}).json()["items"] if t["id"] == tx["id"])
    assert tx2["category_id"] == cats["Streaming"] and tx2["category_locked"] is True
