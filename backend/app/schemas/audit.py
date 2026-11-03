import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.base import ApiModel


class AuditLogRead(ApiModel):

    id: uuid.UUID
    tenant_id: uuid.UUID | None
    requester: str
    action: str
    request: str
    method: str
    path: str
    status_code: int
    outcome: str
    response: str
    created_at: datetime | None


class AuditLogListQuery(BaseModel):
    outcome: str | None = Field(default=None, max_length=20)
    limit: int = Field(default=200, ge=1, le=500)
