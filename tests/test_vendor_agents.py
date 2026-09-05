from types import SimpleNamespace

from app.fix.agent import build_suggestion_model
from app.fix.prompt import build_prompt
from app.registry.vendors import get_vendor, list_vendors


def make_settings(**overrides):
    defaults = {
        "llm_model": "gpt-4o-mini",
        "llm_base_url": None,
        "gemini_api_key": "gem-key",
        "openai_api_key": None,
        "openrouter_api_key": "or-key",
        "openrouter_model": "fallback-model",
        "api_base_url": "https://api.github.com",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def impact_dict():
    return {
        "file": "app.py",
        "line": 5,
        "method": "get",
        "path": "/repos/x",
        "change_kind": "endpoint_removed",
        "change_severity": "breaking",
        "change_path": "/repos/x",
        "change_detail": "endpoint is no longer documented",
        "language": "py",
    }


def test_vendors_carry_fix_guidance():
    settings = make_settings()
    slugs = {v.slug for v in list_vendors(settings)}
    assert "github" in slugs
    assert "stripe" in slugs
    assert "plaid" in slugs
    assert "dwolla" in slugs
    for slug in slugs:
        vendor = get_vendor(settings, slug)
        assert vendor.fix_guidance, f"{slug} should carry fix guidance"


def test_prompt_includes_vendor_guidance():
    prompt = build_prompt(
        impact_dict(),
        "app.py",
        "1: resp = requests.get('/repos/x')\n",
        language="py",
        vendor_guidance="Stripe migrates via API versioning.",
    )
    assert "Stripe migrates via API versioning." in prompt
    assert "Return valid Python." in prompt


def test_prompt_omits_vendor_section_when_absent():
    prompt = build_prompt(impact_dict(), "app.py", "1: x\n", language="py")
    assert "Vendor migration guidance" not in prompt


def test_prompt_language_hint_js():
    prompt = build_prompt(
        impact_dict(), "app.js", "1: fetch('/repos/x')\n", language="js"
    )
    assert "Return valid JavaScript/TypeScript." in prompt


def test_build_suggestion_model_uses_default_model():
    model = build_suggestion_model(make_settings())
    assert model._model_name == "gpt-4o-mini"


def test_build_suggestion_model_unknown_vendor_uses_default():
    model = build_suggestion_model(make_settings(), vendor_slug="not-a-vendor")
    assert model._model_name == "gpt-4o-mini"


def test_build_suggestion_model_custom_vendor_model():
    from app.fix.agent import SuggestionModel

    model = build_suggestion_model(
        make_settings(),
        vendor_slug="github",
    )
    assert isinstance(model, SuggestionModel)
