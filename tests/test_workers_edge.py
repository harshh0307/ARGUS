from types import SimpleNamespace

import pytest

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
        "snapshot_dir": "data/snapshots",
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


def test_run_detection_persists_when_database_configured(monkeypatch, tmp_path):
    settings, _ = seeded(tmp_path)
    captured = {}

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
    monkeypatch.setattr(tasks, "get_vendor", lambda settings, slug: SimpleNamespace(slug=slug))
    monkeypatch.setattr(
        tasks,
        "persist_detection",
        lambda s, slug, result, vendor: captured.update(
            slug=slug, result=result, vendor=vendor
        ),
    )

    result = tasks.run_detection("github")

    assert result["breaking_count"] == 3
    assert result["additive_count"] == 2
    assert captured["slug"] == "github"
    assert captured["result"]["breaking_count"] == 3


def test_run_detection_skips_persist_without_database(monkeypatch):
    called = {"n": 0}

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
    monkeypatch.setattr(tasks, "get_vendor", lambda settings, slug: SimpleNamespace(slug=slug))
    monkeypatch.setattr(
        tasks, "persist_detection", lambda *a: called.update(n=called["n"] + 1)
    )

    result = tasks.run_detection("github")

    assert result["baselined"] is True
    assert called["n"] == 0


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
        tasks, "run_repo_pipeline", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
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
    session.add(Repository(owner="a", name="one", default_branch="main", is_active=True))
    session.add(Repository(owner="b", name="two", default_branch="main", is_active=False))
    session.commit()
    session.close()

    monkeypatch.setattr(tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(tasks, "open_session", lambda s: session_factory(engine)())

    results = tasks._sync_active_repos_and_dispatch()

    assert "a/one" in results
    assert results["a/one"]["active"] is True
    assert "b/two" not in results

    session = session_factory(engine)()
    repo = session.query(Repository).filter_by(owner="a", name="one").one()
    assert repo.last_run_at is not None
    inactive = session.query(Repository).filter_by(owner="b", name="two").one()
    assert inactive.last_run_at is None
    session.close()


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