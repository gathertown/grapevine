"""Tests for Canva pruner functionality."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from connectors.canva.canva_pruner import (
    CANVA_DESIGN_DOC_ID_PREFIX,
    CanvaPruner,
    canva_pruner,
    get_canva_design_doc_id,
)

from .mock_utils import (
    MockHelper,
    create_mock_db_pool,
    mock_deletion_dependencies,  # noqa: F401 - Used as pytest fixture
    mock_opensearch_manager,  # noqa: F401 - Used as pytest fixture
)


@pytest.fixture
def mock_db_pool_fixture():
    """Fixture for mock database pool."""
    return create_mock_db_pool()


@pytest.fixture
def mock_canva_client():
    """Fixture for mock Canva client."""
    client = MagicMock()
    client.close = AsyncMock()

    # Set up async iterator for designs
    async def empty_async_iter():
        return
        yield  # Make it an async generator

    client.iter_all_designs = MagicMock(return_value=empty_async_iter())
    return client


class TestCanvaPrunerSingleton:
    """Test singleton pattern."""

    def test_singleton_pattern(self):
        """Test that CanvaPruner follows singleton pattern."""
        pruner1 = CanvaPruner()
        pruner2 = CanvaPruner()
        assert pruner1 is pruner2

    def test_singleton_instance_exported(self):
        """Test that the singleton instance is properly exported."""
        assert canva_pruner is not None
        assert isinstance(canva_pruner, CanvaPruner)

    def test_singleton_instance_same_as_new(self):
        """Test that exported singleton is same as newly created instance."""
        new_pruner = CanvaPruner()
        assert canva_pruner is new_pruner


class TestCanvaPrunerHelpers:
    """Test helper functions."""

    def test_get_canva_design_doc_id(self):
        """Test design doc ID generation."""
        assert get_canva_design_doc_id("abc123XYZ") == "canva_design_abc123XYZ"

    def test_get_canva_design_doc_id_with_special_chars(self):
        """Test design doc ID generation with special characters."""
        assert get_canva_design_doc_id("abc-DEF_123") == "canva_design_abc-DEF_123"

    def test_doc_id_prefix_constant(self):
        """Test that doc ID prefix is correct."""
        assert CANVA_DESIGN_DOC_ID_PREFIX == "canva_design_"


class TestCanvaPrunerDeleteDesign:
    """Test suite for delete_design functionality."""

    @pytest.mark.asyncio
    async def test_delete_design_complete_flow(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811
    ):
        """Test complete end-to-end Canva design deletion."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=1)
        MockHelper.setup_no_document_found(conn)

        pruner = CanvaPruner()
        result = await pruner.delete_design(
            design_id="abc123XYZ",
            tenant_id="tenant123",
            db_pool=pool,
        )

        assert result is True
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "canva_design",
            "canva_design_abc123XYZ",
        )
        opensearch_client.delete_document.assert_called_once_with(
            "tenant-tenant123", "canva_design_abc123XYZ"
        )

    @pytest.mark.asyncio
    async def test_delete_design_empty_id(self, mock_db_pool_fixture):
        """Test deletion fails with empty design_id."""
        pool, _ = mock_db_pool_fixture

        pruner = CanvaPruner()
        result = await pruner.delete_design(
            design_id="",
            tenant_id="tenant123",
            db_pool=pool,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_design_handles_database_error(self, mock_db_pool_fixture):
        """Test deletion handles database errors gracefully."""
        pool, conn = mock_db_pool_fixture

        MockHelper.setup_database_error(conn)

        pruner = CanvaPruner()
        result = await pruner.delete_design(
            design_id="abc123XYZ",
            tenant_id="tenant123",
            db_pool=pool,
        )

        assert result is False


class TestCanvaPrunerFindStaleDocuments:
    """Test suite for find_stale_documents functionality."""

    @pytest.mark.asyncio
    async def test_find_stale_documents_no_indexed_documents(
        self, mock_db_pool_fixture, mock_canva_client
    ):
        """Test find_stale_documents with no indexed documents."""
        pool, conn = mock_db_pool_fixture
        conn.fetch = AsyncMock(return_value=[])

        with patch(
            "connectors.canva.canva_pruner.get_canva_client_for_tenant",
            new=AsyncMock(return_value=mock_canva_client),
        ):
            pruner = CanvaPruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
            )

        assert result == []
        mock_canva_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_stale_designs(self, mock_db_pool_fixture, mock_canva_client):
        """Test finding stale designs."""
        pool, conn = mock_db_pool_fixture

        # Setup: 3 indexed designs, API returns only 1
        conn.fetch = AsyncMock(
            return_value=[
                {"id": "canva_design_abc123"},
                {"id": "canva_design_def456"},
                {"id": "canva_design_ghi789"},
            ]
        )

        # API returns only design abc123
        async def mock_iter_designs(*args, **kwargs):
            mock_design = MagicMock()
            mock_design.id = "abc123"
            yield mock_design

        mock_canva_client.iter_all_designs = MagicMock(return_value=mock_iter_designs())

        with patch(
            "connectors.canva.canva_pruner.get_canva_client_for_tenant",
            new=AsyncMock(return_value=mock_canva_client),
        ):
            pruner = CanvaPruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
            )

        # Designs def456 and ghi789 should be stale
        assert len(result) == 2
        assert "canva_design_def456" in result
        assert "canva_design_ghi789" in result
        assert "canva_design_abc123" not in result

    @pytest.mark.asyncio
    async def test_find_stale_designs_all_exist(self, mock_db_pool_fixture, mock_canva_client):
        """Test no stale designs when all exist in API."""
        pool, conn = mock_db_pool_fixture

        conn.fetch = AsyncMock(
            return_value=[
                {"id": "canva_design_abc123"},
                {"id": "canva_design_def456"},
            ]
        )

        # API returns both designs
        async def mock_iter_designs(*args, **kwargs):
            mock_design1 = MagicMock()
            mock_design1.id = "abc123"
            yield mock_design1
            mock_design2 = MagicMock()
            mock_design2.id = "def456"
            yield mock_design2

        mock_canva_client.iter_all_designs = MagicMock(return_value=mock_iter_designs())

        with patch(
            "connectors.canva.canva_pruner.get_canva_client_for_tenant",
            new=AsyncMock(return_value=mock_canva_client),
        ):
            pruner = CanvaPruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_find_stale_documents_handles_client_error(self, mock_db_pool_fixture):
        """Test find_stale_documents handles client creation error."""
        pool, _ = mock_db_pool_fixture

        with patch(
            "connectors.canva.canva_pruner.get_canva_client_for_tenant",
            new=AsyncMock(side_effect=Exception("API error")),
        ):
            pruner = CanvaPruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_find_stale_documents_handles_api_error(
        self, mock_db_pool_fixture, mock_canva_client
    ):
        """Test find_stale_documents handles API errors gracefully."""
        pool, conn = mock_db_pool_fixture

        conn.fetch = AsyncMock(
            return_value=[
                {"id": "canva_design_abc123"},
            ]
        )

        # API throws error during iteration - use a class to avoid unreachable code warning
        class ErrorAsyncIterator:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise Exception("API error")

        mock_canva_client.iter_all_designs = MagicMock(return_value=ErrorAsyncIterator())

        with patch(
            "connectors.canva.canva_pruner.get_canva_client_for_tenant",
            new=AsyncMock(return_value=mock_canva_client),
        ):
            pruner = CanvaPruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
            )

        # Should return empty list on API error (not crash)
        assert result == []

    @pytest.mark.asyncio
    async def test_find_stale_documents_api_returns_empty_aborts(
        self, mock_db_pool_fixture, mock_canva_client
    ):
        """Test that staleness check aborts when API returns empty (safety guard)."""
        pool, conn = mock_db_pool_fixture

        conn.fetch = AsyncMock(
            return_value=[
                {"id": "canva_design_abc123"},
                {"id": "canva_design_def456"},
            ]
        )

        # API returns no designs
        async def mock_iter_empty(*args, **kwargs):
            return
            yield  # Make it an async generator

        mock_canva_client.iter_all_designs = MagicMock(return_value=mock_iter_empty())

        with patch(
            "connectors.canva.canva_pruner.get_canva_client_for_tenant",
            new=AsyncMock(return_value=mock_canva_client),
        ):
            pruner = CanvaPruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
            )

        # Safety guard: should return empty to prevent mass deletion
        assert result == []

    @pytest.mark.asyncio
    async def test_find_stale_documents_closes_client(
        self, mock_db_pool_fixture, mock_canva_client
    ):
        """Test that client is properly closed after find_stale_documents."""
        pool, conn = mock_db_pool_fixture
        conn.fetch = AsyncMock(return_value=[])

        with patch(
            "connectors.canva.canva_pruner.get_canva_client_for_tenant",
            new=AsyncMock(return_value=mock_canva_client),
        ):
            pruner = CanvaPruner()
            await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
            )

        # Client should be closed
        mock_canva_client.close.assert_called_once()
