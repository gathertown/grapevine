"""Forge JWT validation for app system tokens."""

import logging
from typing import Any

import jwt
from jwt import PyJWKClient

logger = logging.getLogger(__name__)

# Atlassian Forge JWKS endpoint
FORGE_JWKS_URL = "https://forge.cdn.prod.atlassian-dev.net/.well-known/jwks.json"
FORGE_ISSUER = "forge/invocation-token"

# Cache for JWKS client
_jwks_client: PyJWKClient | None = None


def get_jwks_client() -> PyJWKClient:
    """Get or create the JWKS client for Forge JWT validation.

    Returns:
        PyJWKClient instance for fetching signing keys
    """
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(
            FORGE_JWKS_URL,
            cache_keys=True,
            lifespan=3600,  # Cache keys for 1 hour
        )
    return _jwks_client


def verify_forge_jwt(token: str, expected_app_id: str) -> dict[str, Any]:
    """Verify a Forge Invocation Token (FIT).

    Args:
        token: JWT token from Authorization header (without 'Bearer ' prefix)
        expected_app_id: Expected Forge app ID (e.g., from JIRA_APP_ID env var)

    Returns:
        Decoded JWT payload with claims

    Raises:
        jwt.InvalidTokenError: If token validation fails
        ValueError: If token is missing required claims
    """
    try:
        # Get the signing key from JWKS
        jwks_client = get_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        # Verify and decode the JWT
        # The audience should be the app ID in format: ari:cloud:ecosystem::app/{app_id}
        expected_audience = f"ari:cloud:ecosystem::app/{expected_app_id}"

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=expected_audience,
            issuer=FORGE_ISSUER,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
                "verify_aud": True,
                "verify_iss": True,
            },
        )

        logger.debug(f"Successfully verified Forge JWT for app {expected_app_id}")
        return payload

    except jwt.ExpiredSignatureError:
        logger.warning("Forge JWT token has expired")
        raise
    except jwt.InvalidAudienceError:
        logger.warning(f"Forge JWT audience mismatch. Expected: {expected_audience}")
        raise
    except jwt.InvalidIssuerError:
        logger.warning(f"Forge JWT issuer mismatch. Expected: {FORGE_ISSUER}")
        raise
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid Forge JWT token: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error verifying Forge JWT: {e}")
        raise jwt.InvalidTokenError(f"JWT verification failed: {e}") from e


def extract_forge_token_from_header(authorization_header: str | None) -> str | None:
    """Extract the JWT token from the Authorization header.

    Args:
        authorization_header: Value of the Authorization header

    Returns:
        JWT token string without 'Bearer ' prefix, or None if invalid
    """
    if not authorization_header:
        return None

    # Authorization header should be in format: "Bearer <token>"
    parts = authorization_header.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer":
        logger.warning(f"Invalid Authorization header format: {authorization_header[:20]}...")
        return None

    return parts[1]


def verify_forge_request(headers: dict[str, str], expected_app_id: str) -> dict[str, Any]:
    """Verify a request from a Forge app using the Forge Invocation Token.

    Args:
        headers: Request headers dictionary
        expected_app_id: Expected Forge app ID

    Returns:
        Decoded JWT payload with claims

    Raises:
        ValueError: If Authorization header is missing or invalid
        jwt.InvalidTokenError: If token validation fails
    """
    # Extract token from Authorization header
    auth_header = headers.get("authorization") or headers.get("Authorization")
    token = extract_forge_token_from_header(auth_header)

    if not token:
        raise ValueError("Missing or invalid Authorization header with Bearer token")

    # Verify the JWT
    return verify_forge_jwt(token, expected_app_id)
