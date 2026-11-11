"""Services par vendeur, étiquettes et actions groupées (données inventées)."""

import pytest

from tests.test_import_ca import _row, make_csv

ICS = "FR00ZZZ000001"
ROWS = [
    _row("05/11/2026", ["Prélèvement", "COURTIER SA - Courtier - Contrat MAISON 11111", "", "M1", ICS, "R1"], "25,50"),
    _row("05/10/2026", ["Prélèvement", "COURTIER SA - Courtier - Contrat MAISON 11111", "", "M1", ICS, "R2"], "25,50"),
    _row("06/11/2026", ["Prélèvement", "COURTIER SA - Courtier - Contrat VOITURE 22222", "", "M1", ICS, "R3"], "83,39"),
    _row("06/10/2026", ["Prélèvement", "COURTIER SA - Courtier - Contrat VOITURE 22222", "", "M1", ICS, "R4"], "83,39"),
    _row("07/10/2026", ["Prélèvement", "COURTIER SA - Courtier - Frais de dossier", "", "M1", ICS, "R5"], "10,00"),
    _row("08/11/2026", ["Paiement par carte", "X1234 MONOP PARIS 11 07/11 - Monoprix"], "12,00"),
    _row("09/11/2026", ["Paiement par carte", "X1234 MONOP PARIS 11 08/11 - Monoprix"], "8,00"),
]


@pytest.fixture
def env(auth_client):
    acc = auth_client.post("/api/accounts", json={"name": "CA", "type": "courant"}).json()
    r = auth_client.post(
        "/api/imports/credit-agricole",
        files={"file": ("x.csv", make_csv(ROWS, number="55550000111"), "text/csv")},
        data={"account_id": str(acc["id"])},
    )
    assert r.status_code == 200, r.text
    cats = {c["name"]: c["id"] for c in auth_client.get("/api/categories").json()}
    merchants = {m["name"]: m for m in auth_client.get("/api/merchants").json()}
    return {"client": auth_client, "cats": cats, "courtier": merchants["Courtier"], "monoprix": merchants["Monoprix"]}


def _txs(client, **params):
    return client.get("/api/transactions", params=params).json()["items"]


def test_services_split_one_merchant_into_several_categories(env):
    c, cats, courtier = env["client"], env["cats"], env["courtier"]
    c.post(f"/api/merchants/{courtier['id']}/category", json={"category_id": cats["Autres assurances"]})

    maison = next(t for t in _txs(c, merchant_id=courtier["id"]) if "MAISON" in t["raw_label"])
    sug = c.get(f"/api/transactions/{maison['id']}/service-suggestion").json()
    assert sug["pattern"] == "MAISON" and sug["matches"] == 2

    r = c.post(
        f"/api/merchants/{courtier['id']}/services",
        json={"label": "Habitation", "pattern": sug["pattern"], "category_id": cats["Assurance habitation"]},
    )
    assert r.status_code == 201, r.text
    # Service reconnu par le montant seul.
    c.post(
        f"/api/merchants/{courtier['id']}/services",
        json={"label": "Auto", "amount_min_cents": 8339, "amount_max_cents": 8339, "category_id": cats["Assurance auto"]},
    )
    # Ni mot-clé ni montant : refusé.
    assert c.post(f"/api/merchants/{courtier['id']}/services", json={"label": "X", "category_id": cats["Dons"]}).status_code == 422

    by_label = {}
    for t in _txs(c, merchant_id=courtier["id"]):
        by_label.setdefault(t["raw_label"].split(" | ")[1].split(" - ")[-1], set()).add(t["category_id"])
    assert by_label["Contrat MAISON 11111"] == {cats["Assurance habitation"]}
    assert by_label["Contrat VOITURE 22222"] == {cats["Assurance auto"]}
    assert by_label["Frais de dossier"] == {cats["Autres assurances"]}  # catégorie générale du vendeur

    m = next(x for x in c.get("/api/merchants").json() if x["id"] == courtier["id"])
    assert m["services"] == 2 and len(m["categories"]) == 3
    bd = c.get(f"/api/merchants/{courtier['id']}/breakdown").json()
    shares = {s["label"]: s for s in bd["by_service"]}
    assert shares["Habitation"]["count"] == 2 and shares["Habitation"]["spent_cents"] == 5100
    assert shares["Auto"]["count"] == 2 and shares["Hors services"]["count"] == 1

    # Supprimer un service : ses opérations retombent dans la catégorie générale.
    services = c.get(f"/api/merchants/{courtier['id']}/services").json()
    auto = next(s for s in services if s["label"] == "Auto")
    c.delete(f"/api/services/{auto['id']}")
    voiture = [t for t in _txs(c, merchant_id=courtier["id"]) if "VOITURE" in t["raw_label"]]
    assert {t["category_id"] for t in voiture} == {cats["Autres assurances"]}


def test_tags_inherited_and_bulk(env):
    c, cats, courtier, mono = env["client"], env["cats"], env["courtier"], env["monoprix"]
    assurances = c.post("/api/tags", json={"name": "Assurances", "color": "#0f766e"}).json()
    vacances = c.post("/api/tags", json={"name": "Vacances"}).json()
    assert c.post("/api/tags", json={"name": "assurances"}).status_code == 409  # doublon (casse ignorée)

    # Étiquette sur le vendeur : héritée par ses 5 opérations.
    c.put(f"/api/merchants/{courtier['id']}/tags", json={"tag_ids": [assurances["id"]]})
    tagged = _txs(c, tag_id=assurances["id"])
    assert len(tagged) == 5 and all(t["tags"][0]["source"] == "vendeur" for t in tagged)

    # Étiquette sur un service.
    svc = c.post(
        f"/api/merchants/{courtier['id']}/services",
        json={"label": "Habitation", "pattern": "MAISON", "category_id": cats["Assurance habitation"], "tag_ids": [vacances["id"]]},
    ).json()
    assert svc["tag_ids"] == [vacances["id"]]
    assert len(_txs(c, tag_id=vacances["id"])) == 2

    # Sélection multiple : ajout sur 2 opérations Monoprix, puis catégorie groupée.
    ids = [t["id"] for t in _txs(c, merchant_id=mono["id"])]
    r = c.post("/api/transactions/bulk", json={"ids": ids, "add_tag_ids": [vacances["id"]]}).json()
    assert r["updated"] == 2
    assert len(_txs(c, tag_id=vacances["id"])) == 4
    c.post("/api/transactions/bulk", json={"ids": ids, "set_category": True, "category_id": cats["Voyages"]})
    assert {t["category_id"] for t in _txs(c, merchant_id=mono["id"])} == {cats["Voyages"]}

    # Retirer une étiquette héritée d'une seule opération : impossible, signalé.
    one = _txs(c, merchant_id=courtier["id"])[0]["id"]
    r = c.post("/api/transactions/bulk", json={"ids": [one], "remove_tag_ids": [assurances["id"]]}).json()
    assert r["inherited_kept"] == 1
    # Retirer l'étiquette manuelle : OK.
    r = c.post("/api/transactions/bulk", json={"ids": ids, "remove_tag_ids": [vacances["id"]]}).json()
    assert r["updated"] == 2 and len(_txs(c, tag_id=vacances["id"])) == 2

    tags = {t["name"]: t for t in c.get("/api/tags").json()}
    assert tags["Assurances"]["transactions"] == 5 and tags["Assurances"]["merchants"] == 1
    assert tags["Assurances"]["spent_cents"] == 2 * 2550 + 2 * 8339 + 1000
    assert tags["Vacances"]["services"] == 1

    # Supprimer une étiquette la retire partout.
    c.delete(f"/api/tags/{assurances['id']}")
    assert all(not t["tags"] or t["tags"][0]["name"] != "Assurances" for t in _txs(c, merchant_id=courtier["id"]))
