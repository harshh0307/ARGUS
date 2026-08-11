from types import SimpleNamespace

import httpx

from app.github.app_auth import (
    AppTokenProvider,
    AuthError,
    PatTokenProvider,
    build_token_provider,
)
from app.github.client import GitHubClient


def make_settings(**overrides):
    defaults = {
        "github_token": "pat-token",
        "api_base_url": "https://api.github.com",
        "github_app_id": None,
        "github_app_private_key": None,
        "github_install_id": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def rsa_key_pem():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


PRIVATE_KEY = rsa_key_pem()


class TokenExchangeHandler:
    def __init__(self, token="install-token-1", expires_at="2030-01-01T00:00:00Z"):
        self.calls = []
        self.token = token
        self.expires_at = expires_at

    def __call__(self, request):
        self.calls.append(request)
        return httpx.Response(
            201,
            json={"token": self.token, "expires_at": self.expires_at},
        )


def make_app_provider(handler, install_id=123, app_id=456):
    transport = httpx.MockTransport(handler)
    return AppTokenProvider(
        app_id=app_id,
        private_key=PRIVATE_KEY,
        install_id=install_id,
        client=httpx.Client(transport=transport),
    )


def decode_jwt(token):
    import jwt

    return jwt.decode(token, options={"verify_signature": False})


def test_pat_provider_returns_token():
    assert PatTokenProvider("abc").get_token() == "abc"


def test_pat_provider_requires_token():
    try:
        PatTokenProvider("")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_build_provider_uses_pat_by_default():
    provider = build_token_provider(make_settings())
    assert isinstance(provider, PatTokenProvider)
    assert provider.get_token() == "pat-token"


def test_build_provider_prefers_app_credentials():
    provider = build_token_provider(
        make_settings(
            github_token=None,
            github_app_id=456,
            github_app_private_key=PRIVATE_KEY,
            github_install_id=123,
        )
    )
    assert isinstance(provider, AppTokenProvider)


def test_build_provider_raises_without_credentials():
    try:
        build_token_provider(make_settings(github_token=None))
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_app_provider_sends_signed_jwt():
    handler = TokenExchangeHandler()
    provider = make_app_provider(handler)
    token = provider.get_token()
    assert token == "install-token-1"
    assert len(handler.calls) == 1
    auth = handler.calls[0].headers.get("Authorization", "")
    assert auth.startswith("Bearer ")
    jwt_token = auth[len("Bearer "):]
    claims = decode_jwt(jwt_token)
    assert claims["iss"] == "456"
    assert claims["exp"] - claims["iat"] <= 600
    assert handler.calls[0].url.path.endswith("/app/installations/123/access_tokens")


def test_app_provider_caches_token_until_expiry():
    handler = TokenExchangeHandler()
    provider = make_app_provider(handler)
    assert provider.get_token() == "install-token-1"
    assert provider.get_token() == "install-token-1"
    assert len(handler.calls) == 1


def test_app_provider_refreshes_after_expiry():
    handler = TokenExchangeHandler()
    provider = make_app_provider(handler)
    provider.get_token()
    provider._expires_at = 0.0
    provider.get_token()
    assert len(handler.calls) == 2


def test_app_provider_raises_on_failed_exchange():
    def handler(request):
        return httpx.Response(401, json={"message": "Bad credentials"})

    provider = make_app_provider(handler)
    try:
        provider.get_token()
        assert False, "expected AuthError"
    except AuthError:
        pass


class RotatingProvider:
    def __init__(self):
        self.count = 0

    def get_token(self):
        self.count += 1
        return f"rotating-{self.count}"


def test_client_uses_live_provider_token_per_request():
    seen = []
    provider = RotatingProvider()

    def handler(request):
        seen.append(request.headers.get("Authorization"))
        return httpx.Response(200, json={"full_name": "o/r"})

    transport = httpx.MockTransport(handler)
    client = GitHubClient(
        token_provider=provider, client=httpx.Client(transport=transport)
    )
    client.repo_exists("o", "r")
    client.repo_exists("o", "r")
    assert seen == ["Bearer rotating-1", "Bearer rotating-2"]


def test_client_falls_back_to_settings_token():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"full_name": "o/r"})
    )
    client = GitHubClient(
        token=None, token_provider=None, client=httpx.Client(transport=transport)
    )
    client._token_provider = PatTokenProvider("fallback-token")
    assert client._token_provider.get_token() == "fallback-token"