from datetime import datetime

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import DeviceToken, SecurityEvent
from app.schemas import LoginIn
from app.security import (
    KIND_APP,
    KIND_BROWSER,
    current_credential,
    describe_user_agent,
    device_from_header,
    hash_token,
    lockout_seconds,
    log_event,
    new_device_token,
    new_session_token,
    password_is_hashed,
    require_auth,
    session_cookie_name,
    session_from_request,
    verify_password,
)
from app.services.backup_status import backup_status

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        session_cookie_name(),
        token,
        max_age=s.session_max_days * 24 * 3600,
        path="/",
        httponly=True,
        samesite="strict",
        secure=s.cookie_secure,
    )


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    verify_password(db, body.password, "connexion navigateur")
    token = new_session_token()
    name = describe_user_agent(request.headers.get("user-agent"))
    db.add(DeviceToken(name=name, token_hash=hash_token(token), kind=KIND_BROWSER))
    log_event(db, "connexion", name)
    db.commit()
    _set_cookie(response, token)
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    """Ferme la session côté serveur : une copie du cookie ne marche plus."""
    session = session_from_request(db, request)
    if session is not None:
        db.delete(session)
        db.commit()
    s = get_settings()
    response.delete_cookie(session_cookie_name(), path="/", secure=s.cookie_secure, httponly=True, samesite="strict")
    return {"ok": True}


@router.get("/me")
def me(user: str = Depends(require_auth)) -> dict:
    return {"user": user}


# --- Appareils (appli Android, widgets) et sessions du navigateur --------------------------------


class DeviceLoginIn(BaseModel):
    password: str
    name: str = Field(default="Android", min_length=1, max_length=100)


class DeviceOut(BaseModel):
    id: int
    name: str
    kind: str
    created_at: datetime
    last_used_at: datetime | None
    current: bool


@router.post("/device")
def device_login(body: DeviceLoginIn, db: Session = Depends(get_db)) -> dict:
    """Connexion de l'appli : renvoie un jeton d'appareil (à garder sur le téléphone, montré une seule fois)."""
    verify_password(db, body.password, f"appli « {body.name.strip()[:60]} »")
    token = new_device_token()
    db.add(DeviceToken(name=body.name.strip(), token_hash=hash_token(token), kind=KIND_APP))
    log_event(db, "appareil_ajoute", body.name.strip())
    db.commit()
    return {"token": token}


@router.post("/device/logout")
def device_logout(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict:
    """Déconnexion de l'appli : le jeton utilisé est révoqué."""
    device = device_from_header(db, authorization)
    if device is not None:
        db.delete(device)
        db.commit()
    return {"ok": True}


@router.get("/devices", response_model=list[DeviceOut], dependencies=[Depends(require_auth)])
def list_devices(request: Request, db: Session = Depends(get_db)):
    me_ = current_credential(db, request)
    rows = db.scalars(select(DeviceToken).order_by(DeviceToken.kind, DeviceToken.created_at.desc())).all()
    return [
        DeviceOut(id=r.id, name=r.name, kind=r.kind, created_at=r.created_at, last_used_at=r.last_used_at, current=me_ is not None and r.id == me_.id)
        for r in rows
    ]


@router.delete("/devices/{device_id}", dependencies=[Depends(require_auth)])
def revoke_device(device_id: int, db: Session = Depends(get_db)) -> dict:
    device = db.get(DeviceToken, device_id)
    if device is not None:  # déjà révoqué ou expiré : rien à faire
        log_event(db, "appareil_revoque", f"{device.name} ({device.kind})")
        db.delete(device)
        db.commit()
    return {"ok": True}


@router.post("/logout-others", dependencies=[Depends(require_auth)])
def logout_others(request: Request, db: Session = Depends(get_db)) -> dict:
    """Ferme toutes les autres sessions et révoque tous les autres appareils (garde celui-ci)."""
    me_ = current_credential(db, request)
    stmt = delete(DeviceToken)
    if me_ is not None:
        stmt = stmt.where(DeviceToken.id != me_.id)
    n = db.execute(stmt).rowcount
    log_event(db, "deconnexion_globale", f"{n} session(s) / appareil(s)")
    db.commit()
    return {"revoked": n}


# --- Tableau de bord sécurité (Paramètres) ------------------------------------------------------


class EventOut(BaseModel):
    created_at: datetime
    kind: str
    detail: str | None


class SecurityOut(BaseModel):
    password_hashed: bool
    cookie_secure: bool
    lockout_seconds: int
    backup: dict
    events: list[EventOut]


@router.get("/security", response_model=SecurityOut, dependencies=[Depends(require_auth)])
def security_overview(db: Session = Depends(get_db)):
    events = db.scalars(select(SecurityEvent).order_by(SecurityEvent.created_at.desc(), SecurityEvent.id.desc()).limit(60)).all()
    return SecurityOut(
        password_hashed=password_is_hashed(),
        cookie_secure=get_settings().cookie_secure,
        lockout_seconds=lockout_seconds(db),
        backup=backup_status(db),
        events=[EventOut(created_at=e.created_at, kind=e.kind, detail=e.detail) for e in events],
    )
