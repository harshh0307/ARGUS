FINTECH_DRIFT_RULES = {
    "plaid": {
        "schema_fields": {
            "accounts": {"account_id", "balances", "name", "type", "subtype"},
            "transactions": {"transaction_id", "amount", "date", "name", "pending"},
            "auth": {"account_id", "routing", "account"},
        },
        "breaking_patterns": [
            "field_removed:/accounts/*/balances/available",
            "field_renamed:account_id->id",
            "type_changed:amount from number to string",
        ],
    },
    "stripe": {
        "schema_fields": {
            "charges": {"id", "amount", "currency", "status", "customer"},
            "payment_intents": {"id", "amount", "status", "client_secret"},
            "customers": {"id", "email", "name", "metadata"},
        },
        "breaking_patterns": [
            "field_removed:charges/*/paid",
            "enum_value_removed:status->succeeded",
            "type_changed:amount from integer to string",
        ],
    },
    "dwolla": {
        "schema_fields": {
            "transfers": {"id", "amount", "status", "_links"},
            "customers": {"id", "firstName", "lastName", "email"},
            "funding_sources": {"id", "name", "type", "balance"},
        },
        "breaking_patterns": [
            "link_removed:_links/self",
            "field_renamed:firstName->first_name",
            "status_value_removed:pending",
        ],
    },
}
