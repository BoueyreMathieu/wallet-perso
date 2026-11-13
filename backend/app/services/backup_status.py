"""État des sauvegardes automatiques, écrit en base par le service « backup » (docker-compose)."""

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import AppMeta

STALE_DAYS = 3


def _read(db: Session, key: str) -> dict | None:
    meta = db.get(AppMeta, key)
    if meta is None:
        return None
    try:
        data = json.loads(meta.value)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _date(value) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def backup_status(db: Session) -> dict:
    ok, err = _read(db, "backup_last_ok"), _read(db, "backup_last_error")
    ok_at = _date(ok.get("at")) if ok else None
    err_at = _date(err.get("at")) if err else None
    warning = None
    if err_at and (ok_at is None or err_at > ok_at):
        warning = f"Sauvegarde automatique en échec : {err.get('message') or 'erreur inconnue'}"
    elif ok_at is None:
        warning = "Aucune sauvegarde automatique : active-la (docs/sauvegardes.md)."
    else:
        days = (datetime.now(timezone.utc) - ok_at).days
        if days >= STALE_DAYS:
            warning = f"Dernière sauvegarde il y a {days} jours."
    return {
        "last_ok_at": ok_at,
        "last_size_bytes": (ok or {}).get("size"),
        "offsite": (ok or {}).get("offsite"),
        "last_error_at": err_at,
        "last_error": (err or {}).get("message"),
        "warning": warning,
    }
