from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_serializer

from app.core.datetimes import utc_iso


class ApiModel(BaseModel):
    """Read models that expose clock times. Naive DB values are treated as UTC."""

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at", "updated_at", "trial_ends_at", "checked_in_at", "checked_out_at", check_fields=False)
    def serialize_clock(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return utc_iso(value)
