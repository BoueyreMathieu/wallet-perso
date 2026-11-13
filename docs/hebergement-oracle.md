# Héberger le Wallet sur Oracle Cloud « Always Free » (PC éteint)

Objectif : le serveur (API, base, synchro bancaire) tourne en permanence sur une petite machine virtuelle gratuite,
accessible **uniquement par Tailscale** (aucun port ouvert sur Internet). L'appli Android et le navigateur
continuent d'utiliser `https://wallet.<ton-réseau>.ts.net`.

## ⚠️ À savoir avant

- Inscription avec une carte bancaire (vérification, rien n'est débité tant qu'on reste dans les limites gratuites).
- **Instances inactives récupérées** : Oracle peut supprimer une instance « Always Free » si, sur 7 jours, son
  processeur, son réseau **et** (pour Ampere) sa mémoire restent sous 20 %. Le Wallet consomme très peu : risque réel.
  Parades : passer le compte en « Pay As You Go » (on reste gratuit dans les limites ; souvent cité comme évitant
  cette récupération — à vérifier au moment de l'inscription) avec une alerte de budget à 1 €, **et** des
  sauvegardes automatiques hors de la machine (prochaine fonctionnalité prévue).
- Les limites gratuites changent parfois : vérifier dans la console (Limits, Quotas and Usage).

## Avant la migration

- Sauvegardes automatiques **actives et testées** sur le PC ([sauvegardes.md](sauvegardes.md)), avec copie hors
  machine : elles suivront le serveur sur Oracle.
- Lot 3 de [securite.md](securite.md) fait (2FA, device approval, tailnet lock).

## Étapes (prochaine session, ensemble)

1. Créer le compte Oracle Cloud, région proche (Paris ou Marseille).
2. Créer une instance **Ampere A1** (ARM), Ubuntu 24.04, 1 OCPU / 6 Go (ou 2 / 12 Go), disque 50 Go.
3. Sur la machine : Docker + Tailscale, puis verrouillage :
   - `sudo tailscale up --ssh --advertise-tags=tag:wallet` (règles : [tailscale-acl.hujson](tailscale-acl.hujson)) ;
   - une fois Tailscale SSH testé : console Oracle › VCN › *Security List* › **supprimer la règle d'entrée du
     port 22** (aucune règle d'entrée publique ne doit rester) ;
   - `sudo apt install unattended-upgrades` (mises à jour de sécurité automatiques) ;
   - `PasswordAuthentication no` dans `/etc/ssh/sshd_config` (déjà le cas sur les images Oracle, à vérifier) ;
   - ne jamais publier un port Docker sans `127.0.0.1:` (Docker contourne le pare-feu de la VM).
4. Tailscale : renommer le PC (ex. `wallet-pc`) et nommer la machine Oracle **`wallet`** → même adresse
   `https://wallet.<ton-réseau>.ts.net` (rien à changer chez Enable Banking ni dans l'appli), puis
   `tailscale serve --bg 8080` sur la machine Oracle.
5. Déménager les données :
   - PC : forcer une sauvegarde chiffrée (`docker compose run --rm -e BACKUP_NOW=1 -e BACKUP_ONCE=1 backup`) ;
   - copier le dépôt (git clone), `.env`, `secrets/` et le dernier fichier `backups/quotidiennes/*.age` sur la
     machine, par Tailscale (`tailscale file cp`) — **jamais** de dump en clair, jamais dans le dépôt ;
   - machine : `docker compose up -d db`, restauration ([sauvegardes.md](sauvegardes.md) § Restaurer, la clé
     privée age n'est collée que le temps de la commande), puis `docker compose up -d --build` ;
   - PC : `docker compose down` (sinon deux synchros bancaires en parallèle).
6. Vérifier : navigateur, appli Android, widgets, synchro.
