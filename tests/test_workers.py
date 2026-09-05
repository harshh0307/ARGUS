from types import SimpleNamespace

from app.db.engine import get_engine, init_db, session_factory
from app.db.repository import set_default_engine
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


def test_run_detection_task_calls_service(monkeypatch):
    captured = {}

    def fake_detect(settings, vendor_slug="github"):
        captured["vendor"] = vendor_slug
        return {
            "vendor": "github",
            "breaking_count": 2,
            "additive_count": 1,
            "changes": [],
            "baselined": False,
        }

    monkeypatch.setattr(tasks, "detect_changes", fake_detect)
    monkeypatch.setattr(tasks, "get_settings", lambda: make_settings())

    result = tasks.run_detection("github")

    assert result["vendor"] == "github"
    assert result["breaking_count"] == 2
    assert captured["vendor"] == "github"


def test_scan_and_fix_missing_repo(tmp_path):
    settings = make_settings(database_url=f"sqlite:///{tmp_path / 'argus.db'}")
    engine = get_engine(settings.database_url)
    init_db(engine)
    set_default_engine(engine)

    monkeypatch = __import__("pytest").MonkeyPatch()

    def fake_open_session(_settings):
        return session_factory(engine)()

    monkeypatch.setattr(tasks, "open_session", fake_open_session)
    monkeypatch.setattr(tasks, "get_settings", lambda: settings)

    result = tasks.scan_and_fix(999)

    assert result["error"] == "repo row not found"
    monkeypatch.undo()


def test_register_repository_and_scan_and_fix(monkeypatch, tmp_path):
    settings = make_settings(database_url=f"sqlite:///{tmp_path / 'argus.db'}")
    engine = get_engine(settings.database_url)
    init_db(engine)
    set_default_engine(engine)
    monkeypatch = __import__("pytest").MonkeyPatch()
    monkeypatch.setattr(tasks, "get_settings", lambda: settings)

    def fake_open_session(_settings):
        return session_factory(engine)()

    monkeypatch.setattr(tasks, "open_session", fake_open_session)

    repo_id = tasks.register_repository("acme", "website", "main")
    assert repo_id > 0

    def fake_pipeline(settings, owner, name, **kwargs):
        return SimpleNamespace(
            pr_result=SimpleNamespace(
                pr_number=5,
                pr_url="https://github.com/acme/website/pull/5",
                passed=True,
                attempts=2,
                failure=None,
            ),
            merged=True,
            merge_error=None,
            impacts=[1],
        )

    monkeypatch.setattr(tasks, "run_repo_pipeline", fake_pipeline)

    result = tasks.scan_and_fix(repo_id, merge=True)

    assert result["pr_number"] == 5
    assert result["passed"] is True
    assert result["merged"] is True
    assert result["impacted"] == 1
    monkeypatch.undo()


def test_poll_all_vendors_skips_disabled(monkeypatch):
    captured = []

    def fake_run_detection(slug):
        captured.append(slug)
        return {"vendor": slug, "breaking_count": 0}

    def fake_vendor(slug):
        return SimpleNamespace(slug=slug, enabled=(slug != "twilio"))

    monkeypatch.setattr(tasks, "run_detection", fake_run_detection)
    monkeypatch.setattr(
        tasks, "list_vendors", lambda settings: [fake_vendor("github"), fake_vendor("twilio")]
    )
    monkeypatch.setattr(tasks, "get_settings", lambda: make_settings())

    summary = tasks.poll_all_vendors()

    assert captured == ["github"]
    assert "twilio" not in summary
    assert summary["github"]["breaking_count"] == 0
