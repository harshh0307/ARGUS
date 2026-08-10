from app.core.config import Settings
from app.registry.vendors import BUILTIN_VENDORS, get_vendor, list_vendors


def test_github_vendor_uses_settings_urls():
    settings = Settings(
        github_spec_url="https://new",
        github_old_spec_url="https://old",
        snapshot_dir="data/snapshots",
    )
    vendor = get_vendor(settings, "github")
    assert vendor.slug == "github"
    assert vendor.spec_url == "https://new"
    assert vendor.old_spec_url == "https://old"


def test_builtin_vendors_registered():
    settings = Settings(snapshot_dir="data/snapshots")
    slugs = [v.slug for v in list_vendors(settings)]
    assert "github" in slugs
    for slug in ("stripe", "twilio"):
        assert slug in BUILTIN_VENDORS


def test_unknown_vendor_raises():
    settings = Settings(snapshot_dir="data/snapshots")
    try:
        get_vendor(settings, "nope")
    except ValueError as exc:
        assert "unknown vendor" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_vendor_has_poll_interval_default():
    settings = Settings(snapshot_dir="data/snapshots")
    stripe = get_vendor(settings, "stripe")
    assert stripe.poll_interval_seconds >= 60
    assert stripe.enabled is True