"""Tests for Pipedrive pruner functionality."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from connectors.pipedrive.pipedrive_pruner import (
    PIPEDRIVE_DEAL_DOC_ID_PREFIX,
    PIPEDRIVE_ORGANIZATION_DOC_ID_PREFIX,
    PIPEDRIVE_PERSON_DOC_ID_PREFIX,
    PIPEDRIVE_PRODUCT_DOC_ID_PREFIX,
    PipedrivePruner,
    get_pipedrive_deal_doc_id,
    get_pipedrive_organization_doc_id,
    get_pipedrive_person_doc_id,
    get_pipedrive_product_doc_id,
    pipedrive_pruner,
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
def mock_ssm_client():
    """Fixture for mock SSM client."""
    return MagicMock()


@pytest.fixture
def mock_pipedrive_client():
    """Fixture for mock Pipedrive client."""
    client = MagicMock()
    # Set up iterator methods to return empty generators by default
    client.iterate_deals = MagicMock(return_value=iter([]))
    client.iterate_persons = MagicMock(return_value=iter([]))
    client.iterate_organizations = MagicMock(return_value=iter([]))
    client.iterate_products = MagicMock(return_value=iter([]))
    return client


class TestPipedrivePrunerSingleton:
    """Test singleton pattern."""

    def test_singleton_pattern(self):
        """Test that PipedrivePruner follows singleton pattern."""
        pruner1 = PipedrivePruner()
        pruner2 = PipedrivePruner()
        assert pruner1 is pruner2

    def test_singleton_instance_exported(self):
        """Test that the singleton instance is properly exported."""
        assert pipedrive_pruner is not None
        assert isinstance(pipedrive_pruner, PipedrivePruner)

    def test_singleton_instance_same_as_new(self):
        """Test that exported singleton is same as newly created instance."""
        new_pruner = PipedrivePruner()
        assert pipedrive_pruner is new_pruner


class TestPipedrivePrunerHelpers:
    """Test helper functions."""

    def test_get_pipedrive_deal_doc_id(self):
        """Test deal doc ID generation."""
        assert get_pipedrive_deal_doc_id(12345) == "pipedrive_deal_12345"

    def test_get_pipedrive_person_doc_id(self):
        """Test person doc ID generation."""
        assert get_pipedrive_person_doc_id(67890) == "pipedrive_person_67890"

    def test_get_pipedrive_organization_doc_id(self):
        """Test organization doc ID generation."""
        assert get_pipedrive_organization_doc_id(11111) == "pipedrive_organization_11111"

    def test_get_pipedrive_product_doc_id(self):
        """Test product doc ID generation."""
        assert get_pipedrive_product_doc_id(22222) == "pipedrive_product_22222"

    def test_doc_id_prefix_constants(self):
        """Test that doc ID prefixes are correct."""
        assert PIPEDRIVE_DEAL_DOC_ID_PREFIX == "pipedrive_deal_"
        assert PIPEDRIVE_PERSON_DOC_ID_PREFIX == "pipedrive_person_"
        assert PIPEDRIVE_ORGANIZATION_DOC_ID_PREFIX == "pipedrive_organization_"
        assert PIPEDRIVE_PRODUCT_DOC_ID_PREFIX == "pipedrive_product_"


class TestPipedrivePrunerDeleteDeal:
    """Test suite for delete_deal functionality."""

    @pytest.mark.asyncio
    async def test_delete_deal_complete_flow(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811
    ):
        """Test complete end-to-end Pipedrive deal deletion."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=1)
        MockHelper.setup_no_document_found(conn)

        pruner = PipedrivePruner()
        result = await pruner.delete_deal(
            deal_id=12345,
            tenant_id="tenant123",
            db_pool=pool,
        )

        assert result is True
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "pipedrive_deal",
            "pipedrive_deal_12345",
        )
        opensearch_client.delete_document.assert_called_once_with(
            "tenant-tenant123", "pipedrive_deal_12345"
        )

    @pytest.mark.asyncio
    async def test_delete_deal_empty_id(self, mock_db_pool_fixture):
        """Test deletion fails with empty deal_id."""
        pool, _ = mock_db_pool_fixture

        pruner = PipedrivePruner()
        result = await pruner.delete_deal(
            deal_id=0,
            tenant_id="tenant123",
            db_pool=pool,
        )

        assert result is False


class TestPipedrivePrunerDeletePerson:
    """Test suite for delete_person functionality."""

    @pytest.mark.asyncio
    async def test_delete_person_complete_flow(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811
    ):
        """Test complete end-to-end Pipedrive person deletion."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=1)
        MockHelper.setup_no_document_found(conn)

        pruner = PipedrivePruner()
        result = await pruner.delete_person(
            person_id=67890,
            tenant_id="tenant123",
            db_pool=pool,
        )

        assert result is True
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "pipedrive_person",
            "pipedrive_person_67890",
        )

    @pytest.mark.asyncio
    async def test_delete_person_empty_id(self, mock_db_pool_fixture):
        """Test deletion fails with empty person_id."""
        pool, _ = mock_db_pool_fixture

        pruner = PipedrivePruner()
        result = await pruner.delete_person(
            person_id=0,
            tenant_id="tenant123",
            db_pool=pool,
        )

        assert result is False


class TestPipedrivePrunerDeleteOrganization:
    """Test suite for delete_organization functionality."""

    @pytest.mark.asyncio
    async def test_delete_organization_complete_flow(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811
    ):
        """Test complete end-to-end Pipedrive organization deletion."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=1)
        MockHelper.setup_no_document_found(conn)

        pruner = PipedrivePruner()
        result = await pruner.delete_organization(
            org_id=11111,
            tenant_id="tenant123",
            db_pool=pool,
        )

        assert result is True
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "pipedrive_organization",
            "pipedrive_organization_11111",
        )

    @pytest.mark.asyncio
    async def test_delete_organization_empty_id(self, mock_db_pool_fixture):
        """Test deletion fails with empty org_id."""
        pool, _ = mock_db_pool_fixture

        pruner = PipedrivePruner()
        result = await pruner.delete_organization(
            org_id=0,
            tenant_id="tenant123",
            db_pool=pool,
        )

        assert result is False


class TestPipedrivePrunerDeleteProduct:
    """Test suite for delete_product functionality."""

    @pytest.mark.asyncio
    async def test_delete_product_complete_flow(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811
    ):
        """Test complete end-to-end Pipedrive product deletion."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=1)
        MockHelper.setup_no_document_found(conn)

        pruner = PipedrivePruner()
        result = await pruner.delete_product(
            product_id=22222,
            tenant_id="tenant123",
            db_pool=pool,
        )

        assert result is True
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "pipedrive_product",
            "pipedrive_product_22222",
        )

    @pytest.mark.asyncio
    async def test_delete_product_empty_id(self, mock_db_pool_fixture):
        """Test deletion fails with empty product_id."""
        pool, _ = mock_db_pool_fixture

        pruner = PipedrivePruner()
        result = await pruner.delete_product(
            product_id=0,
            tenant_id="tenant123",
            db_pool=pool,
        )

        assert result is False


class TestPipedrivePrunerFindStaleDocuments:
    """Test suite for find_stale_documents functionality."""

    @pytest.mark.asyncio
    async def test_find_stale_documents_no_ssm_client(self, mock_db_pool_fixture):
        """Test find_stale_documents fails without SSM client."""
        pool, _ = mock_db_pool_fixture

        pruner = PipedrivePruner()
        result = await pruner.find_stale_documents(
            tenant_id="tenant123",
            db_pool=pool,
            ssm_client=None,
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_find_stale_documents_no_indexed_documents(
        self, mock_db_pool_fixture, mock_ssm_client, mock_pipedrive_client
    ):
        """Test find_stale_documents with no indexed documents."""
        pool, conn = mock_db_pool_fixture
        conn.fetch = AsyncMock(return_value=[])

        with patch(
            "connectors.pipedrive.pipedrive_pruner.get_pipedrive_client_for_tenant",
            new=AsyncMock(return_value=mock_pipedrive_client),
        ):
            pruner = PipedrivePruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
                ssm_client=mock_ssm_client,
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_find_stale_deals(
        self, mock_db_pool_fixture, mock_ssm_client, mock_pipedrive_client
    ):
        """Test finding stale deals."""
        pool, conn = mock_db_pool_fixture

        # Setup: 3 indexed deals, API returns only 1
        conn.fetch = AsyncMock(
            side_effect=[
                # First call for deals
                [
                    {"id": "pipedrive_deal_100"},
                    {"id": "pipedrive_deal_200"},
                    {"id": "pipedrive_deal_300"},
                ],
                # Other entity types return empty
                [],
                [],
                [],
            ]
        )

        # API returns only deal 100
        mock_pipedrive_client.iterate_deals = MagicMock(return_value=iter([[{"id": 100}]]))

        with patch(
            "connectors.pipedrive.pipedrive_pruner.get_pipedrive_client_for_tenant",
            new=AsyncMock(return_value=mock_pipedrive_client),
        ):
            pruner = PipedrivePruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
                ssm_client=mock_ssm_client,
            )

        # Deals 200 and 300 should be stale
        assert len(result) == 2
        assert "pipedrive_deal_200" in result
        assert "pipedrive_deal_300" in result
        assert "pipedrive_deal_100" not in result

    @pytest.mark.asyncio
    async def test_find_stale_persons(
        self, mock_db_pool_fixture, mock_ssm_client, mock_pipedrive_client
    ):
        """Test finding stale persons."""
        pool, conn = mock_db_pool_fixture

        conn.fetch = AsyncMock(
            side_effect=[
                [],  # deals
                [
                    {"id": "pipedrive_person_100"},
                    {"id": "pipedrive_person_200"},
                ],
                [],  # organizations
                [],  # products
            ]
        )

        # API returns only person 100
        mock_pipedrive_client.iterate_persons = MagicMock(return_value=iter([[{"id": 100}]]))

        with patch(
            "connectors.pipedrive.pipedrive_pruner.get_pipedrive_client_for_tenant",
            new=AsyncMock(return_value=mock_pipedrive_client),
        ):
            pruner = PipedrivePruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
                ssm_client=mock_ssm_client,
            )

        assert len(result) == 1
        assert "pipedrive_person_200" in result

    @pytest.mark.asyncio
    async def test_find_stale_organizations(
        self, mock_db_pool_fixture, mock_ssm_client, mock_pipedrive_client
    ):
        """Test finding stale organizations."""
        pool, conn = mock_db_pool_fixture

        conn.fetch = AsyncMock(
            side_effect=[
                [],  # deals
                [],  # persons
                [
                    {"id": "pipedrive_organization_100"},
                    {"id": "pipedrive_organization_200"},
                ],
                [],  # products
            ]
        )

        # API returns only org 100
        mock_pipedrive_client.iterate_organizations = MagicMock(return_value=iter([[{"id": 100}]]))

        with patch(
            "connectors.pipedrive.pipedrive_pruner.get_pipedrive_client_for_tenant",
            new=AsyncMock(return_value=mock_pipedrive_client),
        ):
            pruner = PipedrivePruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
                ssm_client=mock_ssm_client,
            )

        assert len(result) == 1
        assert "pipedrive_organization_200" in result

    @pytest.mark.asyncio
    async def test_find_stale_products(
        self, mock_db_pool_fixture, mock_ssm_client, mock_pipedrive_client
    ):
        """Test finding stale products."""
        pool, conn = mock_db_pool_fixture

        conn.fetch = AsyncMock(
            side_effect=[
                [],  # deals
                [],  # persons
                [],  # organizations
                [
                    {"id": "pipedrive_product_100"},
                    {"id": "pipedrive_product_200"},
                ],
            ]
        )

        # API returns only product 100
        mock_pipedrive_client.iterate_products = MagicMock(return_value=iter([[{"id": 100}]]))

        with patch(
            "connectors.pipedrive.pipedrive_pruner.get_pipedrive_client_for_tenant",
            new=AsyncMock(return_value=mock_pipedrive_client),
        ):
            pruner = PipedrivePruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
                ssm_client=mock_ssm_client,
            )

        assert len(result) == 1
        assert "pipedrive_product_200" in result

    @pytest.mark.asyncio
    async def test_find_stale_documents_handles_client_error(
        self, mock_db_pool_fixture, mock_ssm_client
    ):
        """Test find_stale_documents handles client creation error."""
        pool, _ = mock_db_pool_fixture

        with patch(
            "connectors.pipedrive.pipedrive_pruner.get_pipedrive_client_for_tenant",
            new=AsyncMock(side_effect=Exception("API error")),
        ):
            pruner = PipedrivePruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
                ssm_client=mock_ssm_client,
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_find_stale_documents_handles_api_error(
        self, mock_db_pool_fixture, mock_ssm_client, mock_pipedrive_client
    ):
        """Test find_stale_documents handles API errors gracefully."""
        pool, conn = mock_db_pool_fixture

        conn.fetch = AsyncMock(
            side_effect=[
                [{"id": "pipedrive_deal_100"}],
                [],
                [],
                [],
            ]
        )

        # API throws error
        mock_pipedrive_client.iterate_deals = MagicMock(side_effect=Exception("API error"))

        with patch(
            "connectors.pipedrive.pipedrive_pruner.get_pipedrive_client_for_tenant",
            new=AsyncMock(return_value=mock_pipedrive_client),
        ):
            pruner = PipedrivePruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
                ssm_client=mock_ssm_client,
            )

        # Should return empty list on API error (not crash)
        assert result == []

    @pytest.mark.asyncio
    async def test_find_stale_documents_invalid_doc_id_format(
        self, mock_db_pool_fixture, mock_ssm_client, mock_pipedrive_client
    ):
        """Test find_stale_documents handles invalid document ID formats."""
        pool, conn = mock_db_pool_fixture

        conn.fetch = AsyncMock(
            side_effect=[
                [
                    {"id": "pipedrive_deal_100"},
                    {"id": "invalid_format"},  # Invalid
                    {"id": "pipedrive_deal_abc"},  # Non-numeric ID
                    {"id": "pipedrive_deal_200"},
                ],
                [],
                [],
                [],
            ]
        )

        # API returns both valid deals
        mock_pipedrive_client.iterate_deals = MagicMock(
            return_value=iter([[{"id": 100}, {"id": 200}]])
        )

        with patch(
            "connectors.pipedrive.pipedrive_pruner.get_pipedrive_client_for_tenant",
            new=AsyncMock(return_value=mock_pipedrive_client),
        ):
            pruner = PipedrivePruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
                ssm_client=mock_ssm_client,
            )

        # No stale documents since valid deals exist
        assert result == []

    @pytest.mark.asyncio
    async def test_find_stale_deals_api_returns_empty_aborts(
        self, mock_db_pool_fixture, mock_ssm_client, mock_pipedrive_client
    ):
        """Test that staleness check aborts when API returns empty (safety guard)."""
        pool, conn = mock_db_pool_fixture

        # We have indexed deals
        conn.fetch = AsyncMock(
            side_effect=[
                [
                    {"id": "pipedrive_deal_100"},
                    {"id": "pipedrive_deal_200"},
                ],
                [],  # persons
                [],  # organizations
                [],  # products
            ]
        )

        # API returns no deals (empty)
        mock_pipedrive_client.iterate_deals = MagicMock(return_value=iter([]))

        with patch(
            "connectors.pipedrive.pipedrive_pruner.get_pipedrive_client_for_tenant",
            new=AsyncMock(return_value=mock_pipedrive_client),
        ):
            pruner = PipedrivePruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
                ssm_client=mock_ssm_client,
            )

        # Safety guard: should return empty to prevent mass deletion
        assert result == []

    @pytest.mark.asyncio
    async def test_find_stale_documents_closes_client_session(
        self, mock_db_pool_fixture, mock_ssm_client, mock_pipedrive_client
    ):
        """Test that client session is properly closed after find_stale_documents."""
        pool, conn = mock_db_pool_fixture
        conn.fetch = AsyncMock(return_value=[])

        # Add a mock session to the client
        mock_session = MagicMock()
        mock_pipedrive_client.session = mock_session

        with patch(
            "connectors.pipedrive.pipedrive_pruner.get_pipedrive_client_for_tenant",
            new=AsyncMock(return_value=mock_pipedrive_client),
        ):
            pruner = PipedrivePruner()
            await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
                ssm_client=mock_ssm_client,
            )

        # Session should be closed
        mock_session.close.assert_called_once()
