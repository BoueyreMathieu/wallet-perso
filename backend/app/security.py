"""Authentification (un seul utilisateur) et chiffrement des secrets."""

import hmac
import json
import time

from cryptography.fernet import Fernet
from fastapi import Cookie, HTTPException, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import get_settings

SESSION_COOKIE = "wallet_session"


def check_password(candidate: str) -> bool:
    ok = hmac.compare_digest(candidate.encode(), get_settings().app_password.encode())
    if not ok:
        time.sleep(0.5)  # ralentit les essais en série
    return ok


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="wallet-session")


def create_session_token() -> str:
    return _serializer().dumps({"user": "owner"})


def session_max_age_seconds() -> int:
    return get_settings().session_max_age_days * 24 * 3600


def require_auth(wallet_session: str | None = Cookie(default=None)) -> str:
    """Dépendance FastAPI : refuse la requête si la session est absente ou invalide."""
    if not wallet_session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Non connecté")
    try:
        data = _serializer().loads(wallet_session, max_age=session_max_age_seconds())
    except (BadSignature, SignatureExpired):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session invalide ou expirée") from None
    return data["user"]


def _fernet() -> Fernet:
    return Fernet(get_settings().encryption_key.encode())


def encrypt_secrets(data: dict) -> str:
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt_secrets(token: str) -> dict:
    return json.loads(_fernet().decrypt(token.encode()))
