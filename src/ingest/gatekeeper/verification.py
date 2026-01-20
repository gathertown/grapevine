"""Webhook verification protocol and result types.

This module defines the interface for webhook verification handlers.
Each handler is responsible for:
1. Fetching any credentials it needs (from SSM, etc.)
2. Performing the actual verification
3. Returning success/failure

This design pushes verification responsibility to the handlers,
keeping the gatekeeper core simple and unopinionated.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from src.clients.ssm import SSMClient


@dataclass
class VerificationResult:
    """Result of webhook verification."""

    success: bool
    error: str | None = None


class WebhookVerifier(Protocol):
    """Protocol for webhook verification handlers.

    Each source type implements this protocol to handle its own
    verification logic, including credential management.
    """

    async def verify(
        self,
        headers: dict[str, str],
        body: bytes,
        tenant_id: str,
        request_url: str | None = None,
    ) -> VerificationResult:
        """Verify a webhook for a given tenant.

        The handler is responsible for:
        - Fetching any credentials it needs (from SSM, etc.)
        - Performing the actual verification
        - Returning success/failure

        Args:
            headers: HTTP headers from the webhook request
            body: Raw request body as bytes
            tenant_id: The tenant ID for credential lookup
            request_url: Full request URL (required for some verifiers like HubSpot)

        Returns:
            VerificationResult indicating success or failure with error message
        """
        ...


# Type alias for verification functions
VerifyFunc = Callable[[dict[str, str], bytes, str], None]


class BaseSigningSecretVerifier:
    """Base class for verifiers that use a signing secret from SSM.

    This covers the common pattern where:
    1. A signing secret is fetched from SSM for the tenant/source
    2. The secret is passed to a verification function
    3. The function raises ValueError on failure

    Subclasses only need to define:
    - source_type: The source identifier for SSM lookup (e.g., "github", "slack")
    - verify_func: The function that performs the actual verification
    """

    source_type: str
    verify_func: VerifyFunc

    def __init__(self) -> None:
        self.ssm_client = SSMClient()

    async def verify(
        self,
        headers: dict[str, str],
        body: bytes,
        tenant_id: str,
        request_url: str | None = None,
    ) -> VerificationResult:
        """Verify a webhook using a signing secret from SSM.

        Fetches the signing secret and delegates to the source-specific verify_func.
        """
        del request_url  # unused for signing secret verifiers
        signing_secret = await self.ssm_client.get_signing_secret(tenant_id, self.source_type)
        if not signing_secret:
            return VerificationResult(
                success=False,
                error=f"No signing secret configured for tenant {tenant_id}",
            )

        try:
            self.verify_func(headers, body, signing_secret)
            return VerificationResult(success=True)
        except ValueError as e:
            return VerificationResult(success=False, error=str(e))
