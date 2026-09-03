"""Tests for authentication endpoints and middleware."""

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.core.config import Settings
from app.db.engine import get_engine, init_db
from app.db.repository import set_default_engine


def make_app(database_url=None, **overrides):
    defaults = {
        "database_url": database_url,
        "webhook_secret": None,
        "github_token": "pat-token",
        "api_base_url": "https://api.github.com",
        "github_app_id": None,
        "github_app_private_key": None,
        "github_install_id": None,
        "auth_secret_key": "test-secret-key-for-jwt",
        "auth_algorithm": "HS256",
        "access_token_expire_minutes": 30,
        "refresh_token_expire_days": 7,
    }
    defaults.update(overrides)
    return create_app(Settings(**defaults))


def seeded_engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'auth.db'}"
    engine = get_engine(url)
    init_db(engine)
    set_default_engine(engine)
    return engine


def register_user(client, email="test@example.com", password="secret123", tenant_id=None):
    payload = {"email": email, "password": password}
    if tenant_id:
        payload["tenant_id"] = tenant_id
    return client.post("/api/v1/auth/register", json=payload)


def login_user(client, email="test@example.com", password="secret123"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


# ── Registration tests ─────────────────────────────────────────────────


def test_register_success(tmp_path):
    engine = seeded_engine(tmp_path)
    client = TestClient(make_app(database_url=engine.url.render_as_string(hide_password=False)))
    response = register_user(client)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "tenant_id" in data


def test_register_duplicate_email(tmp_path):
    engine = seeded_engine(tmp_path)
    client = TestClient(make_app(database_url=engine.url.render_as_string(hide_password=False)))
    register_user(client)
    response = register_user(client)
    assert response.status_code == 409


def test_register_custom_tenant(tmp_path):
    engine = seeded_engine(tmp_path)
    client = TestClient(make_app(database_url=engine.url.render_as_string(hide_password=False)))
    response = register_user(client, tenant_id="my-org")
    assert response.status_code == 201
    assert response.json()["tenant_id"] == "my-org"


# ── Login tests ────────────────────────────────────────────────────────


def test_login_success(tmp_path):
    engine = seeded_engine(tmp_path)
    client = TestClient(make_app(database_url=engine.url.render_as_string(hide_password=False)))
    register_user(client)
    response = login_user(client)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(tmp_path):
    engine = seeded_engine(tmp_path)
    client = TestClient(make_app(database_url=engine.url.render_as_string(hide_password=False)))
    register_user(client)
    response = login_user(client, password="wrongpassword")
    assert response.status_code == 401


def test_login_nonexistent_user(tmp_path):
    engine = seeded_engine(tmp_path)
    client = TestClient(make_app(database_url=engine.url.render_as_string(hide_password=False)))
    response = login_user(client, email="nobody@example.com")
    assert response.status_code == 401


# ── Token refresh tests ───────────────────────────────────────────────


def test_refresh_token_success(tmp_path):
    engine = seeded_engine(tmp_path)
    client = TestClient(make_app(database_url=engine.url.render_as_string(hide_password=False)))
    register_user(client)
    login_resp = login_user(client)
    refresh_token = login_resp.json()["refresh_token"]

    response = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_refresh_token_invalid(tmp_path):
    engine = seeded_engine(tmp_path)
    client = TestClient(make_app(database_url=engine.url.render_as_string(hide_password=False)))
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": "invalid.token.here"})
    assert response.status_code == 401


def test_access_token_rejected_for_refresh(tmp_path):
    engine = seeded_engine(tmp_path)
    client = TestClient(make_app(database_url=engine.url.render_as_string(hide_password=False)))
    register_user(client)
    login_resp = login_user(client)
    access_token = login_resp.json()["access_token"]

    response = client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})
    assert response.status_code == 401


# ── Me endpoint tests ──────────────────────────────────────────────────


def test_me_endpoint(tmp_path):
    engine = seeded_engine(tmp_path)
    client = TestClient(make_app(database_url=engine.url.render_as_string(hide_password=False)))
    register_user(client)
    login_resp = login_user(client)
    token = login_resp.json()["access_token"]

    response = client.get("/api/v1/auth/me", headers=auth_header(token))
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@example.com"
    assert data["is_admin"] is False


def test_me_requires_auth(tmp_path):
    engine = seeded_engine(tmp_path)
    client = TestClient(make_app(database_url=engine.url.render_as_string(hide_password=False)))
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


# ── API Key tests ──────────────────────────────────────────────────────


def test_create_and_list_api_keys(tmp_path):
    engine = seeded_engine(tmp_path)
    client = TestClient(make_app(database_url=engine.url.render_as_string(hide_password=False)))
    register_user(client)
    login_resp = login_user(client)
    token = login_resp.json()["access_token"]
    headers = auth_header(token)

    # Create
    response = client.post("/api/v1/auth/api-keys?name=test-key", headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "test-key"
    assert data["key"].startswith("argus_")

    # List
    response = client.get("/api/v1/auth/api-keys", headers=headers)
    assert response.status_code == 200
    keys = response.json()
    assert len(keys) == 1
    assert keys[0]["name"] == "test-key"


def test_revoke_api_key(tmp_path):
    engine = seeded_engine(tmp_path)
    client = TestClient(make_app(database_url=engine.url.render_as_string(hide_password=False)))
    register_user(client)
    login_resp = login_user(client)
    token = login_resp.json()["access_token"]
    headers = auth_header(token)

    create_resp = client.post("/api/v1/auth/api-keys?name=test-key", headers=headers)
    key_id = create_resp.json()["id"]

    response = client.delete(f"/api/v1/auth/api-keys/{key_id}", headers=headers)
    assert response.status_code == 204


def test_api_key_auth(tmp_path):
    engine = seeded_engine(tmp_path)
    client = TestClient(make_app(database_url=engine.url.render_as_string(hide_password=False)))
    register_user(client)
    login_resp = login_user(client)
    token = login_resp.json()["access_token"]
    headers = auth_header(token)

    create_resp = client.post("/api/v1/auth/api-keys?name=test-key", headers=headers)
    raw_key = create_resp.json()["key"]

    # Access protected endpoint with API key
    response = client.get("/api/v1/auth/me", headers={"X-API-Key": raw_key})
    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"


def test_revoked_api_key_rejected(tmp_path):
    engine = seeded_engine(tmp_path)
    client = TestClient(make_app(database_url=engine.url.render_as_string(hide_password=False)))
    register_user(client)
    login_resp = login_user(client)
    token = login_resp.json()["access_token"]
    headers = auth_header(token)

    create_resp = client.post("/api/v1/auth/api-keys?name=test-key", headers=headers)
    raw_key = create_resp.json()["key"]
    key_id = create_resp.json()["id"]

    client.delete(f"/api/v1/auth/api-keys/{key_id}", headers=headers)

    response = client.get("/api/v1/auth/me", headers={"X-API-Key": raw_key})
    assert response.status_code == 401


# ── Protected endpoint tests ───────────────────────────────────────────


def test_protected_endpoint_requires_auth(tmp_path):
    engine = seeded_engine(tmp_path)
    client = TestClient(make_app(database_url=engine.url.render_as_string(hide_password=False)))
    response = client.get("/api/v1/vendors")
    assert response.status_code == 401


def test_protected_endpoint_with_token(tmp_path):
    engine = seeded_engine(tmp_path)
    client = TestClient(make_app(database_url=engine.url.render_as_string(hide_password=False)))
    register_user(client)
    login_resp = login_user(client)
    token = login_resp.json()["access_token"]

    response = client.get("/api/v1/vendors", headers=auth_header(token))
    assert response.status_code == 200


def test_health_does_not_require_auth():
    client = TestClient(make_app(database_url=None))
    response = client.get("/health")
    assert response.status_code == 200
