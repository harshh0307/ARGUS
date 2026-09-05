from types import SimpleNamespace

from app.db.engine import get_engine, init_db, session_factory
from app.db.models import Repository
from app.db.repository import set_default_engine
from app.services.pipeline import PipelineOutcome
from app.workers import tasks


def make_settings(**overrides):
    defaults = {
        "github_token": "token",
        "api_base_url": "https://api.github.com",
        "fix_max_attempts": 3,
        "llm_model": "m",
        "llm_base_url": None,
        "gemini_api_key": None,
        "openai_api_key": "k",
        "openrouter_api_key": None,
        "openrouter_model": None,
        "database_url": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def seeded(tmp_path):
    settings = make_settings(database_url=f"sqlite:///{tmp_path / 'workers.db'}")
    engine = get_engine(settings.database_url)
    init_db(engine)
    set_default_engine(engine)
    return settings, engine


def test_run_detection_returns_result(monkeypatch, tmp_path):
    settings, _ = seeded(tmp_path)

    monkeypatch.setattr(tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(
        tasks,
        "detect_changes",
        lambda settings, vendor_slug: {
            "vendor": vendor_slug,
            "breaking_count": 3,
            "additive_count": 2,
            "baselined": False,
            "changes": [],
        },
    )

    result = tasks.run_detection("github")

    assert result["breaking_count"] == 3
    assert result["additive_count"] == 2


def test_run_detection_skips_persist_without_database(monkeypatch):
    monkeypatch.setattr(tasks, "get_settings", lambda: make_settings(database_url=None))
    monkeypatch.setattr(
        tasks,
        "detect_changes",
        lambda settings, vendor_slug: {
            "vendor": vendor_slug,
            "breaking_count": 0,
            "additive_count": 0,
            "baselined": True,
            "changes": [],
        },
    )

    result = tasks.run_detection("github")

    assert result["baselined"] is True


def test_scan_and_fix_without_pr_result(monkeypatch, tmp_path):
    settings, _ = seeded(tmp_path)
    session = session_factory(_)()
    repo = Repository(owner="acme", name="web", default_branch="main")
    session.add(repo)
    session.commit()
    repo_id = repo.id
    session.close()

    monkeypatch.setattr(tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(
        tasks,
        "open_session",
        lambda s: session_factory(_)(),
    )
    monkeypatch.setattr(
        tasks,
        "run_repo_pipeline",
        lambda *a, **k: PipelineOutcome(pr_result=None, impacts=[], merged=False),
    )

    result = tasks.scan_and_fix(repo_id, merge=True)

    assert result["repository_id"] == repo_id
    assert result["pr_number"] is None
    assert result["passed"] is None
    assert result["attempts"] == 0
    assert result["merged"] is False
    assert result["impacted"] == 0


def test_scan_and_fix_catches_pipeline_failure(monkeypatch, tmp_path):
    from app.github.client import GitHubApiError

    settings, engine = seeded(tmp_path)
    session = session_factory(engine)()
    repo = Repository(owner="acme", name="web", default_branch="main")
    session.add(repo)
    session.commit()
    repo_id = repo.id
    session.close()

    monkeypatch.setattr(tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(tasks, "open_session", lambda s: session_factory(engine)())
    monkeypatch.setattr(
        tasks, "run_repo_pipeline", lambda *a, **k: (_ for _ in ()).throw(GitHubApiError("boom"))
    )

    result = tasks.scan_and_fix(repo_id)
    assert "error" in result
    assert "boom" in result["error"]


def test_scan_and_fix_with_pr_merge_error(monkeypatch, tmp_path):
    settings, engine = seeded(tmp_path)
    session = session_factory(engine)()
    repo = Repository(owner="acme", name="web", default_branch="main")
    session.add(repo)
    session.commit()
    repo_id = repo.id
    session.close()

    pr_result = SimpleNamespace(
        pr_number=9, pr_url="https://github.com/acme/web/pull/9", passed=True, attempts=1, failure=None
    )

    monkeypatch.setattr(tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(tasks, "open_session", lambda s: session_factory(engine)())
    monkeypatch.setattr(
        tasks,
        "run_repo_pipeline",
        lambda *a, **k: PipelineOutcome(
            pr_result=pr_result,
            impacts=[1, 2],
            merged=False,
            merge_error="merge conflict",
        ),
    )

    result = tasks.scan_and_fix(repo_id, merge=True)

    assert result["pr_number"] == 9
    assert result["passed"] is True
    assert result["merged"] is False
    assert result["merge_error"] == "merge conflict"
    assert result["impacted"] == 2


def test_poll_all_vendors_with_no_vendors(monkeypatch):
    monkeypatch.setattr(tasks, "get_settings", lambda: make_settings())
    monkeypatch.setattr(tasks, "list_vendors", lambda settings: [])
    assert tasks.poll_all_vendors() == {}


def test_sync_active_repos_touches_last_run_at(monkeypatch, tmp_path):
    settings, engine = seeded(tmp_path)
    session = session_factory(engine)()
    session.add(Repository(owner="a", name="one", default_branch="main", is_active=True, vendor_slug="github"))
    session.add(Repository(owner="b", name="two", default_branch="main", is_active=False, vendor_slug="github"))
    session.commit()
    session.close()

    monkeypatch.setattr(tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(tasks, "open_session", lambda s: session_factory(engine)())

    from unittest.mock import MagicMock
    mock_send = MagicMock()
    mock_app = MagicMock(send_task=mock_send)
    monkeypatch.setattr(tasks, "_get_celery_app", lambda: mock_app)

    results = tasks.dispatch_scan_for_vendor("github", breaking_count=1)

    assert results["dispatched"] == 1
    assert results["repos"] == 1
    assert mock_send.call_count == 1


def test_register_repository_returns_same_id_for_existing(monkeypatch, tmp_path):
    settings, engine = seeded(tmp_path)
    monkeypatch.setattr(tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(tasks, "open_session", lambda s: session_factory(engine)())

    first = tasks.register_repository("acme", "web", "main", "github")
    second = tasks.register_repository("acme", "web", None, "github")

    assert second == first
    session = session_factory(engine)()
    assert session.query(Repository).count() == 1
    session.close()
