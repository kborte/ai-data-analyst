from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class User(BaseModel):
    user_id: UUID
    email: str
    display_name: str
    created_at: datetime
