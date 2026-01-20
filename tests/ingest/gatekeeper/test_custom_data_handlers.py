"""Tests for custom data API handlers in gatekeeper service.

This module tests the custom data document ingestion, retrieval, update, and deletion
endpoints that use API key authentication.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.ingest.gatekeeper.custom_data_handlers import (
    _validate_custom_fields,
    _validate_document_core_fields,
    _validate_no_user_provided_id,
    _validate_slug,
    _validate_tenant_id,
)


class TestValidationFunctions:
    """Test validation helper functions."""

    def test_validate_tenant_id_valid(self):
        """Test valid tenant IDs are accepted."""
        # Should not raise
        _validate_tenant_id("abc123")
        _validate_tenant_id("tenant-123")
        _validate_tenant_id("tenant_123")
        _validate_tenant_id("tenant-123_abc")

    def test_validate_tenant_id_invalid(self):
        """Test invalid tenant IDs are rejected."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _validate_tenant_id("tenant@123")
        assert exc_info.value.status_code == 400
        assert "Invalid tenant ID format" in exc_info.value.detail

    def test_validate_slug_valid(self):
        """Test valid slugs are accepted."""
        # Should not raise
        _validate_slug("my_data_type")
        _validate_slug("MyDataType")
        _validate_slug("data123")
        _validate_slug("a")
        _validate_slug("my-data-type")  # hyphens allowed
        _validate_slug("hr-policy")

    def test_validate_slug_invalid_characters(self):
        """Test slugs with invalid characters are rejected."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _validate_slug("my data")  # spaces not allowed
        assert exc_info.value.status_code == 400

        with pytest.raises(HTTPException) as exc_info:
            _validate_slug("my@data")  # special characters not allowed
        assert exc_info.value.status_code == 400

    def test_validate_slug_too_long(self):
        """Test slugs exceeding 64 characters are rejected."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _validate_slug("a" * 65)
        assert exc_info.value.status_code == 400

    def test_validate_document_core_fields_valid(self):
        """Test valid core fields are accepted."""
        doc = {"name": "Test Doc", "content": "Some content"}
        valid, error = _validate_document_core_fields(doc)
        assert valid is True
        assert error is None

    def test_validate_document_core_fields_with_description(self):
        """Test core fields with optional description are accepted."""
        doc = {"name": "Test Doc", "content": "Some content", "description": "A description"}
        valid, error = _validate_document_core_fields(doc)
        assert valid is True
        assert error is None

    def test_validate_document_core_fields_missing_name(self):
        """Test missing name is rejected."""
        doc = {"content": "Some content"}
        valid, error = _validate_document_core_fields(doc)
        assert valid is False
        assert error is not None and "name is required" in error

    def test_validate_document_core_fields_empty_name(self):
        """Test empty name is rejected."""
        doc = {"name": "   ", "content": "Some content"}
        valid, error = _validate_document_core_fields(doc)
        assert valid is False
        assert error is not None and "name is required" in error

    def test_validate_document_core_fields_missing_content(self):
        """Test missing content is rejected."""
        doc = {"name": "Test Doc"}
        valid, error = _validate_document_core_fields(doc)
        assert valid is False
        assert error is not None and "content is required" in error

    def test_validate_document_core_fields_invalid_description_type(self):
        """Test non-string description is rejected."""
        doc = {"name": "Test Doc", "content": "Some content", "description": 123}
        valid, error = _validate_document_core_fields(doc)
        assert valid is False
        assert error is not None and "description must be a string" in error

    def test_validate_no_user_provided_id_valid(self):
        """Test documents without id are accepted."""
        doc = {"name": "Test", "content": "Content"}
        valid, error = _validate_no_user_provided_id(doc)
        assert valid is True
        assert error is None

    def test_validate_no_user_provided_id_rejected(self):
        """Test documents with id are rejected."""
        doc = {"id": "user-provided-id", "name": "Test", "content": "Content"}
        valid, error = _validate_no_user_provided_id(doc)
        assert valid is False
        assert error is not None
        assert "id" in error.lower()
        assert "should not be provided" in error

    def test_validate_custom_fields_valid(self):
        """Test valid custom fields are accepted."""
        schema_fields = [
            {"name": "category", "type": "text", "required": False},
            {"name": "priority", "type": "number", "required": False},
        ]
        data: dict[str, str | int] = {"category": "Engineering", "priority": 5}
        valid, error = _validate_custom_fields(data, schema_fields)
        assert valid is True
        assert error is None

    def test_validate_custom_fields_required_missing(self):
        """Test missing required field is rejected."""
        schema_fields = [
            {"name": "category", "type": "text", "required": True},
        ]
        data: dict[str, str] = {}
        valid, error = _validate_custom_fields(data, schema_fields)
        assert valid is False
        assert error is not None
        assert "category" in error
        assert "missing" in error.lower()

    def test_validate_custom_fields_unknown_field(self):
        """Test unknown fields are rejected."""
        schema_fields = [
            {"name": "category", "type": "text", "required": False},
        ]
        data: dict[str, str] = {"category": "Test", "unknown_field": "value"}
        valid, error = _validate_custom_fields(data, schema_fields)
        assert valid is False
        assert error is not None
        assert "unknown_field" in error
        assert "not defined in the schema" in error

    def test_validate_custom_fields_wrong_type_text(self):
        """Test wrong type for text field is rejected."""
        schema_fields = [
            {"name": "category", "type": "text", "required": False},
        ]
        data: dict[str, int] = {"category": 123}
        valid, error = _validate_custom_fields(data, schema_fields)
        assert valid is False
        assert error is not None
        assert "category" in error
        assert "string" in error

    def test_validate_custom_fields_wrong_type_number(self):
        """Test wrong type for number field is rejected."""
        schema_fields = [
            {"name": "priority", "type": "number", "required": False},
        ]
        data: dict[str, str] = {"priority": "not a number"}
        valid, error = _validate_custom_fields(data, schema_fields)
        assert valid is False
        assert error is not None
        assert "priority" in error
        assert "number" in error

    def test_validate_custom_fields_boolean_rejected(self):
        """Test boolean is rejected for number fields (bool is subclass of int in Python)."""
        schema_fields = [
            {"name": "priority", "type": "number", "required": False},
        ]
        data: dict[str, bool] = {"priority": True}
        valid, error = _validate_custom_fields(data, schema_fields)
        assert valid is False
        assert error is not None and "finite number" in error

    def test_validate_custom_fields_nan_rejected(self):
        """Test NaN is rejected for number fields."""
        schema_fields = [
            {"name": "priority", "type": "number", "required": False},
        ]
        data: dict[str, float] = {"priority": float("nan")}
        valid, error = _validate_custom_fields(data, schema_fields)
        assert valid is False
        assert error is not None and "finite number" in error

    def test_validate_custom_fields_infinity_rejected(self):
        """Test Infinity is rejected for number fields."""
        schema_fields = [
            {"name": "priority", "type": "number", "required": False},
        ]
        data: dict[str, float] = {"priority": float("inf")}
        valid, error = _validate_custom_fields(data, schema_fields)
        assert valid is False
        assert error is not None and "finite number" in error

    def test_validate_custom_fields_valid_date(self):
        """Test valid ISO date is accepted."""
        schema_fields = [
            {"name": "due_date", "type": "date", "required": False},
        ]
        data: dict[str, str] = {"due_date": "2024-01-15T10:30:00Z"}
        valid, error = _validate_custom_fields(data, schema_fields)
        assert valid is True
        assert error is None

    def test_validate_custom_fields_invalid_date(self):
        """Test invalid date format is rejected."""
        schema_fields = [
            {"name": "due_date", "type": "date", "required": False},
        ]
        data: dict[str, str] = {"due_date": "not-a-date"}
        valid, error = _validate_custom_fields(data, schema_fields)
        assert valid is False
        assert error is not None
        assert "due_date" in error
        assert "ISO 8601" in error


@pytest.fixture
def mock_sqs_client():
    """Create a mock SQS client."""
    client = Mock()
    client.send_backfill_ingest_message = AsyncMock(return_value="msg-12345")
    client.send_delete_message = AsyncMock(return_value="msg-67890")
    return client


@pytest.fixture
def test_app(mock_sqs_client):
    """Create test app with mocked dependencies."""
    test_app = FastAPI()

    from src.ingest.gatekeeper.routes import router

    test_app.include_router(router)
    test_app.state.sqs_client = mock_sqs_client

    return test_app


@pytest.fixture
def client(test_app):
    """Create test client."""
    return TestClient(test_app)


class TestCustomDataIngestEndpoint:
    """Test custom data ingest endpoint."""

    @patch("src.ingest.gatekeeper.custom_data_handlers.verify_api_key")
    @patch("src.ingest.gatekeeper.custom_data_handlers._get_custom_data_type_by_slug")
    def test_single_document_ingest_success(
        self, mock_get_type, mock_verify_api_key, client, mock_sqs_client
    ):
        """Test successful single document ingestion."""
        mock_verify_api_key.return_value = "test-tenant"
        mock_get_type.return_value = {
            "id": "type-123",
            "slug": "my_docs",
            "display_name": "My Docs",
            "custom_fields": {"fields": []},
            "state": "enabled",
        }

        response = client.post(
            "/test-tenant/custom-documents/my_docs",
            json={"name": "Test Doc", "content": "Test content"},
            headers={"Authorization": "Bearer test-api-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Document accepted for processing"
        assert data["document"] is not None
        assert data["document"]["name"] == "Test Doc"
        assert "entity_id" in data["document"]
        mock_sqs_client.send_backfill_ingest_message.assert_called_once()

    @patch("src.ingest.gatekeeper.custom_data_handlers.verify_api_key")
    @patch("src.ingest.gatekeeper.custom_data_handlers._get_custom_data_type_by_slug")
    def test_batch_document_ingest_success(
        self, mock_get_type, mock_verify_api_key, client, mock_sqs_client
    ):
        """Test successful batch document ingestion."""
        mock_verify_api_key.return_value = "test-tenant"
        mock_get_type.return_value = {
            "id": "type-123",
            "slug": "my_docs",
            "display_name": "My Docs",
            "custom_fields": {"fields": []},
            "state": "enabled",
        }

        response = client.post(
            "/test-tenant/custom-documents/my_docs",
            json={
                "documents": [
                    {"name": "Doc 1", "content": "Content 1"},
                    {"name": "Doc 2", "content": "Content 2"},
                ]
            },
            headers={"Authorization": "Bearer test-api-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Documents accepted for processing"
        assert data["documents_accepted"] == 2
        assert len(data["documents"]) == 2

    def test_missing_auth_header(self, client):
        """Test request without authorization header is rejected."""
        response = client.post(
            "/test-tenant/custom-documents/my_docs",
            json={"name": "Test Doc", "content": "Test content"},
        )

        assert response.status_code == 401
        assert "Authorization" in response.json()["detail"]

    @patch("src.ingest.gatekeeper.custom_data_handlers.verify_api_key")
    def test_invalid_api_key(self, mock_verify_api_key, client):
        """Test request with invalid API key is rejected."""
        mock_verify_api_key.return_value = None

        response = client.post(
            "/test-tenant/custom-documents/my_docs",
            json={"name": "Test Doc", "content": "Test content"},
            headers={"Authorization": "Bearer invalid-key"},
        )

        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]

    @patch("src.ingest.gatekeeper.custom_data_handlers.verify_api_key")
    def test_api_key_tenant_mismatch(self, mock_verify_api_key, client):
        """Test request where API key tenant doesn't match URL tenant."""
        mock_verify_api_key.return_value = "different-tenant"

        response = client.post(
            "/test-tenant/custom-documents/my_docs",
            json={"name": "Test Doc", "content": "Test content"},
            headers={"Authorization": "Bearer test-api-key"},
        )

        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]

    @patch("src.ingest.gatekeeper.custom_data_handlers.verify_api_key")
    @patch("src.ingest.gatekeeper.custom_data_handlers._get_custom_data_type_by_slug")
    def test_data_type_not_found(self, mock_get_type, mock_verify_api_key, client):
        """Test request for non-existent data type."""
        mock_verify_api_key.return_value = "test-tenant"
        mock_get_type.return_value = None

        response = client.post(
            "/test-tenant/custom-documents/nonexistent",
            json={"name": "Test Doc", "content": "Test content"},
            headers={"Authorization": "Bearer test-api-key"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @patch("src.ingest.gatekeeper.custom_data_handlers.verify_api_key")
    @patch("src.ingest.gatekeeper.custom_data_handlers._get_custom_data_type_by_slug")
    def test_missing_required_field(self, mock_get_type, mock_verify_api_key, client):
        """Test request missing required field."""
        mock_verify_api_key.return_value = "test-tenant"
        mock_get_type.return_value = {
            "id": "type-123",
            "slug": "my_docs",
            "display_name": "My Docs",
            "custom_fields": {"fields": []},
            "state": "enabled",
        }

        response = client.post(
            "/test-tenant/custom-documents/my_docs",
            json={"name": "Test Doc"},  # Missing content
            headers={"Authorization": "Bearer test-api-key"},
        )

        assert response.status_code == 400
        assert "content" in response.json()["detail"].lower()

    @patch("src.ingest.gatekeeper.custom_data_handlers.verify_api_key")
    @patch("src.ingest.gatekeeper.custom_data_handlers._get_custom_data_type_by_slug")
    def test_user_provided_id_rejected(self, mock_get_type, mock_verify_api_key, client):
        """Test request with user-provided ID is rejected."""
        mock_verify_api_key.return_value = "test-tenant"
        mock_get_type.return_value = {
            "id": "type-123",
            "slug": "my_docs",
            "display_name": "My Docs",
            "custom_fields": {"fields": []},
            "state": "enabled",
        }

        response = client.post(
            "/test-tenant/custom-documents/my_docs",
            json={"id": "my-custom-id", "name": "Test Doc", "content": "Content"},
            headers={"Authorization": "Bearer test-api-key"},
        )

        assert response.status_code == 400
        assert "id" in response.json()["detail"].lower()

    @patch("src.ingest.gatekeeper.custom_data_handlers.verify_api_key")
    @patch("src.ingest.gatekeeper.custom_data_handlers._get_custom_data_type_by_slug")
    def test_batch_exceeds_limit(self, mock_get_type, mock_verify_api_key, client):
        """Test batch request exceeding document limit."""
        mock_verify_api_key.return_value = "test-tenant"
        mock_get_type.return_value = {
            "id": "type-123",
            "slug": "my_docs",
            "display_name": "My Docs",
            "custom_fields": {"fields": []},
            "state": "enabled",
        }

        # Create 101 documents (limit is 100)
        documents = [{"name": f"Doc {i}", "content": f"Content {i}"} for i in range(101)]

        response = client.post(
            "/test-tenant/custom-documents/my_docs",
            json={"documents": documents},
            headers={"Authorization": "Bearer test-api-key"},
        )

        assert response.status_code == 400
        assert "100" in response.json()["detail"]

    def test_invalid_slug_format(self, client):
        """Test request with invalid slug format."""
        response = client.post(
            "/test-tenant/custom-documents/invalid@slug",  # special chars not allowed
            json={"name": "Test Doc", "content": "Test content"},
            headers={"Authorization": "Bearer test-api-key"},
        )

        assert response.status_code == 400
        assert "alphanumeric" in response.json()["detail"].lower()

    @patch("src.ingest.gatekeeper.custom_data_handlers.verify_api_key")
    @patch("src.ingest.gatekeeper.custom_data_handlers._get_custom_data_type_by_slug")
    def test_hyphenated_slug_valid(
        self, mock_get_type, mock_verify_api_key, client, mock_sqs_client
    ):
        """Test request with hyphenated slug is accepted."""
        mock_verify_api_key.return_value = "test-tenant"
        mock_get_type.return_value = {
            "id": "type-123",
            "slug": "hr-policy",
            "display_name": "HR Policy",
            "custom_fields": {"fields": []},
            "state": "enabled",
        }

        response = client.post(
            "/test-tenant/custom-documents/hr-policy",
            json={"name": "Test Doc", "content": "Test content"},
            headers={"Authorization": "Bearer test-api-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestCustomDataGetEndpoint:
    """Test custom data GET endpoint."""

    @patch("src.ingest.gatekeeper.custom_data_handlers._authenticate_request")
    @patch("src.ingest.gatekeeper.custom_data_handlers._get_custom_document_artifact")
    def test_get_document_success(self, mock_get_artifact, mock_auth, client):
        """Test successful document retrieval."""
        mock_auth.return_value = None
        mock_get_artifact.return_value = {
            "id": "artifact-123",
            "entity": "custom_data_document",
            "entity_id": "my_docs::doc-456",
            "content": {"name": "Test Doc", "content": "Content"},
            "metadata": {},
            "source_updated_at": "2024-01-15T10:00:00+00:00",
        }

        response = client.get(
            "/test-tenant/custom-documents/my_docs/doc-456",
            headers={"Authorization": "Bearer test-api-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["document"] is not None

    @patch("src.ingest.gatekeeper.custom_data_handlers._authenticate_request")
    @patch("src.ingest.gatekeeper.custom_data_handlers._get_custom_document_artifact")
    def test_get_document_not_found(self, mock_get_artifact, mock_auth, client):
        """Test retrieval of non-existent document."""
        mock_auth.return_value = None
        mock_get_artifact.return_value = None

        response = client.get(
            "/test-tenant/custom-documents/my_docs/nonexistent",
            headers={"Authorization": "Bearer test-api-key"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestCustomDataDeleteEndpoint:
    """Test custom data DELETE endpoint."""

    @patch("src.ingest.gatekeeper.custom_data_handlers._authenticate_request")
    @patch("src.ingest.gatekeeper.custom_data_handlers._delete_custom_document_artifact")
    def test_delete_document_success(
        self, mock_delete_artifact, mock_auth, client, mock_sqs_client
    ):
        """Test successful document deletion."""
        mock_auth.return_value = None
        mock_delete_artifact.return_value = True

        response = client.delete(
            "/test-tenant/custom-documents/my_docs/doc-456",
            headers={"Authorization": "Bearer test-api-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["deleted_id"] == "doc-456"
        mock_sqs_client.send_delete_message.assert_called_once()

    @patch("src.ingest.gatekeeper.custom_data_handlers._authenticate_request")
    @patch("src.ingest.gatekeeper.custom_data_handlers._delete_custom_document_artifact")
    def test_delete_document_not_found(self, mock_delete_artifact, mock_auth, client):
        """Test deletion of non-existent document."""
        mock_auth.return_value = None
        mock_delete_artifact.return_value = False

        response = client.delete(
            "/test-tenant/custom-documents/my_docs/nonexistent",
            headers={"Authorization": "Bearer test-api-key"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestHostHeaderBasedRoutes:
    """Test custom data endpoints with tenant ID from Host header."""

    @patch("src.ingest.gatekeeper.routes.extract_tenant_from_request")
    @patch("src.ingest.gatekeeper.custom_data_handlers.verify_api_key")
    @patch("src.ingest.gatekeeper.custom_data_handlers._get_custom_data_type_by_slug")
    def test_ingest_with_host_header(
        self, mock_get_type, mock_verify_api_key, mock_extract_tenant, client, mock_sqs_client
    ):
        """Test document ingestion using tenant from Host header."""
        mock_extract_tenant.return_value = Mock(tenant_id="test-tenant", error=None)
        mock_verify_api_key.return_value = "test-tenant"
        mock_get_type.return_value = {
            "id": "type-123",
            "slug": "hr-policy",
            "display_name": "HR Policy",
            "custom_fields": {"fields": []},
            "state": "enabled",
        }

        response = client.post(
            "/custom-documents/hr-policy",
            json={"name": "Test Doc", "content": "Test content"},
            headers={
                "Authorization": "Bearer test-api-key",
                "Host": "test-tenant.ingest.stg.example.com",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        mock_extract_tenant.assert_called_once()

    @patch("src.ingest.gatekeeper.routes.extract_tenant_from_request")
    @patch("src.ingest.gatekeeper.custom_data_handlers._authenticate_request")
    @patch("src.ingest.gatekeeper.custom_data_handlers._get_custom_document_artifact")
    def test_get_with_host_header(self, mock_get_artifact, mock_auth, mock_extract_tenant, client):
        """Test document retrieval using tenant from Host header."""
        mock_extract_tenant.return_value = Mock(tenant_id="test-tenant", error=None)
        mock_auth.return_value = None
        mock_get_artifact.return_value = {
            "id": "artifact-123",
            "entity": "custom_data_document",
            "entity_id": "hr-policy::doc-456",
            "content": {"name": "Test Doc", "content": "Content"},
            "metadata": {},
            "source_updated_at": "2024-01-15T10:00:00+00:00",
        }

        response = client.get(
            "/custom-documents/hr-policy/doc-456",
            headers={
                "Authorization": "Bearer test-api-key",
                "Host": "test-tenant.ingest.stg.example.com",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        mock_extract_tenant.assert_called_once()

    @patch("src.ingest.gatekeeper.routes.extract_tenant_from_request")
    @patch("src.ingest.gatekeeper.custom_data_handlers._authenticate_request")
    @patch("src.ingest.gatekeeper.custom_data_handlers._delete_custom_document_artifact")
    def test_delete_with_host_header(
        self, mock_delete_artifact, mock_auth, mock_extract_tenant, client, mock_sqs_client
    ):
        """Test document deletion using tenant from Host header."""
        mock_extract_tenant.return_value = Mock(tenant_id="test-tenant", error=None)
        mock_auth.return_value = None
        mock_delete_artifact.return_value = True

        response = client.delete(
            "/custom-documents/hr-policy/doc-456",
            headers={
                "Authorization": "Bearer test-api-key",
                "Host": "test-tenant.ingest.stg.example.com",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        mock_extract_tenant.assert_called_once()

    @patch("src.ingest.gatekeeper.routes.extract_tenant_from_request")
    def test_ingest_with_invalid_host_header(self, mock_extract_tenant, client):
        """Test request with invalid Host header is rejected."""
        mock_extract_tenant.return_value = Mock(tenant_id=None, error="Invalid host format")

        response = client.post(
            "/custom-documents/hr-policy",
            json={"name": "Test Doc", "content": "Test content"},
            headers={
                "Authorization": "Bearer test-api-key",
                "Host": "invalid-host.example.com",
            },
        )

        assert response.status_code == 400
        assert "tenant" in response.json()["detail"].lower()
