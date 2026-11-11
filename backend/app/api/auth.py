from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.config import get_settings
from app.schemas import LoginIn
from app.security import (
    SESSION_COOKIE,
    check_password,
    create_session_token,
    require_auth,
    session_max_age_seconds,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginIn, response: Response) -> dict:
    if not check_password(body.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Mot de passe incorrect")
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(),
        max_age=session_max_age_seconds(),
        httponly=True,
        samesite="strict",
        secure=get_settings().cookie_secure,
    )
    return {"ok": True}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@router.get("/me")
def me(user: str = Depends(require_auth)) -> dict:
    return {"user": user}
