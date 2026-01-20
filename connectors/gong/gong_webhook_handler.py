"""Utilities for verifying Gong webhooks signed with tenant-provided keys."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import jwt
from jwt import InvalidTokenError

from src.clients.ssm import SSMClient
from src.ingest.gatekeeper.verification import VerificationResult
from src.utils.logging import get_logger

logger = get_logger(__name__)


class GongWebhookVerifier:
    """Verifier for Gong webhooks using RS256 JWT with tenant-provided public keys.

    Note: Does not inherit from BaseSigningSecretVerifier because Gong uses
    RS256 JWT verification with a public key, not HMAC with a signing secret.
    """

    async def verify(
        self,
        headers: dict[str, str],
        body: bytes,
        tenant_id: str,
        request_url: str | None = None,
    ) -> VerificationResult:
        """Verify a Gong webhook for a given tenant."""
        del request_url  # unused for Gong
        try:
            await verify_gong_webhook(headers, body, tenant_id)
            return VerificationResult(success=True)
        except GongWebhookVerificationError as e:
            return VerificationResult(success=False, error=str(e))


@dataclass(slots=True)
class GongVerificationResult:
    """Verification result for a Gong webhook payload."""

    tenant_id: str
    claims: dict[str, Any]


class GongWebhookVerificationError(ValueError):
    """Raised when a Gong webhook cannot be verified."""


def _normalize_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {key.lower(): value for key, value in headers.items()}


def _extract_token_from_authorization_header(headers: Mapping[str, str]) -> str:
    normalized = _normalize_headers(headers)

    auth_header = normalized.get("authorization")
    if not auth_header:
        raise GongWebhookVerificationError("Missing Authorization header")

    # Gong sends JWT directly without "Bearer " prefix
    token = auth_header.strip()
    if not token:
        raise GongWebhookVerificationError("Authorization header is empty")

    return token


def _extract_tenant_claim(claims: dict[str, Any]) -> str | None:
    """Return tenant identifier claim if present."""

    for key in ("tenantId", "tenant_id", "accountId", "account_id"):
        value = claims.get(key)
        if value is not None:
            return str(value)
    return None


_ssm_client = SSMClient()


def _normalize_public_key_to_pem(public_key: str) -> str:
    """Normalize a public key to PEM format.

    If the key is just the base64 content, wrap it with PEM markers.
    This handles keys copied from Gong's UI which only show the key content.

    Args:
        public_key: The public key, with or without PEM markers.

    Returns:
        The public key in proper PEM format.
    """
    trimmed = public_key.strip()

    # If already in PEM format, return as-is
    if "-----BEGIN PUBLIC KEY-----" in trimmed and "-----END PUBLIC KEY-----" in trimmed:
        return trimmed

    # Otherwise, wrap the key content with PEM markers
    # Remove any newlines from the key content for cleaner formatting
    key_content = trimmed.replace("\n", "")
    return f"-----BEGIN PUBLIC KEY-----\n{key_content}\n-----END PUBLIC KEY-----"


async def verify_gong_webhook(
    headers: Mapping[str, str],
    body: bytes,
    tenant_id: str,
) -> GongVerificationResult:
    """Verify a Gong webhook request using the tenant's stored public key.

    Args:
        headers: Incoming request headers.
        body: Raw request body used for SHA256 verification.
        tenant_id: Tenant the webhook endpoint belongs to.

    Returns:
        GongVerificationResult containing the decoded JWT claims.

    Raises:
        GongWebhookVerificationError: If the webhook cannot be verified.
    """

    token = _extract_token_from_authorization_header(headers)

    public_key = await _ssm_client.get_gong_webhook_public_key(tenant_id)
    if not public_key:
        raise GongWebhookVerificationError(
            "Gong webhook public key not configured for this tenant."
        )

    # Ensure the public key is in proper PEM format
    public_key = _normalize_public_key_to_pem(public_key)

    try:
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
        )
    except InvalidTokenError as exc:
        logger.error("Gong webhook JWT verification failed", tenant_id=tenant_id, error=str(exc))
        raise GongWebhookVerificationError("Invalid Gong webhook signature") from exc

    # Verify body SHA256 hash matches the claim in the JWT
    body_sha256_claim = claims.get("body_sha256")
    if body_sha256_claim:
        actual_hash = hashlib.sha256(body).hexdigest()
        if actual_hash != body_sha256_claim:
            logger.error(
                "Gong webhook body SHA256 mismatch",
                tenant_id=tenant_id,
                expected=body_sha256_claim,
                actual=actual_hash,
            )
            raise GongWebhookVerificationError("Request body SHA256 doesn't match JWT claim")
        logger.debug("Gong webhook body SHA256 verification passed", tenant_id=tenant_id)

    claim_tenant = _extract_tenant_claim(claims)
    if claim_tenant and claim_tenant != tenant_id:
        raise GongWebhookVerificationError(
            f"Gong webhook tenant mismatch (expected {tenant_id}, got {claim_tenant})"
        )

    return GongVerificationResult(tenant_id=tenant_id, claims=claims)
