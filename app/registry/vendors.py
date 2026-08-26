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
    fix_guidance: str | None = None
    fix_model: str | None = None


BUILTIN_VENDORS: dict[str, Vendor] = {
    "stripe": Vendor(
        slug="stripe",
        name="Stripe",
        spec_url="https://raw.githubusercontent.com/stripe/openapi/master/openapi/spec3.json",
        fix_guidance=(
            "Stripe migrates via API versioning: prefer the new version's "
            "endpoints and payload shapes. List/object responses come from "
            "stripe.api_key and typed Stripe SDK helpers when available."
        ),
    ),
    "twilio": Vendor(
        slug="twilio",
        name="Twilio",
        spec_url="https://raw.githubusercontent.com/twilio/twilio-oai/main/spec/json/twilio_api_v2010.json",
        fix_guidance=(
            "Twilio's API uses account SIDs and subresource URIs under "
            "/2010-04-01/Accounts/{AccountSid}. Prefer the Twilio SDK's "
            "typed client methods over raw HTTP calls when migrating."
        ),
    ),
    "slack": Vendor(
        slug="slack",
        name="Slack",
        spec_url="https://raw.githubusercontent.com/slackapi/slack-api-specs/master/web-api/slack_web_api_openapi.json",
        fix_guidance=(
            "Slack's Web API uses token-based auth and method-based routing. "
            "Migrate deprecated methods to their replacement endpoints. "
            "Prefer the official Slack SDKs over raw HTTP calls."
        ),
    ),
    "aws": Vendor(
        slug="aws",
        name="AWS",
        spec_url="https://raw.githubusercontent.com/awslabs/smithy/main/smithy-aws-protocol-tests/main/resources/airy-aws/restJson1.json",
        fix_guidance=(
            "AWS APIs use AWS SDKs with service-specific clients. "
            "When endpoints change, update the SDK version and use the new "
            "client methods. Avoid raw HTTP calls to AWS APIs."
        ),
    ),
    "azure": Vendor(
        slug="azure",
        name="Azure",
        spec_url="https://raw.githubusercontent.com/Azure/azure-rest-api-specs/main/specification/securityinsights/data-plane/Microsoft.SecurityInsights/stable/2024-01-01/SecurityInsights.json",
        fix_guidance=(
            "Azure APIs use Azure SDKs with service-specific clients. "
            "When API versions change, update the SDK and use the new "
            "client methods. Prefer Azure SDK over raw HTTP calls."
        ),
    ),
    "google_cloud": Vendor(
        slug="google_cloud",
        name="Google Cloud",
        spec_url="https://raw.githubusercontent.com/googleapis/googleapis/main/google/cloud/secretmanager/v1/secretmanager_v1.json",
        fix_guidance=(
            "Google Cloud APIs use Google Cloud client libraries. "
            "When APIs change, update the client library version. "
            "Prefer the official Google Cloud SDKs over raw HTTP calls."
        ),
    ),
}


def get_vendor(settings: Settings, slug: str = "github") -> Vendor:
    if slug == "github":
        spec_url = getattr(settings, "github_spec_url", None)
        old_spec_url = getattr(settings, "github_old_spec_url", None)
        if spec_url is None:
            raise ValueError("GITHUB_SPEC_URL is not set in settings")
        return Vendor(
            slug="github",
            name="GitHub REST API",
            spec_url=spec_url,
            old_spec_url=old_spec_url,
            fix_guidance=(
                "GitHub REST API: some endpoints are removed in favor of "
                "GraphQL or newer REST routes. If the endpoint was removed, "
                "migrate to its documented replacement when one exists."
            ),
        )
    try:
        return BUILTIN_VENDORS[slug]
    except KeyError as exc:
        known = ", ".join(sorted(BUILTIN_VENDORS) + ["github"])
        raise ValueError(f"unknown vendor {slug!r}; known vendors: {known}") from exc


def list_vendors(settings: Settings) -> list[Vendor]:
    return [get_vendor(settings, "github"), *BUILTIN_VENDORS.values()]