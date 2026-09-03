import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.core.config import Settings
from app.db.engine import get_engine, init_db, session_factory
from app.db.models import DetectionRun, Repository, Vendor
from app.db.repository import set_default_engine

AUTH_SETTINGS = {
    "auth_secret_key": "test-secret-key-for-jwt",
    "auth_algorithm": "HS256",
    "access_token_expire_minutes": 30,
    "refresh_token_expire_days": 7,
}


def make_app(database_url=None, webhook_secret=None, **overrides):
    defaults = {
        "database_url": database_url,
        "webhook_secret": webhook_secret,
        "github_token": "pat-token",
        "api_base_url": "https://api.github.com",
        "github_app_id": None,
        "github_app_private_key": None,
        "github_install_id": None,
    }
    defaults.update(AUTH_SETTINGS)
    defaults.update(overrides)
    return create_app(Settings(**defaults))


def seeded_engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'api.db'}"
    engine = get_engine(url)
    init_db(engine)
    set_default_engine(engine)
    return engine


def seed(engine, rows):
    session = session_factory(engine)()
    session.add_all(rows)
    session.commit()
    ids = {type(r).__name__: r.id for r in rows if getattr(r, "id", None) is not None}
    session.close()
    return ids


def sign(secret, payload):
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def push_payload(owner="octo", repo="demo"):
    return json.dumps(
        {
            "repository": {
                "owner": {"login": owner},
                "name": repo,
                "full_name": f"{owner}/{repo}",
            },
            "ref": "refs/heads/main",
        }
    ).encode("utf-8")


def register_and_login(client, email="test@example.com", password="secret123"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_health_reports_no_database():
    client = TestClient(make_app(database_url=None))
    assert client.get("/health").json() == {"status": "ok", "database": False}


def test_health_reports_database(tmp_path):
    engine = seeded_engine(tmp_path)
    client = TestClient(make_app(database_url=engine.url.render_as_string(hide_password=False)))
    assert client.get("/health").json()["database"] is True


def test_list_vendors(tmp_path):
    engine = seeded_engine(tmp_path)
    url = engine.url.render_as_string(hide_password=False)
    client = TestClient(make_app(database_url=url))
    headers = register_and_login(client)
    response = client.get("/api/v1/vendors", headers=headers)
    assert response.status_code == 200
    slugs = {item["slug"] for item in response.json()}
    assert slugs == {"github", "stripe", "twilio", "slack", "aws", "azure", "google_cloud"}
    github = next(item for item in response.json() if item["slug"] == "github")
    assert github["poll_interval_seconds"] == 21600


def test_vendor_by_slug(tmp_path):
    engine = seeded_engine(tmp_path)
    url = engine.url.render_as_string(hide_password=False)
    client = TestClient(make_app(database_url=url))
    headers = register_and_login(client)
    response = client.get("/api/v1/vendors/stripe", headers=headers)
    assert response.status_code == 200
    assert response.json()["name"] == "Stripe"


def test_vendor_by_slug_unknown(tmp_path):
    engine = seeded_engine(tmp_path)
    url = engine.url.render_as_string(hide_password=False)
    client = TestClient(make_app(database_url=url))
    headers = register_and_login(client)
    assert client.get("/api/v1/vendors/nope", headers=headers).status_code == 404


def test_detection_runs_require_database():
    client = TestClient(make_app(database_url=None))
    assert client.get("/api/v1/detection-runs").status_code in (401, 503)


def test_detection_runs_listing(tmp_path):
    engine = seeded_engine(tmp_path)
    url = engine.url.render_as_string(hide_password=False)
    seed(
        engine,
        [
            Vendor(slug="stripe", name="Stripe", spec_url="https://s"),
            DetectionRun(
                vendor_slug="stripe",
                old_digest="old1",
                new_digest="new1",
                breaking_count=2,
                additive_count=1,
                changes=[{"kind": "endpoint_removed", "severity": "breaking"}],
            ),
        ],
    )
    client = TestClient(make_app(database_url=url))
    headers = register_and_login(client)
    response = client.get("/api/v1/detection-runs", headers=headers)
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["vendor_slug"] == "stripe"
    assert rows[0]["breaking_count"] == 2
    assert rows[0]["changes"][0]["kind"] == "endpoint_removed"

    one = client.get(f"/api/v1/detection-runs/{rows[0]['id']}", headers=headers)
    assert one.status_code == 200
    assert one.json()["new_digest"] == "new1"

    assert client.get("/api/v1/detection-runs/999", headers=headers).status_code == 404


def test_repositories_register_and_list(tmp_path, monkeypatch):
    engine = seeded_engine(tmp_path)
    url = engine.url.render_as_string(hide_password=False)
    client = TestClient(make_app(database_url=url))
    headers = register_and_login(client)

    from app.workers.celery_app import app as celery_app_mod

    monkeypatch.setattr(celery_app_mod, "send_task", lambda *a, **kw: None)

    created = client.post(
        "/api/v1/repositories",
        json={"owner": "acme", "name": "website", "default_branch": "main"},
        headers=headers,
    )
    assert created.status_code == 201
    repo_id = created.json()["id"]
    assert repo_id > 0

    rows = client.get("/api/v1/repositories", headers=headers).json()
    assert len(rows) == 1
    assert rows[0]["owner"] == "acme"
    assert rows[0]["is_active"] is True

    again = client.post(
        "/api/v1/repositories", json={"owner": "acme", "name": "website"}, headers=headers
    )
    assert again.json()["id"] == repo_id


def test_webhook_requires_secret():
    client = TestClient(make_app(database_url=None, webhook_secret=None))
    assert client.post("/api/v1/webhook", content=b"{}").status_code == 503


def test_webhook_bad_signature():
    client = TestClient(make_app(database_url=None, webhook_secret="s3cret"))
    response = client.post("/api/v1/webhook", content=b"{}")
    assert response.status_code == 401

    response = client.post(
        "/api/v1/webhook",
        content=b"{}",
        headers={"X-Hub-Signature-256": "sha256=deadbeef"},
    )
    assert response.status_code == 401


def test_webhook_ping_ignored():
    client = TestClient(make_app(database_url=None, webhook_secret="s3cret"))
    response = client.post(
        "/api/v1/webhook",
        content=b"{}",
        headers={
            "X-GitHub-Event": "ping",
            "X-Hub-Signature-256": sign("s3cret", b"{}"),
        },
    )
    assert response.status_code == 200
    assert response.json()["reason"] == "ignored event"


def test_webhook_push_not_registered(tmp_path):
    engine = seeded_engine(tmp_path)
    url = engine.url.render_as_string(hide_password=False)
    client = TestClient(make_app(database_url=url, webhook_secret="s3cret"))
    payload = push_payload(owner="ghost", repo="nowhere")
    response = client.post(
        "/api/v1/webhook",
        content=payload,
        headers={
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": sign("s3cret", payload),
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "event": "push",
        "dispatched": False,
        "reason": "repository not registered",
    }


def test_webhook_push_registered_dispatches(tmp_path, monkeypatch):
    engine = seeded_engine(tmp_path)
    url = engine.url.render_as_string(hide_password=False)
    ids = seed(
        engine,
        [Repository(owner="octo", name="demo", default_branch="main", is_active=True)],
    )
    dispatched = {}

    def fake_dispatch(repository_id, merge=True):
        dispatched["repository_id"] = repository_id
        return True

    from app.api import main as api_main

    monkeypatch.setattr(api_main, "_dispatch_scan_and_fix", fake_dispatch)

    client = TestClient(make_app(database_url=url, webhook_secret="s3cret"))
    payload = push_payload()
    response = client.post(
        "/api/v1/webhook",
        content=payload,
        headers={
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": sign("s3cret", payload),
        },
    )
    assert response.status_code == 200
    assert response.json()["dispatched"] is True
    assert dispatched == {"repository_id": ids["Repository"]}


def _post_webhook(client, event, payload):
    body = json.dumps(payload).encode("utf-8")
    return client.post(
        "/api/v1/webhook",
        content=body,
        headers={
            "X-GitHub-Event": event,
            "X-Hub-Signature-256": sign("s3cret", body),
        },
    )


def test_webhook_unknown_event_ignored(tmp_path):
    engine = seeded_engine(tmp_path)
    url = engine.url.render_as_string(hide_password=False)
    client = TestClient(make_app(database_url=url, webhook_secret="s3cret"))
    response = _post_webhook(client, "star", {"action": "created"})
    assert response.status_code == 200
    assert response.json()["reason"] == "ignored event"


def test_webhook_installation_created_registers_install(tmp_path):
    engine = seeded_engine(tmp_path)
    url = engine.url.render_as_string(hide_password=False)
    client = TestClient(make_app(database_url=url, webhook_secret="s3cret"))
    headers = register_and_login(client)
    response = _post_webhook(
        client,
        "installation",
        {
            "action": "created",
            "installation": {"id": 42, "account": {"login": "acme"}},
        },
    )
    assert response.status_code == 200
    assert response.json()["reason"] == "installation created -> owner acme active=True"
    installs = client.get("/api/v1/installations", headers=headers).json()
    assert len(installs) == 1
    assert installs[0]["install_id"] == 42
    assert installs[0]["owner"] == "acme"
    assert installs[0]["is_active"] is True


def test_webhook_installation_deleted_deactivates(tmp_path):
    engine = seeded_engine(tmp_path)
    url = engine.url.render_as_string(hide_password=False)
    client = TestClient(make_app(database_url=url, webhook_secret="s3cret"))
    headers = register_and_login(client)
    _post_webhook(
        client,
        "installation",
        {
            "action": "created",
            "installation": {"id": 7, "account": {"login": "acme"}},
        },
    )
    response = _post_webhook(
        client,
        "installation",
        {
            "action": "deleted",
            "installation": {"id": 7, "account": {"login": "acme"}},
        },
    )
    assert response.json()["reason"] == "installation deleted -> owner acme active=False"
    installs = client.get("/api/v1/installations", headers=headers).json()
    assert installs[0]["is_active"] is False


def test_webhook_repository_dispatch_dispatches(tmp_path, monkeypatch):
    engine = seeded_engine(tmp_path)
    url = engine.url.render_as_string(hide_password=False)
    ids = seed(
        engine,
        [Repository(owner="octo", name="demo", default_branch="main", is_active=True)],
    )
    dispatched = {}

    def fake_dispatch(repository_id, merge=True):
        dispatched["repository_id"] = repository_id
        return True

    from app.api import main as api_main

    monkeypatch.setattr(api_main, "_dispatch_scan_and_fix", fake_dispatch)

    client = TestClient(make_app(database_url=url, webhook_secret="s3cret"))
    response = _post_webhook(
        client,
        "repository_dispatch",
        {"action": "argus-scan", "repository": {"owner": {"login": "octo"}, "name": "demo"}},
    )
    assert response.status_code == 200
    assert response.json()["dispatched"] is True
    assert dispatched == {"repository_id": ids["Repository"]}


def test_webhook_repository_dispatch_unregistered(tmp_path):
    engine = seeded_engine(tmp_path)
    url = engine.url.render_as_string(hide_password=False)
    client = TestClient(make_app(database_url=url, webhook_secret="s3cret"))
    response = _post_webhook(
        client,
        "repository_dispatch",
        {"action": "argus-scan", "repository": {"owner": {"login": "ghost"}, "name": "nowhere"}},
    )
    assert response.json()["reason"] == "repository not registered"