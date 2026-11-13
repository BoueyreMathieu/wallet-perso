# Sécurité de Wallet perso

Rapport d'audit complet : doc projet `audit-securite.md`. Ce guide décrit ce qui est en place (version 0.8) et
**les réglages à faire toi-même** (hors code).

## Ce que fait l'appli

| Protection | Détail |
|---|---|
| Aucune exposition Internet | seul `127.0.0.1:8080` est ouvert ; l'accès passe par Tailscale |
| Mot de passe | empreinte scrypt dans `.env` (`APP_PASSWORD_HASH`), essais traités un par un |
| Blocage | après 5 échecs : 1 min, puis 2, 4, 8… jusqu'à 1 h par échec (remis à zéro à la connexion réussie) |
| Sessions du navigateur | en base, révocables ; expirent après 14 j sans usage (90 j max) ; cookie `__Host-`, HttpOnly, SameSite=Strict, Secure |
| Téléphones | jeton par appareil, révocable, expiré après 90 j sans usage |
| Actions destructrices | mot de passe redemandé (tout effacer, vider/supprimer un compte, annuler un import, réinitialiser, supprimer une connexion) |
| Journal | Paramètres › Sécurité : connexions, échecs, appareils, actions sensibles |
| Navigateur | CSP stricte, anti-iframe, `nosniff`, HSTS, pas de cache des réponses de l'API |
| Conteneurs | sans root, système de fichiers en lecture seule, aucun privilège Linux, mémoire limitée, logs plafonnés |
| Sauvegardes | quotidiennes, chiffrées (age), hors machine : [sauvegardes.md](sauvegardes.md) |
| Android | pas de sauvegarde Google des données de l'appli, build release signé possible ([android.md](android.md)) |
| Banque | accès DSP2 en **lecture seule** : aucun virement possible depuis l'appli, même en cas d'intrusion |

## Après la mise à jour 0.8 (une fois)

1. `docker compose up -d --build` (nouvelle migration, nouveau service `backup`).
2. `powershell -ExecutionPolicy Bypass -File scripts\securiser-env.ps1` : remplace le mot de passe en clair par
   son empreinte et passe `COOKIE_SECURE=true`. Puis reconnecte-toi.
3. Sauvegardes : [sauvegardes.md](sauvegardes.md) (clé age + copie hors machine).
4. Paramètres › Sécurité : tout doit être ✅.

## À faire toi-même (lot 3)

### 1. Compte d'identité de Tailscale (le plus important)

Qui contrôle le compte (Google, Microsoft, GitHub…) qui sert à te connecter à Tailscale peut ajouter un appareil
à ton réseau, donc atteindre le Wallet.

- Active la **2FA par clé de sécurité ou passkey** sur ce compte (pas de SMS).
- Tailscale › Settings › **Device approval** : activé (tout nouvel appareil doit être approuvé).
- Tailscale › Machines : supprime les appareils que tu n'utilises plus.
- Laisse l'**expiration des clés** active sur tes appareils personnels.
- **Tailnet lock** (Settings › Tailnet lock) : les nouveaux appareils doivent être signés par un de tes
  appareils de confiance. Même un compte Tailscale compromis ne suffit plus.
- **Jamais** `tailscale funnel` (ça publierait l'appli sur Internet).

### 2. Règles d'accès Tailscale (au moment de la migration Oracle)

[tailscale-acl.hujson](tailscale-acl.hujson) : seuls tes appareils atteignent le serveur, uniquement en HTTPS ;
SSH seulement par Tailscale SSH. Étiquette la machine Oracle `tag:wallet` (`tailscale up --advertise-tags=tag:wallet`).

### 3. GitHub

- 2FA par clé de sécurité / passkey.
- Le dépôt reste **privé**.
- Vérifie qu'aucune donnée n'a jamais été commitée (doit ne rien afficher) :

```powershell
git log --all --name-only --format="" -- "*.sql" "*.dump" "*.csv" "*.ofx" ".env" "secrets/*" "*.pem" | Sort-Object -Unique
```

- Dépendances : déplace `docs/dependabot.yml` vers `.github/dependabot.yml` (mises à jour de sécurité automatiques).
- Si tu installes [gitleaks](https://github.com/gitleaks/gitleaks) : `gitleaks git .` analyse tout l'historique.

### 4. Dépendances verrouillées (package-lock.json)

Une fois, sur le PC, dans `frontend` :

```powershell
npm install
git add package-lock.json; git commit -m "Verrouille les dépendances npm"
```

Le build Docker passe alors automatiquement en `npm ci` (versions exactes, vérifiées par empreinte).

### 5. Le PC

- **BitLocker** activé sur le disque (Paramètres › Confidentialité et sécurité › Chiffrement de l'appareil).
- Session Windows quotidienne **sans** droits administrateur, mises à jour automatiques.
- `.env`, `secrets/` et `backups/` : ne les copie jamais sur une clé USB ou un cloud non chiffré.

### 6. Le mot de passe de l'appli

16 caractères ou plus, **unique**, généré par ton gestionnaire. À changer (avec `scripts\securiser-env.ps1`) si tu
as le moindre doute ; les sessions des navigateurs sont alors fermées, et tu peux déconnecter les téléphones dans
Paramètres › Sécurité.

### 7. Le téléphone

Verrouillage de l'écran (code + biométrie), chiffrement (par défaut), débogage USB **désactivé** hors développement.
En cas de perte : Paramètres › Sécurité › « Déconnecter » sur ce téléphone.

## En cas de doute (intrusion suspectée)

1. Paramètres › Sécurité › **Déconnecter tous les autres**.
2. Change le mot de passe (`scripts\securiser-env.ps1`).
3. Tailscale › Machines : retire tout appareil inconnu.
4. Enable Banking : supprime la connexion dans l'appli (le consentement bancaire est révoqué), puis recrée-la.
5. Si `.env` a pu fuiter : nouvelle `SECRET_KEY`, nouvelle clé Enable Banking (`.pem`), puis reconnecte les banques.
