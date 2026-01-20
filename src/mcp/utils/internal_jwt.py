from typing import Any

import jwt
from jwt import InvalidTokenError

from src.utils.config import (
    get_internal_jwt_audience,
    get_internal_jwt_issuer,
    get_internal_jwt_jwks_uri,
    get_internal_jwt_public_key,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


def _get_internal_jwt_verifier():
    """Get configuration for internal JWT verification.

    Returns:
        Tuple of (public_key, issuer, audience) or None if not configured
    """
    jwks_uri = get_internal_jwt_jwks_uri()
    public_key = get_internal_jwt_public_key()
    issuer = get_internal_jwt_issuer()
    audience = get_internal_jwt_audience()

    if not jwks_uri and not public_key:
        return None

    return (public_key, issuer, audience)


def verify_internal_jwt(token: str) -> dict[str, Any] | None:
    """Verify internal JWT token and return claims.

    Args:
        token: JWT token string

    Returns:
        Token claims dict if valid, None otherwise
    """
    config = _get_internal_jwt_verifier()
    if not config:
        logger.error("Internal JWT verification not configured")
        return None

    public_key, issuer, audience = config

    try:
        # Decode and verify JWT
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer=issuer if issuer else None,
            audience=audience if audience else None,
        )
        return claims
    except InvalidTokenError as exc:
        logger.debug("Internal JWT verification failed", error=str(exc))
        return None
