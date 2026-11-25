# Mode démo (données de test)

Le jeu de données fictif s'affiche dans deux cas :

- **à la main**, à tout moment : bouton 🧪 « Données de test » sur l'accueil (mémorisé sur l'appareil ; « Revenir à
  mes données » dans le bandeau pour en sortir) ;
- **automatiquement**, quand le serveur est injoignable **et** que l'appareil n'a pas de copie hors ligne de tes
  vraies données (navigateur, ou appli Android jamais utilisée connectée). Sinon, c'est le mode hors ligne qui
  s'affiche : voir `docs/hors-ligne.md`.

Ce qu'on voit alors :

- un bandeau 🧪 « Données de test » et une pastille **TEST** dans l'en-tête ;
- trois comptes à part : « Compte courant (démo) », « Livret A (démo) », « PayPal (démo) », avec ~14 mois
  d'opérations inventées ;
- lecture seule : modifier, catégoriser ou supprimer affiche « Mode démo : rien n'est enregistré » ;
- en automatique : dès que le serveur répond (vérifié toutes les 15 s), l'appli se recharge et les vraies données
  reprennent leur place.

Avant de passer en démo, l'appli vérifie que le serveur est vraiment injoignable (pas seulement lent).

## Fabriquer le jeu de test

Aucune donnée réelle n'est utilisée. L'outil crée des comptes et des opérations **inventés** dans une base SQLite
jetable, dans le conteneur. Il ne se connecte jamais à la vraie base : il refuse de tourner si ce n'est pas du
SQLite. Il calcule les écrans avec le vrai moteur (catégories, récurrents, budgets, prévisions), puis écrit le
résultat dans `frontend/public/demo/snapshot.json`.

Dans PowerShell, depuis le dossier du projet :

```powershell
docker compose build api
docker compose run --rm --no-deps -v "${PWD}/frontend/public/demo:/out" api python -m app.tools.demo_snapshot /out/snapshot.json
docker compose up -d --build
```

Puis, pour l'appli Android : `cd frontend`, `npm run android:prepare`, et ▶ Run dans Android Studio.

À refaire de temps en temps : les dates du jeu de test sont figées au jour où il a été fabriqué, et après un
changement de l'API, pour que les écrans de démo restent à jour.

Limites :

- les réglages du scénario « Et si… » ne recalculent rien : la prévision par défaut reste affichée ;
- les pages Connexions, Sécurité et Réglages ne sont pas disponibles en démo.

## Retirer le mode démo

- Le couper sans rien supprimer : `DEMO_ENABLED = false` dans `frontend/src/demo/demo.ts`. Autre façon : supprimer
  `frontend/public/demo/snapshot.json` ; sans ce fichier, l'appli se comporte comme avant.
- Le supprimer complètement :
  1. supprimer les dossiers `frontend/src/demo/` et `frontend/public/demo/`, ainsi que `backend/app/tools/demo_snapshot.py` et ce fichier ;
  2. dans `frontend/src/api.ts` et `frontend/src/App.tsx`, retirer les lignes marquées `DÉMO` ;
  3. dans `api.ts`, remettre `let res = await send();` à la place du bloc `try { res = await send(); } …`.
