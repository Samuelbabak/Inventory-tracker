from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import Role
from app.modules.identity.dependencies import get_current_user
from app.modules.identity.service import AuthenticatedUser
from app.modules.recipients.models import EmployeeRecipient
from app.modules.recipients.schemas import RecipientResponse
from app.platform.database import get_db

router = APIRouter(prefix="/recipients", tags=["recipients"])


@router.get("")
def list_recipients(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
) -> list[RecipientResponse]:
    query = (
        select(EmployeeRecipient)
        .where(
            EmployeeRecipient.warehouse_id == user.warehouse_id,
            EmployeeRecipient.is_active.is_(True),
        )
        .order_by(EmployeeRecipient.display_name)
    )
    directory_roles = {
        Role.FOREMAN,
        Role.WAREHOUSE_WORKER,
        Role.INVENTORY_MANAGER,
        Role.SYSTEM_ADMINISTRATOR,
    }
    if not user.roles.intersection(directory_roles):
        query = query.where(EmployeeRecipient.linked_user_id == user.id)
    recipients = session.scalars(query).all()
    return [
        RecipientResponse(
            id=recipient.id,
            employee_number=recipient.employee_number,
            display_name=recipient.display_name,
        )
        for recipient in recipients
    ]
