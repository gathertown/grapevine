"""Mock utilities for pruner tests."""

from functools import wraps
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest


def create_mock_db_pool():
    """Create a mock database connection pool with connection."""
    pool = MagicMock(spec=asyncpg.Pool)
    conn = MagicMock(spec=asyncpg.Connection)

    # Mock connection context manager
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    # Mock transaction context manager
    conn.transaction.return_value.__aenter__ = AsyncMock()
    conn.transaction.return_value.__aexit__ = AsyncMock()

    return pool, conn


def create_mock_opensearch_client():
    """Create a mock OpenSearch client."""
    client = MagicMock()
    client.delete_document = AsyncMock()
    return client


@pytest.fixture
def mock_opensearch_manager():
    """Fixture that provides mocked tenant OpenSearch manager."""
    with patch("connectors.base.base_pruner.tenant_opensearch_manager") as mock_manager:
        mock_client = create_mock_opensearch_client()
        mock_manager.acquire_client.return_value.__aenter__ = AsyncMock(
            return_value=(mock_client, "test-index")
        )
        mock_manager.acquire_client.return_value.__aexit__ = AsyncMock()

        yield mock_manager, mock_client


def create_mock_turbopuffer_client():
    """Create a mock Turbopuffer client."""
    client = MagicMock()
    client.delete_chunks = AsyncMock()
    return client


@pytest.fixture
def mock_turbopuffer_client():
    """Fixture that provides mocked turbopuffer client."""
    with patch("src.ingest.services.deletion_service.get_turbopuffer_client") as mock_get_client:
        mock_client = create_mock_turbopuffer_client()
        mock_get_client.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_deletion_dependencies():
    """Fixture that mocks the underlying deletion dependencies instead of the main function."""
    with (
        patch(
            "src.ingest.services.deletion_service.prepare_referrer_updates_for_deletion"
        ) as mock_prepare,
        patch("src.ingest.services.deletion_service.apply_referrer_updates_to_db") as mock_apply_db,
        patch(
            "src.ingest.services.deletion_service.apply_referrer_updates_to_opensearch"
        ) as mock_apply_os,
        patch("src.ingest.services.deletion_service.get_turbopuffer_client") as mock_get_client,
    ):
        # Set up default behaviors
        mock_prepare.return_value = []  # No referrer updates by default
        mock_apply_db.return_value = None
        mock_apply_os.return_value = None

        # Set up turbopuffer client mock
        mock_turbopuffer = create_mock_turbopuffer_client()
        mock_get_client.return_value = mock_turbopuffer

        yield {
            "prepare_referrer_updates": mock_prepare,
            "apply_referrer_updates_db": mock_apply_db,
            "apply_referrer_updates_opensearch": mock_apply_os,
            "turbopuffer_client": mock_turbopuffer,
        }


def mock_tenant_opensearch_manager_decorator(test_func):
    """Decorator to mock tenant OpenSearch manager - for individual test use."""

    @wraps(test_func)
    async def wrapper(*args, **kwargs):
        with patch("connectors.base.base_pruner.tenant_opensearch_manager") as mock_manager:
            mock_client = create_mock_opensearch_client()
            mock_manager.acquire_client.return_value.__aenter__ = AsyncMock(
                return_value=(mock_client, "test-index")
            )
            mock_manager.acquire_client.return_value.__aexit__ = AsyncMock()

            # Pass mock objects to the test function
            return await test_func(
                *args,
                mock_opensearch_manager=mock_manager,
                mock_opensearch_client=mock_client,
                **kwargs,
            )

    return wrapper


class MockHelper:
    """Helper class for setting up common mock behaviors."""

    @staticmethod
    def setup_successful_artifact_deletion(conn, num_artifacts=1):
        """Setup mock for successful artifact deletion."""
        # Mock the artifact deletion query
        conn.execute.return_value = f"DELETE {num_artifacts}"

    @staticmethod
    def setup_document_with_references(conn, reference_id="ref123", referenced_docs=None):
        """Setup mock for document with references."""
        if referenced_docs is None:
            referenced_docs = {"doc1": 1, "doc2": 2}

        # Mock the document lookup queries
        def mock_fetchrow(query, *args):
            if "SELECT reference_id, referenced_docs FROM documents" in query:
                return {
                    "reference_id": reference_id,
                    "referenced_docs": referenced_docs,
                }
            return None

        conn.fetchrow.side_effect = mock_fetchrow
        # Mock the document deletion query
        conn.execute.return_value = "DELETE 1"

    @staticmethod
    def setup_no_document_found(conn):
        """Setup mock for no document found."""

        def mock_fetchrow(query, *args):
            if "SELECT reference_id, referenced_docs FROM documents" in query:
                return None
            return None

        conn.fetchrow.side_effect = mock_fetchrow
        # No document to delete, but should still work
        conn.execute.return_value = "DELETE 0"

    @staticmethod
    def setup_database_error(conn, error_message="Database connection failed"):
        """Setup mock for database error."""
        conn.execute.side_effect = Exception(error_message)

    @staticmethod
    def setup_opensearch_error(mock_manager, error_message="OpenSearch connection failed"):
        """Setup mock for OpenSearch error."""
        mock_manager.acquire_client.side_effect = Exception(error_message)

    @staticmethod
    def setup_referrer_updates(deletion_deps, referrer_updates=None):
        """Setup mock for referrer updates during deletion."""
        if referrer_updates is None:
            referrer_updates = []

        deletion_deps["prepare_referrer_updates"].return_value = referrer_updates
