from __future__ import annotations

from pydantic import BaseModel

from app.core.config import Settings


class Vendor(BaseModel):
    slug: str
    name: str
    enabled: bool = True
    fix_guidance: str | None = None
    fix_model: str | None = None
    # Investigation Layer
    changelog_urls: list[str] = []
    docs_url: str | None = None
    rss_url: str | None = None
    # Telemetry Layer
    base_api_url: str | None = None
    critical_endpoints: list[str] = []
    field_watch: list[str] = []


BUILTIN_VENDORS: dict[str, Vendor] = {
    "stripe": Vendor(
        slug="stripe",
        name="Stripe",
        base_api_url="https://api.stripe.com",
        changelog_urls=["https://stripe.com/blog/changelog"],
        docs_url="https://stripe.com/docs/api",
        rss_url="https://stripe.com/blog/feed.rss",
        critical_endpoints=["/v1/charges", "/v1/customers", "/v1/payment_intents"],
        field_watch=["status", "amount", "currency"],
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
    "plaid": Vendor(
        slug="plaid",
        name="Plaid",
        base_api_url="https://production.plaid.com",
        changelog_urls=["https://plaid.com/docs/api/updates/"],
        docs_url="https://plaid.com/docs/api/",
        critical_endpoints=["/accounts/get", "/transactions/get", "/auth/get"],
        field_watch=["account_id", "balance", "transactions"],
        fix_guidance=(
            "Plaid uses versioning via the Plaid-Version header. "
            "When migrating: (1) Update the Plaid-Version header. "
            "(2) Use the official Python SDK instead of raw HTTP. "
            "Example: client.accounts_get({'access_token': ...}) instead of requests.post(...)"
        ),
    ),
    "dwolla": Vendor(
        slug="dwolla",
        name="Dwolla",
        base_api_url="https://api.dwolla.com",
        changelog_urls=["https://docs.dwolla.com/"],
        docs_url="https://docs.dwolla.com/",
        critical_endpoints=["/transfers", "/customers", "/funding-sources"],
        field_watch=["_links", "status", "amount"],
        fix_guidance=(
            "Dwolla uses HATEOAS links. When migrating: (1) Follow the _links structure. "
            "(2) Use the official Dwolla SDK instead of raw HTTP. "
            "Check the _links.self.href for resource URLs."
        ),
    ),
    "twilio": Vendor(
        slug="twilio",
        name="Twilio",
        base_api_url="https://api.twilio.com",
        changelog_urls=["https://www.twilio.com/changelog"],
        docs_url="https://www.twilio.com/docs/usage/api",
        critical_endpoints=["/2010-04-01/Accounts", "/Messages.json"],
        field_watch=["sid", "status", "body"],
        fix_guidance=(
            "Twilio uses account SIDs in URI paths under /2010-04-01/Accounts/{AccountSid}. "
            "When migrating: (1) Update the URI pattern if the endpoint changed. "
            "(2) Use the Twilio helper library's typed methods: "
            "client.messages.create(to=..., from_=..., body=...) instead of raw HTTP."
        ),
    ),
    "slack": Vendor(
        slug="slack",
        name="Slack",
        base_api_url="https://slack.com/api",
        changelog_urls=["https://api.slack.com/changelog"],
        docs_url="https://api.slack.com/docs",
        critical_endpoints=["/chat.postMessage", "/conversations.list"],
        field_watch=["ok", "error", "channel"],
        fix_guidance=(
            "Slack Web API uses method-based routing (POST to /method-name). "
            "When migrating: (1) Update the method name in the POST body. "
            "(2) Use the official Slack SDK: slack_sdk.WebClient(token=...).chat_postMessage(...) "
            "instead of raw HTTP."
        ),
    ),
    "aws": Vendor(
        slug="aws",
        name="AWS",
        changelog_urls=[],
        docs_url="https://docs.aws.amazon.com/",
        fix_guidance=(
            "Use the AWS SDK for Python (boto3) with service-specific clients. "
            "When endpoints change: (1) Update boto3 version: pip install --upgrade boto3. "
            "(2) Use the new client method: s3 = boto3.client('s3'); s3.get_object(...)."
        ),
    ),
    "azure": Vendor(
        slug="azure",
        name="Azure",
        changelog_urls=[],
        docs_url="https://docs.microsoft.com/azure/",
        fix_guidance=(
            "Use the Azure SDK for Python (azure-*) with service-specific clients. "
            "When API versions change: (1) Update the api_version parameter. "
            "(2) Use the new client method: client.get_incidents(...)."
        ),
    ),
    "google_cloud": Vendor(
        slug="google_cloud",
        name="Google Cloud",
        changelog_urls=[],
        docs_url="https://cloud.google.com/docs",
        fix_guidance=(
            "Use the Google Cloud client library (google-cloud-*). "
            "When APIs change: (1) Update the client library. "
            "(2) Use the new client method: client.access_secret_version(name=...)."
        ),
    ),
}


def get_vendor(settings: Settings, slug: str = "github") -> Vendor:
    if slug == "github":
        return Vendor(
            slug="github",
            name="GitHub REST API",
            base_api_url="https://api.github.com",
            changelog_urls=["https://docs.github.com/en/rest/changelog"],
            docs_url="https://docs.github.com/en/rest",
            critical_endpoints=["/repos", "/pulls", "/issues"],
            field_watch=["id", "status", "node_id"],
            fix_guidance=(
                "GitHub REST API uses versioning via the Accept header "
                "(X-GitHub-Api-Version: 2022-11-28). When migrating: "
                "(1) Update the endpoint path if it changed. "
                "(2) Consider using PyGithub for typed access."
            ),
        )
    try:
        return BUILTIN_VENDORS[slug]
    except KeyError as exc:
        known = ", ".join(sorted(BUILTIN_VENDORS) + ["github"])
        raise ValueError(f"unknown vendor {slug!r}; known vendors: {known}") from exc


def list_vendors(settings: Settings) -> list[Vendor]:
    return [get_vendor(settings, "github"), *BUILTIN_VENDORS.values()]
