from app.core.config import Settings
from app.registry.vendors import BUILTIN_VENDORS, get_vendor, list_vendors


def test_github_vendor_has_base_api_url():
    settings = Settings()
    vendor = get_vendor(settings, "github")
    assert vendor.slug == "github"
    assert vendor.base_api_url == "https://api.github.com"


def test_builtin_vendors_registered():
    settings = Settings()
    slugs = [v.slug for v in list_vendors(settings)]
    assert "github" in slugs
    for slug in ("stripe", "plaid", "dwolla", "twilio"):
        assert slug in BUILTIN_VENDORS


def test_unknown_vendor_raises():
    settings = Settings()
    try:
        get_vendor(settings, "nope")
    except ValueError as exc:
        assert "unknown vendor" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_vendor_has_fix_guidance():
    settings = Settings()
    stripe = get_vendor(settings, "stripe")
    assert stripe.fix_guidance is not None
    assert stripe.enabled is True


def test_vendor_has_changelog_urls():
    settings = Settings()
    stripe = get_vendor(settings, "stripe")
    assert len(stripe.changelog_urls) > 0


def test_fintech_vendors_present():
    settings = Settings()
    slugs = [v.slug for v in list_vendors(settings)]
    assert "plaid" in slugs
    assert "dwolla" in slugs
