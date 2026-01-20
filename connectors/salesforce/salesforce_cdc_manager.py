"""Salesforce Change Data Capture (CDC) manager for all tenants."""

import asyncio
import contextlib
from typing import Any

from connectors.salesforce.salesforce_cdc_listener import SalesforceCDCListener
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.clients.tenant_db import tenant_db_manager
from src.utils.logging import get_logger

logger = get_logger(__name__)


class SalesforceCDCManager:
    """Manages CDC connections for all Salesforce-enabled tenants."""

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient):
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client
        self.listeners: dict[str, SalesforceCDCListener] = {}
        self.running = False
        self._discovery_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the CDC manager and discover tenants."""
        if self.running:
            return

        logger.info("Starting Salesforce CDC manager")
        self.running = True

        # Discover and start listeners for all Salesforce tenants
        await self._discover_and_start_listeners()

        # Start periodic tenant discovery task
        self._discovery_task = asyncio.create_task(self._periodic_tenant_discovery())

    async def stop(self) -> None:
        """Stop all CDC listeners."""
        if not self.running:
            return

        logger.info("Stopping Salesforce CDC manager")
        self.running = False

        # Cancel discovery task
        if self._discovery_task:
            self._discovery_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._discovery_task

        # Stop all listeners
        tasks = [listener.stop() for listener in self.listeners.values()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self.listeners.clear()
        logger.info("Stopped all Salesforce CDC listeners")

    async def _discover_salesforce_tenants(self) -> list[str]:
        """Query control database for Salesforce-enabled tenants."""
        try:
            control_pool = await tenant_db_manager.get_control_db()
            async with control_pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT id FROM public.tenants WHERE has_salesforce_connected = true"
                )
                tenant_ids = [row["id"] for row in rows]
                logger.info(f"Found {len(tenant_ids)} Salesforce-enabled tenants")
                return tenant_ids
        except Exception as e:
            logger.error(f"Error querying control database for Salesforce tenants: {e}")
            return []

    async def _discover_and_start_listeners(self) -> None:
        """Discover Salesforce tenants and start CDC listeners."""
        tenant_ids = await self._discover_salesforce_tenants()

        # Start listeners for new tenants
        for tenant_id in tenant_ids:
            if tenant_id not in self.listeners:
                listener = SalesforceCDCListener(tenant_id, self.ssm_client, self.sqs_client)
                self.listeners[tenant_id] = listener
                await listener.start()

        # Stop listeners for tenants that are no longer Salesforce-enabled
        current_tenants = set(tenant_ids)
        tenants_to_remove = set(self.listeners.keys()) - current_tenants

        for tenant_id in tenants_to_remove:
            listener = self.listeners.pop(tenant_id)
            await listener.stop()
            logger.info(f"Removed Salesforce CDC listener for tenant {tenant_id}")

    async def _periodic_tenant_discovery(self) -> None:
        """Periodically discover new/removed Salesforce tenants."""
        while self.running:
            try:
                # Discover tenants every 1 minute
                await asyncio.sleep(60)

                if self.running:  # Check again after sleep
                    await self._discover_and_start_listeners()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic tenant discovery: {e}")
                # Continue running even if discovery fails

    def health_check(self) -> dict[str, Any]:
        """Check health of all CDC connections."""
        total_listeners = len(self.listeners)
        running_listeners = sum(1 for listener in self.listeners.values() if listener.running)

        status = "healthy" if running_listeners == total_listeners else "degraded"

        return {
            "component": "salesforce_cdc",
            "status": status,
            "total_listeners": total_listeners,
            "running_listeners": running_listeners,
            "tenant_ids": list(self.listeners.keys()),
        }
