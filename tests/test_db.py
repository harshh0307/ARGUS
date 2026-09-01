from app.db.engine import get_engine, init_db, session_factory
from app.db.models import DetectionRun, SpecSnapshot, Vendor
from app.db.repository import (
    open_session,
    persist_detection,
    record_snapshot,
    set_default_engine,
)
from app.detection.models import BREAKING, Change
from app.registry.vendors import Vendor as VendorSpec


def test_models_create_and_query(tmp_path):
    url = f"sqlite:///{tmp_path / 'argus.db'}"
    engine = get_engine(url)
    init_db(engine)
    session = session_factory(engine)()

    session.add(Vendor(slug="github", name="GitHub REST API", spec_url="https://s"))
    session.add(
        SpecSnapshot(vendor_slug="github", digest="abc123", etag='"ethag"')
    )
    session.add(
        DetectionRun(
            vendor_slug="github",
            old_digest="old12",
            new_digest="new12",
            breaking_count=1,
            additive_count=0,
            changes=[{"kind": "endpoint_removed", "severity": "breaking"}],
        )
    )
    session.commit()

    assert session.get(Vendor, "github").name == "GitHub REST API"
    snapshots = session.query(SpecSnapshot).all()
    assert len(snapshots) == 1
    assert snapshots[0].digest == "abc123"
    runs = session.query(DetectionRun).all()
    assert len(runs) == 1
    assert runs[0].breaking_count == 1
    session.close()


def test_persist_detection_writes_vendor_and_run(tmp_path):
    url = f"sqlite:///{tmp_path / 'argus.db'}"
    set_default_engine(get_engine(url))

    class FakeSettings:
        database_url = url

    spec = VendorSpec(
        slug="stripe",
        name="Stripe",
        spec_url="https://stripe",
    )
    result = {
        "old_digest": "o",
        "new_digest": "n",
        "breaking_count": 2,
        "additive_count": 1,
        "changes": [
            Change("endpoint_removed", BREAKING, "/v1/x", "post"),
            Change("schema_property_added", "additive", "/v1/x", "get"),
        ],
    }

    run = persist_detection(FakeSettings(), "stripe", result, spec)

    assert run is not None
    session = open_session(FakeSettings())
    vendor = session.get(Vendor, "stripe")
    assert vendor is not None
    assert vendor.name == "Stripe"
    rows = session.query(DetectionRun).filter_by(vendor_slug="stripe").all()
    assert len(rows) == 1
    assert rows[0].breaking_count == 2
    session.close()


def test_record_snapshot_deduplicates(tmp_path):
    url = f"sqlite:///{tmp_path / 'argus.db'}"
    engine = get_engine(url)
    init_db(engine)
    session = session_factory(engine)()
    session.add(Vendor(slug="twilio", name="Twilio", spec_url="https://t"))
    session.commit()

    record_snapshot(session, "twilio", "digest1", etag='"e1"')
    session.commit()
    record_snapshot(session, "twilio", "digest1", etag='"e1"')
    session.commit()

    assert session.query(SpecSnapshot).count() == 1
    session.close()