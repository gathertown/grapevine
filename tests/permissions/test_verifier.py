"""Tests for permissions verifier module."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest
from asyncpg import Connection

from src.permissions.verifier import (
    _get_tenant_policy_documents,
    batch_verify_document_access,
    filter_results_by_permissions,
)


@pytest.fixture
def mock_conn():
    """Create mock database connection."""
    return Mock(spec=Connection)


class TestBatchVerifyDocumentAccess:
    """Test batch document access verification."""

    @pytest.mark.asyncio
    async def test_empty_document_list(self, mock_conn):
        """Test that empty document list returns empty set."""
        result = await batch_verify_document_access(
            document_ids=[], permission_token="token123", permission_audience=None, conn=mock_conn
        )
        assert result == set()

    @pytest.mark.asyncio
    async def test_no_permission_token_returns_tenant_docs(self, mock_conn):
        """Test that without permission token, only tenant docs are returned."""
        document_ids = ["doc1", "doc2", "doc3"]

        with patch("src.permissions.verifier._get_tenant_policy_documents") as mock_get_tenant:
            mock_get_tenant.return_value = {"doc1", "doc3"}

            result = await batch_verify_document_access(
                document_ids=document_ids,
                permission_token=None,
                permission_audience="private",
                conn=mock_conn,
            )

            assert result == {"doc1", "doc3"}
            mock_get_tenant.assert_called_once_with(document_ids, mock_conn)

    @pytest.mark.asyncio
    async def test_with_permission_token_tenant_policy(self, mock_conn):
        """Test access verification with tenant policy documents."""
        document_ids = ["doc1", "doc2"]
        permission_token = "e:user@example.com"

        # Mock database response - doc1 is tenant, doc2 is private
        mock_conn.fetch = AsyncMock(
            return_value=[
                {
                    "document_id": "doc1",
                    "permission_policy": "tenant",
                    "permission_allowed_tokens": [],
                },
                {
                    "document_id": "doc2",
                    "permission_policy": "private",
                    "permission_allowed_tokens": ["e:other@example.com"],
                },
            ]
        )

        with patch("src.permissions.verifier.can_access_document") as mock_can_access:
            # Tenant doc accessible, private doc not accessible
            mock_can_access.side_effect = [True, False]

            result = await batch_verify_document_access(
                document_ids=document_ids,
                permission_token=permission_token,
                permission_audience="private",
                conn=mock_conn,
            )

            assert result == {"doc1"}
            assert mock_can_access.call_count == 2

    @pytest.mark.asyncio
    async def test_with_permission_token_private_policy_access_granted(self, mock_conn):
        """Test access verification with private policy where access is granted."""
        document_ids = ["doc1"]
        permission_token = "e:user@example.com"

        mock_conn.fetch = AsyncMock(
            return_value=[
                {
                    "document_id": "doc1",
                    "permission_policy": "private",
                    "permission_allowed_tokens": ["e:user@example.com"],
                }
            ]
        )

        with patch("src.permissions.verifier.can_access_document") as mock_can_access:
            mock_can_access.return_value = True

            result = await batch_verify_document_access(
                document_ids=document_ids,
                permission_token=permission_token,
                permission_audience="private",
                conn=mock_conn,
            )

            assert result == {"doc1"}
            mock_can_access.assert_called_once_with(
                permission_policy="private",
                permission_allowed_tokens=["e:user@example.com"],
                permission_token=permission_token,
            )

    @pytest.mark.asyncio
    async def test_documents_without_permissions(self, mock_conn):
        """Test that documents without permission entries are denied access."""
        document_ids = ["doc1", "doc2", "doc3"]
        permission_token = "e:user@example.com"

        # Only doc1 has permissions, doc2 and doc3 are missing
        mock_conn.fetch = AsyncMock(
            return_value=[
                {
                    "document_id": "doc1",
                    "permission_policy": "tenant",
                    "permission_allowed_tokens": [],
                }
            ]
        )

        with (
            patch("src.permissions.verifier.can_access_document") as mock_can_access,
            patch("src.permissions.verifier.logger") as mock_logger,
        ):
            mock_can_access.return_value = True

            result = await batch_verify_document_access(
                document_ids=document_ids,
                permission_token=permission_token,
                permission_audience="private",
                conn=mock_conn,
            )

            assert result == {"doc1"}
            mock_logger.warning.assert_called_once_with(
                "Found documents without permission entries. Denying access by default.",
                documents=["doc2", "doc3"],
            )

    @pytest.mark.asyncio
    async def test_database_error_handling(self, mock_conn):
        """Test that database errors are handled gracefully."""
        document_ids = ["doc1", "doc2"]
        permission_token = "e:user@example.com"

        mock_conn.fetch = AsyncMock(side_effect=Exception("Database error"))

        with patch("src.permissions.verifier.logger") as mock_logger:
            result = await batch_verify_document_access(
                document_ids=document_ids,
                permission_token=permission_token,
                permission_audience="private",
                conn=mock_conn,
            )

            assert result == set()
            mock_logger.error.assert_called_once_with(
                "Error during batch permission verification: Database error"
            )

    @pytest.mark.asyncio
    async def test_debug_logging(self, mock_conn):
        """Test that debug logging includes correct information."""
        document_ids = ["doc1", "doc2"]
        permission_token = "e:user@example.com"

        mock_conn.fetch = AsyncMock(
            return_value=[
                {
                    "document_id": "doc1",
                    "permission_policy": "tenant",
                    "permission_allowed_tokens": [],
                }
            ]
        )

        with patch("src.permissions.verifier.can_access_document", return_value=True):
            result = await batch_verify_document_access(
                document_ids=document_ids,
                permission_token=permission_token,
                permission_audience="private",
                conn=mock_conn,
            )

            assert result == {"doc1"}

    @pytest.mark.asyncio
    async def test_public_audience_returns_only_tenant_docs(self, mock_conn):
        """Test that public audience only returns tenant docs even with token."""
        document_ids = ["doc1", "doc2"]
        permission_token = "e:user@example.com"

        with patch("src.permissions.verifier._get_tenant_policy_documents") as mock_get_tenant:
            mock_get_tenant.return_value = {"doc1"}

            result = await batch_verify_document_access(
                document_ids=document_ids,
                permission_token=permission_token,
                permission_audience="tenant",
                conn=mock_conn,
            )

            assert result == {"doc1"}
            mock_get_tenant.assert_called_once_with(document_ids, mock_conn)

    @pytest.mark.asyncio
    async def test_none_audience_returns_only_tenant_docs(self, mock_conn):
        """Test that None audience defaults to public (tenant only) even with token."""
        document_ids = ["doc1", "doc2"]
        permission_token = "e:user@example.com"

        with patch("src.permissions.verifier._get_tenant_policy_documents") as mock_get_tenant:
            mock_get_tenant.return_value = {"doc1"}

            result = await batch_verify_document_access(
                document_ids=document_ids,
                permission_token=permission_token,
                permission_audience=None,
                conn=mock_conn,
            )

            assert result == {"doc1"}
            mock_get_tenant.assert_called_once_with(document_ids, mock_conn)


class TestGetTenantPolicyDocuments:
    """Test _get_tenant_policy_documents function."""

    @pytest.mark.asyncio
    async def test_successful_query(self, mock_conn):
        """Test successful query for tenant policy documents."""
        document_ids = ["doc1", "doc2", "doc3"]

        mock_conn.fetch = AsyncMock(
            return_value=[
                {"document_id": "doc1"},
                {"document_id": "doc3"},
            ]
        )

        result = await _get_tenant_policy_documents(document_ids, mock_conn)

        assert result == {"doc1", "doc3"}
        mock_conn.fetch.assert_called_once_with(
            """
            SELECT document_id
            FROM document_permissions
            WHERE document_id = ANY($1::varchar[])
              AND permission_policy = 'tenant'
        """,
            document_ids,
        )

    @pytest.mark.asyncio
    async def test_empty_result(self, mock_conn):
        """Test when no tenant policy documents are found."""
        document_ids = ["doc1", "doc2"]

        mock_conn.fetch = AsyncMock(return_value=[])

        result = await _get_tenant_policy_documents(document_ids, mock_conn)

        assert result == set()

    @pytest.mark.asyncio
    async def test_database_error_handling(self, mock_conn):
        """Test error handling in tenant policy document query."""
        document_ids = ["doc1", "doc2"]

        mock_conn.fetch = AsyncMock(side_effect=Exception("Database error"))

        with patch("src.permissions.verifier.logger") as mock_logger:
            result = await _get_tenant_policy_documents(document_ids, mock_conn)

            assert result == set()
            mock_logger.error.assert_called_once_with(
                "Error querying tenant policy documents: Database error"
            )


class TestFilterResultsByPermissions:
    """Test filter_results_by_permissions function."""

    def test_empty_accessible_document_ids(self):
        """Test that empty accessible document IDs returns empty list."""
        results = [{"doc_id": "doc1"}, {"doc_id": "doc2"}]
        accessible_ids: set[str] = set()
        get_doc_id = lambda x: x["doc_id"]

        result = filter_results_by_permissions(results, accessible_ids, get_doc_id)

        assert result == []

    def test_filter_results_correctly(self):
        """Test that results are filtered correctly based on accessible document IDs."""
        results = [
            {"doc_id": "doc1", "content": "content1"},
            {"doc_id": "doc2", "content": "content2"},
            {"doc_id": "doc3", "content": "content3"},
        ]
        accessible_ids = {"doc1", "doc3"}
        get_doc_id = lambda x: x["doc_id"]

        result = filter_results_by_permissions(results, accessible_ids, get_doc_id)

        assert result == [
            {"doc_id": "doc1", "content": "content1"},
            {"doc_id": "doc3", "content": "content3"},
        ]

    def test_no_matching_documents(self):
        """Test when no results match accessible document IDs."""
        results = [
            {"doc_id": "doc1", "content": "content1"},
            {"doc_id": "doc2", "content": "content2"},
        ]
        accessible_ids = {"doc3", "doc4"}
        get_doc_id = lambda x: x["doc_id"]

        result = filter_results_by_permissions(results, accessible_ids, get_doc_id)

        assert result == []

    def test_all_documents_accessible(self):
        """Test when all results are accessible."""
        results = [
            {"doc_id": "doc1", "content": "content1"},
            {"doc_id": "doc2", "content": "content2"},
        ]
        accessible_ids = {"doc1", "doc2"}
        get_doc_id = lambda x: x["doc_id"]

        result = filter_results_by_permissions(results, accessible_ids, get_doc_id)

        assert result == results

    def test_custom_get_document_id_function(self):
        """Test with custom document ID extraction function."""
        results = [
            {"metadata": {"id": "doc1"}, "content": "content1"},
            {"metadata": {"id": "doc2"}, "content": "content2"},
            {"metadata": {"id": "doc3"}, "content": "content3"},
        ]
        accessible_ids = {"doc1", "doc3"}
        get_doc_id = lambda x: x["metadata"]["id"]

        result = filter_results_by_permissions(results, accessible_ids, get_doc_id)

        assert result == [
            {"metadata": {"id": "doc1"}, "content": "content1"},
            {"metadata": {"id": "doc3"}, "content": "content3"},
        ]

    def test_empty_results_list(self):
        """Test with empty results list."""
        results: list[dict[str, str]] = []
        accessible_ids = {"doc1", "doc2"}
        get_doc_id = lambda x: x["doc_id"]

        result = filter_results_by_permissions(results, accessible_ids, get_doc_id)

        assert result == []
