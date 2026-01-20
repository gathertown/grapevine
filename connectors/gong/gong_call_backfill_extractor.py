"""Child extractor for Gong call backfills."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, BaseIngestArtifact, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.gong.gong_artifacts import (
    GongCallArtifact,
    GongCallContent,
    GongCallMetadata,
    GongCallTranscriptArtifact,
    GongCallTranscriptContent,
    GongCallUsersAccessArtifact,
    GongCallUsersAccessContent,
    GongLibraryFolderArtifact,
    GongLibraryFolderContent,
    GongLibraryFolderMetadata,
    GongPermissionProfileArtifact,
    GongPermissionProfileContent,
    GongPermissionProfileMetadata,
    GongPermissionProfileUsersArtifact,
    GongPermissionProfileUsersContent,
    GongPermissionProfileUsersMetadata,
    GongUserArtifact,
    GongUserContent,
    GongUserMetadata,
)
from connectors.gong.gong_models import GongCallBackfillConfig, GongCallBatch
from src.clients.gong import GongClient
from src.clients.gong_factory import get_gong_client_for_tenant
from src.clients.ssm import SSMClient
from src.ingest.repositories import ArtifactRepository
from src.ingest.utils import DEFAULT_INDEX_BATCH_SIZE
from src.utils.logging import get_logger
from src.utils.tenant_config import (
    increment_backfill_attempted_ingest_jobs,
    increment_backfill_done_ingest_jobs,
    increment_backfill_total_index_jobs,
)

logger = get_logger(__name__)


class GongCallBackfillExtractor(BaseExtractor[GongCallBackfillConfig]):
    """Processes Gong call batches to create artifacts and trigger indexing."""

    source_name = "gong_call_backfill"

    def __init__(self, ssm_client: SSMClient) -> None:
        super().__init__()
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: GongCallBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        start_time = time.perf_counter()
        total_calls = sum(len(batch.call_ids) for batch in config.call_batches)

        logger.info(
            "Processing Gong call backfill job",
            tenant_id=config.tenant_id,
            job_id=job_id,
            batch_count=len(config.call_batches),
            total_calls=total_calls,
        )

        gong_client = await get_gong_client_for_tenant(config.tenant_id, self.ssm_client)
        repository = ArtifactRepository(db_pool)

        all_entity_ids: list[str] = []
        total_api_calls = 0
        total_artifacts = 0

        try:
            # Check if permissions were pre-fetched by root job
            if config.workspace_permissions:
                logger.info(
                    "Using pre-fetched workspace permissions",
                    workspace_id=config.workspace_permissions.workspace_id,
                    user_count=len(config.workspace_permissions.users),
                    profile_count=len(config.workspace_permissions.permission_profiles),
                    folder_count=len(config.workspace_permissions.library_folders),
                )
                users = config.workspace_permissions.users
            else:
                # Fall back to fetching users (backward compatibility)
                users_start = time.perf_counter()
                users = await gong_client.get_users_extensive()
                users_duration = time.perf_counter() - users_start
                total_api_calls += 1  # Count get_users_extensive call

                logger.info(
                    "Fetched users for job",
                    user_count=len(users),
                    duration_seconds=round(users_duration, 2),
                )

            for batch_idx, call_batch in enumerate(config.call_batches):
                batch_entity_ids, batch_api_calls, batch_artifacts = await self._process_call_batch(
                    job_id=job_id,
                    config=config,
                    call_batch=call_batch,
                    gong_client=gong_client,
                    repository=repository,
                    users=users,  # Pass cached or pre-fetched users
                    batch_index=batch_idx,
                )
                all_entity_ids.extend(batch_entity_ids)
                total_api_calls += batch_api_calls
                total_artifacts += batch_artifacts

            total_index_batches = (
                len(all_entity_ids) + DEFAULT_INDEX_BATCH_SIZE - 1
            ) // DEFAULT_INDEX_BATCH_SIZE
            if config.backfill_id and total_index_batches > 0:
                await increment_backfill_total_index_jobs(
                    config.backfill_id, config.tenant_id, total_index_batches
                )

            indexing_start = time.perf_counter()
            for i in range(0, len(all_entity_ids), DEFAULT_INDEX_BATCH_SIZE):
                entity_ids_slice = all_entity_ids[i : i + DEFAULT_INDEX_BATCH_SIZE]
                await trigger_indexing(
                    entity_ids_slice,
                    DocumentSource.GONG,
                    config.tenant_id,
                    config.backfill_id,
                    config.suppress_notification,
                )
            indexing_duration = time.perf_counter() - indexing_start

            if config.backfill_id:
                await increment_backfill_done_ingest_jobs(config.backfill_id, config.tenant_id, 1)

            total_duration = time.perf_counter() - start_time

            logger.info(
                "Gong call backfill job completed",
                tenant_id=config.tenant_id,
                job_id=job_id,
                backfill_id=config.backfill_id,
                total_calls_processed=total_calls,
                total_artifacts_created=total_artifacts,
                total_api_calls=total_api_calls,
                indexing_duration_seconds=round(indexing_duration, 2),
                total_duration_seconds=round(total_duration, 2),
                avg_seconds_per_call=round(total_duration / total_calls, 2)
                if total_calls > 0
                else 0,
            )
        finally:
            if config.backfill_id:
                await increment_backfill_attempted_ingest_jobs(
                    config.backfill_id, config.tenant_id, 1
                )
            await gong_client.close()

    async def _process_call_batch(
        self,
        job_id: str,
        config: GongCallBackfillConfig,
        call_batch: GongCallBatch,
        gong_client: GongClient,
        repository: ArtifactRepository,
        users: list[dict[str, Any]],
        batch_index: int = 0,
    ) -> tuple[list[str], int, int]:
        """Process a batch of calls and return (entity_ids, api_call_count, artifact_count)."""
        batch_start_time = time.perf_counter()
        call_ids = call_batch.call_ids
        if not call_ids:
            return [], 0, 0

        logger.info(
            "Processing Gong call batch",
            tenant_id=config.tenant_id,
            batch_index=batch_index,
            call_count=len(call_ids),
            workspace_id=call_batch.workspace_id,
        )

        artifacts: list[BaseIngestArtifact] = []
        api_call_count = 0

        # Users (already fetched at job level or pre-fetched by root)
        for user in users:
            user_id = str(user.get("id"))
            metadata = GongUserMetadata(
                workspace_id=user.get("workspaceId"),
                email=user.get("emailAddress"),
            )
            content = GongUserContent.model_validate(user)
            artifacts.append(
                GongUserArtifact(
                    entity_id=f"gong_user_{user_id}",
                    ingest_job_id=UUID(job_id),
                    content=content,
                    metadata=metadata,
                    source_updated_at=datetime.now(tz=UTC),
                )
            )

        # Check if permissions were pre-fetched
        call_to_folders: dict[str, list[str]] = {}
        if config.workspace_permissions and call_batch.workspace_id:
            # Use pre-fetched permission data
            logger.info(
                "Using pre-fetched permission profiles and folders",
                workspace_id=call_batch.workspace_id,
            )

            profiles = config.workspace_permissions.permission_profiles
            for profile in profiles:
                profile_id = str(profile.get("id"))
                profile_metadata = GongPermissionProfileMetadata(
                    workspace_id=call_batch.workspace_id
                )
                profile_content = GongPermissionProfileContent.model_validate(profile)
                artifacts.append(
                    GongPermissionProfileArtifact(
                        entity_id=f"gong_permission_profile_{profile_id}",
                        ingest_job_id=UUID(job_id),
                        content=profile_content,
                        metadata=profile_metadata,
                        source_updated_at=datetime.now(tz=UTC),
                    )
                )

                # Use pre-fetched profile users
                profile_users = config.workspace_permissions.permission_profile_users.get(
                    profile_id, []
                )
                profile_users_content = GongPermissionProfileUsersContent(
                    profile_id=profile_id,
                    users=profile_users,
                )
                artifacts.append(
                    GongPermissionProfileUsersArtifact(
                        entity_id=f"gong_permission_profile_users_{profile_id}",
                        ingest_job_id=UUID(job_id),
                        content=profile_users_content,
                        metadata=GongPermissionProfileUsersMetadata(
                            workspace_id=call_batch.workspace_id
                        ),
                        source_updated_at=datetime.now(tz=UTC),
                    )
                )

            # Use pre-fetched library folders
            folders = config.workspace_permissions.library_folders
            call_to_folders = config.workspace_permissions.call_to_folder_ids

            logger.info(
                "Using pre-fetched library folders",
                folder_count=len(folders),
                calls_with_folders=len(call_to_folders),
            )

            for folder in folders:
                folder_id = str(folder.get("id"))
                folder_metadata = GongLibraryFolderMetadata(workspace_id=call_batch.workspace_id)
                folder_content = GongLibraryFolderContent.model_validate(folder)
                artifacts.append(
                    GongLibraryFolderArtifact(
                        entity_id=f"gong_library_folder_{folder_id}",
                        ingest_job_id=UUID(job_id),
                        content=folder_content,
                        metadata=folder_metadata,
                        source_updated_at=datetime.now(tz=UTC),
                    )
                )

        elif call_batch.workspace_id:
            # Fall back to fetching permission data (backward compatibility)
            logger.info(
                "Fetching permission profiles and folders (no pre-fetched data)",
                workspace_id=call_batch.workspace_id,
            )

            profiles = await gong_client.get_permission_profiles(call_batch.workspace_id)
            api_call_count += 1  # Count get_permission_profiles call
            for profile in profiles:
                profile_id = str(profile.get("id"))
                profile_metadata = GongPermissionProfileMetadata(
                    workspace_id=call_batch.workspace_id
                )
                profile_content = GongPermissionProfileContent.model_validate(profile)
                artifacts.append(
                    GongPermissionProfileArtifact(
                        entity_id=f"gong_permission_profile_{profile_id}",
                        ingest_job_id=UUID(job_id),
                        content=profile_content,
                        metadata=profile_metadata,
                        source_updated_at=datetime.now(tz=UTC),
                    )
                )
                profile_users = await gong_client.get_permission_profile_users(profile_id)
                api_call_count += 1  # Count get_permission_profile_users call
                profile_users_content = GongPermissionProfileUsersContent(
                    profile_id=profile_id, users=profile_users
                )
                artifacts.append(
                    GongPermissionProfileUsersArtifact(
                        entity_id=f"gong_permission_profile_users_{profile_id}",
                        ingest_job_id=UUID(job_id),
                        content=profile_users_content,
                        metadata=GongPermissionProfileUsersMetadata(
                            workspace_id=call_batch.workspace_id
                        ),
                        source_updated_at=datetime.now(tz=UTC),
                    )
                )

            # Library folders and their contents
            folders = await gong_client.get_library_folders(call_batch.workspace_id)
            api_call_count += 1  # Count get_library_folders call
            logger.debug(
                f"Found {len(folders)} library folders for workspace {call_batch.workspace_id}"
            )

            for folder in folders:
                folder_id = str(folder.get("id"))
                folder_name = folder.get("name", "Unknown")
                folder_metadata = GongLibraryFolderMetadata(workspace_id=call_batch.workspace_id)
                folder_content = GongLibraryFolderContent.model_validate(folder)

                # Fetch calls in this folder
                try:
                    logger.debug(f"Fetching content for folder {folder_id} (name: {folder_name})")
                    folder_calls = await gong_client.get_library_folder_content(folder_id)
                    api_call_count += 1  # Count get_library_folder_content call

                    logger.debug(
                        f"Folder {folder_id} ({folder_name}) contains {len(folder_calls)} calls"
                    )
                    for call in folder_calls:
                        call_id = str(call.get("id"))
                        if not call_id:
                            logger.warning(
                                f"Call in folder {folder_id} has no ID",
                                folder_id=folder_id,
                                call_data=call,
                            )
                            continue

                        if call_id not in call_to_folders:
                            call_to_folders[call_id] = []
                        call_to_folders[call_id].append(folder_id)
                        logger.debug(
                            f"Mapped call {call_id} to folder {folder_id}",
                            call_id=call_id,
                            folder_id=folder_id,
                            folder_name=folder_name,
                        )
                except Exception as e:
                    logger.warning(
                        f"Failed to fetch content for folder {folder_id}: {e}",
                        folder_id=folder_id,
                        error=str(e),
                    )

                artifacts.append(
                    GongLibraryFolderArtifact(
                        entity_id=f"gong_library_folder_{folder_id}",
                        ingest_job_id=UUID(job_id),
                        content=folder_content,
                        metadata=folder_metadata,
                        source_updated_at=datetime.now(tz=UTC),
                    )
                )

        logger.info(f"Built call-to-folders mapping with {len(call_to_folders)} call entries")
        logger.debug(f"Sample call-to-folders mapping: {dict(list(call_to_folders.items())[:3])}")
        logger.debug(f"Call IDs being processed: {call_ids[:5]}...")  # Show first 5

        # Calls
        extensive_calls_start = time.perf_counter()
        extensive_calls = await gong_client.get_calls_extensive(call_ids)
        extensive_calls_duration = time.perf_counter() - extensive_calls_start
        api_call_count += 1  # Count get_calls_extensive call

        logger.info(
            "Fetched extensive call data",
            call_count=len(call_ids),
            duration_seconds=round(extensive_calls_duration, 2),
        )

        # Check if the call_ids from extensive calls match what's in call_to_folders
        extensive_call_ids = [
            str(call.get("metaData", {}).get("id"))
            for call in extensive_calls
            if call.get("metaData", {}).get("id")
        ]
        logger.debug(f"Extensive call IDs: {extensive_call_ids[:5]}...")
        logger.debug(f"Call IDs in call_to_folders: {list(call_to_folders.keys())[:5]}...")

        # Find intersection
        common_ids = set(extensive_call_ids) & set(call_to_folders.keys())
        logger.info(
            f"Found {len(common_ids)}/{len(extensive_call_ids)} calls that exist in both extensive calls and folder mapping"
        )

        # Pass date range to transcript API (required by Gong API)
        from_dt = self._format_datetime_for_api(config.from_datetime)
        to_dt = self._format_datetime_for_api(config.to_datetime)

        transcripts_start = time.perf_counter()
        transcript_batches = await gong_client.get_call_transcripts(
            call_ids,
            from_datetime=from_dt,
            to_datetime=to_dt,
        )
        transcripts_duration = time.perf_counter() - transcripts_start
        api_call_count += 1  # Count get_call_transcripts call

        user_access_start = time.perf_counter()
        user_access_entries = await gong_client.get_call_users_access(call_ids)
        user_access_duration = time.perf_counter() - user_access_start
        api_call_count += 1  # Count get_call_users_access call

        logger.info(
            "Fetched Gong call supplementary data",
            call_count=len(extensive_calls),
            transcript_count=len(transcript_batches),
            access_entry_count=len(user_access_entries),
            transcripts_duration_seconds=round(transcripts_duration, 2),
            user_access_duration_seconds=round(user_access_duration, 2),
        )

        transcript_lookup = {str(entry.get("callId")): entry for entry in transcript_batches}
        access_lookup = {
            str(entry.get("callId")): entry.get("users", []) for entry in user_access_entries
        }

        call_entity_ids: list[str] = []

        for call_data in extensive_calls:
            meta = call_data.get("metaData", {})
            call_id = str(meta.get("id"))
            if not call_id:
                continue

            logger.debug(f"Processing call {call_id} for metadata creation")

            # Parse and convert datetime to ISO string
            started_dt = self._parse_datetime(meta.get("started"))
            source_created_at_str = started_dt.isoformat() if started_dt else None

            folder_ids = call_to_folders.get(call_id, [])
            logger.debug(f"Call {call_id} has {len(folder_ids)} folder IDs: {folder_ids}")
            logger.debug(f"Call {call_id} exists in call_to_folders: {call_id in call_to_folders}")

            call_metadata = GongCallMetadata(
                call_id=call_id,
                workspace_id=call_batch.workspace_id,
                owner_user_id=str(meta.get("primaryUserId")) if meta.get("primaryUserId") else None,
                is_private=bool(meta.get("isPrivate", False)),
                library_folder_ids=folder_ids,
                explicit_access_user_ids=[
                    str(user.get("id"))  # Changed from "userId" to "id" to match API
                    for user in access_lookup.get(call_id, [])
                    if user.get("id")
                ],
                source_created_at=source_created_at_str,
            )

            parties = call_data.get("parties", [])
            call_artifact = GongCallArtifact(
                entity_id=f"gong_call_{call_id}",
                ingest_job_id=UUID(job_id),
                content=GongCallContent(meta_data=meta, parties=parties),
                metadata=call_metadata,
                source_updated_at=self._parse_datetime(meta.get("updated"))
                or self._parse_datetime(meta.get("started"))
                or datetime.now(tz=UTC),
            )
            artifacts.append(call_artifact)
            call_entity_ids.append(call_artifact.entity_id)

            transcript_entry = transcript_lookup.get(call_id)
            if transcript_entry:
                normalized_transcript = self._normalize_transcript(transcript_entry)
                logger.debug(
                    "Adding transcript for call",
                    call_id=call_id,
                    sentence_count=len(normalized_transcript),
                )
                transcript_artifact = GongCallTranscriptArtifact(
                    entity_id=f"gong_call_transcript_{call_id}",
                    ingest_job_id=UUID(job_id),
                    content=GongCallTranscriptContent(
                        call_id=call_id,
                        transcript=normalized_transcript,
                    ),
                    source_updated_at=datetime.now(tz=UTC),
                )
                artifacts.append(transcript_artifact)
            else:
                logger.warning("No transcript found for call", call_id=call_id)

            access_users = access_lookup.get(call_id)
            if access_users is not None:
                access_artifact = GongCallUsersAccessArtifact(
                    entity_id=f"gong_call_users_access_{call_id}",
                    ingest_job_id=UUID(job_id),
                    content=GongCallUsersAccessContent(
                        call_id=call_id,
                        users=access_users,
                    ),
                    source_updated_at=datetime.now(tz=UTC),
                )
                artifacts.append(access_artifact)

        # Store artifacts in database
        # Use force_upsert to ensure workspace attribution and permissions are always updated
        storage_start = time.perf_counter()
        await repository.force_upsert_artifacts_batch(artifacts, backfill_id=config.backfill_id)
        storage_duration = time.perf_counter() - storage_start

        batch_total_duration = time.perf_counter() - batch_start_time

        logger.info(
            "Gong call batch processing completed",
            tenant_id=config.tenant_id,
            batch_index=batch_index,
            calls_processed=len(call_ids),
            artifacts_created=len(artifacts),
            api_calls_made=api_call_count,
            storage_duration_seconds=round(storage_duration, 2),
            batch_total_duration_seconds=round(batch_total_duration, 2),
            avg_seconds_per_call=round(batch_total_duration / len(call_ids), 2) if call_ids else 0,
        )

        return call_entity_ids, api_call_count, len(artifacts)

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            return None

    def _format_datetime_for_api(self, value: str | datetime | None) -> str | None:
        """Convert datetime objects to ISO format strings with timezone for API calls."""
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, datetime):
            # Ensure the datetime has timezone info, default to UTC if not
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            return value.isoformat()
        # This should never be reached given the type annotation, but for completeness
        return None  # type: ignore[unreachable]

    def _normalize_transcript(self, transcript_payload: dict[str, Any]) -> list[dict[str, object]]:
        """Normalize Gong transcript payload to a flat list of sentences."""

        normalized: list[dict[str, object]] = []

        blocks: list[Any] | None = None
        transcript = transcript_payload.get("transcript")
        if isinstance(transcript, list):
            blocks = transcript

        if not blocks:
            return normalized

        for block in blocks:
            if not isinstance(block, dict):
                continue
            speaker_id = block.get("speakerId")
            sentences = block.get("sentences", [])
            if not isinstance(sentences, list):
                continue
            for sentence in sentences:
                if not isinstance(sentence, dict):
                    continue
                normalized.append(
                    {
                        "index": len(normalized),
                        "speakerId": speaker_id,
                        "start": sentence.get("start"),
                        "end": sentence.get("end"),
                        "text": sentence.get("text", ""),
                    }
                )

        return normalized
