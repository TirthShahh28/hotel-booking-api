from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

ACCESS = "access"
REFRESH = "refresh"

# bcrypt truncates inputs longer than 72 bytes; we truncate defensively so callers
# never hit the library-level error for extremely long passwords.
_BCRYPT_MAX_BYTES = 72


def _to_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_to_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(_to_bytes(password), hashed.encode("utf-8"))


def _encode(subject: str, token_type: str, expires_delta: timedelta, extra: dict[str, Any]) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        **extra,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: int, role: str) -> str:
    return _encode(
        subject=str(user_id),
        token_type=ACCESS,
        expires_delta=timedelta(minutes=settings.access_token_minutes),
        extra={"role": role},
    )


def create_refresh_token(user_id: int) -> str:
    return _encode(
        subject=str(user_id),
        token_type=REFRESH,
        expires_delta=timedelta(days=settings.refresh_token_days),
        extra={},
    )


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("invalid token") from exc
    if payload.get("type") != expected_type:
        raise ValueError(f"wrong token type; expected {expected_type}")
    return payload
