from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class EmployeeLoginUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str | None = Field(default=None, min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def password_bytes(cls, value):
        if value is not None and len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes")
        return value


class OwnLoginUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    current_password: str = Field(min_length=1, max_length=72)

    @field_validator("current_password")
    @classmethod
    def password_bytes(cls, value):
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes")
        return value
