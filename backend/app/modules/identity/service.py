from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.enums import Role
from app.modules.identity.models import RoleAssignment, User, UserSession
from app.modules.warehouses.models import Warehouse
from app.platform.database.base import utc_now
from app.platform.security.tokens import new_opaque_token, token_digest, verify_password


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    id: UUID
    warehouse_id: UUID
    warehouse_code: str
    username: str
    display_name: str
    roles: frozenset[Role]

    def has_any_role(self, allowed_roles: frozenset[Role]) -> bool:
        return bool(self.roles & allowed_roles)


@dataclass(frozen=True, slots=True)
class CreatedSession:
    user: AuthenticatedUser
    session_token: str
    csrf_token: str


def _to_authenticated_user(
    user: User, warehouse_code: str, roles: list[Role]
) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=user.id,
        warehouse_id=user.warehouse_id,
        warehouse_code=warehouse_code,
        username=user.username,
        display_name=user.display_name,
        roles=frozenset(roles),
    )


def authenticate_local_user(
    session: Session,
    *,
    username: str,
    password: str,
    warehouse_code: str,
    ttl_hours: int,
) -> CreatedSession | None:
    row = session.execute(
        select(User, Warehouse.code)
        .join(Warehouse, Warehouse.id == User.warehouse_id)
        .where(
            Warehouse.code == warehouse_code.upper(),
            User.username == username.lower(),
            User.is_active.is_(True),
        )
    ).one_or_none()
    if row is None:
        return None

    user, resolved_warehouse_code = row
    if user.password_hash is None or not verify_password(password, user.password_hash):
        return None

    roles = list(
        session.scalars(
            select(RoleAssignment.role).where(RoleAssignment.user_id == user.id)
        ).all()
    )
    session_token = new_opaque_token()
    csrf_token = new_opaque_token()
    session.add(
        UserSession(
            warehouse_id=user.warehouse_id,
            user_id=user.id,
            token_hash=token_digest(session_token),
            csrf_hash=token_digest(csrf_token),
            expires_at=utc_now() + timedelta(hours=ttl_hours),
        )
    )
    session.execute(delete(UserSession).where(UserSession.expires_at < utc_now()))
    session.commit()

    return CreatedSession(
        user=_to_authenticated_user(user, resolved_warehouse_code, roles),
        session_token=session_token,
        csrf_token=csrf_token,
    )


def resolve_session(
    session: Session, raw_token: str
) -> tuple[AuthenticatedUser, UserSession] | None:
    row = session.execute(
        select(UserSession, User, Warehouse.code)
        .join(User, User.id == UserSession.user_id)
        .join(Warehouse, Warehouse.id == User.warehouse_id)
        .where(
            UserSession.token_hash == token_digest(raw_token),
            UserSession.expires_at > utc_now(),
            User.is_active.is_(True),
        )
    ).one_or_none()
    if row is None:
        return None

    user_session, user, warehouse_code = row
    roles = list(
        session.scalars(
            select(RoleAssignment.role).where(RoleAssignment.user_id == user.id)
        ).all()
    )
    return _to_authenticated_user(user, warehouse_code, roles), user_session
