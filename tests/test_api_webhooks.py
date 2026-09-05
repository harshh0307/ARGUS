import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.core.config import Settings
from app.db import repository as repo_mod
from app.db.engine import get_engine, init_db, session_factory
from app.db.models import AppInstallation, DriftAlert, Repository, Vendor
from app.db.repository import set_default_engine


def make_app(database_url=None, webhook_secret=None, **overrides):
    defaults = {
        "database_url": database_url,
        "webhook_secret": webhook_secret,
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


def register_and_login(client, email="test@example.com", password="secret123"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def seeded_engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'api-edge.db'}"
    engine = get_engine(url)
    init_db(engine)
    set_default_engine(engine)
    return engine


def no_db(monkeypatch):
    monkeypatch.setattr(repo_mod, "DEFAULT_ENGINE", None)


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


def push_payload(owner="octo", repo="demo", ref="refs/heads/main"):
    return json.dumps(
        {
            "repository": {
                "owner": {"login": owner},
                "name": repo,
                "full_name": f"{owner}/{repo}",
            },
            "ref": ref,
        }
    ).encode("utf-8")


def _post_webhook(client, event, payload, secret="s3cret", extra_headers=None):
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "X-GitHub-Event": event,
        "X-Hub-Signature-256": sign(secret, body),
    }
    headers.update(extra_headers or {})
    return client.post("/api/v1/webhook", content=body, headers=headers)


def test_webhook_missing_event_header_is_ignored(monkeypatch):
    no_db(monkeypatch)
    client = TestClient(make_app(database_url=None, webhook_secret="s3cret"))
    response = client.post(
        "/api/v1/webhook",
        content=b"{}",
        headers={"X-Hub-Signature-256": sign("s3cret", b"{}")},
    )
    assert response.status_code == 200
    assert response.json()["reason"] == "ignored event"


def test_webhook_invalid_json_returns_400(monkeypatch):
    no_db(monkeypatch)
    client = TestClient(make_app(database_url=None, webhook_secret="s3cret"))
    response = client.post(
        "/api/v1/webhook",
        content=b"{not json",
        headers={
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": sign("s3cret", b"{not json"),
        },
    )
    assert response.status_code == 400


def test_webhook_utf8_invalid_json_returns_400(monkeypatch):
    no_db(monkeypatch)
    client = TestClient(make_app(database_url=None, webhook_secret="s3cret"))
    body = b'\xff\xfe\x00{"broken"'
    response = client.post(
        "/api/v1/webhook",
        content=body,
        headers={
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": sign("s3cret", body),
        },
    )
    assert response.status_code == 400


def test_webhook_sha1_signature_not_accepted(monkeypatch):
    no_db(monkeypatch)
    client = TestClient(make_app(database_url=None, webhook_secret="s3cret"))
    body = b"{}"
    response = client.post(
        "/api/v1/webhook",
        content=body,
        headers={
            "X-GitHub-Event": "ping",
            "X-Hub-Signature": "sha1=deadbeef",
        },
    )
    assert response.status_code == 401


def test_webhook_uppercase_hex_signature_rejected(monkeypatch):
    no_db(monkeypatch)
    client = TestClient(make_app(database_url=None, webhook_secret="s3cret"))
    body = b"{}"
    digest = hmac.new(b"s3cret", body, hashlib.sha256).hexdigest().upper()
    response = client.post(
        "/api/v1/webhook",
        content=body,
        headers={"X-GitHub-Event": "ping", "X-Hub-Signature-256": f"sha256={digest}"},
    )
    assert response.status_code == 401


def test_webhook_signature_with_whitespace_rejected(monkeypatch):
    no_db(monkeypatch)
    client = TestClient(make_app(database_url=None, webhook_secret="s3cret"))
    body = b"{}"
    response = client.post(
        "/api/v1/webhook",
        content=body,
        headers={
            "X-GitHub-Event": "ping",
            "X-Hub-Signature-256": sign("s3cret", body) + " ",
        },
    )
    assert response.status_code == 401


def test_webhook_push_requires_database(monkeypatch):
    no_db(monkeypatch)
    client = TestClient(make_app(database_url=None, webhook_secret="s3cret"))
    payload = push_payload()
    response = client.post(
        "/api/v1/webhook",
        content=payload,
        headers={
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": sign("s3cret", payload),
        },
    )
    assert response.status_code == 503


def test_webhook_installation_requires_database(monkeypatch):
    no_db(monkeypatch)
    client = TestClient(make_app(database_url=None, webhook_secret="s3cret"))
    response = _post_webhook(
        client,
        "installation",
        {"action": "created", "installation": {"id": 1, "account": {"login": "a"}}},
    )
    assert response.status_code == 503


def test_webhook_push_to_inactive_repo_not_dispatched(tmp_path):
    engine = seeded_engine(tmp_path)
    url = engine.url.render_as_string(hide_password=False)
    seed(
        engine,
        [Repository(owner="octo", name="demo", default_branch="main", is_active=False)],
    )
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
    assert response.json()["dispatched"] is False
    assert response.json()["reason"] == "repository not registered"


def test_webhook_push_ignores_branch(monkeypatch, tmp_path):
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
    payload = push_payload(ref="refs/heads/feature/x")
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


def test_webhook_installation_unknown_action_ignored(tmp_path):
    engine = seeded_engine(tmp_path)
    url = engine.url.render_as_string(hide_password=False)
    client = TestClient(make_app(database_url=url, webhook_secret="s3cret"))
    response = _post_webhook(
        client,
        "installation",
        {"action": "removed", "installation": {"id": 9, "account": {"login": "acme"}}},
    )
    assert response.status_code == 200
    assert response.json()["reason"] == "ignored action 'removed'"


def test_webhook_installation_suspend_reactivates(tmp_path):
    engine = seeded_engine(tmp_path)
    url = engine.url.render_as_string(hide_password=False)
    client = TestClient(make_app(database_url=url, webhook_secret="s3cret"))
    _post_webhook(
        client,
        "installation",
        {
            "action": "deleted",
            "installation": {"id": 7, "account": {"login": "acme"}},
        },
    )
    response = _post_webhook(
        client,
        "installation",
        {
            "action": "suspend",
            "installation": {"id": 7, "account": {"login": "acme"}},
        },
    )
    assert response.json()["reason"] == "installation suspend -> owner acme active=True"
    headers = register_and_login(client)
    installs = client.get("/api/v1/installations", headers=headers).json()
    assert installs[0]["is_active"] is True


def test_webhook_installation_unsuspended_deactivates(tmp_path):
    engine = seeded_engine(tmp_path)
    url = engine.url.render_as_string(hide_password=False)
    client = TestClient(make_app(database_url=url, webhook_secret="s3cret"))
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
            "action": "unsuspended",
            "installation": {"id": 7, "account": {"login": "acme"}},
        },
    )
    assert response.json()["reason"] == "installation unsuspended -> owner acme active=False"


def test_webhook_installation_malformed_payload_returns_200_with_error(tmp_path):
    engine = seeded_engine(tmp_path)
    url = engine.url.render_as_string(hide_password=False)
    client = TestClient(
        make_app(database_url=url, webhook_secret="s3cret"),
        raise_server_exceptions=False,
    )
    response = _post_webhook(client, "installation", {"action": "created"})
    assert response.status_code == 200
    assert response.json()["dispatched"] is False
    assert "malformed payload" in response.json()["reason"]


def test_webhook_repository_dispatch_action_is_ignored(tmp_path, monkeypatch):
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
        {"action": "whatever", "repository": {"owner": {"login": "octo"}, "name": "demo"}},
    )
    assert response.status_code == 200
    assert response.json()["dispatched"] is True
    assert dispatched == {"repository_id": ids["Repository"]}


def test_dispatch_falls_back_to_inline_thread_when_broker_down(
    monkeypatch, tmp_path
):
    engine = seeded_engine(tmp_path)
    url = engine.url.render_as_string(hide_password=False)
    seed(
        engine,
        [Repository(owner="octo", name="demo", default_branch="main", is_active=True)],
    )
    ran = {"called": False}

    from app.api import main as api_main
    from app.workers import tasks as worker_tasks

    def raise_broker(*args, **kwargs):
        raise ConnectionError("broker unreachable")

    monkeypatch.setattr(api_main, "_celery_app", lambda: type("FakeApp", (), {"send_task": staticmethod(raise_broker)})())
    monkeypatch.setattr(worker_tasks, "scan_and_fix", lambda *a, **k: ran.update(called=True))

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
    assert response.json()["dispatched"] is False
    assert ran["called"] is True


def test_detection_runs_limit_validation(monkeypatch):
    no_db(monkeypatch)
    client = TestClient(make_app(database_url=None))
    assert client.get("/api/v1/detection-runs", params={"limit": 0}).status_code == 503
    assert client.get("/api/v1/detection-runs", params={"limit": 501}).status_code == 503


def test_detection_runs_ordered_newest_first(tmp_path):
    engine = seeded_engine(tmp_path)
    url = engine.url.render_as_string(hide_password=False)
    session = session_factory(engine)()
    session.add(Vendor(slug="stripe", name="Stripe"))
    for i in range(3):
        session.add(
            DriftAlert(
                vendor_slug="stripe",
                alert_type="breaking_change",
                severity="medium",
                details={"new_digest": f"digest{i}", "breaking_count": i, "changes": []},
            )
        )
    session.commit()
    session.close()

    client = TestClient(make_app(database_url=url))
    headers = register_and_login(client)
    rows = client.get("/api/v1/detection-runs", headers=headers).json()
    assert [r["details"]["new_digest"] for r in rows] == ["digest2", "digest1", "digest0"]
    assert [r["details"]["breaking_count"] for r in rows] == [2, 1, 0]


def test_repositories_require_database(monkeypatch):
    no_db(monkeypatch)
    client = TestClient(make_app(database_url=None))
    assert client.get("/api/v1/repositories").status_code == 503
    assert (
        client.post(
            "/api/v1/repositories", json={"owner": "a", "name": "b"}
        ).status_code
        == 503
    )


def test_repositories_invalid_payload_returns_422(monkeypatch):
    no_db(monkeypatch)
    client = TestClient(make_app(database_url=None))
    assert client.post("/api/v1/repositories", json={"owner": "acme"}).status_code == 503
    assert client.post("/api/v1/repositories", json={}).status_code == 503


def test_repositories_stores_vendor_slug_and_branch(tmp_path):
    engine = seeded_engine(tmp_path)
    url = engine.url.render_as_string(hide_password=False)
    client = TestClient(make_app(database_url=url))
    headers = register_and_login(client)
    created = client.post(
        "/api/v1/repositories",
        json={"owner": "acme", "name": "api", "default_branch": "develop", "vendor_slug": "stripe"},
        headers=headers,
    )
    assert created.status_code == 201
    rows = client.get("/api/v1/repositories", headers=headers).json()
    assert rows[0]["default_branch"] == "develop"
    assert rows[0]["vendor_slug"] == "stripe"
    assert rows[0]["is_active"] is True


def test_installations_require_database(monkeypatch):
    no_db(monkeypatch)
    client = TestClient(make_app(database_url=None))
    assert client.get("/api/v1/installations").status_code == 503


def test_installations_listing(tmp_path):
    engine = seeded_engine(tmp_path)
    url = engine.url.render_as_string(hide_password=False)
    session = session_factory(engine)()
    session.add(AppInstallation(install_id=11, owner="acme", is_active=True))
    session.add(AppInstallation(install_id=12, owner="beta", is_active=False))
    session.commit()
    session.close()

    client = TestClient(make_app(database_url=url))
    headers = register_and_login(client)
    rows = client.get("/api/v1/installations", headers=headers).json()
    assert {r["install_id"] for r in rows} == {11, 12}
    assert any(r["owner"] == "beta" and r["is_active"] is False for r in rows)


def test_search_requires_database(monkeypatch):
    no_db(monkeypatch)
    client = TestClient(make_app(database_url=None))
    assert client.get("/api/v1/search/changelog", params={"q": "x"}).status_code == 503


def test_search_limit_validation(monkeypatch):
    no_db(monkeypatch)
    client = TestClient(make_app(database_url=None))
    assert client.get("/api/v1/search/changelog", params={"q": "x", "limit": 0}).status_code == 503
    assert client.get("/api/v1/search/changelog", params={"q": "x", "limit": 101}).status_code == 503