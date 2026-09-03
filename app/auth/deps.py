"""FastAPI dependencies for authentication."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.api_keys import hash_api_key
from app.auth.jwt import decode_token
from app.core.config import Settings
from app.db.models import ApiKey, User
from app.db.repository import open_session

_bearer_scheme = HTTPBearer(auto_error=False)


def _get_settings(request: Request) -> Settings:
    return request.app.state.settings


def _get_db(settings: Settings) -> Session:
    if not settings.database_url:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "DATABASE_URL is not set; auth requires a database",
        )
    return open_session(settings)


def _extract_bearer_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),  # noqa: B008
) -> str | None:
    return credentials.credentials if credentials else None


def _extract_api_key(request: Request) -> str | None:
    return request.headers.get("X-API-Key")


def get_current_user(
    request: Request,
    token: str | None = Depends(_extract_bearer_token),
    api_key: str | None = Depends(_extract_api_key),
    settings: Settings = Depends(_get_settings),  # noqa: B008
) -> User:
    """Authenticate via JWT Bearer token or X-API-Key header."""
    if not settings.database_url:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "DATABASE_URL is not set; auth requires a database",
        )

    session = _get_db(settings)
    try:
        # Try JWT first
        if token:
            payload = decode_token(token, settings.auth_secret_key, settings.auth_algorithm)
            if payload and payload.get("type") != "refresh":
                user_id = payload.get("sub")
                if user_id:
                    user = session.get(User, int(user_id))
                    if user and user.is_active:
                        return user

        # Try API key
        if api_key:
            key_hash = hash_api_key(api_key)
            row = session.execute(
                select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
            ).scalar_one_or_none()
            if row:
                user = session.get(User, row.user_id)
                if user and user.is_active:
                    row.last_used_at = datetime.now(UTC)
                    session.commit()
                    return user

        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    finally:
        session.close()


def get_current_admin(
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> User:
    if not current_user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return current_user


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(get_current_admin)]
