# Travailler à deux conversations sur le même code

Deux conversations Claude modifient ce dépôt sur le PC :

- **conversation principale** : serveur (backend), interface web, sécurité, docs générales ;
- **conversation Android** : appli Capacitor et widgets.

Pour ne jamais écraser, casser ou dupliquer le travail de l'autre, chacune suit ces règles.

## Verrou de livraison : `.dev-lock` (à la racine, ignoré par git)

```
etat: en cours            (ou : libre)
par: conversation principale    (ou : conversation Android)
depuis: 2026-11-13T00:10Z
fichiers: backend/app/services/planning.py, …
```

1. **Avant de livrer**, lire `.dev-lock`. S'il dit `en cours` pour l'autre conversation depuis moins de 30 minutes :
   attendre et relire (ou demander à l'utilisateur). Au-delà de 30 minutes, demander à l'utilisateur avant de passer outre.
2. Écrire le verrou (`etat: en cours`, son nom, l'heure, la liste des fichiers).
3. **Pour chaque fichier à modifier** : comparer son empreinte (md5) sur le PC à la dernière version connue.
   Différente ⇒ l'autre l'a changé : relire la version du PC et y appliquer ses modifications (jamais l'inverse).
4. Livrer, vérifier les empreintes.
5. Remettre `etat: libre` et noter la livraison (fichiers touchés) dans le journal du projet (`journal-et-idees.md`).

## Qui s'occupe de quoi

| Domaine | Conversation | Fichiers |
|---|---|---|
| Android | Android | `frontend/android-overlay/**`, `frontend/scripts/prepare-android.mjs`, `frontend/capacitor.config.json`, `frontend/src/native.ts`, `backend/app/api/widgets.py`, `docs/android.md`, `docs/workflow-android.yml` |
| Serveur, web | principale | `backend/**` (sauf `widgets.py`), `frontend/src/pages/**`, `frontend/src/components/**`, `docker-compose.yml`, `backup/**`, `docs/**` (sauf Android) |
| Partagés | les deux | `frontend/src/App.tsx`, `api.ts`, `main.tsx`, `index.css`, `frontend/package.json`, `README.md`, `.gitignore` |

Sur un fichier partagé : modifications **ciblées** (remplacer un passage précis), jamais réécrire le fichier entier à partir
d'une ancienne copie. Un besoin dans le domaine de l'autre (ex. un nouvel endpoint pour un widget) : le noter dans le
journal du projet plutôt que de le coder soi-même, sauf accord de l'utilisateur.
