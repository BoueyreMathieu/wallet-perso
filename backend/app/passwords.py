"""Empreinte du mot de passe de l'appli (scrypt, inclus dans Python : aucune dépendance en plus).

Format stocké dans APP_PASSWORD_HASH : « scrypt:N:r:p:sel:empreinte » (sel et empreinte en base64 URL, sans « $ »
pour que Docker Compose ne tente pas d'interpréter la valeur dans le fichier .env).
"""

import base64
import hashlib
import hmac
import os

N, R, P = 2**15, 8, 1
_MAXMEM = 64 * 1024 * 1024


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, maxmem=_MAXMEM, dklen=32)
    return f"scrypt:{N}:{R}:{P}:{_b64(salt)}:{_b64(digest)}"


def is_valid_hash(stored: str) -> bool:
    parts = stored.split(":")
    return len(parts) == 6 and parts[0] == "scrypt" and all(p.isdigit() for p in parts[1:4])


def verify_password(password: str, stored: str) -> bool:
    if not password or not is_valid_hash(stored):
        return False
    _, n, r, p, salt, digest = stored.split(":")
    try:
        expected = _unb64(digest)
        candidate = hashlib.scrypt(
            password.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), maxmem=_MAXMEM, dklen=len(expected)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, expected)
