"""Tests for GitHub PR backfill extractor - review normalization."""

import pytest

from connectors.github import GitHubPRBackfillExtractor, GitHubReview
from connectors.github.github_utils import normalize_reviews
from src.clients.ssm import SSMClient


@pytest.fixture
def extractor():
    """Create GitHub PR backfill extractor."""
    mock_ssm = SSMClient()
    return GitHubPRBackfillExtractor(mock_ssm)


class TestReviewNormalization:
    """Test suite for review normalization."""

    def test_normalize_reviews_success(self, extractor):
        """Test reviews normalized correctly."""
        raw_reviews = [
            {
                "id": 123,
                "body": "Looks good",
                "state": "APPROVED",
                "submitted_at": "2024-01-15T10:00:00Z",
                "url": "https://github.com/owner/repo/pull/1#review-123",
                "commit_id": "abc123",
                "user": {"login": "reviewer", "id": 456, "type": "User"},
            }
        ]

        result = normalize_reviews(raw_reviews)

        assert len(result) == 1
        assert isinstance(result[0], GitHubReview)

        review = result[0]
        assert review.id == 123
        assert review.body == "Looks good"
        assert review.state == "APPROVED"
        assert review.submitted_at == "2024-01-15T10:00:00Z"
        assert review.html_url == "https://github.com/owner/repo/pull/1#review-123"
        assert review.commit_id == "abc123"
        assert review.user is not None
        assert review.user.login == "reviewer"
        assert review.user.id == 456

    def test_normalize_reviews_empty_list(self, extractor):
        """Test empty reviews list."""
        result = normalize_reviews([])

        assert result == []
        assert isinstance(result, list)

    def test_normalize_reviews_missing_id_skipped(self, extractor):
        """Test reviews without ID are skipped."""
        raw_reviews = [
            {
                # Missing "id" field
                "body": "This should be skipped",
                "state": "COMMENTED",
                "submitted_at": "2024-01-15T10:00:00Z",
                "url": "https://github.com/owner/repo/pull/1#review-999",
                "user": {"login": "reviewer", "id": 456},
            }
        ]

        result = normalize_reviews(raw_reviews)

        assert result == []

    def test_normalize_reviews_null_body(self, extractor):
        """Test reviews with null body handled correctly."""
        raw_reviews = [
            {
                "id": 123,
                "body": None,  # Null body
                "state": "COMMENTED",
                "submitted_at": "2024-01-15T10:00:00Z",
                "url": "https://github.com/owner/repo/pull/1#review-123",
                "user": {"login": "reviewer", "id": 456},
            }
        ]

        result = normalize_reviews(raw_reviews)

        assert len(result) == 1
        review = result[0]
        assert review.id == 123
        assert review.body is None  # Null preserved
        assert review.state == "COMMENTED"

    def test_normalize_reviews_all_states(self, extractor):
        """Test all review states are handled correctly."""
        raw_reviews = [
            {
                "id": 1,
                "body": "Approved!",
                "state": "APPROVED",
                "submitted_at": "2024-01-15T10:00:00Z",
                "url": "https://github.com/owner/repo/pull/1#review-1",
                "user": {"login": "reviewer1", "id": 100},
            },
            {
                "id": 2,
                "body": "Needs changes",
                "state": "CHANGES_REQUESTED",
                "submitted_at": "2024-01-15T11:00:00Z",
                "url": "https://github.com/owner/repo/pull/1#review-2",
                "user": {"login": "reviewer2", "id": 200},
            },
            {
                "id": 3,
                "body": "Just a comment",
                "state": "COMMENTED",
                "submitted_at": "2024-01-15T12:00:00Z",
                "url": "https://github.com/owner/repo/pull/1#review-3",
                "user": {"login": "reviewer3", "id": 300},
            },
            {
                "id": 4,
                "body": "Dismissed review",
                "state": "DISMISSED",
                "submitted_at": "2024-01-15T13:00:00Z",
                "url": "https://github.com/owner/repo/pull/1#review-4",
                "user": {"login": "reviewer4", "id": 400},
            },
        ]

        result = normalize_reviews(raw_reviews)

        assert len(result) == 4

        # Verify all states preserved
        states = [r.state for r in result]
        assert "APPROVED" in states
        assert "CHANGES_REQUESTED" in states
        assert "COMMENTED" in states
        assert "DISMISSED" in states

        # Verify all IDs present
        ids = [r.id for r in result]
        assert ids == [1, 2, 3, 4]

    def test_normalize_reviews_missing_optional_fields(self, extractor):
        """Test reviews with missing optional fields."""
        raw_reviews = [
            {
                "id": 123,
                # No body
                # No state - should get default
                # No submitted_at
                # No url
                # No commit_id
                # No user
            }
        ]

        result = normalize_reviews(raw_reviews)

        assert len(result) == 1
        review = result[0]
        assert review.id == 123
        assert review.body is None
        assert review.state == "COMMENTED"  # Default state
        assert review.submitted_at is None
        assert review.html_url is None
        assert review.commit_id is None
        assert review.user is None

    def test_normalize_reviews_multiple_reviews(self, extractor):
        """Test normalizing multiple reviews preserves order."""
        raw_reviews = [
            {
                "id": 1,
                "body": "First review",
                "state": "APPROVED",
                "submitted_at": "2024-01-15T10:00:00Z",
                "user": {"login": "reviewer1", "id": 100},
            },
            {
                "id": 2,
                "body": "Second review",
                "state": "CHANGES_REQUESTED",
                "submitted_at": "2024-01-15T11:00:00Z",
                "user": {"login": "reviewer2", "id": 200},
            },
            {
                "id": 3,
                "body": "Third review",
                "state": "APPROVED",
                "submitted_at": "2024-01-15T12:00:00Z",
                "user": {"login": "reviewer3", "id": 300},
            },
        ]

        result = normalize_reviews(raw_reviews)

        assert len(result) == 3
        # Verify order preserved
        assert result[0].id == 1
        assert result[1].id == 2
        assert result[2].id == 3
        assert result[0].body == "First review"
        assert result[1].body == "Second review"
        assert result[2].body == "Third review"
