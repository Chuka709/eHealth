"""Access tokens: ES256 JWTs with a session id and token_version (docs/04 §6.3).

The JWT alone is never trusted for long: every request also checks session_check() so that
logout, admin reset and disabling an account apply immediately.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from uuid import UUID

import jwt
import structlog
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from labtrack.config import get_settings

_ALGORITHM = "ES256"
log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class SigningKey:
    kid: str
    private_pem: bytes
    public_pem: bytes


@dataclass(frozen=True)
class AccessClaims:
    user_id: UUID
    session_id: UUID
    token_version: int
    role: str


class InvalidTokenError(Exception):
    """Expired, malformed, wrong audience/issuer or signed by an unknown key."""


def _public_pem(private_pem: bytes) -> bytes:
    key = serialization.load_pem_private_key(private_pem, password=None)
    return key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )


@lru_cache
def signing_key() -> SigningKey:
    settings = get_settings()
    if settings.jwt_private_key is not None:
        pem = settings.jwt_private_key.get_secret_value().encode()
        return SigningKey(settings.jwt_kid, pem, _public_pem(pem))
    if settings.environment not in {"dev", "test"}:
        raise RuntimeError("JWT_PRIVATE_KEY is required outside dev/test")
    # Dev/test only: an ephemeral key (tokens stop working on restart, which is fine there).
    log.warning("jwt_ephemeral_key")
    pem = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return SigningKey("dev", pem, _public_pem(pem))


def issue_access_token(claims: AccessClaims, *, now: datetime | None = None) -> tuple[str, int]:
    settings = get_settings()
    key = signing_key()
    issued = now or datetime.now(UTC)
    ttl = timedelta(seconds=settings.access_token_ttl_seconds)
    token = jwt.encode(
        {
            "sub": str(claims.user_id),
            "sid": str(claims.session_id),
            "tv": claims.token_version,
            "role": claims.role,
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": issued,
            "exp": issued + ttl,
        },
        key.private_pem,
        algorithm=_ALGORITHM,
        headers={"kid": key.kid},
    )
    return token, int(ttl.total_seconds())


def decode_access_token(token: str) -> AccessClaims:
    settings = get_settings()
    key = signing_key()
    try:
        if jwt.get_unverified_header(token).get("kid") != key.kid:
            raise InvalidTokenError
        data = jwt.decode(
            token,
            key.public_pem,
            algorithms=[_ALGORITHM],  # never accept "none" or HS* with the public key
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "sid", "tv", "aud", "iss"]},
        )
        return AccessClaims(
            user_id=UUID(data["sub"]),
            session_id=UUID(data["sid"]),
            token_version=int(data["tv"]),
            role=str(data["role"]),
        )
    except (jwt.PyJWTError, ValueError, KeyError, TypeError) as exc:
        raise InvalidTokenError from exc
