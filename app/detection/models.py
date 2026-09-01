from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

BREAKING = "breaking"
ADDITIVE = "additive"
DEPRECATION = "deprecation"
WARNING = "warning"


class ChangeCategory(str, Enum):
    """High-level category for grouping related change kinds."""

    ENDPOINT = "endpoint"
    OPERATION = "operation"
    PARAMETER = "parameter"
    REQUEST_BODY = "request_body"
    RESPONSE = "response"
    SCHEMA = "schema"
    SCHEMA_CONSTRAINT = "schema_constraint"
    SCHEMA_COMPOSITION = "schema_composition"
    SERVER = "server"
    SECURITY = "security"
    INFO = "info"
    COMPONENT = "component"
    WEBHOOK = "webhook"
    TAG = "tag"
    REF = "ref"


class ChangeKind(str, Enum):
    """Machine-readable identifier for every possible API spec change.

    Organized by category. Each member maps to exactly one
    ``ChangeCategory`` via ``_CATEGORY_MAP``.
    """

    # ── Endpoint (4) ────────────────────────────────────────────────
    ENDPOINT_ADDED = "endpoint_added"
    ENDPOINT_REMOVED = "endpoint_removed"
    HTTP_METHOD_ADDED = "http_method_added"
    HTTP_METHOD_REMOVED = "http_method_removed"

    # ── Operation (12) ──────────────────────────────────────────────
    OPERATION_DEPRECATED = "operation_deprecated"
    OPERATION_UNDEPRECATED = "operation_undeprecated"
    OPERATION_ID_CHANGED = "operation_id_changed"
    OPERATION_ID_ADDED = "operation_id_added"
    OPERATION_ID_REMOVED = "operation_id_removed"
    OPERATION_SUMMARY_CHANGED = "operation_summary_changed"
    OPERATION_DESCRIPTION_CHANGED = "operation_description_changed"
    OPERATION_TAGS_CHANGED = "operation_tags_changed"
    OPERATION_SECURITY_ADDED = "operation_security_added"
    OPERATION_SECURITY_REMOVED = "operation_security_removed"
    OPERATION_SECURITY_CHANGED = "operation_security_changed"
    SUNSET_DATE = "sunset_date"

    # ── Method Change (2) ───────────────────────────────────────────
    METHOD_CHANGED = "method_changed"
    CONTENT_TYPE_CHANGED = "content_type_changed"

    # ── Parameters (16) ─────────────────────────────────────────────
    PARAM_ADDED = "param_added"
    PARAM_REMOVED = "param_removed"
    PARAM_REQUIRED = "param_required"
    PARAM_OPTIONAL = "param_optional"
    PARAM_TYPE_CHANGED = "param_type_changed"
    PARAM_FORMAT_CHANGED = "param_format_changed"
    PARAM_LOCATION_CHANGED = "param_location_changed"
    PARAM_DEPRECATED = "param_deprecated"
    PARAM_UNDEPRECATED = "param_undeprecated"
    PARAM_DESCRIPTION_CHANGED = "param_description_changed"
    PARAM_STYLE_CHANGED = "param_style_changed"
    PARAM_EXPLODE_CHANGED = "param_explode_changed"
    PARAM_ALLOW_EMPTY_VALUE_CHANGED = "param_allow_empty_value_changed"
    PARAM_DEFAULT_CHANGED = "param_default_changed"
    PARAM_EXAMPLE_CHANGED = "param_example_changed"
    PARAM_ENUM_CHANGED = "param_enum_changed"

    # ── Request Body (6) ────────────────────────────────────────────
    REQUEST_BODY_ADDED = "request_body_added"
    REQUEST_BODY_REMOVED = "request_body_removed"
    REQUEST_BODY_REQUIRED_CHANGED = "request_body_required_changed"
    REQUEST_CONTENT_TYPE_ADDED = "request_content_type_added"
    REQUEST_CONTENT_TYPE_REMOVED = "request_content_type_removed"
    REQUEST_BODY_SCHEMA_CHANGED = "request_body_schema_changed"

    # ── Response (12) ───────────────────────────────────────────────
    RESPONSE_CODE_ADDED = "response_code_added"
    RESPONSE_CODE_REMOVED = "response_code_removed"
    RESPONSE_DESCRIPTION_CHANGED = "response_description_changed"
    RESPONSE_CONTENT_TYPE_ADDED = "response_content_type_added"
    RESPONSE_CONTENT_TYPE_REMOVED = "response_content_type_removed"
    RESPONSE_SCHEMA_CHANGED = "response_schema_changed"
    RESPONSE_SCHEMA_ADDED = "response_schema_added"
    RESPONSE_SCHEMA_REMOVED = "response_schema_removed"
    RESPONSE_HEADER_ADDED = "response_header_added"
    RESPONSE_HEADER_REMOVED = "response_header_removed"
    RESPONSE_HEADER_CHANGED = "response_header_changed"
    RESPONSE_LINK_CHANGED = "response_link_changed"

    # ── Schema Core (20) ────────────────────────────────────────────
    SCHEMA_TYPE_CHANGED = "schema_type_changed"
    SCHEMA_FORMAT_CHANGED = "schema_format_changed"
    SCHEMA_PROPERTY_ADDED = "schema_property_added"
    SCHEMA_PROPERTY_REMOVED = "schema_property_removed"
    SCHEMA_PROPERTY_TYPE_CHANGED = "schema_property_type_changed"
    REQUIRED_FIELD_ADDED = "required_field_added"
    REQUIRED_FIELD_REMOVED = "required_field_removed"
    ENUM_VALUE_ADDED = "enum_value_added"
    ENUM_VALUE_REMOVED = "enum_value_removed"
    SCHEMA_NULLABLE_CHANGED = "schema_nullable_changed"
    SCHEMA_READ_ONLY_CHANGED = "schema_read_only_changed"
    SCHEMA_WRITE_ONLY_CHANGED = "schema_write_only_changed"
    SCHEMA_DEFAULT_CHANGED = "schema_default_changed"
    SCHEMA_DESCRIPTION_CHANGED = "schema_description_changed"
    SCHEMA_TITLE_CHANGED = "schema_title_changed"
    SCHEMA_DEPRECATED_CHANGED = "schema_deprecated_changed"
    SCHEMA_DISCRIMINATOR_CHANGED = "schema_discriminator_changed"
    SCHEMA_EXAMPLE_CHANGED = "schema_example_changed"
    ADDITIONAL_PROPERTIES_CHANGED = "additional_properties_changed"
    SCHEMA_EXAMPLES_CHANGED = "schema_examples_changed"

    # ── Schema Constraints (16) ─────────────────────────────────────
    SCHEMA_MIN_CHANGED = "schema_min_changed"
    SCHEMA_MAX_CHANGED = "schema_max_changed"
    SCHEMA_EXCLUSIVE_MIN_CHANGED = "schema_exclusive_min_changed"
    SCHEMA_EXCLUSIVE_MAX_CHANGED = "schema_exclusive_max_changed"
    SCHEMA_MIN_LENGTH_CHANGED = "schema_min_length_changed"
    SCHEMA_MAX_LENGTH_CHANGED = "schema_max_length_changed"
    SCHEMA_PATTERN_CHANGED = "schema_pattern_changed"
    SCHEMA_MIN_ITEMS_CHANGED = "schema_min_items_changed"
    SCHEMA_MAX_ITEMS_CHANGED = "schema_max_items_changed"
    SCHEMA_UNIQUE_ITEMS_CHANGED = "schema_unique_items_changed"
    SCHEMA_MIN_PROPERTIES_CHANGED = "schema_min_properties_changed"
    SCHEMA_MAX_PROPERTIES_CHANGED = "schema_max_properties_changed"
    SCHEMA_MULTIPLE_OF_CHANGED = "schema_multiple_of_changed"
    SCHEMA_CONTENT_MEDIA_TYPE_CHANGED = "schema_content_media_type_changed"
    SCHEMA_CONTENT_ENCODING_CHANGED = "schema_content_encoding_changed"
    SCHEMA_IF_THEN_ELSE_CHANGED = "schema_if_then_else_changed"

    # ── Schema Composition (12) ─────────────────────────────────────
    SCHEMA_ALLOF_ADDED = "schema_allof_added"
    SCHEMA_ALLOF_REMOVED = "schema_allof_removed"
    SCHEMA_ALLOF_SCHEMA_CHANGED = "schema_allof_schema_changed"
    SCHEMA_ONEOF_ADDED = "schema_oneof_added"
    SCHEMA_ONEOF_REMOVED = "schema_oneof_removed"
    SCHEMA_ONEOF_SCHEMA_CHANGED = "schema_oneof_schema_changed"
    SCHEMA_ANYOF_ADDED = "schema_anyof_added"
    SCHEMA_ANYOF_REMOVED = "schema_anyof_removed"
    SCHEMA_ANYOF_SCHEMA_CHANGED = "schema_anyof_schema_changed"
    SCHEMA_NOT_CHANGED = "schema_not_changed"
    SCHEMA_PREFIX_ITEMS_CHANGED = "schema_prefix_items_changed"
    SCHEMA_CONTAINS_CHANGED = "schema_contains_changed"

    # ── Servers (8) ─────────────────────────────────────────────────
    SERVER_ADDED = "server_added"
    SERVER_REMOVED = "server_removed"
    SERVER_URL_CHANGED = "server_url_changed"
    SERVER_DESCRIPTION_CHANGED = "server_description_changed"
    SERVER_VARIABLE_ADDED = "server_variable_added"
    SERVER_VARIABLE_REMOVED = "server_variable_removed"
    SERVER_VARIABLE_DEFAULT_CHANGED = "server_variable_default_changed"
    SERVER_VARIABLE_ENUM_CHANGED = "server_variable_enum_changed"

    # ── Security (12) ───────────────────────────────────────────────
    GLOBAL_SECURITY_ADDED = "global_security_added"
    GLOBAL_SECURITY_REMOVED = "global_security_removed"
    GLOBAL_SECURITY_CHANGED = "global_security_changed"
    SECURITY_SCHEME_ADDED = "security_scheme_added"
    SECURITY_SCHEME_REMOVED = "security_scheme_removed"
    SECURITY_SCHEME_TYPE_CHANGED = "security_scheme_type_changed"
    SECURITY_SCHEME_NAME_CHANGED = "security_scheme_name_changed"
    SECURITY_SCHEME_IN_CHANGED = "security_scheme_in_changed"
    OAUTH_SCOPE_ADDED = "oauth_scope_added"
    OAUTH_SCOPE_REMOVED = "oauth_scope_removed"
    OAUTH_FLOW_CHANGED = "oauth_flow_changed"
    OAUTH_URL_CHANGED = "oauth_url_changed"

    # ── Info (8) ────────────────────────────────────────────────────
    API_VERSION_CHANGED = "api_version_changed"
    INFO_TITLE_CHANGED = "info_title_changed"
    INFO_DESCRIPTION_CHANGED = "info_description_changed"
    INFO_CONTACT_CHANGED = "info_contact_changed"
    INFO_LICENSE_CHANGED = "info_license_changed"
    INFO_TERMS_OF_SERVICE_CHANGED = "info_terms_of_service_changed"
    OPENAPI_VERSION_CHANGED = "openapi_version_changed"
    EXTERNAL_DOCS_CHANGED = "external_docs_changed"

    # ── Components (6) ──────────────────────────────────────────────
    COMPONENT_SCHEMA_CHANGED = "component_schema_changed"
    COMPONENT_PARAMETER_CHANGED = "component_parameter_changed"
    COMPONENT_RESPONSE_CHANGED = "component_response_changed"
    COMPONENT_REQUEST_BODY_CHANGED = "component_request_body_changed"
    COMPONENT_HEADER_CHANGED = "component_header_changed"
    COMPONENT_SECURITY_SCHEME_CHANGED = "component_security_scheme_changed"

    # ── Webhooks (6) ────────────────────────────────────────────────
    WEBHOOK_ADDED = "webhook_added"
    WEBHOOK_REMOVED = "webhook_removed"
    WEBHOOK_METHOD_ADDED = "webhook_method_added"
    WEBHOOK_METHOD_REMOVED = "webhook_method_removed"
    WEBHOOK_OPERATION_CHANGED = "webhook_operation_changed"
    WEBHOOK_SCHEMA_CHANGED = "webhook_schema_changed"

    # ── Tags (3) ────────────────────────────────────────────────────
    TAG_ADDED = "tag_added"
    TAG_REMOVED = "tag_removed"
    TAG_DESCRIPTION_CHANGED = "tag_description_changed"

    # ── $ref (3) ────────────────────────────────────────────────────
    REF_TARGET_CHANGED = "ref_target_changed"
    REF_BECAME_INLINE = "ref_became_inline"
    REF_BECAME_REFERENCE = "ref_became_reference"


# ── Category mapping ───────────────────────────────────────────────────────
# Maps every ChangeKind to its ChangeCategory.  Built once at import time.
_CATEGORY_MAP: dict[ChangeKind, ChangeCategory] = {
    # Endpoint
    ChangeKind.ENDPOINT_ADDED: ChangeCategory.ENDPOINT,
    ChangeKind.ENDPOINT_REMOVED: ChangeCategory.ENDPOINT,
    ChangeKind.HTTP_METHOD_ADDED: ChangeCategory.ENDPOINT,
    ChangeKind.HTTP_METHOD_REMOVED: ChangeCategory.ENDPOINT,
    ChangeKind.METHOD_CHANGED: ChangeCategory.ENDPOINT,
    # Operation
    ChangeKind.OPERATION_DEPRECATED: ChangeCategory.OPERATION,
    ChangeKind.OPERATION_UNDEPRECATED: ChangeCategory.OPERATION,
    ChangeKind.OPERATION_ID_CHANGED: ChangeCategory.OPERATION,
    ChangeKind.OPERATION_ID_ADDED: ChangeCategory.OPERATION,
    ChangeKind.OPERATION_ID_REMOVED: ChangeCategory.OPERATION,
    ChangeKind.OPERATION_SUMMARY_CHANGED: ChangeCategory.OPERATION,
    ChangeKind.OPERATION_DESCRIPTION_CHANGED: ChangeCategory.OPERATION,
    ChangeKind.OPERATION_TAGS_CHANGED: ChangeCategory.OPERATION,
    ChangeKind.OPERATION_SECURITY_ADDED: ChangeCategory.OPERATION,
    ChangeKind.OPERATION_SECURITY_REMOVED: ChangeCategory.OPERATION,
    ChangeKind.OPERATION_SECURITY_CHANGED: ChangeCategory.OPERATION,
    ChangeKind.SUNSET_DATE: ChangeCategory.OPERATION,
    ChangeKind.CONTENT_TYPE_CHANGED: ChangeCategory.OPERATION,
    # Parameter
    ChangeKind.PARAM_ADDED: ChangeCategory.PARAMETER,
    ChangeKind.PARAM_REMOVED: ChangeCategory.PARAMETER,
    ChangeKind.PARAM_REQUIRED: ChangeCategory.PARAMETER,
    ChangeKind.PARAM_OPTIONAL: ChangeCategory.PARAMETER,
    ChangeKind.PARAM_TYPE_CHANGED: ChangeCategory.PARAMETER,
    ChangeKind.PARAM_FORMAT_CHANGED: ChangeCategory.PARAMETER,
    ChangeKind.PARAM_LOCATION_CHANGED: ChangeCategory.PARAMETER,
    ChangeKind.PARAM_DEPRECATED: ChangeCategory.PARAMETER,
    ChangeKind.PARAM_UNDEPRECATED: ChangeCategory.PARAMETER,
    ChangeKind.PARAM_DESCRIPTION_CHANGED: ChangeCategory.PARAMETER,
    ChangeKind.PARAM_STYLE_CHANGED: ChangeCategory.PARAMETER,
    ChangeKind.PARAM_EXPLODE_CHANGED: ChangeCategory.PARAMETER,
    ChangeKind.PARAM_ALLOW_EMPTY_VALUE_CHANGED: ChangeCategory.PARAMETER,
    ChangeKind.PARAM_DEFAULT_CHANGED: ChangeCategory.PARAMETER,
    ChangeKind.PARAM_EXAMPLE_CHANGED: ChangeCategory.PARAMETER,
    ChangeKind.PARAM_ENUM_CHANGED: ChangeCategory.PARAMETER,
    # Request Body
    ChangeKind.REQUEST_BODY_ADDED: ChangeCategory.REQUEST_BODY,
    ChangeKind.REQUEST_BODY_REMOVED: ChangeCategory.REQUEST_BODY,
    ChangeKind.REQUEST_BODY_REQUIRED_CHANGED: ChangeCategory.REQUEST_BODY,
    ChangeKind.REQUEST_CONTENT_TYPE_ADDED: ChangeCategory.REQUEST_BODY,
    ChangeKind.REQUEST_CONTENT_TYPE_REMOVED: ChangeCategory.REQUEST_BODY,
    ChangeKind.REQUEST_BODY_SCHEMA_CHANGED: ChangeCategory.REQUEST_BODY,
    # Response
    ChangeKind.RESPONSE_CODE_ADDED: ChangeCategory.RESPONSE,
    ChangeKind.RESPONSE_CODE_REMOVED: ChangeCategory.RESPONSE,
    ChangeKind.RESPONSE_DESCRIPTION_CHANGED: ChangeCategory.RESPONSE,
    ChangeKind.RESPONSE_CONTENT_TYPE_ADDED: ChangeCategory.RESPONSE,
    ChangeKind.RESPONSE_CONTENT_TYPE_REMOVED: ChangeCategory.RESPONSE,
    ChangeKind.RESPONSE_SCHEMA_CHANGED: ChangeCategory.RESPONSE,
    ChangeKind.RESPONSE_SCHEMA_ADDED: ChangeCategory.RESPONSE,
    ChangeKind.RESPONSE_SCHEMA_REMOVED: ChangeCategory.RESPONSE,
    ChangeKind.RESPONSE_HEADER_ADDED: ChangeCategory.RESPONSE,
    ChangeKind.RESPONSE_HEADER_REMOVED: ChangeCategory.RESPONSE,
    ChangeKind.RESPONSE_HEADER_CHANGED: ChangeCategory.RESPONSE,
    ChangeKind.RESPONSE_LINK_CHANGED: ChangeCategory.RESPONSE,
    # Schema Core
    ChangeKind.SCHEMA_TYPE_CHANGED: ChangeCategory.SCHEMA,
    ChangeKind.SCHEMA_FORMAT_CHANGED: ChangeCategory.SCHEMA,
    ChangeKind.SCHEMA_PROPERTY_ADDED: ChangeCategory.SCHEMA,
    ChangeKind.SCHEMA_PROPERTY_REMOVED: ChangeCategory.SCHEMA,
    ChangeKind.SCHEMA_PROPERTY_TYPE_CHANGED: ChangeCategory.SCHEMA,
    ChangeKind.REQUIRED_FIELD_ADDED: ChangeCategory.SCHEMA,
    ChangeKind.REQUIRED_FIELD_REMOVED: ChangeCategory.SCHEMA,
    ChangeKind.ENUM_VALUE_ADDED: ChangeCategory.SCHEMA,
    ChangeKind.ENUM_VALUE_REMOVED: ChangeCategory.SCHEMA,
    ChangeKind.SCHEMA_NULLABLE_CHANGED: ChangeCategory.SCHEMA,
    ChangeKind.SCHEMA_READ_ONLY_CHANGED: ChangeCategory.SCHEMA,
    ChangeKind.SCHEMA_WRITE_ONLY_CHANGED: ChangeCategory.SCHEMA,
    ChangeKind.SCHEMA_DEFAULT_CHANGED: ChangeCategory.SCHEMA,
    ChangeKind.SCHEMA_DESCRIPTION_CHANGED: ChangeCategory.SCHEMA,
    ChangeKind.SCHEMA_TITLE_CHANGED: ChangeCategory.SCHEMA,
    ChangeKind.SCHEMA_DEPRECATED_CHANGED: ChangeCategory.SCHEMA,
    ChangeKind.SCHEMA_DISCRIMINATOR_CHANGED: ChangeCategory.SCHEMA,
    ChangeKind.SCHEMA_EXAMPLE_CHANGED: ChangeCategory.SCHEMA,
    ChangeKind.ADDITIONAL_PROPERTIES_CHANGED: ChangeCategory.SCHEMA,
    ChangeKind.SCHEMA_EXAMPLES_CHANGED: ChangeCategory.SCHEMA,
    # Schema Constraints
    ChangeKind.SCHEMA_MIN_CHANGED: ChangeCategory.SCHEMA_CONSTRAINT,
    ChangeKind.SCHEMA_MAX_CHANGED: ChangeCategory.SCHEMA_CONSTRAINT,
    ChangeKind.SCHEMA_EXCLUSIVE_MIN_CHANGED: ChangeCategory.SCHEMA_CONSTRAINT,
    ChangeKind.SCHEMA_EXCLUSIVE_MAX_CHANGED: ChangeCategory.SCHEMA_CONSTRAINT,
    ChangeKind.SCHEMA_MIN_LENGTH_CHANGED: ChangeCategory.SCHEMA_CONSTRAINT,
    ChangeKind.SCHEMA_MAX_LENGTH_CHANGED: ChangeCategory.SCHEMA_CONSTRAINT,
    ChangeKind.SCHEMA_PATTERN_CHANGED: ChangeCategory.SCHEMA_CONSTRAINT,
    ChangeKind.SCHEMA_MIN_ITEMS_CHANGED: ChangeCategory.SCHEMA_CONSTRAINT,
    ChangeKind.SCHEMA_MAX_ITEMS_CHANGED: ChangeCategory.SCHEMA_CONSTRAINT,
    ChangeKind.SCHEMA_UNIQUE_ITEMS_CHANGED: ChangeCategory.SCHEMA_CONSTRAINT,
    ChangeKind.SCHEMA_MIN_PROPERTIES_CHANGED: ChangeCategory.SCHEMA_CONSTRAINT,
    ChangeKind.SCHEMA_MAX_PROPERTIES_CHANGED: ChangeCategory.SCHEMA_CONSTRAINT,
    ChangeKind.SCHEMA_MULTIPLE_OF_CHANGED: ChangeCategory.SCHEMA_CONSTRAINT,
    ChangeKind.SCHEMA_CONTENT_MEDIA_TYPE_CHANGED: ChangeCategory.SCHEMA_CONSTRAINT,
    ChangeKind.SCHEMA_CONTENT_ENCODING_CHANGED: ChangeCategory.SCHEMA_CONSTRAINT,
    ChangeKind.SCHEMA_IF_THEN_ELSE_CHANGED: ChangeCategory.SCHEMA_CONSTRAINT,
    # Schema Composition
    ChangeKind.SCHEMA_ALLOF_ADDED: ChangeCategory.SCHEMA_COMPOSITION,
    ChangeKind.SCHEMA_ALLOF_REMOVED: ChangeCategory.SCHEMA_COMPOSITION,
    ChangeKind.SCHEMA_ALLOF_SCHEMA_CHANGED: ChangeCategory.SCHEMA_COMPOSITION,
    ChangeKind.SCHEMA_ONEOF_ADDED: ChangeCategory.SCHEMA_COMPOSITION,
    ChangeKind.SCHEMA_ONEOF_REMOVED: ChangeCategory.SCHEMA_COMPOSITION,
    ChangeKind.SCHEMA_ONEOF_SCHEMA_CHANGED: ChangeCategory.SCHEMA_COMPOSITION,
    ChangeKind.SCHEMA_ANYOF_ADDED: ChangeCategory.SCHEMA_COMPOSITION,
    ChangeKind.SCHEMA_ANYOF_REMOVED: ChangeCategory.SCHEMA_COMPOSITION,
    ChangeKind.SCHEMA_ANYOF_SCHEMA_CHANGED: ChangeCategory.SCHEMA_COMPOSITION,
    ChangeKind.SCHEMA_NOT_CHANGED: ChangeCategory.SCHEMA_COMPOSITION,
    ChangeKind.SCHEMA_PREFIX_ITEMS_CHANGED: ChangeCategory.SCHEMA_COMPOSITION,
    ChangeKind.SCHEMA_CONTAINS_CHANGED: ChangeCategory.SCHEMA_COMPOSITION,
    # Servers
    ChangeKind.SERVER_ADDED: ChangeCategory.SERVER,
    ChangeKind.SERVER_REMOVED: ChangeCategory.SERVER,
    ChangeKind.SERVER_URL_CHANGED: ChangeCategory.SERVER,
    ChangeKind.SERVER_DESCRIPTION_CHANGED: ChangeCategory.SERVER,
    ChangeKind.SERVER_VARIABLE_ADDED: ChangeCategory.SERVER,
    ChangeKind.SERVER_VARIABLE_REMOVED: ChangeCategory.SERVER,
    ChangeKind.SERVER_VARIABLE_DEFAULT_CHANGED: ChangeCategory.SERVER,
    ChangeKind.SERVER_VARIABLE_ENUM_CHANGED: ChangeCategory.SERVER,
    # Security
    ChangeKind.GLOBAL_SECURITY_ADDED: ChangeCategory.SECURITY,
    ChangeKind.GLOBAL_SECURITY_REMOVED: ChangeCategory.SECURITY,
    ChangeKind.GLOBAL_SECURITY_CHANGED: ChangeCategory.SECURITY,
    ChangeKind.SECURITY_SCHEME_ADDED: ChangeCategory.SECURITY,
    ChangeKind.SECURITY_SCHEME_REMOVED: ChangeCategory.SECURITY,
    ChangeKind.SECURITY_SCHEME_TYPE_CHANGED: ChangeCategory.SECURITY,
    ChangeKind.SECURITY_SCHEME_NAME_CHANGED: ChangeCategory.SECURITY,
    ChangeKind.SECURITY_SCHEME_IN_CHANGED: ChangeCategory.SECURITY,
    ChangeKind.OAUTH_SCOPE_ADDED: ChangeCategory.SECURITY,
    ChangeKind.OAUTH_SCOPE_REMOVED: ChangeCategory.SECURITY,
    ChangeKind.OAUTH_FLOW_CHANGED: ChangeCategory.SECURITY,
    ChangeKind.OAUTH_URL_CHANGED: ChangeCategory.SECURITY,
    # Info
    ChangeKind.API_VERSION_CHANGED: ChangeCategory.INFO,
    ChangeKind.INFO_TITLE_CHANGED: ChangeCategory.INFO,
    ChangeKind.INFO_DESCRIPTION_CHANGED: ChangeCategory.INFO,
    ChangeKind.INFO_CONTACT_CHANGED: ChangeCategory.INFO,
    ChangeKind.INFO_LICENSE_CHANGED: ChangeCategory.INFO,
    ChangeKind.INFO_TERMS_OF_SERVICE_CHANGED: ChangeCategory.INFO,
    ChangeKind.OPENAPI_VERSION_CHANGED: ChangeCategory.INFO,
    ChangeKind.EXTERNAL_DOCS_CHANGED: ChangeCategory.INFO,
    # Components
    ChangeKind.COMPONENT_SCHEMA_CHANGED: ChangeCategory.COMPONENT,
    ChangeKind.COMPONENT_PARAMETER_CHANGED: ChangeCategory.COMPONENT,
    ChangeKind.COMPONENT_RESPONSE_CHANGED: ChangeCategory.COMPONENT,
    ChangeKind.COMPONENT_REQUEST_BODY_CHANGED: ChangeCategory.COMPONENT,
    ChangeKind.COMPONENT_HEADER_CHANGED: ChangeCategory.COMPONENT,
    ChangeKind.COMPONENT_SECURITY_SCHEME_CHANGED: ChangeCategory.COMPONENT,
    # Webhooks
    ChangeKind.WEBHOOK_ADDED: ChangeCategory.WEBHOOK,
    ChangeKind.WEBHOOK_REMOVED: ChangeCategory.WEBHOOK,
    ChangeKind.WEBHOOK_METHOD_ADDED: ChangeCategory.WEBHOOK,
    ChangeKind.WEBHOOK_METHOD_REMOVED: ChangeCategory.WEBHOOK,
    ChangeKind.WEBHOOK_OPERATION_CHANGED: ChangeCategory.WEBHOOK,
    ChangeKind.WEBHOOK_SCHEMA_CHANGED: ChangeCategory.WEBHOOK,
    # Tags
    ChangeKind.TAG_ADDED: ChangeCategory.TAG,
    ChangeKind.TAG_REMOVED: ChangeCategory.TAG,
    ChangeKind.TAG_DESCRIPTION_CHANGED: ChangeCategory.TAG,
    # Refs
    ChangeKind.REF_TARGET_CHANGED: ChangeCategory.REF,
    ChangeKind.REF_BECAME_INLINE: ChangeCategory.REF,
    ChangeKind.REF_BECAME_REFERENCE: ChangeCategory.REF,
}

# Sanity check: every ChangeKind must have a category mapping
assert set(ChangeKind) == set(_CATEGORY_MAP), (
    f"Category map missing kinds: {set(ChangeKind) - set(_CATEGORY_MAP)}"
)


def categorize_change(kind: ChangeKind) -> ChangeCategory:
    """Return the category for a given change kind."""
    return _CATEGORY_MAP[kind]


@dataclass(frozen=True)
class Change:
    """A single detected change between two API spec versions."""

    kind: ChangeKind
    severity: str
    path: str
    method: str
    detail: str = ""
    old_value: Any | None = field(default=None, repr=False)
    new_value: Any | None = field(default=None, repr=False)
    schema_path: str | None = None
    ref_source: str | None = None
    old_method: str | None = None
    new_method: str | None = None
    category: ChangeCategory | None = field(default=None, repr=False)
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if self.category is None:
            object.__setattr__(self, "category", categorize_change(self.kind))

    def __str__(self) -> str:
        return f"[{self.severity}] {self.method.upper()} {self.path} - {self.kind.value}: {self.detail}"
