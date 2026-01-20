"""Root extractor for Gong call backfills."""

from __future__ import annotations

import asyncio
import secrets
import time
from collections import defaultdict
from datetime import datetime

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.gong.gong_models import (
    GongCallBackfillConfig,
    GongCallBackfillRootConfig,
    GongCallBatch,
    GongWorkspacePermissions,
)
from src.clients.gong import GongClient
from src.clients.gong_factory import get_gong_client_for_tenant
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.utils.logging import get_logger
from src.utils.tenant_config import increment_backfill_total_ingest_jobs

logger = get_logger(__name__)

# Default batch size for call IDs when not specified in config
DEFAULT_CALL_BATCH_SIZE = 100


class GongCallBackfillRootExtractor(BaseExtractor[GongCallBackfillRootConfig]):
    """Discovers Gong calls and enqueues child jobs to process them."""

    source_name = "gong_call_backfill_root"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient) -> None:
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client
        self._sqs_semaphore = asyncio.Semaphore(50)

    async def process_job(
        self,
        job_id: str,
        config: GongCallBackfillRootConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        start_time = time.perf_counter()
        backfill_id = secrets.token_hex(8)
        logger.info(
            "Processing Gong call backfill root job",
            tenant_id=config.tenant_id,
            job_id=job_id,
            backfill_id=backfill_id,
        )

        # Fetch Gong client for the tenant
        gong_client = await get_gong_client_for_tenant(config.tenant_id, self.ssm_client)

        try:
            discovery_start = time.perf_counter()
            call_batches, api_call_count, total_calls = await self._discover_call_batches(
                config, gong_client
            )
            discovery_duration = time.perf_counter() - discovery_start

            logger.info(
                "Gong call discovery completed",
                tenant_id=config.tenant_id,
                backfill_id=backfill_id,
                total_calls_discovered=total_calls,
                batch_count=len(call_batches),
                api_calls_made=api_call_count,
                discovery_duration_seconds=round(discovery_duration, 2),
            )

            if not call_batches:
                logger.warning(
                    "No Gong calls discovered for backfill",
                    tenant_id=config.tenant_id,
                )
                return

            await increment_backfill_total_ingest_jobs(
                backfill_id, config.tenant_id, len(call_batches)
            )

            # Fetch workspace permissions once per workspace
            permissions_start = time.perf_counter()
            workspace_permissions_map: dict[str, GongWorkspacePermissions] = {}
            permissions_api_calls = 0

            # Get unique workspace IDs from batches
            unique_workspace_ids = {
                batch.workspace_id for batch in call_batches if batch.workspace_id
            }

            for workspace_id in unique_workspace_ids:
                # Get all call IDs for this workspace
                workspace_call_ids = [
                    call_id
                    for batch in call_batches
                    if batch.workspace_id == workspace_id
                    for call_id in batch.call_ids
                ]

                permissions, perm_api_calls = await self._fetch_workspace_permissions(
                    workspace_id, gong_client, workspace_call_ids
                )
                workspace_permissions_map[workspace_id] = permissions
                permissions_api_calls += perm_api_calls

            permissions_duration = time.perf_counter() - permissions_start

            logger.info(
                "Fetched permissions for all workspaces",
                workspace_count=len(unique_workspace_ids),
                permissions_api_calls=permissions_api_calls,
                duration_seconds=round(permissions_duration, 2),
            )

            dispatch_start = time.perf_counter()
            await self._dispatch_child_jobs(
                config=config,
                call_batches=call_batches,
                backfill_id=backfill_id,
                workspace_permissions_map=workspace_permissions_map,
            )
            dispatch_duration = time.perf_counter() - dispatch_start

            total_duration = time.perf_counter() - start_time

            logger.info(
                "Gong call backfill root job completed",
                backfill_id=backfill_id,
                tenant_id=config.tenant_id,
                batch_count=len(call_batches),
                total_calls=total_calls,
                discovery_api_calls=api_call_count,
                permissions_api_calls=permissions_api_calls,
                total_api_calls=api_call_count + permissions_api_calls,
                discovery_duration_seconds=round(discovery_duration, 2),
                permissions_duration_seconds=round(permissions_duration, 2),
                dispatch_duration_seconds=round(dispatch_duration, 2),
                total_duration_seconds=round(total_duration, 2),
            )

            # Note: Pruning of stale entities happens AFTER all child jobs complete
            # See: IndexJobWorker._track_backfill_completion() which triggers pruning
            # when backfill finishes
        finally:
            await gong_client.close()

    async def _discover_call_batches(
        self, config: GongCallBackfillRootConfig, gong_client: GongClient
    ) -> tuple[list[GongCallBatch], int, int]:
        """Discover call batches and return (batches, api_call_count, total_calls)."""
        batch_size = config.batch_size or DEFAULT_CALL_BATCH_SIZE
        from_datetime = (
            config.from_datetime.isoformat()
            if isinstance(config.from_datetime, datetime)
            else config.from_datetime
        )
        to_datetime = (
            config.to_datetime.isoformat()
            if isinstance(config.to_datetime, datetime)
            else config.to_datetime
        )

        batches: list[GongCallBatch] = []
        workspace_calls: defaultdict[str, list[str]] = defaultdict(list)
        call_limit = config.call_limit
        api_call_count = 0

        workspace_ids_config = config.workspace_ids
        if workspace_ids_config:
            workspace_ids_list = [str(ws_id) for ws_id in workspace_ids_config]
        else:
            workspaces = await gong_client.get_workspaces()
            api_call_count += 1  # Count get_workspaces API call
            workspace_ids_list = [str(ws.get("id")) for ws in workspaces if ws.get("id")]

        logger.info(
            "Discovering Gong calls",
            tenant_id=config.tenant_id,
            workspace_count=len(workspace_ids_list),
            from_datetime=from_datetime,
            to_datetime=to_datetime,
        )

        for workspace_id in workspace_ids_list:
            call_iterator = gong_client.iter_calls(
                workspace_id=workspace_id,
                from_datetime=from_datetime,
                to_datetime=to_datetime,
                limit=batch_size,
            )
            count = 0
            async for call in call_iterator:
                # iter_calls makes paginated API calls, count them
                if count % batch_size == 0:
                    api_call_count += 1

                call_id = call.get("id") or call.get("callId")
                if not call_id:
                    continue
                workspace_calls[workspace_id].append(str(call_id))
                count += 1
                if call_limit and count >= call_limit:
                    logger.info(
                        "Reached call_limit for workspace",
                        workspace_id=workspace_id,
                        call_limit=call_limit,
                    )
                    break

        total_calls = sum(len(call_ids) for call_ids in workspace_calls.values())

        for workspace_id, call_ids in workspace_calls.items():
            for i in range(0, len(call_ids), batch_size):
                batches.append(
                    GongCallBatch(
                        call_ids=call_ids[i : i + batch_size],
                        workspace_id=workspace_id,
                    )
                )

        return batches, api_call_count, total_calls

    async def _fetch_workspace_permissions(
        self,
        workspace_id: str,
        gong_client: GongClient,
        all_call_ids: list[str],
    ) -> tuple[GongWorkspacePermissions, int]:
        """Fetch all permission data for a workspace. Returns (permissions, api_call_count)."""
        api_call_count = 0

        # Fetch users
        users = await gong_client.get_users_extensive()
        api_call_count += 1

        # Fetch permission profiles
        profiles = await gong_client.get_permission_profiles(workspace_id)
        api_call_count += 1

        # Fetch users for each permission profile
        profile_users_map: dict[str, list[dict[str, object]]] = {}
        for profile in profiles:
            profile_id = str(profile.get("id"))
            profile_users = await gong_client.get_permission_profile_users(profile_id)
            profile_users_map[profile_id] = profile_users
            api_call_count += 1

        # Fetch library folders
        folders = await gong_client.get_library_folders(workspace_id)
        api_call_count += 1

        # Build call_id -> folder_ids mapping
        call_to_folder_ids: dict[str, list[str]] = {}
        for folder in folders:
            folder_id = str(folder.get("id"))
            try:
                folder_calls = await gong_client.get_library_folder_content(folder_id)
                api_call_count += 1

                for call in folder_calls:
                    call_id = str(call.get("id"))
                    if not call_id:
                        continue
                    if call_id not in call_to_folder_ids:
                        call_to_folder_ids[call_id] = []
                    call_to_folder_ids[call_id].append(folder_id)
            except Exception as e:
                logger.warning(
                    "Failed to fetch folder content",
                    folder_id=folder_id,
                    error=str(e),
                )

        permissions = GongWorkspacePermissions(
            workspace_id=workspace_id,
            users=users,
            permission_profiles=profiles,
            permission_profile_users=profile_users_map,
            library_folders=folders,
            call_to_folder_ids=call_to_folder_ids,
        )

        logger.info(
            "Fetched workspace permissions",
            workspace_id=workspace_id,
            user_count=len(users),
            profile_count=len(profiles),
            folder_count=len(folders),
            calls_with_folders=len(call_to_folder_ids),
            api_calls_made=api_call_count,
        )

        return permissions, api_call_count

    async def _dispatch_child_jobs(
        self,
        config: GongCallBackfillRootConfig,
        call_batches: list[GongCallBatch],
        backfill_id: str,
        workspace_permissions_map: dict[str, GongWorkspacePermissions],
    ) -> None:
        tasks = []
        for batch_index, batch in enumerate(call_batches):
            # Convert datetime objects to ISO strings for JSON serialization
            from_dt_str = (
                config.from_datetime.isoformat()
                if isinstance(config.from_datetime, datetime)
                else config.from_datetime
            )
            to_dt_str = (
                config.to_datetime.isoformat()
                if isinstance(config.to_datetime, datetime)
                else config.to_datetime
            )

            # Get workspace permissions for this batch
            workspace_permissions = None
            if batch.workspace_id:
                workspace_permissions = workspace_permissions_map.get(batch.workspace_id)

            child_config = GongCallBackfillConfig(
                tenant_id=config.tenant_id,
                call_batches=[batch],
                backfill_id=backfill_id,
                from_datetime=from_dt_str,
                to_datetime=to_dt_str,
                workspace_permissions=workspace_permissions,
                suppress_notification=config.suppress_notification,
            )
            tasks.append(self._send_child_job(child_config, batch_index))

        logger.info("Sending %s Gong call child jobs", len(tasks))
        await asyncio.gather(*tasks)

    async def _send_child_job(
        self,
        child_config: GongCallBackfillConfig,
        batch_index: int,
    ) -> None:
        async with self._sqs_semaphore:
            success = await self.sqs_client.send_backfill_ingest_message(
                backfill_config=child_config
            )
            if not success:
                raise RuntimeError(f"Failed to send Gong call child job {batch_index}")
