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
    spec_format: str = "json"


BUILTIN_VENDORS: dict[str, Vendor] = {
    "stripe": Vendor(
        slug="stripe",
        name="Stripe",
        spec_url="https://raw.githubusercontent.com/stripe/openapi/master/openapi/spec3.json",
        fix_guidance=(
            "Stripe uses API versioning via the Stripe-Version header. "
            "When migrating: (1) Update the API version in your Stripe config, "
            "e.g. stripe.api_version = '2024-12-18'. (2) Endpoints rarely change; "
            "the version header controls response shapes. (3) Use the official "
            "Stripe SDK: stripe.Customer.create({...}) instead of raw HTTP. "
            "Example migration: requests.post('https://api.stripe.com/v1/customers', ...) "
            "-> stripe.Customer.create({...})"
        ),
    ),
    "twilio": Vendor(
        slug="twilio",
        name="Twilio",
        spec_url="https://raw.githubusercontent.com/twilio/twilio-oai/main/spec/json/twilio_api_v2010.json",
        fix_guidance=(
            "Twilio uses account SIDs in URI paths under /2010-04-01/Accounts/{AccountSid}. "
            "When migrating: (1) Update the URI pattern if the endpoint changed. "
            "(2) Use the Twilio helper library's typed methods: "
            "client.messages.create(to=..., from_=..., body=...) instead of raw HTTP. "
            "Example migration: requests.post(f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json', ...) "
            "-> client.messages.create(to=..., from_=..., body=...)"
        ),
    ),
    "slack": Vendor(
        slug="slack",
        name="Slack",
        spec_url="https://raw.githubusercontent.com/slackapi/slack-api-specs/master/web-api/slack_web_api_openapi.json",
        fix_guidance=(
            "Slack Web API uses method-based routing (POST to /method-name). "
            "When migrating: (1) Update the method name in the POST body. "
            "(2) Use the official Slack SDK: slack_sdk.WebClient(token=...).chat_postMessage(...) "
            "instead of raw HTTP. "
            "Example migration: requests.post('https://slack.com/api/chat.postMessage', json={...}) "
            "-> client.chat_postMessage(channel=..., text=...)"
        ),
    ),
    "aws": Vendor(
        slug="aws",
        name="AWS",
        spec_url="https://raw.githubusercontent.com/awslabs/smithy/main/smithy-aws-protocol-tests/main/resources/airy-aws/restJson1.json",
        fix_guidance=(
            "Use the AWS SDK for Python (boto3) with service-specific clients. "
            "When endpoints change: (1) Update boto3 version: pip install --upgrade boto3. "
            "(2) Use the new client method: s3 = boto3.client('s3'); s3.get_object(...). "
            "Avoid raw HTTP calls to AWS APIs."
        ),
    ),
    "azure": Vendor(
        slug="azure",
        name="Azure",
        spec_url="https://raw.githubusercontent.com/Azure/azure-rest-api-specs/main/specification/securityinsights/data-plane/Microsoft.SecurityInsights/stable/2024-01-01/SecurityInsights.json",
        fix_guidance=(
            "Use the Azure SDK for Python (azure-*) with service-specific clients. "
            "When API versions change: (1) Update the api_version parameter. "
            "(2) Use the new client method: client.get_incidents(...) instead of raw HTTP. "
            "Example migration: requests.get('https://management.azure.com/...', headers={...}) "
            "-> client.get_incidents(workspace_name=...)"
        ),
    ),
    "google_cloud": Vendor(
        slug="google_cloud",
        name="Google Cloud",
        spec_url="https://raw.githubusercontent.com/googleapis/googleapis/main/google/cloud/secretmanager/v1/secretmanager_v1.json",
        fix_guidance=(
            "Use the Google Cloud client library (google-cloud-*). "
            "When APIs change: (1) Update the client library: pip install --upgrade google-cloud-secretmanager. "
            "(2) Use the new client method: client.access_secret_version(name=...). "
            "Avoid raw HTTP calls to Google Cloud APIs."
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
                "GitHub REST API uses versioning via the Accept header "
                "(X-GitHub-Api-Version: 2022-11-28). When migrating: "
                "(1) Update the endpoint path if it changed. "
                "(2) Use the requests library with the correct headers: "
                "requests.get('https://api.github.com/...', headers={'Accept': 'application/vnd.github+json', "
                "'X-GitHub-Api-Version': '2022-11-28'}). "
                "(3) Consider using PyGithub for typed access: "
                "from github import Github; g = Github(token); repo = g.get_repo('owner/repo')."
            ),
        )
    try:
        return BUILTIN_VENDORS[slug]
    except KeyError as exc:
        known = ", ".join(sorted(BUILTIN_VENDORS) + ["github"])
        raise ValueError(f"unknown vendor {slug!r}; known vendors: {known}") from exc


def list_vendors(settings: Settings) -> list[Vendor]:
    return [get_vendor(settings, "github"), *BUILTIN_VENDORS.values()]
