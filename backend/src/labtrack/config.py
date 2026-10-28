from functools import lru_cache
from typing import Literal

from pydantic import PostgresDsn, RedisDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Secrets come from the environment (Docker secrets in production)."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore", frozen=True)

    environment: Literal["dev", "test", "staging", "production"] = "dev"
    # Runtime role: labtrack_app (RLS enforced, no access to secret columns).
    database_url: PostgresDsn
    redis_url: RedisDsn = RedisDsn("redis://valkey:6379/0")
    sentry_dsn: SecretStr | None = None
    api_prefix: str = "/api/v1"

    @field_validator("sentry_dsn", mode="before")
    @classmethod
    def _empty_is_unset(cls, value: object) -> object:
        # Compose passes `SENTRY_DSN=` when unset; that must disable Sentry, not init it.
        return None if value == "" else value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # values come from the environment
