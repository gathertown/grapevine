"""Webhook processor service for gatekeeper.

This service provides shared infrastructure for webhook handlers:
- SSM client for credential management
- Health checks for monitoring

Note: Verification is handled directly by each webhook handler using
verifier classes from the connectors. This keeps the core simple and
pushes verification responsibility to the handlers.
"""

import logging
from typing import Any

import asyncpg

from src.clients.ssm import SSMClient
from src.utils.config import get_control_database_url

logger = logging.getLogger(__name__)


class WebhookProcessor:
    """Service providing shared infrastructure for webhook handlers.

    Handlers use this for:
    - SSM client access (for storing signing secrets during setup)
    - Health check endpoint

    Verification is handled directly by handlers using verifier classes.
    """

    def __init__(self):
        """Initialize webhook processor."""
        self.ssm_client = SSMClient()
        self.control_db_pool: asyncpg.Pool | None = None

    async def initialize(self) -> None:
        """Initialize the webhook processor including database connections."""
        try:
            self.control_db_pool = await asyncpg.create_pool(
                get_control_database_url(), min_size=1, max_size=5, timeout=30
            )
            logger.info("Control database pool initialized in WebhookProcessor")
        except Exception as e:
            logger.error(f"Failed to initialize control database pool: {e}")

    async def cleanup(self) -> None:
        """Clean up resources."""
        if self.control_db_pool:
            await self.control_db_pool.close()
            logger.info("Control database pool closed in WebhookProcessor")

    async def health_check(self) -> dict[str, Any]:
        """Perform health check of all dependencies.

        Returns:
            Dictionary with health status of each component
        """
        health_status: dict[str, Any] = {"status": "healthy", "components": {}}

        # Check control database connectivity
        if self.control_db_pool:
            try:
                async with self.control_db_pool.acquire() as conn:
                    # Simple connectivity test
                    await conn.fetchval("SELECT 1")
                health_status["components"]["control_db"] = "healthy"
            except Exception as e:
                health_status["components"]["control_db"] = f"unhealthy: {e}"
                health_status["status"] = "unhealthy"
        else:
            health_status["components"]["control_db"] = "not initialized"

        # Check AWS SSM connectivity
        try:
            # Test SSM connectivity using dedicated health check parameter
            health_param = await self.ssm_client.get_parameter(
                "/health-check/signing-secret/connectivity", use_cache=False
            )
            if health_param != "ok":
                raise Exception("SSM health check parameter has unexpected value")
            health_status["components"]["ssm"] = "healthy"
        except Exception as e:
            health_status["components"]["ssm"] = f"unhealthy: {e}"
            health_status["status"] = "unhealthy"

        return health_status
