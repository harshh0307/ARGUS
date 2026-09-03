"""API key generation and verification."""

import hashlib
import secrets


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key.

    Returns:
        (raw_key, key_hash, prefix) - raw_key shown once, key_hash stored in DB,
        prefix is first 8 chars for identification.
    """
    raw = f"argus_{secrets.token_urlsafe(32)}"
    prefix = raw[:8]
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    return raw, key_hash, prefix


def hash_api_key(raw_key: str) -> str:
    """Hash an API key for comparison."""
    return hashlib.sha256(raw_key.encode()).hexdigest()
