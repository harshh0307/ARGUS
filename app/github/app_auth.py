from __future__ import annotations

import time
from datetime import datetime
from typing import Protocol

import httpx


class TokenProvider(Protocol):
    def get_token(self) -> str: ...


class AuthError(Exception):
    pass


class PatTokenProvider:
    def __init__(self, token: str):
        if not token:
            raise ValueError("a GitHub token is required to build a PatTokenProvider")
        self._token = token

    def get_token(self) -> str:
        return self._token


class AppTokenProvider:
    """GitHub App auth: signs an RS256 JWT with the app's private key, then
    exchanges it for an installation access token via the API. Tokens are
    cached until ~60s before expiry; the JWT itself is minted per exchange."""

    def __init__(
        self,
        app_id: int,
        private_key: str,
        install_id: int,
        base_url: str = "https://api.github.com",
        timeout: float = 15.0,
        client: httpx.Client | None = None,
    ):
        import jwt

        self._jwt = jwt
        if not app_id:
            raise ValueError("GitHub App id is required")
        if not private_key:
            raise ValueError("GitHub App private key is required")
        if not install_id:
            raise ValueError("GitHub App installation id is required")
        self._app_id = int(app_id)
        self._key = private_key
        self._install_id = int(install_id)
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "argus/0.1 (api-change-agent)",
            },
            timeout=timeout,
        )
        self._token: str | None = None
        self._expires_at: float = 0.0

    def _app_jwt(self) -> str:
        now = int(time.time())
        return self._jwt.encode(
            {"iat": now - 60, "exp": now + 540, "iss": str(self._app_id)},
            self._key,
            algorithm="RS256",
            headers={"alg": "RS256", "typ": "JWT"},
        )

    def _refresh(self) -> None:
        response = self._client.post(
            f"{self._base_url}/app/installations/{self._install_id}/access_tokens",
            headers={"Authorization": f"Bearer {self._app_jwt()}"},
        )
        if response.status_code >= 400:
            raise AuthError(
                f"GitHub App token exchange failed: {response.status_code}: "
                f"{response.text[:300]}"
            )
        data = response.json()
        self._token = data["token"]
        expires_at = data.get("expires_at")
        try:
            self._expires_at = datetime.fromisoformat(expires_at).timestamp()
        except (AttributeError, ValueError):
            self._expires_at = time.time() + 3600

    def get_token(self) -> str:
        if self._token is None or time.time() > self._expires_at - 60:
            self._refresh()
        return self._token


def build_token_provider(settings) -> TokenProvider:
    app_id = getattr(settings, "github_app_id", None)
    private_key = getattr(settings, "github_app_private_key", None)
    install_id = getattr(settings, "github_install_id", None)
    if app_id and private_key and install_id:
        return AppTokenProvider(
            app_id=int(app_id),
            private_key=private_key,
            install_id=int(install_id),
            base_url=getattr(settings, "api_base_url", "https://api.github.com"),
        )
    token = getattr(settings, "github_token", None)
    if token:
        return PatTokenProvider(token)
    raise ValueError(
        "no GitHub credentials configured; set GITHUB_TOKEN or GitHub App "
        "settings (GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY, GITHUB_INSTALL_ID)"
    )