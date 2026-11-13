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
| Lancer les tests | `docker compose run --rm api pytest -q -p no:cacheprovider` |
| Sauvegardes | automatiques et chiffrées : [docs/sauvegardes.md](docs/sauvegardes.md) |
| Sauvegarde immédiate | `docker compose run --rm -e BACKUP_NOW=1 -e BACKUP_ONCE=1 backup` |
| Sécuriser `.env` (mot de passe haché) | `powershell -ExecutionPolicy Bypass -File scripts\securiser-env.ps1` |

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

## Synchro bancaire automatique (Enable Banking)

1. Crée un compte sur https://enablebanking.com, puis une application dans **API applications**.
   - **Sandbox** pour essayer (banques de test uniquement, ex. « Mock ASPSP »).
   - **Production** pour tes vrais comptes : l'adresse de retour doit être en **https** (voir Tailscale ci-dessous).
     Formulaire : description, email, URL de confidentialité `https://<hôte>/confidentialite.html` et de conditions
     `https://<hôte>/conditions.html` (pages fournies par l'appli). Ensuite, sur la page de l'application,
     **« Activate by linking accounts »** (production restreinte à tes propres comptes).
2. Range le fichier `.pem` téléchargé dans `secrets/` (ignoré par git ; s'il y en a plusieurs, celui nommé
   `<id>.pem` est choisi) et renseigne dans `.env` :
   `ENABLE_BANKING_APP_ID=<id>` et `ENABLE_BANKING_REDIRECT_URL=<adresse de retour déclarée>`.
3. `docker compose up -d --build`, puis page **Connexions** → « Choisir ma banque ».
4. Associe chaque compte bancaire à un compte de l'appli (reconnu automatiquement si tu l'avais déjà importé en CSV)
   et lance une première synchro **dans l'heure** (c'est là que la banque donne le plus d'historique).

### Adresse https avec Tailscale

Tailscale donne au PC une adresse https privée, visible seulement de tes appareils (utile aussi pour le mobile) :
1. Installe Tailscale, connecte-toi ; dans la console admin, renomme la machine (ex. `wallet` : le nom devient
   public dans les registres de certificats), puis page **DNS** : MagicDNS + **Enable HTTPS**.
2. `tailscale serve --bg 8080` → l'appli répond sur `https://wallet.<ton-réseau>.ts.net` (`tailscale serve off` pour arrêter).
3. Adresse de retour : `https://wallet.<ton-réseau>.ts.net/api/connections/callback` (la racine `/` fonctionne aussi :
   l'interface transmet le retour de banque à l'API).

Ensuite la synchro tourne toute seule toutes les `SYNC_INTERVAL_HOURS` heures (6 par défaut) tant que l'appli tourne.
L'autorisation est à renouveler au plus tous les 180 jours (obligation DSP2) : la page Connexions prévient.
Une opération déjà importée en CSV n'est pas recréée par la synchro (même compte, même montant, même date ou ±2 jours).

## Accueil, catégories, virements, thème

- **Navigation** : Accueil, Opérations, Vendeurs, Comptes, **Paramètres** (Catégories, Connexions, Importer,
  Données, Préférences).
- **Accueil** : choix des comptes pris en compte (mémorisé), clic sur une catégorie = vue détaillée de cette
  catégorie (sous-catégories, paiements du mois, 12 mois), « ← Toutes les catégories » pour revenir. Condensé du mois (dépensé vs mois précédent à la même date, revenus, patrimoine, taux d'épargne),
  dépenses par catégorie (clic → opérations correspondantes), rythme des dépenses, revenus/dépenses sur 12 mois
  (clic sur un mois pour l'afficher), plus grosses dépenses, vendeurs du mois, comptes, choses à traiter.
- **Catégories** : créer, renommer, recolorer, changer d'icône, déplacer une sous-catégorie, supprimer.
  À la suppression, les opérations sont soit déplacées vers une autre catégorie, soit remises « à catégoriser »
  (tes autres règles sont réappliquées d'abord). Une catégorie par défaut supprimée ou renommée n'est jamais recréée.
  « Transferts › Virement interne » est une catégorie système (non supprimable).
- **Virements entre mes comptes** : −X sur un compte et +X sur un autre (±3 jours, libellés de virement) sont
  appariés automatiquement et exclus des dépenses/revenus. Manuellement : cocher les deux opérations →
  « Virement entre mes comptes ». « Ce n'est pas un virement entre mes comptes » défait l'appariement.
- **PayPal synchronisé** : PayPal ne fournit que les achats ; chaque achat est rapproché directement du
  prélèvement bancaire « PayPal » de même montant (dates proches) → la ligne bancaire prend le vrai vendeur et
  sa catégorie, l'achat PayPal n'est pas compté deux fois.
- **Libellés bancaires** : « Paiement par carte X1234 MONOP 01/11 », « Virement émis vers … », « Prlv SEPA … » →
  le vendeur est extrait du libellé (type d'opération, n° de carte, dates et références retirés) ; les retraits sont
  regroupés sous « Retrait d'espèces ». Les anciens vendeurs mal nommés sont recalculés au démarrage.
- **Accueil** : cartes du haut et segments de la roue cliquables ; Retour du navigateur = retour à toutes les catégories.
- **Vendeurs similaires** : même nom à une troncature ou une référence près (« … JEA » / « … JEAN 12 ») → fusion
  automatique (à l'import, à la synchro, au démarrage). Même début mais suite différente → suggestion dans Vendeurs
  (« Regrouper » ou « Ce sont des vendeurs différents »).
- **Ton nom de titulaire** (Paramètres › Préférences) : un vendeur qui commence par ton nom = virement entre tes
  comptes (« Virement interne », hors statistiques). Appris du titulaire des exports CSV, modifiable.
- **Choix d'une catégorie** : champ de recherche (taper « resto », « carbu »…), flèches + Entrée, catégories récentes en tête.
- **Thème** : Auto (suit l'appareil, par défaut), Clair ou Sombre — en bas du menu (ordinateur) ou dans l'en-tête (téléphone).

Outil de diagnostic (structure des opérations synchronisées, sans contenu) :
`docker compose exec api python -m app.tools.eb_structure` puis `--account N`.

## Appli Android et widgets

Appli Android (Capacitor) avec 8 widgets à taille évolutive (solde d'un compte au choix, fin du mois, ce mois-ci,
budgets, à venir, patrimoine, dernières opérations, ajout rapide) :
voir [docs/android.md](docs/android.md). APK construit par GitHub Actions (onglet Actions › « Appli Android »).
Pour qu'elle marche PC éteint : [docs/hebergement-oracle.md](docs/hebergement-oracle.md).

## Prévoir : trésorerie, budgets, récurrents

Menu **🔮 Prévoir** (et deux cartes sur l'accueil) :

- **Récurrents** : abonnements, prélèvements, salaires et virements programmés détectés automatiquement dans
  l'historique (même vendeur, montant proche, rythme régulier : hebdomadaire → annuel), à confirmer ou écarter ;
  coût mensuel / annuel, hausses de prix signalées, « résilié ? » quand une échéance ne vient plus. Ajout à la main
  (assurance annuelle…) ou depuis une opération (« Suivre comme récurrent »). Détection relancée à chaque import /
  synchro et au démarrage.
- **Budgets** mensuels par catégorie (sous-catégories comprises) : dépensé, repère « où tu devrais en être »,
  projection de fin de mois (prélèvements encore attendus + rythme des dépenses courantes), alerte réglable,
  suggestions d'après les 3 derniers mois.
- **Trésorerie** : solde prévu jour par jour (fin du mois, mois prochain, 30 j, 3 / 6 mois, 1 an ou une date choisie),
  construit en couches : le **socle** (solde + revenus récurrents et habituels − charges fixes, à leur date), puis les
  **essentiels** et les **plaisirs** selon la tendance de chaque catégorie (moyenne pondérée de 12 mois, les plus récents
  comptant plus, mois exceptionnels écrêtés) répartie selon tes jours de dépense habituels. Point bas, alerte de découvert.
- **Projection** mois par mois (3 à 36 mois ou jusqu'à un mois choisi) : revenus, couches de dépenses, épargne, solde.
- **Scénario « et si »** commun aux deux : plaisirs de 0 à 150 %, « je respecte mes budgets », objectifs par catégorie
  (enregistrables comme budgets), épargne en plus ; comparaison avec tes habitudes.
- Récurrents repérés aussi **par catégorie** (salaire, loyer aux libellés changeants).
- La couche de chaque catégorie de dépenses est automatique et se règle dans **Catégories**.

## Mode démo (hors connexion)

Serveur injoignable : l'appli affiche un jeu de données **fictif** (bandeau 🧪 « Données de test », comptes « (démo) », lecture seule) et revient aux vraies données dès que le serveur répond. Fabriquer le jeu de test et retirer le mode démo : [docs/demo.md](docs/demo.md).

## Sécurité

Accessible uniquement par Tailscale, mot de passe haché avec blocage progressif, sessions révocables, mot de passe
redemandé pour les actions destructrices, journal de sécurité, sauvegardes chiffrées hors machine.
Guide et réglages à faire soi-même : [docs/securite.md](docs/securite.md).

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
3. ✅ Synchro automatique (Enable Banking) — validée en production avec Crédit Agricole
4. ✅ PayPal (synchro) + virements entre comptes + catégories personnalisées
5. ✅ Dashboard + nouvelle apparence (clair/sombre)
6. ✅ Budgets + abonnements / récurrents + prévision de trésorerie
7. Objectifs d'épargne + projection du patrimoine
8. Conseils d'optimisation
9. ⏳ Appli Android + widgets (Capacitor) — puis hébergement Oracle Cloud
10. Trade Republic (pytr) — module à part, centré investissement
