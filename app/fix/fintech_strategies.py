from __future__ import annotations

from app.fix.strategies import FixStrategy, register_strategy


def register_fintech_strategies() -> None:
    register_strategy(FixStrategy(
        kind="auth_changed",
        pattern=r'headers\[["\']Plaid-Version["\']\]\s*=\s*["\'][^"\']+["\']',
        replacement_template='headers["Plaid-Version"] = "{new_version}"',
        prompt_instructions="Update Plaid-Version header to the new API version",
    ))

    register_strategy(FixStrategy(
        kind="schema_field_renamed",
        pattern=r'\[["\']account_id["\']\]',
        replacement_template='["{new_field}"]',
        prompt_instructions="Rename field to match Plaid's new response schema",
    ))

    register_strategy(FixStrategy(
        kind="auth_changed",
        pattern=r'stripe\.api_version\s*=\s*["\'][^"\']+["\']',
        replacement_template='stripe.api_version = "{new_version}"',
        prompt_instructions="Update Stripe API version",
    ))

    register_strategy(FixStrategy(
        kind="response结构调整",
        pattern=r'\[["\']_links["\']\]\[["\']self["\']\]',
        replacement_template='["_links"]["{new_link}"]',
        prompt_instructions="Update Dwolla HATEOAS link following",
    ))

    register_strategy(FixStrategy(
        kind="error_code_changed",
        pattern=r'["\']ITEM_NOT_FOUND["\']',
        replacement_template='"{new_error_code}"',
        prompt_instructions="Update error code to match new Plaid error taxonomy",
    ))

    register_strategy(FixStrategy(
        kind="error_code_changed",
        pattern=r'["\']resource_missing["\']',
        replacement_template='"{new_error_code}"',
        prompt_instructions="Update Stripe error code",
    ))


register_fintech_strategies()
