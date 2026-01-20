#!/usr/bin/env python
"""Generate long-lived bearer tokens for MCP service authentication.

This script generates RS256 JWT tokens that can be used to authenticate
internal services with the MCP server using the Internal JWT auth provider.

Usage:
    # Generate a token for a tenant (default: 1 year expiry)
    python scripts/generate_mcp_token.py --tenant-id abc123def456

    # Generate with custom expiry
    python scripts/generate_mcp_token.py --tenant-id abc123def456 --expires-in 30d

    # Generate with description (included in JWT payload)
    python scripts/generate_mcp_token.py --tenant-id abc123def456 --description "Production indexing service"

    # Generate non-billable token (for internal operations)
    python scripts/generate_mcp_token.py --tenant-id abc123def456 --non-billable

Environment Variables:
    INTERNAL_JWT_PRIVATE_KEY: RSA private key in PKCS8 format (required)
    INTERNAL_JWT_ISSUER: Token issuer (optional, recommended)
    INTERNAL_JWT_AUDIENCE: Token audience (optional, recommended)
"""

import argparse
import os
import re
import sys
import time
from datetime import UTC, datetime

import jwt


def parse_expiry(expiry_str: str) -> int:
    """Parse expiry string like '1h', '30d', '365d' into seconds.

    Args:
        expiry_str: Expiry string in format like '1h', '30m', '365d'

    Returns:
        Number of seconds

    Raises:
        ValueError: If expiry format is invalid
    """
    match = re.match(r"^(\d+)([smhd])$", expiry_str)
    if not match:
        raise ValueError(f"Invalid expiry format: {expiry_str}. Use format like: 1h, 30d, 365d")

    value = int(match[1])
    unit = match[2]

    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}

    return value * multipliers[unit]


def get_jwt_config():
    """Get JWT configuration from environment variables.

    Returns:
        Dict with private_key, issuer, and audience

    Raises:
        ValueError: If required configuration is missing
    """
    private_key = os.environ.get("INTERNAL_JWT_PRIVATE_KEY")
    if not private_key:
        raise ValueError(
            "INTERNAL_JWT_PRIVATE_KEY environment variable is required. "
            "This should be an RSA private key in PKCS8 format."
        )

    # Issuer and audience are optional but recommended
    issuer = os.environ.get("INTERNAL_JWT_ISSUER")
    audience = os.environ.get("INTERNAL_JWT_AUDIENCE")

    return {"private_key": private_key, "issuer": issuer, "audience": audience}


def generate_token(
    tenant_id: str,
    expires_in: str = "365d",
    description: str | None = None,
    non_billable: bool = False,
) -> tuple[str, dict]:
    """Generate a long-lived RS256 JWT token.

    Args:
        tenant_id: Tenant ID to include in token
        expires_in: Token expiration (default: 365d)
        description: Optional description for tracking
        non_billable: If True, mark requests as non-billable (for internal operations)

    Returns:
        Tuple of (token_string, token_metadata_dict)

    Raises:
        ValueError: If configuration is invalid or token generation fails
    """
    config = get_jwt_config()

    try:
        expiry_seconds = parse_expiry(expires_in)
    except ValueError as e:
        raise ValueError(f"Invalid expiry format: {e}") from e

    now = int(time.time())
    exp = now + expiry_seconds

    # Build JWT payload
    payload = {
        "tenant_id": tenant_id,
        "iat": now,
        "exp": exp,
    }

    if config["issuer"]:
        payload["iss"] = config["issuer"]

    if config["audience"]:
        payload["aud"] = config["audience"]

    # Add description to payload if provided (for debugging/logging)
    if description:
        payload["description"] = description

    # Add nonBillable flag if specified (for internal operations)
    if non_billable:
        payload["nonBillable"] = True

    try:
        # Generate RS256 JWT
        token = jwt.encode(payload, config["private_key"], algorithm="RS256")

        # Create metadata for display
        metadata = {
            "tenant_id": tenant_id,
            "description": description,
            "issued_at": datetime.fromtimestamp(now, tz=UTC).isoformat(),
            "expires_at": datetime.fromtimestamp(exp, tz=UTC).isoformat(),
            "expires_in": expires_in,
            "issuer": config["issuer"],
            "audience": config["audience"],
            "non_billable": non_billable,
        }

        return token, metadata

    except Exception as e:
        raise ValueError(f"Failed to generate token: {e}") from e


def print_token_info(token: str, metadata: dict):
    """Pretty-print token information."""
    print("\n" + "=" * 80)
    print("🔑 MCP Service Token Generated")
    print("=" * 80)
    print(f"\nToken (copy this):\n{token}\n")
    print("-" * 80)
    print("Token Details:")
    print(f"  Tenant ID:   {metadata['tenant_id']}")
    print(f"  Issued:      {metadata['issued_at']}")
    print(f"  Expires:     {metadata['expires_at']} ({metadata['expires_in']})")
    if metadata.get("issuer"):
        print(f"  Issuer:      {metadata['issuer']}")
    if metadata.get("audience"):
        print(f"  Audience:    {metadata['audience']}")
    if metadata.get("description"):
        print(f"  Description: {metadata['description']}")
    if metadata.get("non_billable"):
        print("  Non-Billable: Yes (requests will not count toward usage limits)")
    print("-" * 80)
    print("\n⚠️  SECURITY WARNING:")
    print("  - Store this token securely (e.g., environment variable, secrets manager)")
    print("  - Do not commit this token to version control")
    print("  - This token provides full access to the tenant's MCP server")
    print("  - Treat it like a password - if compromised, generate a new one")
    print("\n💡 Usage Example:")
    print(f"  curl -H 'Authorization: Bearer {token[:20]}...' https://your-mcp-server/")
    print("=" * 80 + "\n")


def main():
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Generate long-lived MCP service bearer tokens",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate token with 1 year expiry (default)
  python scripts/generate_mcp_token.py --tenant-id abc123def456

  # Generate token with 30 day expiry
  python scripts/generate_mcp_token.py --tenant-id abc123def456 --expires-in 30d

  # Generate token with description
  python scripts/generate_mcp_token.py --tenant-id abc123def456 --description "Production indexing service"

  # Generate non-billable token
  python scripts/generate_mcp_token.py --tenant-id abc123def456 --non-billable --description "Internal testing"

Expiry formats:
  1h   = 1 hour
  30m  = 30 minutes
  30d  = 30 days
  365d = 365 days (1 year)
        """,
    )

    parser.add_argument("--tenant-id", required=True, help="Tenant ID for the token")
    parser.add_argument(
        "--expires-in",
        default="365d",
        help="Token expiration (e.g., 1h, 30d, 365d). Default: 365d (1 year)",
    )
    parser.add_argument(
        "--description", help="Optional description (included in JWT payload for debugging)"
    )
    parser.add_argument(
        "--non-billable",
        action="store_true",
        help="Mark requests as non-billable (for internal operations like testing)",
    )

    args = parser.parse_args()

    try:
        # Generate token
        token, metadata = generate_token(
            tenant_id=args.tenant_id,
            expires_in=args.expires_in,
            description=args.description,
            non_billable=args.non_billable,
        )

        print_token_info(token, metadata)
        return 0

    except ValueError as e:
        print(f"\n❌ Error: {e}\n", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}\n", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
