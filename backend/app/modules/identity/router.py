from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.modules.identity.dependencies import get_csrf_user, get_current_user
from app.modules.identity.models import UserSession
from app.modules.identity.schemas import LoginRequest, LoginResponse, UserContextResponse
from app.modules.identity.service import AuthenticatedUser, authenticate_local_user
from app.platform.database import get_db
from app.platform.security.tokens import token_digest

router = APIRouter(prefix="/auth", tags=["authentication"])


def _user_response(user: AuthenticatedUser) -> UserContextResponse:
    return UserContextResponse(
        id=user.id,
        warehouse_id=user.warehouse_id,
        warehouse_code=user.warehouse_code,
        username=user.username,
        display_name=user.display_name,
        roles=sorted(user.roles),
    )


@router.post("/login")
def login(
    payload: LoginRequest,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LoginResponse:
    if settings.auth_provider != "local":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local authentication is disabled",
        )
    created = authenticate_local_user(
        session,
        username=payload.username,
        password=payload.password,
        warehouse_code=payload.warehouse_code,
        ttl_hours=settings.session_ttl_hours,
    )
    if created is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    max_age = settings.session_ttl_hours * 60 * 60
    response.set_cookie(
        settings.session_cookie_name,
        created.session_token,
        max_age=max_age,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict",
        path="/",
    )
    return LoginResponse(user=_user_response(created.user), csrf_token=created.csrf_token)


@router.get("/me")
def me(user: Annotated[AuthenticatedUser, Depends(get_current_user)]) -> UserContextResponse:
    return _user_response(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    user: Annotated[AuthenticatedUser, Depends(get_csrf_user)],
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    del user
    raw_token = request.cookies.get(settings.session_cookie_name)
    if raw_token:
        session.execute(
            delete(UserSession).where(UserSession.token_hash == token_digest(raw_token))
        )
        session.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")
