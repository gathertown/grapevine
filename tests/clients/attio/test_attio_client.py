"""Tests for Attio API client."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from src.clients.attio import AttioClient
from src.jobs.exceptions import ExtendVisibilityException
from src.utils.rate_limiter import RateLimitedError


@pytest.fixture
def attio_client():
    """Create an Attio client instance for testing."""
    return AttioClient(access_token="test_token")


@pytest.fixture
def mock_companies_response():
    """Mock response for companies query."""
    return {
        "data": [
            {
                "id": {"record_id": "rec_company_123"},
                "values": {
                    "name": [{"value": "Test Company"}],
                    "domains": [{"domain": "testcompany.com"}],
                    "created_at": [{"value": "2024-01-15T10:00:00.000Z"}],
                },
                "created_at": "2024-01-15T10:00:00.000Z",
            },
            {
                "id": {"record_id": "rec_company_456"},
                "values": {
                    "name": [{"value": "Another Company"}],
                    "domains": [{"domain": "another.com"}],
                    "created_at": [{"value": "2024-01-16T10:00:00.000Z"}],
                },
                "created_at": "2024-01-16T10:00:00.000Z",
            },
        ],
        "pagination": {"next_cursor": None},
    }


@pytest.fixture
def mock_people_response():
    """Mock response for people query."""
    return {
        "data": [
            {
                "id": {"record_id": "rec_person_123"},
                "values": {
                    "name": [{"first_name": "John", "last_name": "Doe", "full_name": "John Doe"}],
                    "email_addresses": [{"email_address": "john@example.com"}],
                    "created_at": [{"value": "2024-01-15T10:00:00.000Z"}],
                },
                "created_at": "2024-01-15T10:00:00.000Z",
            }
        ],
        "pagination": {"next_cursor": "cursor_abc"},
    }


@pytest.fixture
def mock_deals_response():
    """Mock response for deals query."""
    return {
        "data": [
            {
                "id": {"record_id": "rec_deal_123"},
                "values": {
                    "name": [{"value": "Big Deal"}],
                    "value": [{"currency_value": 50000}],
                    "stage": [{"status": {"title": "Negotiation"}}],
                    "created_at": [{"value": "2024-01-15T10:00:00.000Z"}],
                },
                "created_at": "2024-01-15T10:00:00.000Z",
            }
        ],
        "pagination": {"next_cursor": None},
    }


class TestAttioClientInitialization:
    """Test suite for Attio client initialization."""

    def test_client_initialization_with_token(self):
        """Test that client initializes with access token."""
        client = AttioClient(access_token="test_token")
        assert client.session is not None
        assert "Authorization" in client.session.headers
        assert client.session.headers["Authorization"] == "Bearer test_token"

    def test_client_initialization_without_token_raises(self):
        """Test that client raises error without token."""
        with pytest.raises(ValueError, match="access token is required"):
            AttioClient(access_token="")

    def test_client_initialization_with_none_token_raises(self):
        """Test that client raises error with None token."""
        with pytest.raises(ValueError, match="access token is required"):
            AttioClient(access_token=None)  # type: ignore


class TestAttioClientQueryRecords:
    """Test suite for Attio query_records method."""

    def test_query_companies_success(self, attio_client, mock_companies_response):
        """Test successful companies query."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_companies_response
        mock_response.content = b'{"data": []}'

        with patch.object(attio_client.session, "post", return_value=mock_response):
            result = attio_client.query_records("companies")

        assert len(result.records) == 2
        assert result.next_cursor is None
        assert result.records[0]["id"]["record_id"] == "rec_company_123"

    def test_query_people_with_pagination(self, attio_client, mock_people_response):
        """Test people query returns pagination cursor."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_people_response
        mock_response.content = b'{"data": []}'

        with patch.object(attio_client.session, "post", return_value=mock_response):
            result = attio_client.query_records("people")

        assert len(result.records) == 1
        assert result.next_cursor == "cursor_abc"

    def test_query_records_with_cursor(self, attio_client, mock_companies_response):
        """Test query with pagination cursor."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_companies_response
        mock_response.content = b'{"data": []}'

        with patch.object(attio_client.session, "post", return_value=mock_response) as mock_post:
            attio_client.query_records("companies", cursor="previous_cursor")

        # Verify cursor was included in request body
        call_args = mock_post.call_args
        assert call_args[1]["json"]["cursor"] == "previous_cursor"

    def test_query_records_with_custom_limit(self, attio_client, mock_companies_response):
        """Test query with custom limit."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_companies_response
        mock_response.content = b'{"data": []}'

        with patch.object(attio_client.session, "post", return_value=mock_response) as mock_post:
            attio_client.query_records("companies", limit=50)

        call_args = mock_post.call_args
        assert call_args[1]["json"]["limit"] == 50

    def test_query_records_limit_capped_at_100(self, attio_client, mock_companies_response):
        """Test that limit is capped at 100."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_companies_response
        mock_response.content = b'{"data": []}'

        with patch.object(attio_client.session, "post", return_value=mock_response) as mock_post:
            attio_client.query_records("companies", limit=500)

        call_args = mock_post.call_args
        assert call_args[1]["json"]["limit"] == 100


class TestAttioClientRateLimiting:
    """Test suite for Attio rate limiting.

    Note: The AttioClient uses the @rate_limited decorator which has built-in
    retry logic. After exhausting retries (with exponential backoff), it raises
    ExtendVisibilityException rather than RateLimitedError directly.
    """

    def test_rate_limit_retries_then_raises(self, attio_client):
        """Test that 429 responses can raise ExtendVisibilityException."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "3000-01-15T10:00:05.000Z"}

        # The rate_limited decorator retries and eventually raises ExtendVisibilityException
        with (
            patch("time.sleep", return_value=None),
            patch.object(attio_client.session, "post", return_value=mock_response),
            pytest.raises(ExtendVisibilityException),
        ):
            attio_client.query_records("companies")

    def test_rate_limit_internal_error_raised(self, attio_client):
        """Test that _make_request directly raises RateLimitedError on 429."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "invalid-timestamp"}

        # Call _make_request directly to bypass the retry decorator
        with (
            patch.object(attio_client.session, "post", return_value=mock_response),
            pytest.raises(RateLimitedError) as exc_info,
        ):
            attio_client._make_request("/objects/companies/records/query", method="POST")

        # Should fall back to 1.0 second retry
        assert exc_info.value.retry_after == 1.0


class TestAttioClientErrorHandling:
    """Test suite for Attio error handling."""

    def test_unauthorized_error(self, attio_client):
        """Test that 401 responses raise HTTPError."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError()

        with (
            patch.object(attio_client.session, "post", return_value=mock_response),
            pytest.raises(requests.exceptions.HTTPError),
        ):
            attio_client.query_records("companies")

    def test_not_found_error(self, attio_client):
        """Test that 404 responses raise HTTPError."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError()

        with (
            patch.object(attio_client.session, "get", return_value=mock_response),
            pytest.raises(requests.exceptions.HTTPError),
        ):
            attio_client.get_record("companies", "nonexistent_id")

    def test_empty_response_handling(self, attio_client):
        """Test handling of empty response body."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b""
        mock_response.json.return_value = {}

        with patch.object(attio_client.session, "get", return_value=mock_response):
            result = attio_client.get_workspace_members()

        assert result == []


class TestAttioClientGetRecord:
    """Test suite for Attio get_record method."""

    def test_get_single_record(self, attio_client):
        """Test fetching a single record by ID."""
        mock_data = {
            "data": {
                "id": {"record_id": "rec_123"},
                "values": {"name": [{"value": "Test Company"}]},
            }
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_data
        mock_response.content = b'{"data": {}}'

        with patch.object(attio_client.session, "get", return_value=mock_response) as mock_get:
            result = attio_client.get_record("companies", "rec_123")

        assert result["id"]["record_id"] == "rec_123"
        # Verify correct URL was called
        mock_get.assert_called_once()
        call_url = mock_get.call_args[0][0]
        assert "/objects/companies/records/rec_123" in call_url


class TestAttioClientQueryRecordsWithFilter:
    """Test suite for Attio query_records with filter parameter."""

    def test_query_records_with_filter(self, attio_client, mock_companies_response):
        """Test query with filter parameter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_companies_response
        mock_response.content = b'{"data": []}'

        filter_query = {"updated_at": {"$gte": "2024-01-15T10:00:00+00:00"}}

        with patch.object(attio_client.session, "post", return_value=mock_response) as mock_post:
            attio_client.query_records("companies", filter=filter_query)

        # Verify filter was included in request body
        call_args = mock_post.call_args
        assert call_args[1]["json"]["filter"] == filter_query

    def test_query_records_without_filter_omits_filter(self, attio_client, mock_companies_response):
        """Test query without filter parameter doesn't include filter in request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_companies_response
        mock_response.content = b'{"data": []}'

        with patch.object(attio_client.session, "post", return_value=mock_response) as mock_post:
            attio_client.query_records("companies")

        # Verify filter was not included in request body
        call_args = mock_post.call_args
        assert "filter" not in call_args[1]["json"]

    def test_query_records_with_complex_filter(self, attio_client, mock_companies_response):
        """Test query with complex filter containing multiple conditions."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_companies_response
        mock_response.content = b'{"data": []}'

        complex_filter = {
            "$and": [
                {"updated_at": {"$gte": "2024-01-15T10:00:00+00:00"}},
                {"updated_at": {"$lte": "2024-01-20T10:00:00+00:00"}},
            ]
        }

        with patch.object(attio_client.session, "post", return_value=mock_response) as mock_post:
            attio_client.query_records("companies", filter=complex_filter)

        call_args = mock_post.call_args
        assert call_args[1]["json"]["filter"] == complex_filter


class TestAttioClientIterateRecords:
    """Test suite for Attio iterate_records method."""

    def test_iterate_all_pages(self, attio_client):
        """Test iterating through multiple pages of records."""
        page1 = {
            "data": [{"id": {"record_id": "rec_1"}}, {"id": {"record_id": "rec_2"}}],
            "pagination": {"next_cursor": "cursor_1"},
        }
        page2 = {
            "data": [{"id": {"record_id": "rec_3"}}],
            "pagination": {"next_cursor": None},
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"data": []}'
        mock_response.json.side_effect = [page1, page2]

        with patch.object(attio_client.session, "post", return_value=mock_response):
            all_pages = list(attio_client.iterate_records("companies"))

        assert len(all_pages) == 2
        assert len(all_pages[0]) == 2
        assert len(all_pages[1]) == 1

    def test_iterate_empty_results(self, attio_client):
        """Test iterating when no records exist."""
        empty_response = {"data": [], "pagination": {"next_cursor": None}}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = empty_response
        mock_response.content = b'{"data": []}'

        with patch.object(attio_client.session, "post", return_value=mock_response):
            all_pages = list(attio_client.iterate_records("companies"))

        assert len(all_pages) == 0

    def test_iterate_with_start_cursor(self, attio_client):
        """Test iterating with a start cursor for resumable backfills."""
        page1 = {
            "data": [{"id": {"record_id": "rec_3"}}],
            "pagination": {"next_cursor": None},
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"data": []}'
        mock_response.json.return_value = page1

        with patch.object(attio_client.session, "post", return_value=mock_response) as mock_post:
            list(attio_client.iterate_records("companies", start_cursor="resume_cursor"))

        # Verify the start cursor was passed to the API
        call_args = mock_post.call_args
        assert call_args[1]["json"]["cursor"] == "resume_cursor"

    def test_iterate_with_filter(self, attio_client):
        """Test iterating with filter parameter for incremental sync."""
        page1 = {
            "data": [{"id": {"record_id": "rec_1"}}],
            "pagination": {"next_cursor": "cursor_1"},
        }
        page2 = {
            "data": [{"id": {"record_id": "rec_2"}}],
            "pagination": {"next_cursor": None},
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"data": []}'
        mock_response.json.side_effect = [page1, page2]

        filter_query = {"updated_at": {"$gte": "2024-01-15T10:00:00+00:00"}}

        with patch.object(attio_client.session, "post", return_value=mock_response) as mock_post:
            all_pages = list(attio_client.iterate_records("companies", filter=filter_query))

        # Verify filter was passed to all API calls
        assert len(all_pages) == 2
        for call in mock_post.call_args_list:
            assert call[1]["json"]["filter"] == filter_query

    def test_iterate_with_filter_and_sorts(self, attio_client):
        """Test iterating with both filter and custom sorts (typical incremental sync)."""
        page1 = {
            "data": [{"id": {"record_id": "rec_1"}, "updated_at": "2024-01-15T10:00:00Z"}],
            "pagination": {"next_cursor": None},
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"data": []}'
        mock_response.json.return_value = page1

        filter_query = {"updated_at": {"$gte": "2024-01-15T10:00:00+00:00"}}
        sorts = [{"attribute": "updated_at", "direction": "asc"}]

        with patch.object(attio_client.session, "post", return_value=mock_response) as mock_post:
            list(attio_client.iterate_records("companies", filter=filter_query, sorts=sorts))

        call_args = mock_post.call_args
        assert call_args[1]["json"]["filter"] == filter_query
        assert call_args[1]["json"]["sorts"] == sorts


class TestAttioClientIterateRecordsWithCursor:
    """Test suite for Attio iterate_records_with_cursor method."""

    def test_yields_attio_search_results(self, attio_client):
        """Test that method yields AttioSearchResult objects with cursors."""
        page1 = {
            "data": [{"id": {"record_id": "rec_1"}}, {"id": {"record_id": "rec_2"}}],
            "pagination": {"next_cursor": "cursor_1"},
        }
        page2 = {
            "data": [{"id": {"record_id": "rec_3"}}],
            "pagination": {"next_cursor": None},
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"data": []}'
        mock_response.json.side_effect = [page1, page2]

        with patch.object(attio_client.session, "post", return_value=mock_response):
            results = list(attio_client.iterate_records_with_cursor("companies"))

        # Should yield AttioSearchResult objects
        assert len(results) == 2

        # First result should have next_cursor
        assert results[0].next_cursor == "cursor_1"
        assert len(results[0].records) == 2

        # Second result should have no cursor (end of pagination)
        assert results[1].next_cursor is None
        assert len(results[1].records) == 1

    def test_iterate_with_cursor_resumable(self, attio_client):
        """Test resuming iteration from a saved cursor."""
        page1 = {
            "data": [{"id": {"record_id": "rec_5"}}],
            "pagination": {"next_cursor": "cursor_next"},
        }
        page2 = {
            "data": [{"id": {"record_id": "rec_6"}}],
            "pagination": {"next_cursor": None},
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"data": []}'
        mock_response.json.side_effect = [page1, page2]

        with patch.object(attio_client.session, "post", return_value=mock_response) as mock_post:
            results = list(
                attio_client.iterate_records_with_cursor("people", start_cursor="saved_cursor_abc")
            )

        # Verify the start cursor was used
        first_call = mock_post.call_args_list[0]
        assert first_call[1]["json"]["cursor"] == "saved_cursor_abc"

        # Should still get all remaining pages
        assert len(results) == 2

    def test_iterate_with_cursor_empty_results(self, attio_client):
        """Test iterating with cursor when no records exist."""
        empty_response = {"data": [], "pagination": {"next_cursor": None}}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = empty_response
        mock_response.content = b'{"data": []}'

        with patch.object(attio_client.session, "post", return_value=mock_response):
            results = list(attio_client.iterate_records_with_cursor("companies"))

        # No results should be yielded for empty data
        assert len(results) == 0

    def test_iterate_with_cursor_preserves_cursor_chain(self, attio_client):
        """Test that cursor chain is preserved across pages."""
        page1 = {
            "data": [{"id": {"record_id": "rec_1"}}],
            "pagination": {"next_cursor": "cursor_A"},
        }
        page2 = {
            "data": [{"id": {"record_id": "rec_2"}}],
            "pagination": {"next_cursor": "cursor_B"},
        }
        page3 = {
            "data": [{"id": {"record_id": "rec_3"}}],
            "pagination": {"next_cursor": None},
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"data": []}'
        mock_response.json.side_effect = [page1, page2, page3]

        with patch.object(attio_client.session, "post", return_value=mock_response) as mock_post:
            results = list(attio_client.iterate_records_with_cursor("deals"))

        assert len(results) == 3

        # Verify each subsequent call used the previous cursor
        assert mock_post.call_args_list[1][1]["json"]["cursor"] == "cursor_A"
        assert mock_post.call_args_list[2][1]["json"]["cursor"] == "cursor_B"

        # Verify cursors in results match what we expect
        assert results[0].next_cursor == "cursor_A"
        assert results[1].next_cursor == "cursor_B"
        assert results[2].next_cursor is None


class TestAttioClientNotes:
    """Test suite for Attio notes methods."""

    def test_get_notes(self, attio_client):
        """Test fetching notes."""
        mock_data = {
            "data": [
                {
                    "id": {"note_id": "note_123"},
                    "title": "Meeting Notes",
                    "content_plaintext": "Discussion about deal progress",
                    "created_at": "2024-01-15T10:00:00.000Z",
                }
            ],
            "pagination": {"next_cursor": None},
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_data
        mock_response.content = b'{"data": []}'

        with patch.object(attio_client.session, "get", return_value=mock_response):
            result = attio_client.get_notes()

        assert len(result.records) == 1
        assert result.records[0]["title"] == "Meeting Notes"

    def test_get_notes_for_record(self, attio_client):
        """Test fetching notes for a specific record."""
        mock_data = {
            "data": [{"id": {"note_id": "note_123"}, "title": "Deal Note"}],
            "pagination": {"next_cursor": None},
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_data
        mock_response.content = b'{"data": []}'

        with patch.object(attio_client.session, "get", return_value=mock_response) as mock_get:
            result = attio_client.get_notes_for_record("deals", "rec_deal_123")

        assert len(result) == 1
        # Verify parent_object and parent_record_id were passed
        call_args = mock_get.call_args
        assert call_args[1]["params"]["parent_object"] == "deals"
        assert call_args[1]["params"]["parent_record_id"] == "rec_deal_123"


class TestAttioClientTasks:
    """Test suite for Attio tasks methods."""

    def test_get_tasks(self, attio_client):
        """Test fetching tasks."""
        mock_data = {
            "data": [
                {
                    "id": {"task_id": "task_123"},
                    "content_plaintext": "Follow up with client",
                    "is_completed": False,
                    "deadline_at": "2024-02-01T10:00:00.000Z",
                }
            ],
            "pagination": {"next_cursor": None},
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_data
        mock_response.content = b'{"data": []}'

        with patch.object(attio_client.session, "get", return_value=mock_response):
            result = attio_client.get_tasks()

        assert len(result.records) == 1
        assert result.records[0]["content_plaintext"] == "Follow up with client"

    def test_get_tasks_for_record(self, attio_client):
        """Test fetching tasks for a specific record."""
        mock_data = {
            "data": [{"id": {"task_id": "task_123"}, "content_plaintext": "Call prospect"}],
            "pagination": {"next_cursor": None},
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_data
        mock_response.content = b'{"data": []}'

        with patch.object(attio_client.session, "get", return_value=mock_response) as mock_get:
            result = attio_client.get_tasks_for_record("deals", "rec_deal_123")

        assert len(result) == 1
        # Verify linked_object and linked_record_id were passed
        call_args = mock_get.call_args
        assert call_args[1]["params"]["linked_object"] == "deals"
        assert call_args[1]["params"]["linked_record_id"] == "rec_deal_123"


class TestAttioClientWorkspaceMembers:
    """Test suite for Attio workspace members method."""

    def test_get_workspace_members(self, attio_client):
        """Test fetching workspace members."""
        mock_data = {
            "data": [
                {
                    "id": {"workspace_member_id": "member_123"},
                    "first_name": "John",
                    "last_name": "Doe",
                    "email_address": "john@example.com",
                }
            ]
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_data
        mock_response.content = b'{"data": []}'

        with patch.object(attio_client.session, "get", return_value=mock_response):
            result = attio_client.get_workspace_members()

        assert len(result) == 1
        assert result[0]["first_name"] == "John"
