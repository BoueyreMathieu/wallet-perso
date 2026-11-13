# Sauvegardes automatiques chiffrées

Le service `backup` (dans `docker-compose.yml`) fait une sauvegarde de la base **toutes les 24 h** :

- `pg_dump` vérifié (`pg_restore --list`), puis **chiffré avec [age](https://age-encryption.org)** pour ta clé publique ;
- le dump en clair ne touche jamais le disque ;
- rotation : 7 quotidiennes, 4 hebdomadaires, 12 mensuelles, dans le dossier `backups/` (ignoré par git) ;
- copie **hors de la machine** avec rclone (optionnel mais fortement conseillé) ;
- état visible dans l'appli : Paramètres › Sécurité, et un rappel sur l'accueil si rien depuis 3 jours ou en cas d'échec.

Le serveur ne détient que la clé **publique** : il peut chiffrer, pas déchiffrer. Une sauvegarde volée est
illisible sans la clé privée, qui ne doit vivre **que** dans ton gestionnaire de mots de passe.

## 1. Créer la paire de clés (une fois)

```powershell
docker compose build backup
docker compose run --rm backup age-keygen
```

Ça affiche :

```
# created: …
# public key: age1…
AGE-SECRET-KEY-1…
```

- **Clé privée** `AGE-SECRET-KEY-1…` → dans ton gestionnaire de mots de passe (note « Wallet – clé des sauvegardes »).
  Pas dans un fichier du PC, pas sur le serveur, pas dans git.
- **Clé publique** `age1…` → dans `.env` :

```
BACKUP_AGE_RECIPIENT=age1…
```

Puis `docker compose up -d`. Vérifie : `docker compose logs backup` doit afficher « sauvegarde wallet-… ».

## 2. Copie hors machine (rclone)

Sans copie ailleurs, une sauvegarde sur la même machine ne protège ni d'un disque mort, ni d'un ransomware, ni
d'Oracle qui récupère la VM. Options gratuites :

| Destination | Pour qui |
|---|---|
| Oracle Object Storage (20 Go gratuits) | VM Oracle (mais même fournisseur que la VM) |
| Google Drive / OneDrive | simple, compte perso |
| Ton PC par Tailscale (SFTP) | si le PC est souvent allumé |

Configuration (exemple Google Drive), une fois :

```powershell
docker compose run --rm -it backup rclone config
# n (nouveau) › nom : wallet-remote › type : drive › suivre les questions
# (« Use auto config? » : n, puis copier le lien dans ton navigateur)
```

La configuration est enregistrée dans `backup/rclone/rclone.conf` (ignoré par git). Puis dans `.env` :

```
BACKUP_RCLONE_REMOTE=wallet-remote:wallet-sauvegardes
```

`docker compose up -d backup`. Le dossier distant est un miroir de `backups/` (les fichiers sont déjà chiffrés).

## 3. Restaurer

Dans un dossier hors du dépôt, avec le fichier `wallet-….dump.age` voulu :

```powershell
# 1. Colle la clé privée dans un fichier temporaire (à supprimer juste après)
notepad $env:TEMP\cle.txt

# 2. Déchiffre (le dump en clair reste dans le conteneur)
docker compose run --rm -v "${PWD}:/restaure" -v "$env:TEMP\cle.txt:/cle.txt:ro" backup sh -c `
  "age -d -i /cle.txt /restaure/wallet-AAAA-MM-JJ_HHMM.dump.age > /tmp/w.dump && pg_restore --clean --if-exists --no-owner -d wallet /tmp/w.dump"

# 3. Supprime la clé temporaire
Remove-Item $env:TEMP\cle.txt
docker compose restart api
```

⚠️ `--clean` remplace le contenu actuel de la base par celui de la sauvegarde.

## 4. Tester la restauration (tous les 3 mois)

Une sauvegarde jamais restaurée n'est pas une sauvegarde. Sans toucher à la vraie base :

```powershell
docker compose run --rm -v "${PWD}\backups:/b:ro" -v "$env:TEMP\cle.txt:/cle.txt:ro" backup sh -c `
  "age -d -i /cle.txt `$(ls -1 /b/quotidiennes/*.age | tail -n 1) > /tmp/w.dump && pg_restore --list /tmp/w.dump | grep -c 'TABLE DATA'"
```

Un nombre (de tables) s'affiche : la sauvegarde se déchiffre et se lit.

## Réglages

| Variable `.env` | Défaut | Rôle |
|---|---|---|
| `BACKUP_AGE_RECIPIENT` | — | clé publique age (obligatoire) |
| `BACKUP_INTERVAL_HOURS` | 24 | fréquence |
| `BACKUP_RCLONE_REMOTE` | — | destination hors machine (`remote:dossier`) |

À garder dans le gestionnaire de mots de passe, **séparément des sauvegardes** : la clé privée age et
`ENCRYPTION_KEY` (elle chiffre les accès bancaires dans la base).
