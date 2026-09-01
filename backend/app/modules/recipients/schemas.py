from uuid import UUID

from pydantic import BaseModel


class RecipientResponse(BaseModel):
    id: UUID
    employee_number: str
    display_name: str
