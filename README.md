# Wallet perso

Application personnelle de gestion d'argent : agrégation de comptes (Crédit Agricole, PayPal, Trade Republic, comptes manuels), suivi des dépenses, budgets, abonnements, projections et conseils.

Auto-hébergée, un seul utilisateur, données privées.

## Stack

- **API** : Python 3.12, FastAPI, SQLAlchemy 2, Alembic
- **Base** : PostgreSQL 16
- **Interface** : React 18, Vite, Tailwind
- **Déploiement** : Docker Compose

## Lancer l'appli (Windows)

Prérequis : [Docker Desktop](https://www.docker.com/products/docker-desktop/) lancé, et [Git](https://git-scm.com/download/win).

```powershell
cd wallet-perso
# 1. Crée le fichier .env (mot de passe + clés aléatoires)
powershell -ExecutionPolicy Bypass -File scripts\init-env.ps1
# 2. Construit et démarre
docker compose up -d --build
```

Puis ouvre http://localhost:8080 et connecte-toi avec ton mot de passe.

⚠️ Sauvegarde la valeur `ENCRYPTION_KEY` du fichier `.env` dans un gestionnaire de mots de passe : elle chiffre les accès bancaires enregistrés.

### Commandes utiles

| Action | Commande |
|---|---|
| Arrêter | `docker compose down` |
| Voir les logs de l'API | `docker compose logs -f api` |
| Mettre à jour après un `git pull` | `docker compose up -d --build` |
| Lancer les tests | `docker compose run --rm api pytest -q` |
| Sauvegarder la base | `docker compose exec db pg_dump -U wallet wallet > sauvegarde.sql` |

## Développement sans Docker (optionnel)

```powershell
# API
cd backend
python -m venv .venv; .venv\Scripts\activate
pip install -r requirements.txt
$env:DATABASE_URL="sqlite:///./dev.db"; alembic upgrade head
uvicorn app.main:app --reload
# Interface (autre terminal)
cd frontend; npm install; npm run dev   # http://localhost:5173
```

## Organisation

```
backend/
  app/models.py        modèle de données (toutes les tables)
  app/api/             routes HTTP
  app/security.py      connexion + chiffrement des secrets
  migrations/versions/ migrations de la base
  tests/
frontend/src/
  pages/               écrans
  api.ts               appels à l'API
scripts/init-env.ps1   génération du .env
```

## Conventions

- Montants en **centimes** (entiers) : `-1250` = −12,50 €. Dépense négative, revenu positif.
- Chaque changement de schéma passe par une migration Alembic :
  `docker compose run --rm api alembic revision --autogenerate -m "description"`.
- Les exports bancaires (CSV…) ne sont jamais versionnés (voir `.gitignore`).

## Feuille de route

0. ✅ Socle : base, login, comptes manuels, patrimoine net
1. Import CSV Crédit Agricole + catégorisation par règles
2. Dashboard des dépenses
3. PayPal + Trade Republic, virements internes
4. Synchro automatique (Enable Banking)
5. Budgets + abonnements
6. Projections + objectifs
7. Conseils d'optimisation
8. Mobile (PWA + accès distant)
