"""Tests for the Gong call backfill extractors."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from connectors.gong import GongCallBackfillExtractor, GongCallBackfillRootExtractor
from connectors.gong.gong_models import (
    GongCallBackfillConfig,
    GongCallBackfillRootConfig,
    GongCallBatch,
)
from src.clients.gong import GongClient
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient


@pytest.fixture()
def gong_client_mock() -> AsyncMock:
    client = AsyncMock(spec=GongClient)
    return client


class TestGongCallBackfillRootExtractor:
    @pytest.mark.asyncio
    async def test_discover_batches_from_api(
        self,
        gong_client_mock: AsyncMock,
    ) -> None:
        ssm_client = MagicMock(spec=SSMClient)
        mock_sqs = MagicMock(spec=SQSClient)
        extractor = GongCallBackfillRootExtractor(ssm_client, mock_sqs)

        gong_client_mock.get_workspaces.return_value = [{"id": "ws1"}]

        async def iter_calls(**_kwargs: object) -> AsyncIterator[dict[str, str]]:
            for call_id in ["c1", "c2", "c3"]:
                yield {"id": call_id}

        gong_client_mock.iter_calls.side_effect = iter_calls

        with patch(
            "connectors.gong.gong_call_backfill_root_extractor.get_gong_client_for_tenant",
            return_value=gong_client_mock,
        ):
            batches, api_calls, total_calls = await extractor._discover_call_batches(
                GongCallBackfillRootConfig(tenant_id="tenant", workspace_ids=None),
                gong_client_mock,
            )

        assert len(batches) == 1
        assert batches[0].call_ids == ["c1", "c2", "c3"]
        assert batches[0].workspace_id == "ws1"


class TestGongCallBackfillExtractor:
    @pytest.mark.asyncio
    async def test_process_call_batch_creates_artifacts(
        self,
        gong_client_mock: AsyncMock,
    ) -> None:
        ssm_client = MagicMock(spec=SSMClient)
        extractor = GongCallBackfillExtractor(ssm_client)

        repository_mock = AsyncMock()

        gong_client_mock.get_users_extensive.return_value = [
            {
                "id": "u1",
                "workspaceId": "ws1",
                "emailAddress": "user@example.com",
            }
        ]
        gong_client_mock.get_permission_profiles.return_value = []
        gong_client_mock.get_library_folders.return_value = []
        gong_client_mock.get_calls_extensive.return_value = [
            {
                "metaData": {
                    "id": "call1",
                    "started": "2024-01-01T00:00:00Z",
                    "updated": "2024-01-02T00:00:00Z",
                },
                "parties": [],
            }
        ]
        gong_client_mock.get_call_transcripts.return_value = []
        gong_client_mock.get_call_users_access.return_value = []

        batch = GongCallBatch(call_ids=["call1"], workspace_id="ws1")

        entity_ids, api_calls, artifacts_created = await extractor._process_call_batch(
            job_id=str(UUID("12345678-1234-5678-1234-567812345678")),
            config=GongCallBackfillConfig(
                tenant_id="tenant",
                call_batches=[batch],
            ),
            call_batch=batch,
            gong_client=gong_client_mock,
            repository=repository_mock,
            users=gong_client_mock.get_users_extensive.return_value,
        )

        assert entity_ids == ["gong_call_call1"]
        repository_mock.force_upsert_artifacts_batch.assert_awaited()

    @pytest.mark.asyncio
    async def test_process_call_batch_handles_empty_call_ids(self) -> None:
        ssm_client = MagicMock(spec=SSMClient)
        extractor = GongCallBackfillExtractor(ssm_client)

        batch = GongCallBatch(call_ids=[], workspace_id=None)

        entity_ids, api_calls, artifacts_created = await extractor._process_call_batch(
            job_id=str(UUID("12345678-1234-5678-1234-567812345678")),
            config=GongCallBackfillConfig(
                tenant_id="tenant",
                call_batches=[batch],
            ),
            call_batch=batch,
            gong_client=AsyncMock(spec=GongClient),
            repository=AsyncMock(),
            users=[],
        )

        assert entity_ids == []

    @pytest.mark.asyncio
    async def test_process_job_handles_gong_client_error(self, gong_client_mock: AsyncMock) -> None:
        ssm_client = MagicMock(spec=SSMClient)
        extractor = GongCallBackfillExtractor(ssm_client)

        config = GongCallBackfillConfig(
            tenant_id="tenant",
            call_batches=[GongCallBatch(call_ids=["call1"], workspace_id="ws1")],
            backfill_id="backfill-123",
        )

        gong_client_mock.get_users_extensive.side_effect = RuntimeError("boom")

        with (
            patch(
                "connectors.gong.gong_call_backfill_extractor.get_gong_client_for_tenant",
                return_value=gong_client_mock,
            ),
            patch(
                "connectors.gong.gong_call_backfill_extractor.ArtifactRepository",
                return_value=AsyncMock(),
            ) as repo_mock,
            patch(
                "connectors.gong.gong_call_backfill_extractor.increment_backfill_attempted_ingest_jobs"
            ) as attempted_mock,
            patch("src.utils.tenant_config.increment_backfill_done_ingest_jobs") as done_mock,
            patch("src.utils.tenant_config.increment_backfill_total_index_jobs") as total_mock,
            pytest.raises(RuntimeError, match="boom"),
        ):
            await extractor.process_job(
                job_id="job-123",
                config=config,
                db_pool=AsyncMock(),
                trigger_indexing=AsyncMock(),
            )

        repo_instance = repo_mock.return_value
        repo_instance.force_upsert_artifacts_batch.assert_not_awaited()
        done_mock.assert_not_called()
        total_mock.assert_not_called()
        attempted_mock.assert_awaited_once_with("backfill-123", "tenant", 1)
        gong_client_mock.close.assert_awaited()
