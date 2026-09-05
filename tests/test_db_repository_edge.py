from datetime import UTC

from app.db.engine import get_engine, init_db, session_factory
from app.db.models import Repository, Vendor
from app.db.repository import (
    create_drift_alert,
    list_active_repositories,
    list_installations,
    touch_repository,
    upsert_app_installation,
    upsert_repository,
    upsert_vendor,
)
from app.scan.models import DriftSignal
from app.registry.vendors import Vendor as VendorSpec


def make_session(tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path / 'repo.db'}")
    init_db(engine)
    return session_factory(engine)()


def test_upsert_repository_creates_then_updates(tmp_path):
    session = make_session(tmp_path)
    row = upsert_repository(session, "acme", "web", "main", git_provider="github", vendor_slug="github")
    session.commit()
    created_at = row.created_at
    assert row.id > 0

    again = upsert_repository(session, "acme", "web", "develop", git_provider="stripe", vendor_slug="stripe")
    session.commit()

    assert again.id == row.id
    assert again.default_branch == "develop"
    assert again.vendor_slug == "stripe"
    assert again.created_at == created_at
    assert session.query(Repository).count() == 1
    session.close()


def test_upsert_repository_keeps_defaults_when_none_passed(tmp_path):
    session = make_session(tmp_path)
    upsert_repository(session, "acme", "web", "main", git_provider="github")
    session.commit()
    again = upsert_repository(session, "acme", "web", None, git_provider="github")
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
    session.add(Vendor(slug="stripe", name="Stripe"))
    session.commit()

    spec = VendorSpec(
        slug="stripe",
        name="Stripe API",
        enabled=False,
    )
    row = upsert_vendor(session, spec)
    session.commit()

    assert row.name == "Stripe API"
    assert row.enabled is False
    assert session.query(Vendor).count() == 1
    session.close()


def test_create_drift_alert_stores_details(tmp_path):
    session = make_session(tmp_path)
    session.add(Vendor(slug="github", name="GitHub"))
    session.commit()

    alert = create_drift_alert(
        session,
        vendor_slug="github",
        alert_type="endpoint_removed",
        severity="breaking",
        details={
            "old_digest": "old1",
            "new_digest": "new1",
            "breaking_count": 1,
            "additive_count": 1,
        },
        endpoint="/users/{id}",
    )
    session.commit()

    assert alert.vendor_slug == "github"
    assert alert.alert_type == "endpoint_removed"
    assert alert.severity == "breaking"
    assert alert.endpoint == "/users/{id}"
    assert alert.details["breaking_count"] == 1
    session.close()


def test_create_drift_alert_defaults(tmp_path):
    session = make_session(tmp_path)
    session.add(Vendor(slug="github", name="GitHub"))
    session.commit()
    alert = create_drift_alert(
        session,
        vendor_slug="github",
        alert_type="info",
        severity="info",
        details={"message": "test"},
    )
    session.commit()
    assert alert.severity == "info"
    assert alert.resolved is False
    session.close()
