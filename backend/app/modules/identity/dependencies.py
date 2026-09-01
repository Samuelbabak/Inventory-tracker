from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.domain.enums import Role
from app.modules.identity.service import AuthenticatedUser, resolve_session
from app.platform.database import get_db
from app.platform.security.tokens import token_matches


def get_current_user(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthenticatedUser:
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )

    resolved = resolve_session(session, raw_token)
    if resolved is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    return resolved[0]


def get_csrf_user(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> AuthenticatedUser:
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )

    resolved = resolve_session(session, raw_token)
    if resolved is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    user, user_session = resolved
    if csrf_token is None or not token_matches(csrf_token, user_session.csrf_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")
    return user


def require_roles(
    *roles: Role, csrf: bool = False
) -> Callable[..., AuthenticatedUser]:
    allowed_roles = frozenset(roles)
    source = get_csrf_user if csrf else get_current_user

    def authorize(user: Annotated[AuthenticatedUser, Depends(source)]) -> AuthenticatedUser:
        if not user.has_any_role(allowed_roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return authorize
