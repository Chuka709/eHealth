from functools import lru_cache
from ipaddress import ip_network
from pathlib import Path
from typing import Literal

from pydantic import (
    Field,
    IPvAnyNetwork,
    PostgresDsn,
    RedisDsn,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from labtrack.openbao import OpenBaoConfig

SECRETS_DIR = "/run/secrets"


class Settings(BaseSettings):
    """Runtime configuration. Secrets come from the environment (Docker secrets in production)."""

    # Docker secrets (production overlay): /run/secrets/<field name>, e.g. jwt_private_key,
    # identity_pepper, s3_secret_key, openbao_secret_id - kept out of `docker inspect` and
    # /proc/*/environ. A variable of the same name wins over the file.
    model_config = SettingsConfigDict(
        env_file=None,
        extra="ignore",
        frozen=True,
        # `X=` (compose's `${X:-}`) is no value at all: a secret file or the default applies
        env_ignore_empty=True,
        secrets_dir=SECRETS_DIR if Path(SECRETS_DIR).is_dir() else None,
    )

    # Required: a missing ENVIRONMENT must not silently mean "dev" (ephemeral JWT key, docs).
    environment: Literal["dev", "test", "staging", "production"]
    # Runtime role: labtrack_app (RLS enforced, no access to secret columns).
    database_url: PostgresDsn
    redis_url: RedisDsn = RedisDsn("redis://valkey:6379/0")
    # the AI worker (B10): no remote control, no task results, its own unacked keys, its queue
    # not declared by it - all its Valkey user allows (infra/valkey/start.sh); it hands its
    # answer back through ai-output:*
    ai_worker_isolation: bool = False
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
    # Per account (api/ratelimit.py per_user): the app registers its push token on start-up,
    # foreground and refresh, a few times an hour at most.
    rate_push_token_per_minute: int = 10
    # Caregiver invitations per account (the database also caps lookups at 30 an hour).
    rate_caregiver_invite_per_minute: int = 10
    # Opening a share link with its PIN, per client address (the PIN itself locks after 5).
    rate_share_open_per_minute: int = 10
    # Share links made per account.
    rate_share_link_per_minute: int = 10
    # Summary PDFs and exports per account (each reads a whole profile).
    rate_export_per_minute: int = 6

    # Expo push (worker/push.py). Off until the Expo/FCM/APNs credentials exist (PROGRESS 2.8
    # decision (c)): the worker then sends nothing and marks nothing as sent.
    push_enabled: bool = False
    expo_access_token: SecretStr | None = None

    # Field encryption (keys.py): dev/test KEK; production uses OpenBao transit.
    dev_kek: SecretStr | None = Field(default=None, validation_alias="LABTRACK_DEV_KEK")
    # OpenBao (keys.py, user_keys.py; docs/04 §1): set, it is used in any environment - the
    # only key provider outside dev/test. AppRole per process (api: transit encrypt/decrypt;
    # maint-worker: destroy user keys only - infra/openbao/policies). https outside dev/test.
    openbao_addr: str | None = None
    openbao_role_id: str | None = None
    openbao_secret_id: SecretStr | None = None
    openbao_ca_cert: str | None = None  # a private CA's certificate file
    openbao_mount: str = "transit"
    # Pepper for the national-id identity check (0004: bcrypt in the database, 16-60 chars).
    identity_pepper: SecretStr | None = Field(default=None, min_length=16, max_length=60)

    # Admin API (docs/04 §1 "Супер админ"): role labtrack_admin, never the app or owner role.
    admin_database_url: PostgresDsn | None = None
    # Admin sign-in only (labtrack_admin_login): the admin API role cannot mint sessions.
    admin_login_database_url: PostgresDsn | None = None
    # Daily maintenance worker (labtrack_maint): account purge, auth_attempts retention.
    maint_database_url: PostgresDsn | None = None
    # push worker only (labtrack_push, migration 0028)
    push_database_url: PostgresDsn | None = None
    # Uploaded documents (Phase 3; Q49): private S3-compatible storage, files sealed with the
    # KEK envelope before they leave the API. Unset endpoint: the in-memory store (tests only).
    s3_endpoint_url: str | None = None
    s3_access_key: SecretStr | None = None
    s3_secret_key: SecretStr | None = None
    s3_bucket: str = "labtrack-documents"
    rate_upload_per_minute: int = 20
    rate_document_file_per_minute: int = 60
    rate_document_read_per_minute: int = 120
    rate_lab_review_per_minute: int = 60  # each change recomputes the whole row
    # virus scan (Phase 3.3): clamd over TCP; unset only in dev/test (documents go unscanned)
    clamd_host: str | None = None
    clamd_port: int = 3310
    # reading by AI (Phase 4.5, Q50): text PDFs of no known layout, names removed, with the
    # person's consent. The default worker only needs the switch and the daily cap; the key and
    # model live on the AI worker alone (rule 11).
    ai_extraction_enabled: bool = False
    ai_daily_documents: int = Field(default=20, ge=0, le=500)  # per user
    ai_daily_documents_total: int = Field(default=500, ge=0, le=100_000)  # all users
    anthropic_api_key: SecretStr | None = None
    extraction_model: str | None = None
    # Client networks allowed to reach /admin (also enforced by Caddy). Unset: private and
    # loopback ranges in dev/test, nobody elsewhere - production must list them explicitly.
    admin_allowed_networks: list[IPvAnyNetwork] | None = None
    rate_admin_login_per_minute: int = 10
    # Activation/reset link in the QR and SMS; the token goes in the fragment (never logged).
    activation_link_base: str = "labtrack://activate"

    @field_validator(
        "sentry_dsn",
        "jwt_private_key",
        "dev_kek",
        "identity_pepper",
        "admin_database_url",
        "admin_login_database_url",
        "maint_database_url",
        "push_database_url",
        "s3_endpoint_url",
        "clamd_host",
        "s3_access_key",
        "s3_secret_key",
        "admin_allowed_networks",
        "expo_access_token",
        "openbao_addr",
        "openbao_role_id",
        "openbao_secret_id",
        "openbao_ca_cert",
        "anthropic_api_key",
        "extraction_model",
        mode="before",
    )
    @classmethod
    def _empty_is_unset(cls, value: object) -> object:
        # Compose passes `SENTRY_DSN=` when unset; that must disable Sentry, not init it.
        return None if value == "" else value

    @model_validator(mode="after")
    def _scanner_outside_dev(self) -> "Settings":
        # uploads are never accepted unscanned outside dev/test (security review 3.3): a
        # forgotten ENVIRONMENT must not quietly skip the virus scan
        if self.environment not in {"dev", "test"} and not self.clamd_host:
            raise ValueError("CLAMD_HOST is required outside dev/test")
        return self

    @model_validator(mode="after")
    def _admin_networks_outside_docker(self) -> "Settings":
        # Inside the stack every container has an address in Docker's private pools: an
        # allowlist that includes them lets any container that reaches the API past Caddy open
        # /admin (security review S2 M2). Production lists the office/VPN's public ranges.
        if self.environment in {"dev", "test"} or not self.admin_allowed_networks:
            return self
        docker = (
            ip_network("172.16.0.0/12"),
            ip_network("192.168.0.0/16"),
            ip_network("10.0.0.0/8"),
        )
        for net in self.admin_allowed_networks:
            if any(net.version == d.version and net.overlaps(d) for d in docker):
                raise ValueError("ADMIN_ALLOWED_NETWORKS: no private ranges outside dev/test")
        return self

    @model_validator(mode="after")
    def _openbao_complete(self) -> "Settings":
        if self.openbao_addr is None:
            return self
        if self.openbao_ca_cert is not None and not Path(self.openbao_ca_cert).is_file():
            raise ValueError("OPENBAO_CA_CERT is not a file")
        if not (self.openbao_role_id and self.openbao_secret_id):
            raise ValueError("OPENBAO_ROLE_ID and OPENBAO_SECRET_ID go with OPENBAO_ADDR")
        # keys and wrapped data keys never cross a network in the clear
        if self.environment not in {"dev", "test"} and not self.openbao_addr.startswith("https://"):
            raise ValueError("OPENBAO_ADDR must be https outside dev/test")
        return self

    def openbao(self) -> OpenBaoConfig | None:
        if self.openbao_addr is None or self.openbao_role_id is None:
            return None
        if self.openbao_secret_id is None:
            return None
        return OpenBaoConfig(
            addr=self.openbao_addr,
            role_id=self.openbao_role_id,
            secret_id=self.openbao_secret_id.get_secret_value(),
            mount=self.openbao_mount,
            ca_cert=self.openbao_ca_cert,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # values come from the environment
