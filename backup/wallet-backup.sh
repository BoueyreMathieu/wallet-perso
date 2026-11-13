#!/bin/sh
# Sauvegarde chiffrée de la base Wallet, en boucle (toutes les BACKUP_INTERVAL_HOURS heures).
#   - pg_dump au format « custom », vérifié avec pg_restore --list ;
#   - chiffré avec age pour la clé publique BACKUP_AGE_RECIPIENT (seule la clé privée, gardée hors du serveur,
#     permet de le relire) ; le dump en clair ne touche jamais le disque (dossier /tmp en mémoire) ;
#   - rotation : 7 quotidiennes, 4 hebdomadaires, 12 mensuelles ;
#   - copie hors machine avec rclone si BACKUP_RCLONE_REMOTE est défini ;
#   - état (réussite / erreur) écrit dans la base, affiché dans l'appli (Paramètres > Sécurité).
set -eu

DIR=/backups
INTERVAL_H="${BACKUP_INTERVAL_HOURS:-24}"
KEEP_DAILY="${BACKUP_KEEP_DAILY:-7}"
KEEP_WEEKLY="${BACKUP_KEEP_WEEKLY:-4}"
KEEP_MONTHLY="${BACKUP_KEEP_MONTHLY:-12}"
REMOTE="${BACKUP_RCLONE_REMOTE:-}"
RECIPIENT="${BACKUP_AGE_RECIPIENT:-}"
PLAIN=/tmp/wallet.dump

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }

# Écrit l'état dans app_meta (clé, JSON). Les apostrophes sont doublées pour SQL.
status() {
  json=$(printf '%s' "$2" | sed "s/'/''/g")
  psql -q -v ON_ERROR_STOP=1 -c "INSERT INTO app_meta (key, value) VALUES ('$1', '$json') ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value" >/dev/null 2>&1 \
    || log "impossible d'écrire l'état en base"
}

fail() {
  msg=$(printf '%s' "$1" | tr '"\\\n' "'/ " | cut -c1-180)
  log "ÉCHEC : $1"
  status backup_last_error "{\"at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"message\": \"$msg\"}"
  rm -f "$PLAIN"
}

# Garde les N fichiers les plus récents d'un dossier (noms datés : l'ordre alphabétique est l'ordre chronologique).
prune() {
  ls -1 "$1" 2>/dev/null | grep '^wallet-.*\.dump\.age$' | sort -r | tail -n +"$(($2 + 1))" | while read -r f; do
    rm -f "$1/$f"
  done || true
}

backup_once() {
  if [ -z "$RECIPIENT" ]; then
    fail "BACKUP_AGE_RECIPIENT manquant dans .env (voir docs/sauvegardes.md)"
    return 0
  fi
  mkdir -p "$DIR/quotidiennes" "$DIR/hebdomadaires" "$DIR/mensuelles"
  stamp=$(date -u +%Y-%m-%d_%H%M)
  name="wallet-$stamp.dump.age"

  if ! err=$(pg_dump --format=custom --compress=9 --file="$PLAIN" 2>&1); then fail "pg_dump : $err"; return 0; fi
  if ! pg_restore --list "$PLAIN" >/dev/null 2>&1; then fail "dump illisible (pg_restore --list)"; return 0; fi
  if ! err=$(age --encrypt --recipient "$RECIPIENT" --output "$DIR/quotidiennes/.$name.part" "$PLAIN" 2>&1); then
    rm -f "$DIR/quotidiennes/.$name.part"
    fail "chiffrement age : $err"
    return 0
  fi
  rm -f "$PLAIN"
  mv "$DIR/quotidiennes/.$name.part" "$DIR/quotidiennes/$name"

  # Hebdomadaire / mensuelle : la première sauvegarde de la semaine / du mois est conservée plus longtemps.
  week=$(date -u +%G-S%V)
  month=$(date -u +%Y-%m)
  ls "$DIR/hebdomadaires" | grep -q "^wallet-$week" || cp "$DIR/quotidiennes/$name" "$DIR/hebdomadaires/wallet-$week.dump.age"
  ls "$DIR/mensuelles" | grep -q "^wallet-$month" || cp "$DIR/quotidiennes/$name" "$DIR/mensuelles/wallet-$month.dump.age"
  prune "$DIR/quotidiennes" "$KEEP_DAILY"
  prune "$DIR/hebdomadaires" "$KEEP_WEEKLY"
  prune "$DIR/mensuelles" "$KEEP_MONTHLY"

  size=$(wc -c < "$DIR/quotidiennes/$name" | tr -d ' ')
  offsite="non configurée"
  if [ -n "$REMOTE" ]; then
    if err=$(rclone sync "$DIR" "$REMOTE" --exclude ".*" 2>&1); then
      offsite="ok"
    else
      fail "copie hors machine (rclone) : $(printf '%s' "$err" | tail -n 1)"
      return 0
    fi
  fi
  log "sauvegarde $name ($size octets, copie hors machine : $offsite)"
  status backup_last_ok "{\"at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"file\": \"$name\", \"size\": $size, \"offsite\": \"$offsite\"}"
}

# Une sauvegarde de moins d'un intervalle existe déjà (pas de doublon après un redémarrage).
recent() {
  [ -d "$DIR/quotidiennes" ] && [ -n "$(find "$DIR/quotidiennes" -name 'wallet-*.dump.age' -mmin -"$((INTERVAL_H * 60 - 10))" 2>/dev/null | head -n 1)" ]
}

log "service de sauvegarde démarré (toutes les ${INTERVAL_H} h)"
[ "${BACKUP_NOW:-}" = "1" ] && backup_once
until pg_isready -q; do sleep 5; done
# Vérifie toutes les heures s'il est temps d'en faire une (et réessaie dans l'heure après un échec).
while true; do
  recent || backup_once || true
  [ "${BACKUP_ONCE:-}" = "1" ] && exit 0
  sleep 3600
done
