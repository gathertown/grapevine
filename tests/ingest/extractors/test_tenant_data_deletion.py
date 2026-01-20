from unittest.mock import AsyncMock, patch

import pytest
from turbopuffer import NotFoundError

from src.ingest.tenant_data_deletion import TenantDataDeletionExtractor
from src.jobs.models import TenantDataDeletionMessage


class TestTenantDataDeletion:
    """Test suite for tenant data deletion."""

    @pytest.fixture
    def extractor(self):
        return TenantDataDeletionExtractor()

    @pytest.fixture
    def config(self):
        return TenantDataDeletionMessage(tenant_id="test-tenant-123")

    @pytest.mark.asyncio
    async def test_delete_from_turbopuffer_success(self, extractor):
        """Test successful deletion from Turbopuffer."""
        mock_client = AsyncMock()
        mock_client.delete_namespace = AsyncMock()

        with patch("src.clients.turbopuffer.get_turbopuffer_client") as mock_get:
            mock_get.return_value = mock_client

            await extractor._delete_from_turbopuffer("test-tenant-123")

            mock_client.delete_namespace.assert_called_once_with("test-tenant-123")

    @pytest.mark.asyncio
    async def test_delete_from_turbopuffer_not_found(self, extractor):
        """Test deletion from Turbopuffer when namespace doesn't exist."""
        mock_client = AsyncMock()
        mock_client.delete_namespace = AsyncMock(
            side_effect=NotFoundError("Not found", response=AsyncMock(), body=None)
        )

        with patch("src.clients.turbopuffer.get_turbopuffer_client") as mock_get:
            mock_get.return_value = mock_client

            # Should not raise an exception when namespace doesn't exist
            await extractor._delete_from_turbopuffer("test-tenant-123")

            mock_client.delete_namespace.assert_called_once_with("test-tenant-123")

    @pytest.mark.asyncio
    async def test_delete_from_turbopuffer_other_error(self, extractor):
        """Test deletion from Turbopuffer with non-404 error."""
        mock_client = AsyncMock()
        mock_client.delete_namespace = AsyncMock(side_effect=Exception("Connection error"))

        with patch("src.clients.turbopuffer.get_turbopuffer_client") as mock_get:
            mock_get.return_value = mock_client

            # Should raise the exception for non-404 errors
            with pytest.raises(Exception, match="Connection error"):
                await extractor._delete_from_turbopuffer("test-tenant-123")

            mock_client.delete_namespace.assert_called_once_with("test-tenant-123")

    @pytest.mark.asyncio
    async def test_process_job_deletes_all_data(self, extractor, config):
        """Test that process_job deletes data from all databases."""
        mock_db_pool = AsyncMock()
        mock_trigger_indexing = AsyncMock()

        with (
            patch.object(extractor, "_delete_postgres_documents") as mock_delete_docs,
            patch.object(extractor, "_delete_postgres_artifacts") as mock_delete_artifacts,
            patch.object(extractor, "_delete_from_opensearch") as mock_delete_os,
            patch.object(extractor, "_delete_from_turbopuffer") as mock_delete_tp,
        ):
            await extractor.process_job(
                job_id="test-job-123",
                config=config,
                db_pool=mock_db_pool,
                _trigger_indexing=mock_trigger_indexing,
            )

            # Verify all deletion methods were called
            mock_delete_docs.assert_called_once_with(mock_db_pool)
            mock_delete_artifacts.assert_called_once_with(mock_db_pool)
            mock_delete_os.assert_called_once_with("test-tenant-123")
            mock_delete_tp.assert_called_once_with("test-tenant-123")

    @pytest.mark.asyncio
    async def test_process_job_handles_turbopuffer_not_found(self, extractor, config):
        """Test that process_job completes successfully when Turbopuffer namespace doesn't exist."""
        mock_db_pool = AsyncMock()
        mock_trigger_indexing = AsyncMock()

        with (
            patch.object(extractor, "_delete_postgres_documents") as mock_delete_docs,
            patch.object(extractor, "_delete_postgres_artifacts") as mock_delete_artifacts,
            patch.object(extractor, "_delete_from_opensearch") as mock_delete_os,
            patch.object(extractor, "_delete_from_turbopuffer") as mock_delete_tp,
        ):
            # Simulate Turbopuffer namespace not found
            mock_client = AsyncMock()
            mock_client.delete_namespace = AsyncMock(
                side_effect=NotFoundError("Not found", response=AsyncMock(), body=None)
            )

            with patch("src.clients.turbopuffer.get_turbopuffer_client") as mock_get:
                mock_get.return_value = mock_client

                # Should complete successfully without raising
                await extractor.process_job(
                    job_id="test-job-123",
                    config=config,
                    db_pool=mock_db_pool,
                    _trigger_indexing=mock_trigger_indexing,
                )

            # All methods should still be called
            mock_delete_docs.assert_called_once()
            mock_delete_artifacts.assert_called_once()
            mock_delete_os.assert_called_once()
            mock_delete_tp.assert_called_once()
