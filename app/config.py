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
    assistant_enabled: bool = False
    assistant_provider: Literal["azure", "openai_compatible"] = "azure"
    azure_openai_endpoint: str | None = None
    azure_openai_deployment: str | None = None
    azure_openai_api_version: str = "2024-10-21"
    assistant_base_url: str | None = None
    assistant_model: str | None = None
    assistant_timeout_seconds: int = 20
    assistant_max_tool_turns: int = 4
    assistant_strict_schema: bool = True

    @field_validator("environment", mode="before")
    @classmethod
    def empty_environment_is_local(cls, value: object) -> object:
        if value in (None, ""):
            return "local"
        return value


settings = Settings()
