"""Alertes (appli + notifications du téléphone), réglages des notifications, contrôle de solde vérifié."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Account
from app.security import require_auth
from app.services import alerts

router = APIRouter(prefix="/api", tags=["alertes"], dependencies=[Depends(require_auth)])


@router.get("/alerts")
def get_alerts(db: Session = Depends(get_db)) -> dict:
    """Alertes du moment, pour les types activés. Lu par l'appli et, toutes les 30 min, par le téléphone."""
    return {"alerts": alerts.build_alerts(db, date.today())}


class NotifyIn(BaseModel):
    kinds: dict[str, bool]


def _settings_out(values: dict[str, bool]) -> dict:
    return {"kinds": [{"id": k, "label": alerts.KINDS[k], "detail": alerts.DETAILS[k], "enabled": values[k]} for k in alerts.KINDS]}


@router.get("/settings/notifications")
def get_notify_settings(db: Session = Depends(get_db)) -> dict:
    return _settings_out(alerts.notify_settings(db))


@router.put("/settings/notifications")
def put_notify_settings(body: NotifyIn, db: Session = Depends(get_db)) -> dict:
    values = alerts.set_notify_settings(db, body.kinds)
    db.commit()
    return _settings_out(values)


@router.post("/accounts/{account_id}/balance-check/ok")
def balance_checked(account_id: int, db: Session = Depends(get_db)) -> dict:
    """« J'ai vérifié » : l'écart de solde signalé est accepté, le contrôle repart du dernier solde de la banque."""
    acc = db.get(Account, account_id)
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compte introuvable")
    alerts.mark_balance_checked(db, acc)
    db.commit()
    return {"ok": True}
