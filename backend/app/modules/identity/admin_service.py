from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.enums import Role
from app.domain.errors import ConflictError, NotFoundError
from app.modules.audit.service import record_audit
from app.modules.identity.models import RoleAssignment, User, UserSession
from app.modules.identity.schemas import (
    AdminUserResponse,
    CreateUserRequest,
    UpdateUserRequest,
)
from app.modules.identity.service import AuthenticatedUser
from app.platform.security.tokens import hash_password


class UserAdministrationService:
    def __init__(self, session: Session, user: AuthenticatedUser) -> None:
        self.session = session
        self.user = user

    def list_users(self) -> list[AdminUserResponse]:
        users = self.session.scalars(
            select(User)
            .where(User.warehouse_id == self.user.warehouse_id)
            .order_by(User.display_name)
        ).all()
        roles = self.session.execute(
            select(RoleAssignment.user_id, RoleAssignment.role).where(
                RoleAssignment.warehouse_id == self.user.warehouse_id
            )
        ).all()
        roles_by_user: dict[UUID, list[Role]] = {}
        for user_id, role in roles:
            roles_by_user.setdefault(user_id, []).append(role)
        return [
            self._response(account, roles_by_user.get(account.id, []))
            for account in users
        ]

    def create(self, payload: CreateUserRequest) -> AdminUserResponse:
        username = payload.username.strip().lower()
        if self.session.scalar(
            select(User.id).where(
                User.warehouse_id == self.user.warehouse_id,
                User.username == username,
            )
        ):
            raise ConflictError("Username already exists")
        roles = sorted(set(payload.roles))
        account = User(
            warehouse_id=self.user.warehouse_id,
            username=username,
            display_name=payload.display_name.strip(),
            password_hash=hash_password(payload.password) if payload.password else None,
            is_active=True,
        )
        self.session.add(account)
        self.session.flush()
        self.session.add_all(
            RoleAssignment(
                warehouse_id=self.user.warehouse_id,
                user_id=account.id,
                role=role,
            )
            for role in roles
        )
        record_audit(
            self.session,
            warehouse_id=self.user.warehouse_id,
            actor_user_id=self.user.id,
            action="identity.user_created",
            entity_type="user",
            entity_id=account.id,
            changes={
                "username": account.username,
                "roles": [role.value for role in roles],
                "local_password": payload.password is not None,
            },
        )
        self.session.commit()
        return self._response(account, roles)

    def update(self, user_id: UUID, payload: UpdateUserRequest) -> AdminUserResponse:
        account = self.session.scalar(
            select(User)
            .where(
                User.id == user_id,
                User.warehouse_id == self.user.warehouse_id,
            )
            .with_for_update()
        )
        if account is None:
            raise NotFoundError("User not found")
        roles = sorted(set(payload.roles))
        if account.id == self.user.id and (
            not payload.is_active or Role.SYSTEM_ADMINISTRATOR not in roles
        ):
            raise ConflictError("You cannot disable your own administrator access")
        previous_roles = self.session.scalars(
            select(RoleAssignment.role).where(RoleAssignment.user_id == account.id)
        ).all()
        changes = {
            "display_name": [account.display_name, payload.display_name.strip()],
            "is_active": [account.is_active, payload.is_active],
            "roles": [
                [role.value for role in sorted(previous_roles)],
                [role.value for role in roles],
            ],
            "password_reset": payload.password is not None,
        }
        account.display_name = payload.display_name.strip()
        account.is_active = payload.is_active
        if payload.password:
            account.password_hash = hash_password(payload.password)
        self.session.execute(
            delete(RoleAssignment).where(RoleAssignment.user_id == account.id)
        )
        self.session.add_all(
            RoleAssignment(
                warehouse_id=self.user.warehouse_id,
                user_id=account.id,
                role=role,
            )
            for role in roles
        )
        self.session.execute(delete(UserSession).where(UserSession.user_id == account.id))
        record_audit(
            self.session,
            warehouse_id=self.user.warehouse_id,
            actor_user_id=self.user.id,
            action="identity.user_updated",
            entity_type="user",
            entity_id=account.id,
            changes=changes,
            reason=payload.reason,
        )
        self.session.commit()
        return self._response(account, roles)

    @staticmethod
    def _response(account: User, roles: list[Role]) -> AdminUserResponse:
        return AdminUserResponse(
            id=account.id,
            username=account.username,
            display_name=account.display_name,
            is_active=account.is_active,
            roles=sorted(roles),
            created_at=account.created_at.isoformat(),
        )