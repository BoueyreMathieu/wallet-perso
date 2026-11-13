import logging
from datetime import datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.enable_banking import EnableBankingError
from app.db import get_db
from app.models import Connection
from app.security import require_auth, require_confirmation
from app.services import sync

router = APIRouter(prefix="/api/connections", tags=["connexions"])
auth = [Depends(require_auth)]
log = logging.getLogger("wallet.connections")


class ConnectionOut(BaseModel):
    id: int
    provider: str
    label: str
    status: str
    consent_expires_at: datetime | None
    last_sync_at: datetime | None
    last_error: str | None = None
    last_error_at: datetime | None = None
    accounts: list[dict]


class StartIn(BaseModel):
    aspsp_name: str
    country: str = "FR"
    connection_id: int | None = None  # renseigné pour renouveler une autorisation


class MappingIn(BaseModel):
    mapping: dict[str, int | str | None]  # uid → id de compte, « new » ou null


class SyncResultOut(BaseModel):
    account_name: str
    imported: int
    skipped: int
    categorized: int
    reconciled: int


def _out(c: Connection) -> ConnectionOut:
    return ConnectionOut(
        id=c.id, provider=c.provider, label=c.label, status=c.status,
        consent_expires_at=c.consent_expires_at, last_sync_at=c.last_sync_at, last_error=c.last_error, last_error_at=c.last_error_at,
        accounts=sync.public_accounts(c),
    )


def _get(db: Session, connection_id: int) -> Connection:
    c = db.get(Connection, connection_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connexion introuvable")
    return c


def _fail(e: Exception) -> HTTPException:
    code = status.HTTP_502_BAD_GATEWAY if isinstance(e, EnableBankingError) else status.HTTP_422_UNPROCESSABLE_ENTITY
    return HTTPException(code, str(e))


@router.get("/config", dependencies=auth)
def config() -> dict:
    return sync.config_status()


@router.get("", response_model=list[ConnectionOut], dependencies=auth)
def list_connections(db: Session = Depends(get_db)):
    return [_out(c) for c in db.scalars(select(Connection).order_by(Connection.id))]


@router.get("/aspsps", dependencies=auth)
def aspsps(country: str = "FR") -> list[dict]:
    """Banques disponibles (nom + logo) pour un pays."""
    try:
        banks = sync.get_client().aspsps(country)
    except (sync.SyncError, EnableBankingError) as e:
        raise _fail(e) from e
    return [{"name": b.get("name"), "country": b.get("country"), "logo": b.get("logo")} for b in banks]


@router.post("/start", dependencies=auth)
def start(body: StartIn, db: Session = Depends(get_db)) -> dict:
    try:
        return {"url": sync.start(db, body.aspsp_name, body.country, body.connection_id)}
    except (sync.SyncError, EnableBankingError) as e:
        db.rollback()
        raise _fail(e) from e


@router.get("/callback")
def callback(code: str | None = None, state: str | None = None, error: str | None = None,
             error_description: str | None = None, db: Session = Depends(get_db)):
    """Retour depuis la banque. Pas de cookie de session ici (navigation venant d'un autre site) :
    la requête est authentifiée par le jeton « state » généré au départ."""
    if error or not code or not state:
        msg = error_description or error or "autorisation annulée"
        log.warning("Retour de banque sans autorisation : %s", msg)
        return RedirectResponse(f"/parametres/connexions?erreur={quote(msg)}", status_code=303)
    log.info("Retour de banque reçu")
    try:
        c = sync.finish(db, code, state)
    except (sync.SyncError, EnableBankingError) as e:
        db.rollback()
        log.warning("Autorisation non finalisée : %s", e)
        return RedirectResponse(f"/parametres/connexions?erreur={quote(str(e))}", status_code=303)
    except Exception as e:  # noqa: BLE001 - erreur imprévue : on la journalise et on l'affiche
        db.rollback()
        log.exception("Autorisation non finalisée (erreur imprévue)")
        return RedirectResponse(f"/parametres/connexions?erreur={quote(f'erreur imprévue ({type(e).__name__})')}", status_code=303)
    log.info("Connexion %s autorisée (%d compte(s))", c.label, len(sync.public_accounts(c)))
    # Première synchro tout de suite pour les comptes déjà associés : l'historique complet
    # n'est souvent disponible que dans l'heure qui suit l'autorisation.
    try:
        sync.sync_connection(db, c)
    except Exception:  # noqa: BLE001 - l'utilisateur pourra relancer depuis la page
        db.rollback()
        log.exception("Première synchro impossible")
    return RedirectResponse(f"/parametres/connexions?ok={c.id}", status_code=303)


@router.post("/{connection_id}/accounts", response_model=ConnectionOut, dependencies=auth)
def map_accounts(connection_id: int, body: MappingIn, db: Session = Depends(get_db)):
    c = _get(db, connection_id)
    try:
        sync.map_accounts(db, c, body.mapping)
    except sync.SyncError as e:
        raise _fail(e) from e
    return _out(c)


@router.post("/sync-stale", dependencies=auth)
def sync_stale(max_age_minutes: int = Query(default=60, ge=30, le=24 * 60), db: Session = Depends(get_db)) -> dict:
    """À l'ouverture de l'appli : synchronise les connexions pas synchronisées depuis `max_age_minutes`."""
    return sync.sync_stale(db, timedelta(minutes=max_age_minutes))


@router.post("/{connection_id}/sync", response_model=list[SyncResultOut], dependencies=auth)
def sync_now(connection_id: int, db: Session = Depends(get_db)):
    c = _get(db, connection_id)
    try:
        results = sync.sync_connection(db, c)
    except (sync.SyncError, EnableBankingError) as e:
        db.rollback()
        sync.record_error(db, connection_id, e)
        raise _fail(e) from e
    return [
        SyncResultOut(account_name=r.account_name, imported=r.imported, skipped=r.skipped, categorized=r.categorized, reconciled=r.reconciled)
        for r in results
    ]


@router.delete("/{connection_id}", dependencies=[Depends(require_confirmation)])
def delete(connection_id: int, db: Session = Depends(get_db)) -> dict:
    """Supprime la connexion (les comptes et opérations déjà importés sont conservés)."""
    sync.disconnect(db, _get(db, connection_id))
    return {"ok": True}
