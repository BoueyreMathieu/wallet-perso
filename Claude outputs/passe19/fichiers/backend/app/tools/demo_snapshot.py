"""Jeu de données de test pour l'appli quand le serveur est injoignable (mode démo).

Crée des comptes et ~14 mois d'opérations **inventés** dans une base SQLite jetable (jamais la vraie base), les passe
dans le vrai moteur (catégories, récurrents, budgets, prévisions) et enregistre les réponses de l'API dans un fichier
JSON que l'appli lit hors connexion.

    docker compose run --rm --no-deps -v "${PWD}/frontend/public/demo:/out" api python -m app.tools.demo_snapshot /out/snapshot.json

Puis reconstruire le front (`docker compose up -d --build`, et `npm run android:prepare` pour l'appli Android).
Pour retirer le mode démo : voir docs/demo.md.
"""

from __future__ import annotations

import json
import os
import random
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

# --- Base jetable : posé AVANT tout import de l'appli (sinon elle lirait la vraie base) ---------------------------
_TMP = Path(tempfile.mkdtemp(prefix="wallet-demo-"))
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_TMP / 'demo.db'}",
    "APP_PASSWORD": "demo",
    "SECRET_KEY": "demo",
    "SYNC_INTERVAL_HOURS": "0",
    "ENABLE_BANKING_APP_ID": "",
    "SECRETS_DIR": "/nonexistent",
    "COOKIE_SECURE": "false",
})
os.environ.pop("APP_PASSWORD_HASH", None)
from cryptography.fernet import Fernet  # noqa: E402

os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SCENARIO = {"plaisir_pct": 100, "apply_budgets": False, "targets": {}, "extra_saving_cents": 0}


def key_of(method: str, path: str) -> str:
    """Clé d'une requête, identique à celle calculée par le front (src/demo/demo.ts) : paramètres triés, vides ignorés."""
    parts = urlsplit(path)
    params = sorted((k, v) for k, v in parse_qsl(parts.query) if v != "")
    return f"{method} {parts.path}" + ("?" + "&".join(f"{k}={v}" for k, v in params) if params else "")


def _months_back(today: date, n: int) -> list[date]:
    out, d = [], today.replace(day=1)
    for _ in range(n):
        out.append(d)
        d = (d - timedelta(days=1)).replace(day=1)
    return out[::-1]


def _seed(c, today: date) -> None:
    rnd = random.Random(7)
    cats = {x["name"]: x["id"] for x in c.get("/api/categories").json()}

    def account(name: str, kind: str, balance: int) -> int:
        r = c.post("/api/accounts", json={"name": name, "type": kind, "institution": "Banque de démo", "initial_balance_cents": balance})
        r.raise_for_status()
        return r.json()["id"]

    courant = account("Compte courant (démo)", "courant", 134250)
    livret = account("Livret A (démo)", "epargne", 425000)
    paypal = account("PayPal (démo)", "paypal", 2340)

    def op(acc: int, d: date, cents: int, label: str, merchant: str | None, cat: str | None) -> None:
        if d > today:
            return
        r = c.post("/api/transactions", json={"account_id": acc, "booked_at": d.isoformat(), "amount_cents": cents, "label": label,
                                              "merchant": merchant, "category_id": cats.get(cat) if cat else None})
        r.raise_for_status()

    def day(m: date, d: int) -> date:
        nxt = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
        return min(m.replace(day=1) + timedelta(days=d - 1), nxt - timedelta(days=1))

    months = _months_back(today, 14)
    for i, m in enumerate(months):
        # Revenus et charges fixes (récurrents)
        op(courant, day(m, rnd.choice([25, 26, 27, 28])), 235000, "VIR SALAIRE SOCIETE EXEMPLE", "Société Exemple", "Salaire")
        op(courant, day(m, 5), -78000, "PRLV LOYER AGENCE EXEMPLE", "Agence Exemple", "Loyer / crédit")
        op(courant, day(m, 10), -(6200 if i < 8 else 6800), "PRLV ENERGIE EXEMPLE", "Énergie Exemple", "Énergie")
        op(courant, day(m, 12), -2999, "PRLV BOX INTERNET EXEMPLE", "Box Exemple", "Internet / téléphone")
        op(courant, day(m, 3), -1450, "PRLV ASSURANCE HABITATION EX", "Assureur Exemple", "Assurance habitation")
        op(courant, day(m, 21), -1349, "CB STREAMING EXEMPLE", "Streaming Exemple", "Streaming")
        op(courant, day(m, 15), -1099, "CB MUSIQUE EXEMPLE", "Musique Exemple", "Musique")
        op(courant, day(m, 2), -3490, "PRLV SALLE DE SPORT EXEMPLE", "Salle de sport Exemple", "Salle de sport")
        op(courant, day(m, 8), -4200, "PRLV MUTUELLE EXEMPLE", "Mutuelle Exemple", "Mutuelle")
        op(courant, day(m, 1), -8640, "PRLV PASS TRANSPORT EXEMPLE", "Transports Exemple", "Transports en commun")
        op(courant, day(m, 15), -12000, "PRLV IMPOTS EXEMPLE", "Impôts Exemple", "Impôts")
        # Épargne mensuelle vers le livret (virement entre mes comptes)
        op(courant, day(m, 29), -15000, "VIR VERS LIVRET A DEMO", None, "Épargne / investissement")
        op(livret, day(m, 29), 15000, "VIR DEPUIS COMPTE COURANT DEMO", None, "Épargne / investissement")
        # Essentiels : courses, boulangerie, carburant, pharmacie
        d = m
        while d.month == m.month:
            wd = d.weekday()
            if wd == 5 or (wd == 2 and rnd.random() < 0.5):
                op(courant, d, -rnd.randint(4200, 9800), "CB SUPERMARCHE EXEMPLE", "Supermarché Exemple", "Courses")
            if rnd.random() < 0.45:
                op(courant, d, -rnd.randint(180, 850), "CB BOULANGERIE DU COIN", "Boulangerie du Coin", "Boulangerie / café")
            # Plaisirs : bars le week-end, restaurants, livraison
            if wd in (4, 5) and rnd.random() < 0.45:
                op(courant, d, -rnd.randint(1200, 4200), "CB BAR EXEMPLE", "Bar Exemple", "Bars")
            if rnd.random() < 0.08:
                op(courant, d, -rnd.randint(2500, 6200), "CB RESTAURANT EXEMPLE", "Restaurant Exemple", "Restaurants")
            if wd in (0, 6) and rnd.random() < 0.3:
                op(courant, d, -rnd.randint(1800, 3300), "CB LIVRAISON REPAS EXEMPLE", "Livraison Exemple", "Livraison")
            d += timedelta(days=1)
        for _ in range(2):
            op(courant, day(m, rnd.randint(1, 28)), -rnd.randint(4500, 7200), "CB STATION SERVICE EXEMPLE", "Station Exemple", "Carburant")
        if rnd.random() < 0.6:
            op(courant, day(m, rnd.randint(1, 28)), -rnd.randint(600, 2800), "CB PHARMACIE EXEMPLE", "Pharmacie Exemple", "Pharmacie")
        if rnd.random() < 0.7:
            op(courant, day(m, rnd.randint(1, 28)), -1250, "CB CINEMA EXEMPLE", "Cinéma Exemple", "Cinéma")
        for _ in range(rnd.randint(0, 2)):
            op(courant, day(m, rnd.randint(1, 28)), -rnd.randint(2500, 8900), "CB BOUTIQUE VETEMENTS EX", "Boutique Exemple", "Vêtements")
        for _ in range(rnd.randint(1, 2)):
            op(paypal, day(m, rnd.randint(1, 28)), -rnd.randint(1200, 6000), "PAYPAL ACHAT BOUTIQUE EN LIGNE", "Boutique en ligne Exemple", "Achats en ligne")
        op(paypal, day(m, 2), 4000, "PAYPAL APPROVISIONNEMENT", None, "PayPal")
        op(courant, day(m, 2), -4000, "PAYPAL EUROPE APPROVISIONNEMENT", None, "PayPal")
        if i % 2 == 0:
            op(courant, day(m, rnd.randint(1, 28)), -2800, "CB SALON COIFFURE EXEMPLE", "Coiffeur Exemple", "Coiffeur")
        if rnd.random() < 0.35:
            op(courant, day(m, rnd.randint(1, 28)), rnd.randint(1500, 4500), "VIR REMBOURSEMENT SANTE EX", "Assurance maladie Exemple", "Remboursements santé")
        if m.month == 12:
            op(livret, day(m, 31), 3150, "INTERETS LIVRET A", None, "Intérêts / dividendes")
    # Quelques opérations récentes à catégoriser
    for k, (label, cents) in enumerate([("CB COMMERCE INCONNU 1", -1890), ("CB MARCHE DU DIMANCHE", -2340), ("VIR RECU REMBOURSEMENT AMI", 2500)]):
        op(courant, today - timedelta(days=2 + 3 * k), cents, label, None, None)

    c.post("/api/transfers/detect").raise_for_status()
    c.post("/api/recurring/refresh").raise_for_status()
    # Les principaux récurrents confirmés, les autres restent « à confirmer » (pour voir les deux cas).
    for s in c.get("/api/recurring", params={"all": "true"}).json()["items"]:
        if any(w in s["label"] for w in ("Société", "Agence", "Énergie", "Box", "Streaming", "Mutuelle", "Salaire")):
            c.patch(f"/api/recurring/{s['id']}", json={"status": "actif"})
    for name, cents in (("Courses", 38000), ("Restaurants", 9000), ("Bars", 8000), ("Livraison", 6000)):
        c.put(f"/api/budgets/{cats[name]}", json={"monthly_amount_cents": cents})
    in_a_year = (today.replace(day=1) + timedelta(days=400)).replace(day=1)
    c.post("/api/goals", json={"name": "Matelas de sécurité (démo)", "icon": "🛟", "target_cents": 400000, "account_id": livret})
    c.post("/api/goals", json={"name": "Voyage (démo)", "icon": "✈️", "target_cents": 250000, "account_id": livret,
                               "target_date": in_a_year.isoformat(), "priority": 1})


def _record(c, today: date) -> dict:
    responses: dict[str, object] = {}

    def get(path: str) -> None:
        r = c.get(f"/api{path}")
        if r.status_code == 200:
            responses[key_of("GET", path)] = r.json()

    def post(path: str, body: dict) -> None:
        r = c.post(f"/api{path}", json=body)
        if r.status_code == 200:
            responses[key_of("POST", path)] = r.json()

    # Pas de réglages, connexions bancaires ni sécurité : rien de ces pages n'est utile en démo.
    for p in ("/auth/me", "/accounts", "/accounts?include_archived=true", "/accounts/net-worth", "/categories", "/categories/usage",
              "/tags", "/budgets", "/recurring", "/recurring?all=true", "/forecast", "/merchants", "/merchants?include_inactive=true",
              "/merchants/similar", "/transactions/to-categorize", "/connections", "/data/imports", "/pending", "/dashboard",
              "/dashboard/months", "/advice", "/goals", "/recap"):
        get(p)
    for m in _months_back(today, 13):
        get(f"/dashboard?month={m:%Y-%m}")
    for m in _months_back(today, 4):
        get(f"/budgets?month={m:%Y-%m}")
        get(f"/recap?month={m:%Y-%m}")
    for a in c.get("/api/accounts").json():
        get(f"/pending?account_id={a['id']}")
        get(f"/dashboard/months?accounts={a['id']}")
    for h in ("fin_du_mois", "fin_mois_prochain", "30", "90", "182", "365"):
        post(f"/forecast?horizon={h}", DEFAULT_SCENARIO)
    for n in (3, 6, 12, 24, 36):
        post(f"/projection?months={n}", DEFAULT_SCENARIO)
    for s in c.get("/api/recurring", params={"all": "true"}).json()["items"]:
        get(f"/recurring/{s['id']}/transactions")
    for mid in {m["id"] for m in c.get("/api/merchants").json()}:
        get(f"/merchants/{mid}/services")
        get(f"/merchants/{mid}/breakdown")

    # Toutes les opérations : le front les filtre lui-même (compte, catégorie, recherche, dates…).
    items, offset = [], 0
    while True:
        page = c.get("/api/transactions", params={"limit": 500, "offset": offset}).json()
        items += page["items"]
        offset += 500
        if offset >= page["total"]:
            break
    return {"responses": responses, "transactions": items}


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "snapshot.json")
    from alembic import command
    from alembic.config import Config
    from fastapi.testclient import TestClient

    from app.db import get_engine

    assert str(get_engine().url).startswith("sqlite"), "sécurité : le jeu de démo ne doit jamais toucher la vraie base"
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    command.upgrade(cfg, "head")

    from app.main import app

    today = date.today()
    with TestClient(app) as c:
        c.post("/api/auth/login", json={"password": "demo"}).raise_for_status()
        c.headers["X-Confirm-Password"] = "demo"
        _seed(c, today)
        data = _record(c, today)
    data = {"version": 1, "generated_at": datetime.now().isoformat(timespec="minutes"), "today": today.isoformat(), **data}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str), encoding="utf-8")
    print(f"Jeu de démo écrit : {out} ({len(data['responses'])} réponses, {len(data['transactions'])} opérations)")


if __name__ == "__main__":
    main()
