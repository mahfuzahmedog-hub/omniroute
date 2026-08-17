"""Password hashing and JWT access tokens.

We use the ``bcrypt`` library directly (rather than passlib) to avoid a well-known
version-compatibility break, and we transparently handle bcrypt's 72-byte input limit.
Tokens are signed with the configured secret; the algorithm and TTL come from settings
so the signing strategy stays replaceable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from forge.config import get_settings

# bcrypt hashes at most the first 72 bytes of input; longer passwords must be
# pre-truncated or bcrypt raises. We truncate deterministically after encoding.
_BCRYPT_MAX_BYTES = 72


def _prepare_password(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    """Return a salted bcrypt hash of ``password``."""
    return bcrypt.hashpw(_prepare_password(password), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Constant-time verification of ``password`` against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(_prepare_password(password), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(subject: uuid.UUID | str, *, expires_minutes: int | None = None) -> str:
    """Create a signed JWT whose ``sub`` claim identifies the user."""
    settings = get_settings()
    ttl = expires_minutes if expires_minutes is not None else settings.access_token_ttl_minutes
    now = datetime.now(UTC)
    claims = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl)).timestamp()),
        "type": "access",
    }
    return jwt.encode(claims, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str | None:
    """Return the ``sub`` claim if the token is valid, else ``None``."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    if payload.get("type") != "access":
        return None
    subject = payload.get("sub")
    return str(subject) if subject is not None else None
