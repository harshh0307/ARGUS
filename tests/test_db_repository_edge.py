from datetime import UTC

from app.db.engine import get_engine, init_db, session_factory
from app.db.models import Repository, Vendor
from app.db.repository import (
    list_active_repositories,
    list_installations,
    record_detection_run,
    record_snapshot,
    touch_repository,
    upsert_app_installation,
    upsert_repository,
    upsert_vendor,
)
from app.detection.models import ADDITIVE, BREAKING, Change
from app.registry.vendors import Vendor as VendorSpec


def make_session(tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path / 'repo.db'}")
    init_db(engine)
    return session_factory(engine)()


def test_upsert_repository_creates_then_updates(tmp_path):
    session = make_session(tmp_path)
    row = upsert_repository(session, "acme", "web", "main", "github")
    session.commit()
    created_at = row.created_at
    assert row.id > 0

    again = upsert_repository(session, "acme", "web", "develop", "stripe")
    session.commit()

    assert again.id == row.id
    assert again.default_branch == "develop"
    assert again.vendor_slug == "stripe"
    assert again.created_at == created_at
    assert session.query(Repository).count() == 1
    session.close()


def test_upsert_repository_keeps_defaults_when_none_passed(tmp_path):
    session = make_session(tmp_path)
    upsert_repository(session, "acme", "web", "main", "github")
    session.commit()
    again = upsert_repository(session, "acme", "web", None, "github")
    assert again.default_branch == "main"
    session.close()


def test_list_active_repositories_filters_inactive(tmp_path):
    session = make_session(tmp_path)
    session.add(Repository(owner="a", name="one", is_active=True))
    session.add(Repository(owner="b", name="two", is_active=False))
    session.commit()

    rows = list_active_repositories(session)
    assert [r.name for r in rows] == ["one"]
    session.close()


def test_touch_repository_sets_last_run_at(tmp_path):
    session = make_session(tmp_path)
    repo = Repository(owner="a", name="one")
    session.add(repo)
    session.commit()
    assert repo.last_run_at is None

    touch_repository(session, repo)
    session.commit()

    assert repo.last_run_at is not None
    assert repo.last_run_at.tzinfo is UTC
    session.close()


def test_upsert_app_installation_inserts_then_updates(tmp_path):
    session = make_session(tmp_path)
    first = upsert_app_installation(session, 42, "acme", is_active=True)
    session.commit()

    second = upsert_app_installation(session, 42, "renamed", is_active=False)
    session.commit()

    assert second.id == first.id
    assert second.owner == "renamed"
    assert second.is_active is False
    assert len(list_installations(session)) == 1
    session.close()


def test_upsert_vendor_updates_existing_row(tmp_path):
    session = make_session(tmp_path)
    session.add(Vendor(slug="stripe", name="Stripe", spec_url="https://old"))
    session.commit()

    spec = VendorSpec(
        slug="stripe",
        name="Stripe API",
        spec_url="https://new",
        old_spec_url="https://old-url",
        poll_interval_seconds=3600,
        enabled=False,
    )
    row = upsert_vendor(session, spec)
    session.commit()

    assert row.name == "Stripe API"
    assert row.spec_url == "https://new"
    assert row.old_spec_url == "https://old-url"
    assert row.poll_interval_seconds == 3600
    assert row.enabled is False
    assert session.query(Vendor).count() == 1
    session.close()


def test_record_detection_run_maps_changes(tmp_path):
    session = make_session(tmp_path)
    session.add(Vendor(slug="github", name="GitHub", spec_url="https://s"))
    session.commit()

    changes = [
        Change("endpoint_removed", BREAKING, "/users/{id}", "delete", "gone"),
        Change("endpoint_added", ADDITIVE, "/orgs", "post", "new"),
    ]
    run = record_detection_run(
        session,
        "github",
        {
            "old_digest": "old1",
            "new_digest": "new1",
            "breaking_count": 1,
            "additive_count": 1,
            "changes": changes,
        },
    )
    session.commit()

    assert run.old_digest == "old1"
    assert run.new_digest == "new1"
    assert run.breaking_count == 1
    assert run.additive_count == 1
    assert run.changes[0]["kind"] == "endpoint_removed"
    assert run.changes[0]["severity"] == "breaking"
    assert run.changes[1]["path"] == "/orgs"
    session.close()


def test_record_detection_run_defaults_counts(tmp_path):
    session = make_session(tmp_path)
    session.add(Vendor(slug="github", name="GitHub", spec_url="https://s"))
    session.commit()
    run = record_detection_run(session, "github", {"new_digest": "n", "changes": []})
    assert run.breaking_count == 0
    assert run.additive_count == 0
    session.close()


def test_record_snapshot_returns_existing_row(tmp_path):
    session = make_session(tmp_path)
    session.add(Vendor(slug="x", name="X", spec_url="https://s"))
    session.commit()
    first = record_snapshot(session, "x", "digest", etag='"e"')
    second = record_snapshot(session, "x", "digest", etag='"e2"')
    assert first.id == second.id
    assert second.etag == '"e"'
    session.close()