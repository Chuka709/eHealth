from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Secrets come from the environment (Docker secrets in production)."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore", frozen=True)

    # Required: a missing ENVIRONMENT must not silently mean "dev" (ephemeral JWT key, docs).
    environment: Literal["dev", "test", "staging", "production"]
    # Runtime role: labtrack_app (RLS enforced, no access to secret columns).
    database_url: PostgresDsn
    redis_url: RedisDsn = RedisDsn("redis://valkey:6379/0")
    sentry_dsn: SecretStr | None = None
    api_prefix: str = "/api/v1"

    # Auth (docs/04 §1). The ES256 key is required outside dev/test (auth/tokens.py).
    jwt_private_key: SecretStr | None = None
    jwt_kid: str = "k1"
    jwt_issuer: str = "labtrack"
    jwt_audience: str = "labtrack-api"
    access_token_ttl_seconds: int = 15 * 60
    refresh_token_ttl_days: int = 60
    # Requests per minute per client address (api/ratelimit.py).
    rate_login_per_minute: int = 20
    rate_refresh_per_minute: int = 60
    rate_activate_per_minute: int = 10

    # Field encryption (keys.py): dev/test KEK; production uses OpenBao transit.
    dev_kek: SecretStr | None = Field(default=None, validation_alias="LABTRACK_DEV_KEK")
    # Pepper for the national-id identity check (0004: bcrypt in the database, 16-60 chars).
    identity_pepper: SecretStr | None = Field(default=None, min_length=16, max_length=60)

    # Admin API (docs/04 §1 "Супер админ"): role labtrack_admin, never the app or owner role.
    admin_database_url: PostgresDsn | None = None

    @field_validator(
        "sentry_dsn",
        "jwt_private_key",
        "dev_kek",
        "identity_pepper",
        "admin_database_url",
        mode="before",
    )
    @classmethod
    def _empty_is_unset(cls, value: object) -> object:
        # Compose passes `SENTRY_DSN=` when unset; that must disable Sentry, not init it.
        return None if value == "" else value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # values come from the environment
