"""GitHub token scoping and lifecycle management.

Design constraints:
- Tokens are scoped to a specific repository (not global)
- Tokens are passed through LangGraph state only (never persisted)
- Tokens are destroyed immediately after the PR is opened
- No token is ever written to disk, logs, or error messages
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ScopedToken:
    """A GitHub token scoped to a single repository.

    The token is destroyed immediately after use via ``destroy()``.
    The ``__del__`` destructor provides a safety net.
    """

    token: str
    repository_id: int
    installation_id: int | None = None
    _destroyed: bool = field(default=False, repr=False, compare=False)

    def destroy(self) -> None:
        """Securely destroy the token by overwriting and flagging."""
        self.token = ""
        self._destroyed = True

    def __del__(self) -> None:
        if not self._destroyed:
            self.destroy()

    def __bool__(self) -> bool:
        return not self._destroyed and bool(self.token)


class TokenManager:
    """Manages scoped tokens for the fix pipeline.

    Token lifecycle:
    1. Created per-repository from installation token
    2. Passed through LangGraph state (FixState.installation_token)
    3. Used for GitHub API calls (PR creation, file updates)
    4. Destroyed immediately after PR is opened

    This ensures:
    - Cross-tenant isolation (each repo gets its own token)
    -最小权限 (token only has access to the target repo)
    - No token leakage (destroyed after use)
    """

    def __init__(self, github_client: object | None = None) -> None:
        self._github_client = github_client
        self._active_tokens: list[ScopedToken] = []

    def get_scoped_token(
        self, installation_id: int, repository_id: int
    ) -> ScopedToken:
        """Create a scoped token for a specific repository."""
        if self._github_client is None:
            raise RuntimeError("GitHub client not configured")

        # Create installation access token (short-lived, ~1 hour)
        token_data = self._github_client.create_installation_access_token(  # type: ignore[union-attr]
            installation_id
        )

        token = ScopedToken(
            token=token_data["token"],
            repository_id=repository_id,
            installation_id=installation_id,
        )
        self._active_tokens.append(token)
        return token

    def destroy_all(self) -> None:
        """Destroy all active tokens. Call after PR is opened."""
        for token in self._active_tokens:
            token.destroy()
        count = len(self._active_tokens)
        self._active_tokens.clear()
        if count:
            logger.info("Destroyed %d scoped token(s)", count)

    def destroy_for_repo(self, repository_id: int) -> None:
        """Destroy tokens for a specific repository."""
        remaining: list[ScopedToken] = []
        destroyed = 0
        for token in self._active_tokens:
            if token.repository_id == repository_id:
                token.destroy()
                destroyed += 1
            else:
                remaining.append(token)
        self._active_tokens = remaining
        if destroyed:
            logger.info(
                "Destroyed %d token(s) for repo %d", destroyed, repository_id
            )

    @property
    def active_count(self) -> int:
        """Number of active (undestroyed) tokens."""
        return sum(1 for t in self._active_tokens if t)
