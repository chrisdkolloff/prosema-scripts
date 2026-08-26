"""Application settings loaded from the environment / `.env`."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    session_secret: str
    entra_tenant_id: str
    entra_client_id: str
    entra_client_secret: str
    entra_redirect_uri: str
    entra_group_users_id: str
    entra_group_admins_id: str
    environment: Literal["local", "production"] = "local"
    # Shared weclapp tenant (subdomain). Per-user API tokens live in Postgres,
    # encrypted with token_encryption_key — never a shared app-level token.
    weclapp_tenant: str
    token_encryption_key: str

    @field_validator("environment", mode="before")
    @classmethod
    def empty_environment_is_local(cls, value: object) -> object:
        if value in (None, ""):
            return "local"
        return value


settings = Settings()
