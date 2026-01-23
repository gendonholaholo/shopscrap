"""API Key Authentication middleware."""

from __future__ import annotations

import hashlib
import hmac
import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader, APIKeyQuery

from shopee_scraper.utils.config import get_settings
from shopee_scraper.utils.logging import get_logger


logger = get_logger(__name__)

# API Key can be passed via header or query parameter
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query = APIKeyQuery(name="api_key", auto_error=False)


class APIKeyManager:
    """
    Manages API key validation and generation.

    Supports multiple API keys with optional expiration.
    """

    def __init__(self) -> None:
        """Initialize API key manager."""
        self._valid_keys: set[str] = set()
        self._load_keys_from_settings()

    def _load_keys_from_settings(self) -> None:
        """Load API keys from settings/environment."""
        settings = get_settings()

        # Load API keys from auth settings
        keys = settings.auth.get_keys_list()
        if keys:
            self._valid_keys.update(keys)
            logger.info(f"Loaded {len(keys)} API key(s) from configuration")

    def add_key(self, key: str) -> None:
        """Add a valid API key."""
        self._valid_keys.add(key)

    def remove_key(self, key: str) -> None:
        """Remove an API key."""
        self._valid_keys.discard(key)

    def validate_key(self, key: str) -> bool:
        """
        Validate an API key.

        Uses constant-time comparison to prevent timing attacks.
        """
        if not key:
            return False

        for valid_key in self._valid_keys:
            if hmac.compare_digest(key, valid_key):
                return True
        return False

    @staticmethod
    def generate_key(prefix: str = "sk") -> str:
        """
        Generate a new secure API key.

        Format: {prefix}_{random_hex}
        Example: sk_a1b2c3d4e5f6...
        """
        random_bytes = secrets.token_bytes(32)
        key_hash = hashlib.sha256(random_bytes).hexdigest()[:48]
        return f"{prefix}_{key_hash}"

    @property
    def key_count(self) -> int:
        """Get number of registered API keys."""
        return len(self._valid_keys)


# Global API key manager instance
_api_key_manager: APIKeyManager | None = None


def get_api_key_manager() -> APIKeyManager:
    """Get or create API key manager singleton."""
    global _api_key_manager  # noqa: PLW0603
    if _api_key_manager is None:
        _api_key_manager = APIKeyManager()
    return _api_key_manager


async def get_api_key(
    api_key_header_value: str | None = Security(api_key_header),
    api_key_query_value: str | None = Security(api_key_query),
) -> str:
    """
    Extract and validate API key from request.

    API key can be provided via:
    - Header: X-API-Key
    - Query parameter: api_key

    Raises:
        HTTPException: If API key is missing or invalid
    """
    settings = get_settings()

    # Check if authentication is enabled
    if not getattr(settings, "api_auth_enabled", False):
        # Auth disabled, return dummy key
        return "auth_disabled"

    # Get key from header or query
    api_key = api_key_header_value or api_key_query_value

    if not api_key:
        logger.warning("API request without API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is required. Provide via X-API-Key header or api_key query parameter.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Validate key
    manager = get_api_key_manager()
    if not manager.validate_key(api_key):
        logger.warning("Invalid API key attempt", key_prefix=api_key[:8] + "...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    logger.debug("API key validated successfully")
    return api_key


async def optional_api_key(
    api_key_header_value: str | None = Security(api_key_header),
    api_key_query_value: str | None = Security(api_key_query),
) -> str | None:
    """
    Optional API key validation.

    Returns the API key if valid, None if not provided.
    Raises HTTPException only if key is provided but invalid.
    """
    settings = get_settings()

    if not getattr(settings, "api_auth_enabled", False):
        return None

    api_key = api_key_header_value or api_key_query_value

    if not api_key:
        return None

    manager = get_api_key_manager()
    if not manager.validate_key(api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    return api_key


def require_api_key():
    """
    Dependency that requires valid API key.

    Usage:
        @router.get("/protected", dependencies=[Depends(require_api_key())])
        async def protected_endpoint():
            ...
    """
    from fastapi import Depends

    return Depends(get_api_key)


# CLI helper to generate new API keys
def generate_api_key_cli() -> None:
    """Generate and print a new API key (for CLI use)."""
    key = APIKeyManager.generate_key()
    print(f"Generated API Key: {key}")
    print("Add this to your .env file:")
    print(f'API_KEYS="{key}"')
