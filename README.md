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

## Importer ses opérations

Crédit Agricole : espace en ligne → compte → « Télécharger mes opérations » au format CSV, puis onglet **Importer** de l'appli.
Range les exports dans `imports/` (ignoré par git). Réimporter une période déjà importée ne crée pas de doublons.

PayPal : paypal.com → Activité → Télécharger → CSV, puis **Importer** avec la source « PayPal » (crée d'abord
un compte de type PayPal). Les achats PayPal payés par la banque sont rapprochés du prélèvement bancaire :
la ligne bancaire prend le vendeur, la catégorie et les infos de l'achat ; la ligne PayPal reste visible
mais n'est pas comptée (pas de double comptage). « Dissocier » annule un rapprochement faux.

Catégorisation : des règles par défaut (`backend/app/default_rules.py`) + tes propres règles, créées quand tu
catégorises un marchand dans l'onglet **Opérations**. Tes règles passent toujours en premier.

### Préparer un nouvel import (PayPal, Trade Republic…)

Pour décrire un export à Claude **sans partager son contenu** :
```powershell
docker run --rm -v "${PWD}:/w" -w /w python:3.12-slim python scripts/csv_structure.py imports/mon-export.csv
```
Le script affiche les colonnes, types et formats avec des valeurs masquées (lettres → A/a, chiffres → 9).
`--show-values "Type"` révèle les valeurs d'une colonne précise (à réserver aux colonnes de type/statut).

## Vendeurs et données

- **Vendeurs** : dépensé / reçu / nombre d'opérations par vendeur sur une période, catégorie (choisie ou déduite),
  renommer, fusionner deux vendeurs, réinitialiser la catégorie.
- **Services** : un vendeur peut avoir plusieurs services, chacun avec sa catégorie (ex. assurance habitation et
  assurance auto chez le même courtier), reconnus par un mot du libellé et/ou un montant. Ordre : correction à la
  main > service > catégorie générale du vendeur > règles par défaut.
- **Étiquettes** : vues transversales (« Assurances », « Vacances »…) posées sur un vendeur, un service ou une
  sélection d'opérations (cases à cocher dans Opérations). Elles ne changent pas les totaux par catégorie.
- **Données** : annuler un import, vider ou supprimer un compte, réinitialiser une catégorie ou toutes tes
  catégorisations, tout effacer (confirmation « EFFACER »). Les rapprochements PayPal sont défaits proprement.

## Conventions

- Montants en **centimes** (entiers) : `-1250` = −12,50 €. Dépense négative, revenu positif.
- Chaque changement de schéma passe par une migration Alembic :
  `docker compose run --rm api alembic revision --autogenerate -m "description"`.
- Les exports bancaires (CSV…) ne sont jamais versionnés (voir `.gitignore`).

## Feuille de route

0. ✅ Socle : base, login, comptes manuels, patrimoine net
1. ✅ Import CSV Crédit Agricole + catégorisation par règles
2. ✅ Connecteurs (format commun) + import PayPal + rapprochement PayPal ↔ banque
3. Synchro automatique (Enable Banking…)
4. Trade Republic (pytr)
5. Dashboard des dépenses
6. Budgets + abonnements
7. Projections + objectifs
8. Conseils d'optimisation
9. Mobile (PWA + accès distant)
