"""Authentification (un seul utilisateur), sessions révocables, journal de sécurité et chiffrement des secrets.

- Navigateur : cookie HttpOnly contenant un jeton aléatoire « wps_… » ; la session existe en base (table
  device_token, type « navigateur ») et peut être révoquée à tout moment.
- Appli Android / widgets : jeton « wpd_… » envoyé en « Authorization: Bearer » (type « app »).
- Seules les empreintes SHA-256 des jetons sont stockées.
- Mot de passe : blocage progressif après plusieurs échecs (persistant en base), essais traités un par un.
- Actions destructrices : mot de passe redemandé (en-tête X-Confirm-Password).
"""

import hashlib
import hmac
import json
import logging
import math
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

from cryptography.fernet import Fernet
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import passwords
from app.config import get_settings
from app.db import get_db

log = logging.getLogger("wallet.securite")

SESSION_PREFIX = "wps_"
DEVICE_PREFIX = "wpd_"
KIND_BROWSER = "navigateur"
KIND_APP = "app"

# Événements qui remettent le compteur d'échecs à zéro.
SUCCESS_KINDS = ("connexion", "appareil_ajoute", "confirmation")
FAIL_KIND = "echec_mdp"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def session_cookie_name() -> str:
    # Le préfixe __Host- impose HTTPS, le chemin « / » et l'absence de domaine : cookie impossible à injecter
    # depuis un autre sous-domaine.
    return "__Host-wallet_session" if get_settings().cookie_secure else "wallet_session"


# --- Journal de sécurité ------------------------------------------------------------------------


def log_event(db: Session, kind: str, detail: str | None = None) -> None:
    from app.models import SecurityEvent  # import local : models importe la config

    db.add(SecurityEvent(kind=kind, detail=(detail or "")[:200] or None, created_at=utcnow()))
    log.info("Sécurité : %s%s", kind, f" ({detail})" if detail else "")


# --- Mot de passe -------------------------------------------------------------------------------

_password_lock = threading.Lock()  # un essai à la fois : impossible d'en lancer des dizaines en parallèle


def _password_ok(candidate: str) -> bool:
    s = get_settings()
    if s.app_password_hash:
        return passwords.verify_password(candidate, s.app_password_hash)
    if s.app_password and candidate:
        return hmac.compare_digest(candidate.encode(), s.app_password.encode())
    return False


def password_is_hashed() -> bool:
    return bool(get_settings().app_password_hash)


def lockout_seconds(db: Session) -> int:
    """Secondes avant le prochain essai autorisé (0 = pas de blocage).

    Échecs comptés depuis la dernière réussite (sur 24 h au plus). À partir du seuil, chaque échec bloque
    1 min, puis 2, 4, 8… jusqu'à 60 min."""
    from app.models import SecurityEvent

    now = utcnow()
    last_ok = db.scalar(select(func.max(SecurityEvent.created_at)).where(SecurityEvent.kind.in_(SUCCESS_KINDS)))
    since = max(now - timedelta(hours=24), _aware(last_ok)) if last_ok else now - timedelta(hours=24)
    fails = db.scalars(
        select(SecurityEvent.created_at)
        .where(SecurityEvent.kind == FAIL_KIND, SecurityEvent.created_at > since)
        .order_by(SecurityEvent.created_at.desc())
    ).all()
    threshold = max(get_settings().login_max_failures, 1)
    if len(fails) < threshold:
        return 0
    minutes = min(60, 2 ** (len(fails) - threshold))
    until = _aware(fails[0]) + timedelta(minutes=minutes)
    return max(0, math.ceil((until - now).total_seconds()))


def verify_password(db: Session, candidate: str, context: str, fail_status: int = status.HTTP_401_UNAUTHORIZED) -> None:
    """Vérifie le mot de passe ou lève une erreur (401/403 si faux, 429 si trop d'essais récents)."""
    with _password_lock:
        wait = lockout_seconds(db)
        if wait:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Trop d'essais de mot de passe : réessaie dans {math.ceil(wait / 60)} min.",
                headers={"Retry-After": str(wait)},
            )
        if _password_ok(candidate):
            return
        time.sleep(1)
        log_event(db, FAIL_KIND, context)
        db.commit()
    raise HTTPException(fail_status, "Mot de passe incorrect")


def password_fingerprint() -> str:
    """Empreinte (HMAC) de la configuration du mot de passe : sert à détecter un changement au démarrage."""
    s = get_settings()
    material = s.app_password_hash or s.app_password
    return hmac.new(s.secret_key.encode(), f"wallet-password|{material}".encode(), hashlib.sha256).hexdigest()[:16]


# --- Jetons (sessions du navigateur, appareils) -------------------------------------------------


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_device_token() -> str:
    return DEVICE_PREFIX + secrets.token_urlsafe(32)


def new_session_token() -> str:
    return SESSION_PREFIX + secrets.token_urlsafe(32)


def _expired(row, now: datetime) -> bool:
    s = get_settings()
    last = _aware(row.last_used_at or row.created_at)
    if row.kind == KIND_BROWSER:
        return now - last > timedelta(days=s.session_idle_days) or now - _aware(row.created_at) > timedelta(days=s.session_max_days)
    return now - last > timedelta(days=s.device_idle_days)


def _lookup(db: Session, token: str | None, kind: str):
    from app.models import DeviceToken

    prefix = SESSION_PREFIX if kind == KIND_BROWSER else DEVICE_PREFIX
    if not token or not token.startswith(prefix):
        return None
    row = db.scalar(select(DeviceToken).where(DeviceToken.token_hash == hash_token(token), DeviceToken.kind == kind))
    if row is None:
        return None
    now = utcnow()
    if _expired(row, now):
        db.delete(row)
        db.commit()
        return None
    if row.last_used_at is None or now - _aware(row.last_used_at) > timedelta(hours=1):  # pas une écriture à chaque requête
        row.last_used_at = now
        db.commit()
    return row


def _bearer(authorization: str | None) -> str | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return authorization[7:].strip()


def device_from_header(db: Session, authorization: str | None):
    """L'appareil correspondant à « Authorization: Bearer wpd_… », ou None."""
    return _lookup(db, _bearer(authorization), KIND_APP)


def session_from_request(db: Session, request: Request):
    """La session du navigateur correspondant au cookie, ou None."""
    return _lookup(db, request.cookies.get(session_cookie_name()), KIND_BROWSER)


def current_credential(db: Session, request: Request):
    """La session ou l'appareil qui fait la requête (pour « cet appareil » et la déconnexion)."""
    authorization = request.headers.get("authorization")
    if authorization:
        return device_from_header(db, authorization)
    return session_from_request(db, request)


def require_auth(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> str:
    """Dépendance FastAPI : session du navigateur (cookie) OU jeton d'appareil (appli, widgets)."""
    if authorization:
        if device_from_header(db, authorization) is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Appareil non autorisé (jeton invalide, expiré ou révoqué)")
        return "owner"
    if session_from_request(db, request) is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Non connecté (ou session expirée)")
    return "owner"


def require_confirmation(
    request: Request,
    x_confirm_password: str | None = Header(default=None),
    db: Session = Depends(get_db),
    _: str = Depends(require_auth),
) -> None:
    """Actions destructrices : le mot de passe est redemandé, même avec une session valide.

    Un cookie ou un jeton volé ne suffit donc pas pour tout effacer."""
    if not x_confirm_password:
        raise HTTPException(status.HTTP_428_PRECONDITION_REQUIRED, "Confirme cette action avec ton mot de passe.")
    verify_password(db, unquote(x_confirm_password), "confirmation", fail_status=status.HTTP_403_FORBIDDEN)
    log_event(db, "confirmation", f"{request.method} {request.url.path}")
    db.commit()


def describe_user_agent(ua: str | None) -> str:
    """« Chrome · Windows » : juste de quoi reconnaître ses sessions dans la liste."""
    ua = ua or ""
    browser = next(
        (name for key, name in (("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"), ("Chrome/", "Chrome"), ("Safari/", "Safari")) if key in ua),
        "Navigateur",
    )
    system = next(
        (name for key, name in (("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"), ("Windows", "Windows"), ("Mac OS", "Mac"), ("Linux", "Linux")) if key in ua),
        "",
    )
    return f"{browser} · {system}" if system else browser


def purge_expired(db: Session) -> int:
    """Supprime sessions/appareils expirés et vieux événements (au démarrage)."""
    from app.models import DeviceToken, SecurityEvent

    now = utcnow()
    expired = [row for row in db.scalars(select(DeviceToken)) if _expired(row, now)]
    for row in expired:
        db.delete(row)
    db.execute(delete(SecurityEvent).where(SecurityEvent.created_at < now - timedelta(days=365)))
    return len(expired)


def check_password_change(db: Session) -> None:
    """Au démarrage : si le mot de passe a changé, toutes les sessions du navigateur sont fermées."""
    from app.models import AppMeta, DeviceToken

    fp = password_fingerprint()
    meta = db.get(AppMeta, "password_fp")
    if meta is None:
        db.add(AppMeta(key="password_fp", value=fp))
    elif meta.value != fp:
        n = db.execute(delete(DeviceToken).where(DeviceToken.kind == KIND_BROWSER)).rowcount
        meta.value = fp
        log_event(db, "mdp_change", f"{n} session(s) du navigateur fermée(s) ; vérifie la liste des appareils")
    if not password_is_hashed():
        log.warning("APP_PASSWORD est en clair dans .env : remplace-le par APP_PASSWORD_HASH (python -m app.tools.hash_password)")


# --- Chiffrement des secrets bancaires ---------------------------------------------------------


def _fernet() -> Fernet:
    return Fernet(get_settings().encryption_key.encode())


def encrypt_secrets(data: dict) -> str:
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt_secrets(token: str) -> dict:
    return json.loads(_fernet().decrypt(token.encode()))
