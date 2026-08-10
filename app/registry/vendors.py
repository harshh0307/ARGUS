from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.config import Settings


class Vendor(BaseModel):
    slug: str
    name: str
    spec_url: str
    old_spec_url: str | None = None
    poll_interval_seconds: int = Field(default=6 * 60 * 60, ge=60)
    enabled: bool = True


BUILTIN_VENDORS: dict[str, Vendor] = {
    "stripe": Vendor(
        slug="stripe",
        name="Stripe",
        spec_url="https://raw.githubusercontent.com/stripe/openapi/master/openapi/spec3.json",
    ),
    "twilio": Vendor(
        slug="twilio",
        name="Twilio",
        spec_url="https://raw.githubusercontent.com/twilio/twilio-oai/main/spec/json/twilio_api_v2010.json",
    ),
}


def get_vendor(settings: Settings, slug: str = "github") -> Vendor:
    if slug == "github":
        return Vendor(
            slug="github",
            name="GitHub REST API",
            spec_url=settings.github_spec_url,
            old_spec_url=settings.github_old_spec_url,
        )
    try:
        return BUILTIN_VENDORS[slug]
    except KeyError as exc:
        known = ", ".join(sorted(BUILTIN_VENDORS) + ["github"])
        raise ValueError(f"unknown vendor {slug!r}; known vendors: {known}") from exc


def list_vendors(settings: Settings) -> list[Vendor]:
    return [get_vendor(settings, "github"), *BUILTIN_VENDORS.values()]