from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr


class Settings(BaseSettings):
    hrms_base_domain: str = "hrms.techtutor.co.ke"
    hrms_domain_target: str = "hrms.techtutor.co.ke"
    hrms_central_hosts: str = "localhost,127.0.0.1,::1,test,backend"
    hrms_workspace_hosts: str = ""
    domain_tls_secret: str = ""
    google_client_id: str = ""
    google_cookie_secure: bool = False
    brevo_api_key: SecretStr = SecretStr("")
    brevo_sender_email: str = ""
    brevo_sender_name: str = "HRMS"
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://hrms:hrms@localhost:5433/hrms"
    redis_url: str = "redis://localhost:6379/0"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    jwt_secret: str = "dev-insecure-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 10
    refresh_token_expire_minutes: int = 30
    trial_days: int = 14
    platform_admin_email: str = "owner@example.com"
    platform_admin_password: str = "ChangeMe123!"
    platform_admin_name: str = "Platform Owner"


@lru_cache
def get_settings() -> Settings:
    return Settings()
