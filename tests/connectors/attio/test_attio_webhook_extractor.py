"""Tests for Attio webhook extractor.

This module tests:
1. Event type parsing and validation
2. Record upsert handling (created/updated)
3. Record deletion handling
4. Note and task event handling (logging only)
5. Error handling for API failures
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from connectors.attio.attio_artifacts import (
    AttioObjectType,
    AttioWebhookAction,
    AttioWebhookEntityType,
)
from connectors.attio.attio_webhook_extractor import (
    AttioWebhookConfig,
    AttioWebhookExtractor,
)
from connectors.base.document_source import DocumentSource


@pytest.fixture
def mock_ssm_client():
    """Create a mock SSM client."""
    return MagicMock()


@pytest.fixture
def mock_db_pool():
    """Create a mock database pool."""
    pool = MagicMock()
    pool.execute = AsyncMock()
    return pool


@pytest.fixture
def mock_trigger_indexing():
    """Create a mock trigger indexing callback."""
    return AsyncMock()


@pytest.fixture
def mock_attio_client():
    """Create a mock Attio client."""
    client = MagicMock()
    # Default mock for get_object - returns a mock AttioObject
    # Tests can override this behavior as needed
    return client


def make_mock_attio_object(api_slug: str):
    """Create a mock AttioObject with the given api_slug."""
    mock_obj = MagicMock()
    mock_obj.api_slug = api_slug
    mock_obj.object_id = f"uuid-for-{api_slug}"
    mock_obj.workspace_id = "workspace-123"
    mock_obj.singular_noun = api_slug.rstrip("s").title()
    mock_obj.plural_noun = api_slug.title()
    return mock_obj


@pytest.fixture
def mock_company_record() -> dict[str, Any]:
    """Sample company record from Attio API."""
    return {
        "id": {"object_id": "companies", "record_id": "rec_company_123"},
        "values": {
            "name": [{"value": "Acme Corp"}],
            "domains": [{"domain": "acme.com"}],
        },
        "created_at": "2024-01-15T10:00:00.000Z",
        "updated_at": "2024-01-20T10:00:00.000Z",
    }


@pytest.fixture
def mock_person_record() -> dict[str, Any]:
    """Sample person record from Attio API."""
    return {
        "id": {"object_id": "people", "record_id": "rec_person_456"},
        "values": {
            "name": [{"full_name": "John Doe"}],
            "email_addresses": [{"email_address": "john@example.com"}],
            "job_title": [{"value": "Software Engineer"}],
        },
        "created_at": "2024-01-15T10:00:00.000Z",
        "updated_at": "2024-01-20T10:00:00.000Z",
    }


@pytest.fixture
def mock_deal_record() -> dict[str, Any]:
    """Sample deal record from Attio API."""
    return {
        "id": {"object_id": "deals", "record_id": "rec_deal_789"},
        "values": {
            "name": [{"value": "Enterprise Deal"}],
            "value": [{"currency_value": 100000}],
        },
        "created_at": "2024-01-15T10:00:00.000Z",
        "updated_at": "2024-01-20T10:00:00.000Z",
    }


def make_webhook_payload(
    event_type: str,
    object_id: str,
    record_id: str,
    workspace_id: str = "50cf242c-7fa3-4cad-87d0-75b1af71c57b",
    attribute_id: str | None = None,
    webhook_id: str = "dd6b29bb-16a7-47b3-8deb-bddf5a4a64a1",
) -> dict[str, Any]:
    """Create a webhook payload following Attio's actual API structure.

    Attio webhook payloads have a wrapper structure with events array:
    {
        "webhook_id": "...",
        "events": [
            {"event_type": "record.created", "id": {...}, "actor": {...}}
        ]
    }

    See: https://docs.attio.com/rest-api/webhook-reference/record-events/
    """
    id_obj: dict[str, str] = {
        "workspace_id": workspace_id,
        "object_id": object_id,
        "record_id": record_id,
    }
    # record.updated events include attribute_id
    if attribute_id:
        id_obj["attribute_id"] = attribute_id

    return {
        "webhook_id": webhook_id,
        "events": [
            {
                "event_type": event_type,
                "id": id_obj,
                "actor": {"type": "workspace-member", "id": "actor-456"},
            }
        ],
    }


class TestAttioWebhookEntityTypeEnum:
    """Test suite for AttioWebhookEntityType enum."""

    def test_entity_type_values(self):
        """Test that enum has correct values."""
        assert AttioWebhookEntityType.RECORD.value == "record"
        assert AttioWebhookEntityType.NOTE.value == "note"
        assert AttioWebhookEntityType.TASK.value == "task"

    def test_entity_type_from_string(self):
        """Test enum can be created from string."""
        assert AttioWebhookEntityType("record") == AttioWebhookEntityType.RECORD
        assert AttioWebhookEntityType("note") == AttioWebhookEntityType.NOTE
        assert AttioWebhookEntityType("task") == AttioWebhookEntityType.TASK

    def test_invalid_entity_type_raises(self):
        """Test that invalid entity type raises ValueError."""
        with pytest.raises(ValueError):
            AttioWebhookEntityType("invalid")


class TestAttioWebhookActionEnum:
    """Test suite for AttioWebhookAction enum."""

    def test_action_values(self):
        """Test that enum has correct values."""
        assert AttioWebhookAction.CREATED.value == "created"
        assert AttioWebhookAction.UPDATED.value == "updated"
        assert AttioWebhookAction.DELETED.value == "deleted"

    def test_action_from_string(self):
        """Test enum can be created from string."""
        assert AttioWebhookAction("created") == AttioWebhookAction.CREATED
        assert AttioWebhookAction("updated") == AttioWebhookAction.UPDATED
        assert AttioWebhookAction("deleted") == AttioWebhookAction.DELETED

    def test_invalid_action_raises(self):
        """Test that invalid action raises ValueError."""
        with pytest.raises(ValueError):
            AttioWebhookAction("invalid")


class TestAttioWebhookExtractorInit:
    """Test suite for AttioWebhookExtractor initialization."""

    def test_source_name(self, mock_ssm_client):
        """Test that source_name is correctly set."""
        extractor = AttioWebhookExtractor(mock_ssm_client)
        assert extractor.source_name == "attio_webhook"

    def test_ssm_client_stored(self, mock_ssm_client):
        """Test that SSM client is stored."""
        extractor = AttioWebhookExtractor(mock_ssm_client)
        assert extractor.ssm_client is mock_ssm_client


class TestAttioWebhookExtractorEventParsing:
    """Test suite for event type parsing."""

    @pytest.mark.asyncio
    async def test_invalid_event_type_format_logs_warning(
        self, mock_ssm_client, mock_db_pool, mock_trigger_indexing
    ):
        """Test that invalid event type format is handled gracefully."""
        extractor = AttioWebhookExtractor(mock_ssm_client)
        job_id = str(uuid4())

        # Use proper Attio wrapper structure with an event that has invalid format
        config = AttioWebhookConfig(
            body={
                "webhook_id": "webhook-123",
                "events": [
                    {
                        "event_type": "invalid_format",  # Missing dot separator
                        "id": {"workspace_id": "ws-123"},
                        "actor": {"type": "workspace-member", "id": "actor-456"},
                    }
                ],
            },
            tenant_id="tenant_123",
        )

        # Should not raise, just log and return
        await extractor.process_job(
            job_id=job_id,
            config=config,
            db_pool=mock_db_pool,
            trigger_indexing=mock_trigger_indexing,
        )

        # No API calls should be made
        mock_trigger_indexing.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_entity_type_logs_info(
        self, mock_ssm_client, mock_db_pool, mock_trigger_indexing
    ):
        """Test that unknown entity types are handled gracefully."""
        extractor = AttioWebhookExtractor(mock_ssm_client)
        job_id = str(uuid4())

        # Use proper Attio wrapper structure with an unknown entity type
        config = AttioWebhookConfig(
            body={
                "webhook_id": "webhook-123",
                "events": [
                    {
                        "event_type": "unknown.created",  # Unknown entity type
                        "id": {"workspace_id": "ws-123"},
                        "actor": {"type": "workspace-member", "id": "actor-456"},
                    }
                ],
            },
            tenant_id="tenant_123",
        )

        await extractor.process_job(
            job_id=job_id,
            config=config,
            db_pool=mock_db_pool,
            trigger_indexing=mock_trigger_indexing,
        )

        mock_trigger_indexing.assert_not_called()


class TestAttioWebhookExtractorRecordCreated:
    """Test suite for record.created events."""

    @pytest.mark.asyncio
    async def test_company_created_fetches_and_stores(
        self,
        mock_ssm_client,
        mock_db_pool,
        mock_trigger_indexing,
        mock_attio_client,
        mock_company_record,
    ):
        """Test that record.created for company fetches and stores artifact."""
        extractor = AttioWebhookExtractor(mock_ssm_client)
        job_id = str(uuid4())

        payload = make_webhook_payload(
            event_type="record.created",
            object_id=AttioObjectType.COMPANIES.value,
            record_id="rec_company_123",
        )

        config = AttioWebhookConfig(body=payload, tenant_id="tenant_123")

        # Mock get_object to resolve the slug (handles UUID -> slug resolution)
        mock_attio_client.get_object.return_value = make_mock_attio_object("companies")
        mock_attio_client.get_record.return_value = mock_company_record

        with (
            patch(
                "connectors.attio.attio_webhook_extractor.get_attio_client_for_tenant",
                new_callable=AsyncMock,
                return_value=mock_attio_client,
            ),
            patch.object(
                extractor, "force_store_artifacts_batch", new_callable=AsyncMock
            ) as mock_store,
        ):
            await extractor.process_job(
                job_id=job_id,
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

        mock_attio_client.get_record.assert_called_once_with(
            object_slug="companies", record_id="rec_company_123"
        )
        mock_store.assert_called_once()
        mock_trigger_indexing.assert_called_once()

        # Verify document source
        call_args = mock_trigger_indexing.call_args
        assert call_args[0][1] == DocumentSource.ATTIO_COMPANY

    @pytest.mark.asyncio
    async def test_person_created_fetches_and_stores(
        self,
        mock_ssm_client,
        mock_db_pool,
        mock_trigger_indexing,
        mock_attio_client,
        mock_person_record,
    ):
        """Test that record.created for person fetches and stores artifact."""
        extractor = AttioWebhookExtractor(mock_ssm_client)
        job_id = str(uuid4())

        payload = make_webhook_payload(
            event_type="record.created",
            object_id=AttioObjectType.PEOPLE.value,
            record_id="rec_person_456",
        )

        config = AttioWebhookConfig(body=payload, tenant_id="tenant_123")

        # Mock get_object to resolve the slug
        mock_attio_client.get_object.return_value = make_mock_attio_object("people")
        mock_attio_client.get_record.return_value = mock_person_record

        with (
            patch(
                "connectors.attio.attio_webhook_extractor.get_attio_client_for_tenant",
                new_callable=AsyncMock,
                return_value=mock_attio_client,
            ),
            patch.object(extractor, "force_store_artifacts_batch", new_callable=AsyncMock),
        ):
            await extractor.process_job(
                job_id=job_id,
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

        mock_attio_client.get_record.assert_called_once_with(
            object_slug="people", record_id="rec_person_456"
        )
        call_args = mock_trigger_indexing.call_args
        assert call_args[0][1] == DocumentSource.ATTIO_PERSON

    @pytest.mark.asyncio
    async def test_deal_created_fetches_and_stores(
        self,
        mock_ssm_client,
        mock_db_pool,
        mock_trigger_indexing,
        mock_attio_client,
        mock_deal_record,
    ):
        """Test that record.created for deal fetches and stores artifact."""
        extractor = AttioWebhookExtractor(mock_ssm_client)
        job_id = str(uuid4())

        payload = make_webhook_payload(
            event_type="record.created",
            object_id=AttioObjectType.DEALS.value,
            record_id="rec_deal_789",
        )

        config = AttioWebhookConfig(body=payload, tenant_id="tenant_123")

        # Mock get_object to resolve the slug
        mock_attio_client.get_object.return_value = make_mock_attio_object("deals")
        mock_attio_client.get_record.return_value = mock_deal_record

        with (
            patch(
                "connectors.attio.attio_webhook_extractor.get_attio_client_for_tenant",
                new_callable=AsyncMock,
                return_value=mock_attio_client,
            ),
            patch.object(extractor, "force_store_artifacts_batch", new_callable=AsyncMock),
        ):
            await extractor.process_job(
                job_id=job_id,
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

        mock_attio_client.get_record.assert_called_once_with(
            object_slug="deals", record_id="rec_deal_789"
        )
        call_args = mock_trigger_indexing.call_args
        assert call_args[0][1] == DocumentSource.ATTIO_DEAL


class TestAttioWebhookExtractorRecordUpdated:
    """Test suite for record.updated events."""

    @pytest.mark.asyncio
    async def test_person_updated_fetches_and_stores(
        self,
        mock_ssm_client,
        mock_db_pool,
        mock_trigger_indexing,
        mock_attio_client,
        mock_person_record,
    ):
        """Test that record.updated fetches and stores updated artifact."""
        extractor = AttioWebhookExtractor(mock_ssm_client)
        job_id = str(uuid4())

        payload = make_webhook_payload(
            event_type="record.updated",
            object_id=AttioObjectType.PEOPLE.value,
            record_id="rec_person_456",
        )

        config = AttioWebhookConfig(body=payload, tenant_id="tenant_123")

        # Mock get_object to resolve the slug
        mock_attio_client.get_object.return_value = make_mock_attio_object("people")
        # Update the mock to reflect changes
        mock_person_record["values"]["job_title"] = [{"value": "Senior Engineer"}]
        mock_attio_client.get_record.return_value = mock_person_record

        with (
            patch(
                "connectors.attio.attio_webhook_extractor.get_attio_client_for_tenant",
                new_callable=AsyncMock,
                return_value=mock_attio_client,
            ),
            patch.object(
                extractor, "force_store_artifacts_batch", new_callable=AsyncMock
            ) as mock_store,
        ):
            await extractor.process_job(
                job_id=job_id,
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

        mock_attio_client.get_record.assert_called_once()
        mock_store.assert_called_once()
        mock_trigger_indexing.assert_called_once()


class TestAttioWebhookExtractorRecordDeleted:
    """Test suite for record.deleted events."""

    @pytest.mark.asyncio
    async def test_company_deleted_uses_pruner(
        self, mock_ssm_client, mock_db_pool, mock_trigger_indexing, mock_attio_client
    ):
        """Test that record.deleted for company calls the pruner's delete_company method."""
        extractor = AttioWebhookExtractor(mock_ssm_client)
        job_id = str(uuid4())

        payload = make_webhook_payload(
            event_type="record.deleted",
            object_id=AttioObjectType.COMPANIES.value,
            record_id="rec_company_123",
        )

        config = AttioWebhookConfig(body=payload, tenant_id="tenant_123")

        # Mock get_object to resolve the slug for proper entity_id construction
        mock_attio_client.get_object.return_value = make_mock_attio_object("companies")

        mock_pruner = MagicMock()
        mock_pruner.delete_company = AsyncMock(return_value=True)

        with (
            patch(
                "connectors.attio.attio_webhook_extractor.get_attio_client_for_tenant",
                new_callable=AsyncMock,
                return_value=mock_attio_client,
            ),
            patch("connectors.attio.attio_pruner.attio_pruner", mock_pruner),
        ):
            await extractor.process_job(
                job_id=job_id,
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

        # Should call pruner's delete_company method
        mock_pruner.delete_company.assert_called_once_with(
            "rec_company_123", "tenant_123", mock_db_pool
        )

    @pytest.mark.asyncio
    async def test_person_deleted_uses_pruner(
        self, mock_ssm_client, mock_db_pool, mock_trigger_indexing, mock_attio_client
    ):
        """Test that record.deleted for person calls the pruner's delete_person method."""
        extractor = AttioWebhookExtractor(mock_ssm_client)
        job_id = str(uuid4())

        payload = make_webhook_payload(
            event_type="record.deleted",
            object_id=AttioObjectType.PEOPLE.value,
            record_id="rec_person_456",
        )

        config = AttioWebhookConfig(body=payload, tenant_id="tenant_123")

        # Mock get_object to resolve the slug
        mock_attio_client.get_object.return_value = make_mock_attio_object("people")

        mock_pruner = MagicMock()
        mock_pruner.delete_person = AsyncMock(return_value=True)

        with (
            patch(
                "connectors.attio.attio_webhook_extractor.get_attio_client_for_tenant",
                new_callable=AsyncMock,
                return_value=mock_attio_client,
            ),
            patch("connectors.attio.attio_pruner.attio_pruner", mock_pruner),
        ):
            await extractor.process_job(
                job_id=job_id,
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

        # Should call pruner's delete_person method
        mock_pruner.delete_person.assert_called_once_with(
            "rec_person_456", "tenant_123", mock_db_pool
        )

    @pytest.mark.asyncio
    async def test_deal_deleted_uses_pruner(
        self, mock_ssm_client, mock_db_pool, mock_trigger_indexing, mock_attio_client
    ):
        """Test that record.deleted for deal calls the pruner's delete_deal method."""
        extractor = AttioWebhookExtractor(mock_ssm_client)
        job_id = str(uuid4())

        payload = make_webhook_payload(
            event_type="record.deleted",
            object_id=AttioObjectType.DEALS.value,
            record_id="rec_deal_789",
        )

        config = AttioWebhookConfig(body=payload, tenant_id="tenant_123")

        # Mock get_object to resolve the slug
        mock_attio_client.get_object.return_value = make_mock_attio_object("deals")

        mock_pruner = MagicMock()
        mock_pruner.delete_deal = AsyncMock(return_value=True)

        with (
            patch(
                "connectors.attio.attio_webhook_extractor.get_attio_client_for_tenant",
                new_callable=AsyncMock,
                return_value=mock_attio_client,
            ),
            patch("connectors.attio.attio_pruner.attio_pruner", mock_pruner),
        ):
            await extractor.process_job(
                job_id=job_id,
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

        # Should call pruner's delete_deal method
        mock_pruner.delete_deal.assert_called_once_with("rec_deal_789", "tenant_123", mock_db_pool)

    @pytest.mark.asyncio
    async def test_deleted_does_not_fetch_record_from_api(
        self, mock_ssm_client, mock_db_pool, mock_trigger_indexing, mock_attio_client
    ):
        """Test that record.deleted does not call get_record (only get_object to resolve slug)."""
        extractor = AttioWebhookExtractor(mock_ssm_client)
        job_id = str(uuid4())

        payload = make_webhook_payload(
            event_type="record.deleted",
            object_id=AttioObjectType.PEOPLE.value,
            record_id="rec_person_456",
        )

        config = AttioWebhookConfig(body=payload, tenant_id="tenant_123")

        # Mock get_object to resolve the slug
        mock_attio_client.get_object.return_value = make_mock_attio_object("people")

        mock_pruner = MagicMock()
        mock_pruner.delete_person = AsyncMock(return_value=True)

        with (
            patch(
                "connectors.attio.attio_webhook_extractor.get_attio_client_for_tenant",
                new_callable=AsyncMock,
                return_value=mock_attio_client,
            ),
            patch("connectors.attio.attio_pruner.attio_pruner", mock_pruner),
        ):
            await extractor.process_job(
                job_id=job_id,
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

        # get_record should not be called for delete events (only get_object)
        mock_attio_client.get_record.assert_not_called()
        # get_object IS called to resolve the slug for entity_id
        mock_attio_client.get_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_deleted_does_not_trigger_indexing(
        self, mock_ssm_client, mock_db_pool, mock_trigger_indexing, mock_attio_client
    ):
        """Test that record.deleted does not trigger indexing."""
        extractor = AttioWebhookExtractor(mock_ssm_client)
        job_id = str(uuid4())

        payload = make_webhook_payload(
            event_type="record.deleted",
            object_id=AttioObjectType.DEALS.value,
            record_id="rec_deal_789",
        )

        config = AttioWebhookConfig(body=payload, tenant_id="tenant_123")

        # Mock get_object to resolve the slug
        mock_attio_client.get_object.return_value = make_mock_attio_object("deals")

        mock_pruner = MagicMock()
        mock_pruner.delete_deal = AsyncMock(return_value=True)

        with (
            patch(
                "connectors.attio.attio_webhook_extractor.get_attio_client_for_tenant",
                new_callable=AsyncMock,
                return_value=mock_attio_client,
            ),
            patch("connectors.attio.attio_pruner.attio_pruner", mock_pruner),
        ):
            await extractor.process_job(
                job_id=job_id,
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

        mock_trigger_indexing.assert_not_called()

    @pytest.mark.asyncio
    async def test_deleted_unknown_object_type_logs_warning(
        self, mock_ssm_client, mock_db_pool, mock_trigger_indexing, mock_attio_client
    ):
        """Test that deletion of unknown object type logs warning and doesn't call pruner."""
        extractor = AttioWebhookExtractor(mock_ssm_client)
        job_id = str(uuid4())

        payload = make_webhook_payload(
            event_type="record.deleted",
            object_id="custom_objects",  # Unknown object type
            record_id="rec_123",
        )

        config = AttioWebhookConfig(body=payload, tenant_id="tenant_123")

        # Mock get_object to return a custom object slug
        mock_attio_client.get_object.return_value = make_mock_attio_object("custom_objects")

        mock_pruner = MagicMock()
        mock_pruner.delete_company = AsyncMock(return_value=True)
        mock_pruner.delete_person = AsyncMock(return_value=True)
        mock_pruner.delete_deal = AsyncMock(return_value=True)

        with (
            patch(
                "connectors.attio.attio_webhook_extractor.get_attio_client_for_tenant",
                new_callable=AsyncMock,
                return_value=mock_attio_client,
            ),
            patch("connectors.attio.attio_pruner.attio_pruner", mock_pruner),
        ):
            await extractor.process_job(
                job_id=job_id,
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

        # None of the pruner methods should be called
        mock_pruner.delete_company.assert_not_called()
        mock_pruner.delete_person.assert_not_called()
        mock_pruner.delete_deal.assert_not_called()


class TestAttioWebhookExtractorNoteAndTaskEvents:
    """Test suite for note.* and task.* events."""

    @pytest.mark.asyncio
    async def test_note_created_logs_but_does_not_process(
        self, mock_ssm_client, mock_db_pool, mock_trigger_indexing
    ):
        """Test that note.created is logged but not processed."""
        extractor = AttioWebhookExtractor(mock_ssm_client)
        job_id = str(uuid4())

        # Attio note webhook payload structure (wrapped in events array)
        config = AttioWebhookConfig(
            body={
                "webhook_id": "webhook-123",
                "events": [
                    {
                        "event_type": "note.created",
                        "id": {
                            "workspace_id": "workspace-123",
                            "note_id": "note_123",
                        },
                        "actor": {"type": "workspace-member", "id": "actor-456"},
                    }
                ],
            },
            tenant_id="tenant_123",
        )

        await extractor.process_job(
            job_id=job_id,
            config=config,
            db_pool=mock_db_pool,
            trigger_indexing=mock_trigger_indexing,
        )

        mock_trigger_indexing.assert_not_called()
        mock_db_pool.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_task_updated_logs_but_does_not_process(
        self, mock_ssm_client, mock_db_pool, mock_trigger_indexing
    ):
        """Test that task.updated is logged but not processed."""
        extractor = AttioWebhookExtractor(mock_ssm_client)
        job_id = str(uuid4())

        # Attio task webhook payload structure (wrapped in events array)
        config = AttioWebhookConfig(
            body={
                "webhook_id": "webhook-123",
                "events": [
                    {
                        "event_type": "task.updated",
                        "id": {
                            "workspace_id": "workspace-123",
                            "task_id": "task_456",
                        },
                        "actor": {"type": "workspace-member", "id": "actor-456"},
                    }
                ],
            },
            tenant_id="tenant_123",
        )

        await extractor.process_job(
            job_id=job_id,
            config=config,
            db_pool=mock_db_pool,
            trigger_indexing=mock_trigger_indexing,
        )

        mock_trigger_indexing.assert_not_called()
        mock_db_pool.execute.assert_not_called()


class TestAttioWebhookExtractorErrorHandling:
    """Test suite for error handling."""

    @pytest.mark.asyncio
    async def test_missing_object_id_logs_warning(
        self, mock_ssm_client, mock_db_pool, mock_trigger_indexing
    ):
        """Test that missing object_id is handled gracefully."""
        extractor = AttioWebhookExtractor(mock_ssm_client)
        job_id = str(uuid4())

        # Attio payload structure: wrapped in events array
        config = AttioWebhookConfig(
            body={
                "webhook_id": "webhook-123",
                "events": [
                    {
                        "event_type": "record.created",
                        "id": {
                            "workspace_id": "workspace-123",
                            "record_id": "rec_123",
                            # Missing object_id
                        },
                        "actor": {"type": "workspace-member", "id": None},
                    }
                ],
            },
            tenant_id="tenant_123",
        )

        await extractor.process_job(
            job_id=job_id,
            config=config,
            db_pool=mock_db_pool,
            trigger_indexing=mock_trigger_indexing,
        )

        mock_trigger_indexing.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_record_id_logs_warning(
        self, mock_ssm_client, mock_db_pool, mock_trigger_indexing
    ):
        """Test that missing record_id is handled gracefully."""
        extractor = AttioWebhookExtractor(mock_ssm_client)
        job_id = str(uuid4())

        # Attio payload structure: wrapped in events array
        config = AttioWebhookConfig(
            body={
                "webhook_id": "webhook-123",
                "events": [
                    {
                        "event_type": "record.updated",
                        "id": {
                            "workspace_id": "workspace-123",
                            "object_id": "companies",
                            # Missing record_id
                        },
                        "actor": {"type": "workspace-member", "id": None},
                    }
                ],
            },
            tenant_id="tenant_123",
        )

        await extractor.process_job(
            job_id=job_id,
            config=config,
            db_pool=mock_db_pool,
            trigger_indexing=mock_trigger_indexing,
        )

        mock_trigger_indexing.assert_not_called()

    @pytest.mark.asyncio
    async def test_api_failure_logs_error(
        self, mock_ssm_client, mock_db_pool, mock_trigger_indexing, mock_attio_client
    ):
        """Test that API failure is logged and doesn't crash."""
        extractor = AttioWebhookExtractor(mock_ssm_client)
        job_id = str(uuid4())

        payload = make_webhook_payload(
            event_type="record.created",
            object_id=AttioObjectType.COMPANIES.value,
            record_id="rec_company_123",
        )

        config = AttioWebhookConfig(body=payload, tenant_id="tenant_123")

        # Mock get_object to succeed, but get_record to fail
        mock_attio_client.get_object.return_value = make_mock_attio_object("companies")
        mock_attio_client.get_record.side_effect = Exception("API error")

        with patch(
            "connectors.attio.attio_webhook_extractor.get_attio_client_for_tenant",
            new_callable=AsyncMock,
            return_value=mock_attio_client,
        ):
            # Should not raise
            await extractor.process_job(
                job_id=job_id,
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

        mock_trigger_indexing.assert_not_called()

    @pytest.mark.asyncio
    async def test_client_creation_failure_logs_error(
        self, mock_ssm_client, mock_db_pool, mock_trigger_indexing
    ):
        """Test that failure to create Attio client is handled."""
        extractor = AttioWebhookExtractor(mock_ssm_client)
        job_id = str(uuid4())

        payload = make_webhook_payload(
            event_type="record.updated",
            object_id=AttioObjectType.PEOPLE.value,
            record_id="rec_person_456",
        )

        config = AttioWebhookConfig(body=payload, tenant_id="tenant_123")

        with patch(
            "connectors.attio.attio_webhook_extractor.get_attio_client_for_tenant",
            new_callable=AsyncMock,
            side_effect=Exception("No access token"),
        ):
            # Should not raise
            await extractor.process_job(
                job_id=job_id,
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

        mock_trigger_indexing.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_object_type_logs_info(
        self, mock_ssm_client, mock_db_pool, mock_trigger_indexing, mock_attio_client
    ):
        """Test that unknown object type is handled gracefully."""
        extractor = AttioWebhookExtractor(mock_ssm_client)
        job_id = str(uuid4())

        payload = make_webhook_payload(
            event_type="record.created",
            object_id="custom_objects",  # Unknown object type (not companies, people, or deals)
            record_id="rec_123",
        )

        config = AttioWebhookConfig(body=payload, tenant_id="tenant_123")

        # Mock get_object to return the custom object slug (which isn't one we handle)
        mock_attio_client.get_object.return_value = make_mock_attio_object("custom_objects")
        mock_attio_client.get_record.return_value = {
            "id": {"object_id": "custom_objects", "record_id": "rec_123"},
            "values": {},
            "created_at": "2024-01-15T10:00:00.000Z",
        }

        with patch(
            "connectors.attio.attio_webhook_extractor.get_attio_client_for_tenant",
            new_callable=AsyncMock,
            return_value=mock_attio_client,
        ):
            await extractor.process_job(
                job_id=job_id,
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

        # Should not trigger indexing for unknown object types
        mock_trigger_indexing.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_action_logs_warning(
        self, mock_ssm_client, mock_db_pool, mock_trigger_indexing
    ):
        """Test that unknown action is handled gracefully."""
        extractor = AttioWebhookExtractor(mock_ssm_client)
        job_id = str(uuid4())

        payload = make_webhook_payload(
            event_type="record.archived",  # Unknown action
            object_id=AttioObjectType.COMPANIES.value,
            record_id="rec_company_123",
        )

        config = AttioWebhookConfig(body=payload, tenant_id="tenant_123")

        await extractor.process_job(
            job_id=job_id,
            config=config,
            db_pool=mock_db_pool,
            trigger_indexing=mock_trigger_indexing,
        )

        mock_trigger_indexing.assert_not_called()
        mock_db_pool.execute.assert_not_called()


class TestAttioWebhookExtractorObjectUuidResolution:
    """Test suite for object UUID to slug resolution."""

    @pytest.mark.asyncio
    async def test_uuid_resolved_to_slug_for_people(
        self,
        mock_ssm_client,
        mock_db_pool,
        mock_trigger_indexing,
        mock_attio_client,
        mock_person_record,
    ):
        """Test that a UUID object_id is resolved to 'people' slug."""
        extractor = AttioWebhookExtractor(mock_ssm_client)
        job_id = str(uuid4())

        # Attio webhooks send UUIDs for object types, not slugs
        people_object_uuid = "3723f7de-3313-4d89-b030-2ea167b0110a"

        payload = make_webhook_payload(
            event_type="record.updated",
            object_id=people_object_uuid,  # UUID instead of "people"
            record_id="rec_person_456",
        )

        config = AttioWebhookConfig(body=payload, tenant_id="tenant_123")

        # Mock get_object to resolve UUID -> "people" slug
        mock_attio_client.get_object.return_value = make_mock_attio_object("people")
        mock_attio_client.get_record.return_value = mock_person_record

        with (
            patch(
                "connectors.attio.attio_webhook_extractor.get_attio_client_for_tenant",
                new_callable=AsyncMock,
                return_value=mock_attio_client,
            ),
            patch.object(
                extractor, "force_store_artifacts_batch", new_callable=AsyncMock
            ) as mock_store,
        ):
            await extractor.process_job(
                job_id=job_id,
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

        # Verify get_object was called with the UUID to resolve it
        mock_attio_client.get_object.assert_called_once_with(people_object_uuid)
        # Verify get_record was called with the resolved slug
        mock_attio_client.get_record.assert_called_once_with(
            object_slug="people", record_id="rec_person_456"
        )
        mock_store.assert_called_once()
        mock_trigger_indexing.assert_called_once()

        # Verify document source is ATTIO_PERSON (not unknown)
        call_args = mock_trigger_indexing.call_args
        assert call_args[0][1] == DocumentSource.ATTIO_PERSON

    @pytest.mark.asyncio
    async def test_uuid_resolution_failure_falls_back_to_original(
        self,
        mock_ssm_client,
        mock_db_pool,
        mock_trigger_indexing,
        mock_attio_client,
        mock_company_record,
    ):
        """Test that if get_object fails, we fall back to using the original object_id."""
        extractor = AttioWebhookExtractor(mock_ssm_client)
        job_id = str(uuid4())

        # Use the slug directly (this should still work even if get_object fails)
        payload = make_webhook_payload(
            event_type="record.created",
            object_id="companies",
            record_id="rec_company_123",
        )

        config = AttioWebhookConfig(body=payload, tenant_id="tenant_123")

        # Mock get_object to fail - should fall back to using "companies" as-is
        mock_attio_client.get_object.side_effect = Exception("API error")
        mock_attio_client.get_record.return_value = mock_company_record

        with (
            patch(
                "connectors.attio.attio_webhook_extractor.get_attio_client_for_tenant",
                new_callable=AsyncMock,
                return_value=mock_attio_client,
            ),
            patch.object(
                extractor, "force_store_artifacts_batch", new_callable=AsyncMock
            ) as mock_store,
        ):
            await extractor.process_job(
                job_id=job_id,
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

        # Should still work using the original object_id as the slug
        mock_attio_client.get_record.assert_called_once_with(
            object_slug="companies", record_id="rec_company_123"
        )
        mock_store.assert_called_once()
        mock_trigger_indexing.assert_called_once()


class TestAttioWebhookConfig:
    """Test suite for AttioWebhookConfig model."""

    def test_config_accepts_valid_payload(self):
        """Test that config accepts valid webhook payload following Attio's actual structure."""
        # Real Attio payload structure: wrapped in events array
        config = AttioWebhookConfig(
            body={
                "webhook_id": "dd6b29bb-16a7-47b3-8deb-bddf5a4a64a1",
                "events": [
                    {
                        "event_type": "record.created",
                        "id": {
                            "workspace_id": "50cf242c-7fa3-4cad-87d0-75b1af71c57b",
                            "object_id": "companies",
                            "record_id": "rec_123",
                        },
                        "actor": {"type": "workspace-member", "id": "actor-456"},
                    }
                ],
            },
            tenant_id="tenant_123",
        )

        assert config.body["webhook_id"] == "dd6b29bb-16a7-47b3-8deb-bddf5a4a64a1"
        assert len(config.body["events"]) == 1
        assert config.body["events"][0]["event_type"] == "record.created"
        assert config.tenant_id == "tenant_123"

    def test_config_accepts_empty_body(self):
        """Test that config accepts empty body (validation happens in extractor)."""
        config = AttioWebhookConfig(body={}, tenant_id="tenant_123")

        assert config.body == {}
        assert config.tenant_id == "tenant_123"
