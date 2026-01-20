"""Tests for Attio backfill extractors with batch processing."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import requests

from connectors.attio.attio_artifacts import AttioObjectType
from connectors.attio.attio_backfill_root_extractor import AttioBackfillRootExtractor
from connectors.attio.attio_company_backfill_extractor import AttioCompanyBackfillExtractor
from connectors.attio.attio_deal_backfill_extractor import AttioDealBackfillExtractor
from connectors.attio.attio_models import (
    AttioCompanyBackfillConfig,
    AttioDealBackfillConfig,
    AttioPersonBackfillConfig,
)
from connectors.attio.attio_person_backfill_extractor import AttioPersonBackfillExtractor
from src.jobs.exceptions import ExtendVisibilityException


@pytest.fixture
def mock_ssm_client():
    """Create a mock SSM client."""
    return MagicMock()


@pytest.fixture
def mock_db_pool():
    """Create a mock database pool."""
    pool = MagicMock()
    return pool


@pytest.fixture
def mock_trigger_indexing():
    """Create a mock trigger indexing callback."""
    return AsyncMock()


@pytest.fixture
def mock_attio_client():
    """Create a mock Attio client."""
    client = MagicMock()
    return client


@pytest.fixture
def mock_company_record():
    """Sample company record from Attio API."""
    return {
        "id": {"record_id": "rec_company_1"},
        "values": {
            "name": [{"value": "Company One"}],
            "domains": [{"domain": "company1.com"}],
        },
        "created_at": "2024-01-15T10:00:00.000Z",
        "updated_at": "2024-01-20T10:00:00.000Z",
    }


@pytest.fixture
def mock_person_record():
    """Sample person record from Attio API."""
    return {
        "id": {"record_id": "rec_person_1"},
        "values": {
            "name": [{"full_name": "John Doe"}],
            "email_addresses": [{"email_address": "john@example.com"}],
        },
        "created_at": "2024-01-15T10:00:00.000Z",
        "updated_at": "2024-01-20T10:00:00.000Z",
    }


@pytest.fixture
def mock_deal_record():
    """Sample deal record from Attio API."""
    return {
        "id": {"record_id": "rec_deal_1"},
        "values": {
            "name": [{"value": "Big Deal"}],
            "value": [{"currency_value": 50000}],
        },
        "created_at": "2024-01-15T10:00:00.000Z",
        "updated_at": "2024-01-20T10:00:00.000Z",
    }


class TestAttioCompanyBackfillExtractorBatch:
    """Test suite for company backfill extractor batch processing."""

    @pytest.mark.asyncio
    async def test_process_batch_processes_all_record_ids(
        self,
        mock_ssm_client,
        mock_db_pool,
        mock_trigger_indexing,
        mock_attio_client,
        mock_company_record,
    ):
        """Test that all record IDs in the batch are processed."""
        extractor = AttioCompanyBackfillExtractor(mock_ssm_client)
        job_id = str(uuid4())
        tenant_id = "tenant_123"
        record_ids = ["rec_company_1", "rec_company_2", "rec_company_3"]

        config = AttioCompanyBackfillConfig(
            tenant_id=tenant_id,
            record_ids=record_ids,
            backfill_id="backfill_123",
        )

        mock_attio_client.get_record.return_value = mock_company_record

        with (
            patch(
                "connectors.attio.attio_company_backfill_extractor.get_attio_client_for_tenant",
                new_callable=AsyncMock,
                return_value=mock_attio_client,
            ),
            patch.object(extractor, "store_artifacts_batch", new_callable=AsyncMock),
            patch(
                "connectors.attio.attio_company_backfill_extractor.increment_backfill_done_ingest_jobs",
                new_callable=AsyncMock,
            ),
            patch(
                "connectors.attio.attio_company_backfill_extractor.increment_backfill_attempted_ingest_jobs",
                new_callable=AsyncMock,
            ),
            patch(
                "connectors.attio.attio_company_backfill_extractor.increment_backfill_total_index_jobs",
                new_callable=AsyncMock,
            ),
        ):
            await extractor.process_job(
                job_id=job_id,
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

        # Verify get_record was called for each record_id
        assert mock_attio_client.get_record.call_count == 3

    @pytest.mark.asyncio
    async def test_start_timestamp_delays_processing(
        self,
        mock_ssm_client,
        mock_db_pool,
        mock_trigger_indexing,
    ):
        """Test that start_timestamp causes delayed processing."""
        extractor = AttioCompanyBackfillExtractor(mock_ssm_client)
        job_id = str(uuid4())
        tenant_id = "tenant_123"

        # Set start_timestamp in the future
        future_time = datetime.now(UTC) + timedelta(seconds=60)
        config = AttioCompanyBackfillConfig(
            tenant_id=tenant_id,
            record_ids=["rec_1"],
            start_timestamp=future_time,
            backfill_id="backfill_123",
        )

        with pytest.raises(ExtendVisibilityException) as exc_info:
            await extractor.process_job(
                job_id=job_id,
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

        assert exc_info.value.visibility_timeout_seconds > 0

    @pytest.mark.asyncio
    async def test_past_start_timestamp_processes_immediately(
        self,
        mock_ssm_client,
        mock_db_pool,
        mock_trigger_indexing,
        mock_attio_client,
        mock_company_record,
    ):
        """Test that past start_timestamp allows immediate processing."""
        extractor = AttioCompanyBackfillExtractor(mock_ssm_client)
        job_id = str(uuid4())
        tenant_id = "tenant_123"

        # Set start_timestamp in the past
        past_time = datetime.now(UTC) - timedelta(seconds=60)
        config = AttioCompanyBackfillConfig(
            tenant_id=tenant_id,
            record_ids=["rec_1"],
            start_timestamp=past_time,
            backfill_id="backfill_123",
        )

        mock_attio_client.get_record.return_value = mock_company_record

        with (
            patch(
                "connectors.attio.attio_company_backfill_extractor.get_attio_client_for_tenant",
                new_callable=AsyncMock,
                return_value=mock_attio_client,
            ),
            patch.object(extractor, "store_artifacts_batch", new_callable=AsyncMock),
            patch(
                "connectors.attio.attio_company_backfill_extractor.increment_backfill_done_ingest_jobs",
                new_callable=AsyncMock,
            ),
            patch(
                "connectors.attio.attio_company_backfill_extractor.increment_backfill_attempted_ingest_jobs",
                new_callable=AsyncMock,
            ),
            patch(
                "connectors.attio.attio_company_backfill_extractor.increment_backfill_total_index_jobs",
                new_callable=AsyncMock,
            ),
        ):
            # Should not raise ExtendVisibilityException
            await extractor.process_job(
                job_id=job_id,
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

        mock_attio_client.get_record.assert_called_once()


class TestAttioPersonBackfillExtractorBatch:
    """Test suite for person backfill extractor batch processing."""

    @pytest.mark.asyncio
    async def test_process_batch_processes_all_record_ids(
        self,
        mock_ssm_client,
        mock_db_pool,
        mock_trigger_indexing,
        mock_attio_client,
        mock_person_record,
    ):
        """Test that all record IDs in the batch are processed."""
        extractor = AttioPersonBackfillExtractor(mock_ssm_client)
        job_id = str(uuid4())
        tenant_id = "tenant_123"
        record_ids = ["rec_person_1", "rec_person_2"]

        config = AttioPersonBackfillConfig(
            tenant_id=tenant_id,
            record_ids=record_ids,
            backfill_id="backfill_123",
        )

        mock_attio_client.get_record.return_value = mock_person_record

        with (
            patch(
                "connectors.attio.attio_person_backfill_extractor.get_attio_client_for_tenant",
                new_callable=AsyncMock,
                return_value=mock_attio_client,
            ),
            patch.object(extractor, "store_artifacts_batch", new_callable=AsyncMock),
            patch(
                "connectors.attio.attio_person_backfill_extractor.increment_backfill_done_ingest_jobs",
                new_callable=AsyncMock,
            ),
            patch(
                "connectors.attio.attio_person_backfill_extractor.increment_backfill_attempted_ingest_jobs",
                new_callable=AsyncMock,
            ),
            patch(
                "connectors.attio.attio_person_backfill_extractor.increment_backfill_total_index_jobs",
                new_callable=AsyncMock,
            ),
        ):
            await extractor.process_job(
                job_id=job_id,
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

        assert mock_attio_client.get_record.call_count == 2

    @pytest.mark.asyncio
    async def test_start_timestamp_delays_processing(
        self,
        mock_ssm_client,
        mock_db_pool,
        mock_trigger_indexing,
    ):
        """Test that start_timestamp causes delayed processing."""
        extractor = AttioPersonBackfillExtractor(mock_ssm_client)
        job_id = str(uuid4())

        future_time = datetime.now(UTC) + timedelta(seconds=60)
        config = AttioPersonBackfillConfig(
            tenant_id="tenant_123",
            record_ids=["rec_1"],
            start_timestamp=future_time,
            backfill_id="backfill_123",
        )

        with pytest.raises(ExtendVisibilityException):
            await extractor.process_job(
                job_id=job_id,
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )


class TestAttioDealBackfillExtractorBatch:
    """Test suite for deal backfill extractor batch processing."""

    @pytest.mark.asyncio
    async def test_process_batch_processes_all_record_ids(
        self,
        mock_ssm_client,
        mock_db_pool,
        mock_trigger_indexing,
        mock_attio_client,
        mock_deal_record,
    ):
        """Test that all record IDs in the batch are processed."""
        extractor = AttioDealBackfillExtractor(mock_ssm_client)
        job_id = str(uuid4())
        tenant_id = "tenant_123"
        record_ids = ["rec_deal_1", "rec_deal_2"]

        config = AttioDealBackfillConfig(
            tenant_id=tenant_id,
            record_ids=record_ids,
            backfill_id="backfill_123",
            include_notes=False,
            include_tasks=False,
        )

        mock_attio_client.get_record.return_value = mock_deal_record

        with (
            patch(
                "connectors.attio.attio_deal_backfill_extractor.get_attio_client_for_tenant",
                new_callable=AsyncMock,
                return_value=mock_attio_client,
            ),
            patch.object(extractor, "store_artifacts_batch", new_callable=AsyncMock),
            patch(
                "connectors.attio.attio_deal_backfill_extractor.increment_backfill_done_ingest_jobs",
                new_callable=AsyncMock,
            ),
            patch(
                "connectors.attio.attio_deal_backfill_extractor.increment_backfill_attempted_ingest_jobs",
                new_callable=AsyncMock,
            ),
            patch(
                "connectors.attio.attio_deal_backfill_extractor.increment_backfill_total_index_jobs",
                new_callable=AsyncMock,
            ),
        ):
            await extractor.process_job(
                job_id=job_id,
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

        assert mock_attio_client.get_record.call_count == 2

    @pytest.mark.asyncio
    async def test_process_batch_fetches_notes_and_tasks(
        self,
        mock_ssm_client,
        mock_db_pool,
        mock_trigger_indexing,
        mock_attio_client,
        mock_deal_record,
    ):
        """Test that notes and tasks are fetched when enabled."""
        extractor = AttioDealBackfillExtractor(mock_ssm_client)
        job_id = str(uuid4())

        config = AttioDealBackfillConfig(
            tenant_id="tenant_123",
            record_ids=["rec_deal_1"],
            backfill_id="backfill_123",
            include_notes=True,
            include_tasks=True,
        )

        mock_attio_client.get_record.return_value = mock_deal_record
        mock_attio_client.get_notes_for_record.return_value = [{"id": "note_1"}]
        mock_attio_client.get_tasks_for_record.return_value = [{"id": "task_1"}]

        with (
            patch(
                "connectors.attio.attio_deal_backfill_extractor.get_attio_client_for_tenant",
                new_callable=AsyncMock,
                return_value=mock_attio_client,
            ),
            patch.object(extractor, "store_artifacts_batch", new_callable=AsyncMock),
            patch(
                "connectors.attio.attio_deal_backfill_extractor.increment_backfill_done_ingest_jobs",
                new_callable=AsyncMock,
            ),
            patch(
                "connectors.attio.attio_deal_backfill_extractor.increment_backfill_attempted_ingest_jobs",
                new_callable=AsyncMock,
            ),
            patch(
                "connectors.attio.attio_deal_backfill_extractor.increment_backfill_total_index_jobs",
                new_callable=AsyncMock,
            ),
        ):
            await extractor.process_job(
                job_id=job_id,
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

        mock_attio_client.get_notes_for_record.assert_called_once()
        mock_attio_client.get_tasks_for_record.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_timestamp_delays_processing(
        self,
        mock_ssm_client,
        mock_db_pool,
        mock_trigger_indexing,
    ):
        """Test that start_timestamp causes delayed processing."""
        extractor = AttioDealBackfillExtractor(mock_ssm_client)
        job_id = str(uuid4())

        future_time = datetime.now(UTC) + timedelta(seconds=60)
        config = AttioDealBackfillConfig(
            tenant_id="tenant_123",
            record_ids=["rec_1"],
            start_timestamp=future_time,
            backfill_id="backfill_123",
        )

        with pytest.raises(ExtendVisibilityException):
            await extractor.process_job(
                job_id=job_id,
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )


class TestBackfillExtractorErrorHandling:
    """Test suite for error handling in batch processing."""

    @pytest.mark.asyncio
    async def test_company_extractor_continues_on_record_failure(
        self,
        mock_ssm_client,
        mock_db_pool,
        mock_trigger_indexing,
        mock_attio_client,
        mock_company_record,
    ):
        """Test that processing continues when individual records fail."""
        extractor = AttioCompanyBackfillExtractor(mock_ssm_client)
        job_id = str(uuid4())

        config = AttioCompanyBackfillConfig(
            tenant_id="tenant_123",
            record_ids=["rec_1", "rec_2_fail", "rec_3"],
            backfill_id="backfill_123",
        )

        # Second record fails, others succeed
        def get_record_side_effect(object_slug, record_id):
            if record_id == "rec_2_fail":
                raise Exception("Record not found")
            return mock_company_record

        mock_attio_client.get_record.side_effect = get_record_side_effect

        with (
            patch(
                "connectors.attio.attio_company_backfill_extractor.get_attio_client_for_tenant",
                new_callable=AsyncMock,
                return_value=mock_attio_client,
            ),
            patch.object(extractor, "store_artifacts_batch", new_callable=AsyncMock) as mock_store,
            patch(
                "connectors.attio.attio_company_backfill_extractor.increment_backfill_done_ingest_jobs",
                new_callable=AsyncMock,
            ),
            patch(
                "connectors.attio.attio_company_backfill_extractor.increment_backfill_attempted_ingest_jobs",
                new_callable=AsyncMock,
            ),
            patch(
                "connectors.attio.attio_company_backfill_extractor.increment_backfill_total_index_jobs",
                new_callable=AsyncMock,
            ),
        ):
            await extractor.process_job(
                job_id=job_id,
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

        # Should have tried all 3 records
        assert mock_attio_client.get_record.call_count == 3

        # Should have stored 2 successful artifacts
        mock_store.assert_called_once()
        stored_artifacts = mock_store.call_args[0][1]
        assert len(stored_artifacts) == 2

    @pytest.mark.asyncio
    async def test_backfill_tracking_always_runs(
        self,
        mock_ssm_client,
        mock_db_pool,
        mock_trigger_indexing,
    ):
        """Test that backfill tracking runs even on failure."""
        extractor = AttioCompanyBackfillExtractor(mock_ssm_client)
        job_id = str(uuid4())

        config = AttioCompanyBackfillConfig(
            tenant_id="tenant_123",
            record_ids=["rec_1"],
            backfill_id="backfill_123",
        )

        with (
            patch(
                "connectors.attio.attio_company_backfill_extractor.get_attio_client_for_tenant",
                new_callable=AsyncMock,
                side_effect=Exception("Auth failed"),
            ),
            patch(
                "connectors.attio.attio_company_backfill_extractor.increment_backfill_attempted_ingest_jobs",
                new_callable=AsyncMock,
            ) as mock_attempted,
            pytest.raises(Exception, match="Auth failed"),
        ):
            await extractor.process_job(
                job_id=job_id,
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

        # increment_backfill_attempted_ingest_jobs should still be called in finally block
        mock_attempted.assert_called_once_with("backfill_123", "tenant_123", 1)


class TestAttioBackfillRootExtractor:
    """Test suite for the root backfill extractor."""

    @pytest.fixture
    def mock_sqs_client(self):
        """Create a mock SQS client."""
        client = MagicMock()
        client.send_backfill_ingest_message = AsyncMock()
        return client

    def test_collect_record_ids_returns_ids_on_success(self, mock_ssm_client, mock_attio_client):
        """Test that _collect_record_ids returns IDs on successful API call."""
        extractor = AttioBackfillRootExtractor(mock_ssm_client, MagicMock())
        mock_attio_client.collect_all_record_ids.return_value = ["id1", "id2", "id3"]

        result = extractor._collect_record_ids(mock_attio_client, AttioObjectType.COMPANIES)

        assert result == ["id1", "id2", "id3"]
        mock_attio_client.collect_all_record_ids.assert_called_once_with("companies")

    def test_collect_record_ids_returns_empty_on_disabled_object(
        self, mock_ssm_client, mock_attio_client
    ):
        """Test that _collect_record_ids returns empty list when object is disabled."""
        extractor = AttioBackfillRootExtractor(mock_ssm_client, MagicMock())

        # Create a mock HTTP error for disabled object
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"code": "standard_object_disabled"}

        http_error = requests.exceptions.HTTPError()
        http_error.response = mock_response

        mock_attio_client.collect_all_record_ids.side_effect = http_error

        result = extractor._collect_record_ids(mock_attio_client, AttioObjectType.DEALS)

        assert result == []

    def test_collect_record_ids_reraises_other_http_errors(
        self, mock_ssm_client, mock_attio_client
    ):
        """Test that _collect_record_ids re-raises non-disabled HTTP errors."""
        extractor = AttioBackfillRootExtractor(mock_ssm_client, MagicMock())

        # Create a mock HTTP error for auth failure
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"code": "unauthorized"}

        http_error = requests.exceptions.HTTPError("Unauthorized")
        http_error.response = mock_response

        mock_attio_client.collect_all_record_ids.side_effect = http_error

        with pytest.raises(requests.exceptions.HTTPError):
            extractor._collect_record_ids(mock_attio_client, AttioObjectType.COMPANIES)

    def test_collect_record_ids_reraises_rate_limit_errors(
        self, mock_ssm_client, mock_attio_client
    ):
        """Test that _collect_record_ids re-raises rate limit errors."""
        extractor = AttioBackfillRootExtractor(mock_ssm_client, MagicMock())

        # Create a mock HTTP error for rate limiting
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.json.return_value = {"code": "rate_limited"}

        http_error = requests.exceptions.HTTPError("Rate limited")
        http_error.response = mock_response

        mock_attio_client.collect_all_record_ids.side_effect = http_error

        with pytest.raises(requests.exceptions.HTTPError):
            extractor._collect_record_ids(mock_attio_client, AttioObjectType.PEOPLE)

    def test_create_batches_splits_correctly(self, mock_ssm_client):
        """Test that _create_batches splits records into correct batch sizes."""
        extractor = AttioBackfillRootExtractor(mock_ssm_client, MagicMock())

        # Test with 250 records (should create 3 batches with BATCH_SIZE=100)
        record_ids = [f"id_{i}" for i in range(250)]

        with patch("connectors.attio.attio_backfill_root_extractor.BATCH_SIZE", 100):
            batches = extractor._create_batches(record_ids)

        assert len(batches) == 3
        assert len(batches[0]) == 100
        assert len(batches[1]) == 100
        assert len(batches[2]) == 50

    def test_create_batches_handles_empty_list(self, mock_ssm_client):
        """Test that _create_batches handles empty input."""
        extractor = AttioBackfillRootExtractor(mock_ssm_client, MagicMock())

        batches = extractor._create_batches([])

        assert batches == []

    def test_calculate_start_timestamp_burst_returns_none(self, mock_ssm_client):
        """Test that burst batches get no start_timestamp (process immediately)."""
        extractor = AttioBackfillRootExtractor(mock_ssm_client, MagicMock())
        base_time = datetime.now(UTC)

        # Batch index 0-4 should be burst (with burst_batch_count=5)
        for i in range(5):
            result = extractor._calculate_start_timestamp(i, base_time, burst_batch_count=5)
            assert result is None

    def test_calculate_start_timestamp_rate_limited_returns_delayed_time(self, mock_ssm_client):
        """Test that rate-limited batches get delayed start_timestamp."""
        extractor = AttioBackfillRootExtractor(mock_ssm_client, MagicMock())
        base_time = datetime.now(UTC)

        with patch("connectors.attio.attio_backfill_root_extractor.BATCH_DELAY_SECONDS", 10):
            # Batch index 5 (first rate-limited batch)
            result = extractor._calculate_start_timestamp(5, base_time, burst_batch_count=5)
            assert result == base_time + timedelta(seconds=0)

            # Batch index 6 (second rate-limited batch)
            result = extractor._calculate_start_timestamp(6, base_time, burst_batch_count=5)
            assert result == base_time + timedelta(seconds=10)

            # Batch index 7 (third rate-limited batch)
            result = extractor._calculate_start_timestamp(7, base_time, burst_batch_count=5)
            assert result == base_time + timedelta(seconds=20)
