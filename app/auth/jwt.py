"""JWT token creation and verification."""

from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

_DEFAULT_ALGORITHM = "HS256"


def create_access_token(
    data: dict,
    secret_key: str,
    expires_delta: timedelta | None = None,
    algorithm: str = _DEFAULT_ALGORITHM,
) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=30))
    to_encode.update({"exp": expire, "iat": datetime.now(UTC)})
    return jwt.encode(to_encode, secret_key, algorithm=algorithm)


def create_refresh_token(
    data: dict,
    secret_key: str,
    expires_delta: timedelta | None = None,
    algorithm: str = _DEFAULT_ALGORITHM,
) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + (expires_delta or timedelta(days=7))
    to_encode.update({"exp": expire, "iat": datetime.now(UTC), "type": "refresh"})
    return jwt.encode(to_encode, secret_key, algorithm=algorithm)


def decode_token(
    token: str,
    secret_key: str,
    algorithm: str = _DEFAULT_ALGORITHM,
) -> dict | None:
    try:
        return jwt.decode(token, secret_key, algorithms=[algorithm])
    except JWTError:
        return None
