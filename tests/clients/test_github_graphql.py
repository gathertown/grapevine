"""Tests for GitHub GraphQL API integration."""

from unittest.mock import patch

import pytest

from src.clients.github import GitHubClient
from src.utils.rate_limiter import RateLimitedError


@pytest.fixture
def mock_graphql_pr_response():
    """Complete mock GraphQL response for PR with comments and reviews."""
    return {
        "rateLimit": {"cost": 53, "remaining": 4947},
        "repository": {
            "pullRequest": {
                "id": "PR_kwDOABCD123",
                "number": 42,
                "title": "Add new feature",
                "body": "This adds a cool new feature",
                "state": "OPEN",
                "isDraft": False,
                "merged": False,
                "createdAt": "2024-01-15T10:00:00Z",
                "updatedAt": "2024-01-16T12:00:00Z",
                "closedAt": None,
                "mergedAt": None,
                "url": "https://github.com/owner/repo/pull/42",
                "commits": {"totalCount": 5},
                "additions": 120,
                "deletions": 30,
                "changedFiles": 3,
                "author": {"__typename": "User", "login": "contributor", "databaseId": 12345},
                "assignees": {
                    "nodes": [{"__typename": "User", "login": "reviewer1", "databaseId": 67890}]
                },
                "labels": {"nodes": [{"name": "bug"}, {"name": "priority-high"}]},
                "headRef": {"name": "feature-branch", "target": {"oid": "abc123"}},
                "baseRef": {"name": "main", "target": {"oid": "def456"}},
                "comments": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [
                        {
                            "databaseId": 111,
                            "body": "Looks good!",
                            "createdAt": "2024-01-15T11:00:00Z",
                            "updatedAt": "2024-01-15T11:00:00Z",
                            "url": "https://github.com/owner/repo/pull/42#issuecomment-111",
                            "author": {
                                "__typename": "User",
                                "login": "reviewer1",
                                "databaseId": 67890,
                            },
                        }
                    ],
                },
                "reviewThreads": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [
                        {
                            "comments": {
                                "nodes": [
                                    {
                                        "databaseId": 222,
                                        "body": "This line needs fixing",
                                        "createdAt": "2024-01-15T12:00:00Z",
                                        "updatedAt": "2024-01-15T12:00:00Z",
                                        "url": "https://github.com/owner/repo/pull/42#discussion_r222",
                                        "path": "src/main.py",
                                        "line": 42,
                                        "diffHunk": "@@ -40,3 +40,5 @@",
                                        "author": {
                                            "__typename": "User",
                                            "login": "reviewer2",
                                            "databaseId": 11111,
                                        },
                                    }
                                ]
                            }
                        }
                    ],
                },
                "reviews": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [
                        {
                            "databaseId": 333,
                            "body": "Approved with suggestions",
                            "state": "APPROVED",
                            "submittedAt": "2024-01-15T13:00:00Z",
                            "url": "https://github.com/owner/repo/pull/42#pullrequestreview-333",
                            "commit": {"oid": "abc123"},
                            "author": {
                                "__typename": "User",
                                "login": "reviewer1",
                                "databaseId": 67890,
                            },
                        }
                    ],
                },
            }
        },
    }


@pytest.fixture
def github_client():
    """Create a GitHub client instance for testing."""
    return GitHubClient(token="test_token")


class TestGitHubGraphQLPRFetch:
    """Test suite for GitHub GraphQL PR fetching."""

    def test_graphql_pr_fetch_success(self, github_client, mock_graphql_pr_response):
        """Test successful GraphQL query returning PR with comments and reviews."""
        with patch.object(github_client, "_execute_graphql", return_value=mock_graphql_pr_response):
            result = github_client.get_pull_request_with_comments_graphql("owner/repo", 42)

        # Verify result structure
        assert result is not None
        assert isinstance(result, dict)

        # Verify PR fields
        assert result["id"] == 42  # ID is set to PR number
        assert result["number"] == 42
        assert result["title"] == "Add new feature"
        assert result["body"] == "This adds a cool new feature"
        assert result["state"] == "open"  # Lowercased from OPEN
        assert result["draft"] is False
        assert result["merged"] is False
        assert result["created_at"] == "2024-01-15T10:00:00Z"
        assert result["updated_at"] == "2024-01-16T12:00:00Z"
        assert result["closed_at"] is None
        assert result["merged_at"] is None
        assert result["html_url"] == "https://github.com/owner/repo/pull/42"
        assert result["commits"] == 5
        assert result["additions"] == 120
        assert result["deletions"] == 30
        assert result["changed_files"] == 3

        # Verify user/author
        assert result["user"] == {"login": "contributor", "id": 12345, "type": "User"}

        # Verify assignees
        assert len(result["assignees"]) == 1
        assert result["assignees"][0] == {"login": "reviewer1", "id": 67890}

        # Verify labels
        assert result["labels"] == ["bug", "priority-high"]

        # Verify head/base refs
        assert result["head"] == {"ref": "feature-branch", "sha": "abc123"}
        assert result["base"] == {"ref": "main", "sha": "def456"}

        # Verify comments (issue comment + review comment)
        assert len(result["comments"]) == 2

        # Issue comment
        issue_comment = result["comments"][0]
        assert issue_comment["id"] == 111
        assert issue_comment["body"] == "Looks good!"
        assert issue_comment["comment_type"] == "issue"
        assert issue_comment["user"] == {"login": "reviewer1", "id": 67890, "type": "User"}

        # Review comment
        review_comment = result["comments"][1]
        assert review_comment["id"] == 222
        assert review_comment["body"] == "This line needs fixing"
        assert review_comment["comment_type"] == "review"
        assert review_comment["path"] == "src/main.py"
        assert review_comment["line"] == 42
        assert review_comment["diff_hunk"] == "@@ -40,3 +40,5 @@"
        assert review_comment["user"] == {"login": "reviewer2", "id": 11111, "type": "User"}

        # Verify reviews
        assert len(result["reviews"]) == 1
        review = result["reviews"][0]
        assert review["id"] == 333
        assert review["body"] == "Approved with suggestions"
        assert review["state"] == "APPROVED"
        assert review["submitted_at"] == "2024-01-15T13:00:00Z"
        assert review["commit_id"] == "abc123"
        assert review["user"] == {"login": "reviewer1", "id": 67890, "type": "User"}

    def test_graphql_pr_not_found(self, github_client):
        """Test when PR doesn't exist."""
        mock_response = {
            "rateLimit": {"cost": 1, "remaining": 4999},
            "repository": {"pullRequest": None},
        }

        with patch.object(github_client, "_execute_graphql", return_value=mock_response):
            result = github_client.get_pull_request_with_comments_graphql("owner/repo", 999)

        assert result is None

    def test_graphql_pr_empty_comments_and_reviews(self, github_client):
        """Test PR with no comments or reviews."""
        mock_response = {
            "rateLimit": {"cost": 3, "remaining": 4997},
            "repository": {
                "pullRequest": {
                    "id": "PR_123",
                    "number": 1,
                    "title": "Test PR",
                    "body": "Test body",
                    "state": "OPEN",
                    "isDraft": False,
                    "merged": False,
                    "createdAt": "2024-01-15T10:00:00Z",
                    "updatedAt": "2024-01-15T10:00:00Z",
                    "closedAt": None,
                    "mergedAt": None,
                    "url": "https://github.com/owner/repo/pull/1",
                    "commits": {"totalCount": 1},
                    "additions": 10,
                    "deletions": 5,
                    "changedFiles": 1,
                    "author": {"__typename": "User", "login": "author", "databaseId": 123},
                    "assignees": {"nodes": []},
                    "labels": {"nodes": []},
                    "headRef": {"name": "branch", "target": {"oid": "abc"}},
                    "baseRef": {"name": "main", "target": {"oid": "def"}},
                    "comments": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                    "reviewThreads": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                    "reviews": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                }
            },
        }

        with patch.object(github_client, "_execute_graphql", return_value=mock_response):
            result = github_client.get_pull_request_with_comments_graphql("owner/repo", 1)

        assert result is not None
        assert result["comments"] == []
        assert result["reviews"] == []
        assert result["number"] == 1
        assert result["title"] == "Test PR"

    def test_graphql_pr_pagination_warning(self, github_client, caplog):
        """Test warning logged when pagination is needed."""
        mock_response = {
            "rateLimit": {"cost": 53, "remaining": 4947},
            "repository": {
                "pullRequest": {
                    "id": "PR_123",
                    "number": 1,
                    "title": "Test PR",
                    "body": None,
                    "state": "OPEN",
                    "isDraft": False,
                    "merged": False,
                    "createdAt": "2024-01-15T10:00:00Z",
                    "updatedAt": "2024-01-15T10:00:00Z",
                    "closedAt": None,
                    "mergedAt": None,
                    "url": "https://github.com/owner/repo/pull/1",
                    "commits": {"totalCount": 1},
                    "additions": 10,
                    "deletions": 5,
                    "changedFiles": 1,
                    "author": None,
                    "assignees": {"nodes": []},
                    "labels": {"nodes": []},
                    "headRef": None,
                    "baseRef": None,
                    "comments": {
                        "pageInfo": {"hasNextPage": True, "endCursor": "cursor1"},
                        "nodes": [],
                    },
                    "reviewThreads": {
                        "pageInfo": {"hasNextPage": True, "endCursor": "cursor2"},
                        "nodes": [],
                    },
                    "reviews": {
                        "pageInfo": {"hasNextPage": True, "endCursor": "cursor3"},
                        "nodes": [],
                    },
                }
            },
        }

        with patch.object(github_client, "_execute_graphql", return_value=mock_response):
            result = github_client.get_pull_request_with_comments_graphql("owner/repo", 1)

        assert result is not None
        # Check that warnings were logged
        assert "more than 100 comments" in caplog.text
        assert "more than 100 review threads" in caplog.text
        assert "more than 100 reviews" in caplog.text

    def test_graphql_pr_invalid_repo_spec(self, github_client):
        """Test error handling for invalid repo_spec format."""
        # No slash
        with pytest.raises(ValueError, match="Invalid repo_spec format"):
            github_client.get_pull_request_with_comments_graphql("invalidformat", 1)

        # Too many parts
        with pytest.raises(ValueError, match="Invalid repo_spec format"):
            github_client.get_pull_request_with_comments_graphql("owner/repo/extra", 1)

        # Empty string
        with pytest.raises(ValueError, match="Invalid repo_spec format"):
            github_client.get_pull_request_with_comments_graphql("", 1)

    def test_graphql_pr_handles_bot_authors(self, github_client):
        """Test handling of bot authors."""
        mock_response = {
            "rateLimit": {"cost": 3, "remaining": 4997},
            "repository": {
                "pullRequest": {
                    "id": "PR_123",
                    "number": 1,
                    "title": "Bot PR",
                    "body": None,
                    "state": "OPEN",
                    "isDraft": False,
                    "merged": False,
                    "createdAt": "2024-01-15T10:00:00Z",
                    "updatedAt": "2024-01-15T10:00:00Z",
                    "closedAt": None,
                    "mergedAt": None,
                    "url": "https://github.com/owner/repo/pull/1",
                    "commits": {"totalCount": 1},
                    "additions": 10,
                    "deletions": 5,
                    "changedFiles": 1,
                    "author": {
                        "__typename": "Bot",
                        "login": "dependabot[bot]",
                        "databaseId": 99999,
                    },  # Bot author
                    "assignees": {"nodes": []},
                    "labels": {"nodes": []},
                    "headRef": None,
                    "baseRef": None,
                    "comments": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                    "reviewThreads": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                    "reviews": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                }
            },
        }

        with patch.object(github_client, "_execute_graphql", return_value=mock_response):
            result = github_client.get_pull_request_with_comments_graphql("owner/repo", 1)

        assert result is not None
        assert result["user"]["login"] == "dependabot[bot]"
        assert result["user"]["id"] == 99999
        assert result["user"]["type"] == "Bot"

    def test_graphql_pr_rate_limit_error(self, github_client):
        """Test rate limiting is propagated correctly."""
        from src.jobs.exceptions import ExtendVisibilityException

        with (
            patch.object(
                github_client, "_execute_graphql", side_effect=RateLimitedError(retry_after=60)
            ),
            pytest.raises(ExtendVisibilityException),
        ):
            # The rate_limited decorator wraps RateLimitedError in ExtendVisibilityException
            github_client.get_pull_request_with_comments_graphql("owner/repo", 1)

    def test_graphql_pr_merged_state(self, github_client):
        """Test merged PRs have correct state."""
        mock_response = {
            "rateLimit": {"cost": 3, "remaining": 4997},
            "repository": {
                "pullRequest": {
                    "id": "PR_123",
                    "number": 1,
                    "title": "Merged PR",
                    "body": None,
                    "state": "MERGED",  # Merged state
                    "isDraft": False,
                    "merged": True,
                    "createdAt": "2024-01-15T10:00:00Z",
                    "updatedAt": "2024-01-15T10:00:00Z",
                    "closedAt": "2024-01-15T15:00:00Z",
                    "mergedAt": "2024-01-15T15:00:00Z",  # Merge timestamp
                    "url": "https://github.com/owner/repo/pull/1",
                    "commits": {"totalCount": 1},
                    "additions": 10,
                    "deletions": 5,
                    "changedFiles": 1,
                    "author": {"__typename": "User", "login": "author", "databaseId": 123},
                    "assignees": {"nodes": []},
                    "labels": {"nodes": []},
                    "headRef": None,
                    "baseRef": None,
                    "comments": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                    "reviewThreads": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                    "reviews": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                }
            },
        }

        with patch.object(github_client, "_execute_graphql", return_value=mock_response):
            result = github_client.get_pull_request_with_comments_graphql("owner/repo", 1)

        assert result is not None
        assert result["state"] == "merged"  # Lowercased
        assert result["merged"] is True
        assert result["merged_at"] == "2024-01-15T15:00:00Z"
        assert result["closed_at"] == "2024-01-15T15:00:00Z"

    def test_graphql_pr_missing_optional_fields(self, github_client):
        """Test handling of missing optional fields."""
        mock_response = {
            "rateLimit": {"cost": 3, "remaining": 4997},
            "repository": {
                "pullRequest": {
                    "id": "PR_123",
                    "number": 1,
                    "title": "Minimal PR",
                    "body": None,  # No body
                    "state": "OPEN",
                    "isDraft": False,
                    "merged": False,
                    "createdAt": "2024-01-15T10:00:00Z",
                    "updatedAt": "2024-01-15T10:00:00Z",
                    "closedAt": None,
                    "mergedAt": None,
                    "url": "https://github.com/owner/repo/pull/1",
                    "commits": {"totalCount": 1},
                    "additions": None,  # No additions
                    "deletions": None,  # No deletions
                    "changedFiles": None,  # No changed files
                    "author": None,  # No author
                    "assignees": {"nodes": []},  # No assignees
                    "labels": {"nodes": []},  # No labels
                    "headRef": None,  # No head ref
                    "baseRef": None,  # No base ref
                    "comments": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                    "reviewThreads": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                    "reviews": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                }
            },
        }

        with patch.object(github_client, "_execute_graphql", return_value=mock_response):
            result = github_client.get_pull_request_with_comments_graphql("owner/repo", 1)

        assert result is not None
        assert result["body"] is None
        assert result["additions"] is None
        assert result["deletions"] is None
        assert result["changed_files"] is None
        assert result["assignees"] == []
        assert result["labels"] == []

    def test_graphql_pr_multiple_review_threads(self, github_client):
        """Test multiple review threads with multiple comments each."""
        mock_response = {
            "rateLimit": {"cost": 53, "remaining": 4947},
            "repository": {
                "pullRequest": {
                    "id": "PR_123",
                    "number": 1,
                    "title": "Test PR",
                    "body": None,
                    "state": "OPEN",
                    "isDraft": False,
                    "merged": False,
                    "createdAt": "2024-01-15T10:00:00Z",
                    "updatedAt": "2024-01-15T10:00:00Z",
                    "closedAt": None,
                    "mergedAt": None,
                    "url": "https://github.com/owner/repo/pull/1",
                    "commits": {"totalCount": 1},
                    "additions": 10,
                    "deletions": 5,
                    "changedFiles": 1,
                    "author": None,
                    "assignees": {"nodes": []},
                    "labels": {"nodes": []},
                    "headRef": None,
                    "baseRef": None,
                    "comments": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                    "reviewThreads": {
                        "pageInfo": {"hasNextPage": False},
                        "nodes": [
                            {
                                "comments": {
                                    "nodes": [
                                        {
                                            "databaseId": 1,
                                            "body": "Thread 1 Comment 1",
                                            "createdAt": "2024-01-15T11:00:00Z",
                                            "updatedAt": "2024-01-15T11:00:00Z",
                                            "url": "https://github.com/owner/repo/pull/1#r1",
                                            "path": "file1.py",
                                            "line": 10,
                                            "diffHunk": "@@ -8,3 +8,5 @@",
                                            "author": {
                                                "__typename": "User",
                                                "login": "reviewer1",
                                                "databaseId": 100,
                                            },
                                        },
                                        {
                                            "databaseId": 2,
                                            "body": "Thread 1 Comment 2",
                                            "createdAt": "2024-01-15T11:05:00Z",
                                            "updatedAt": "2024-01-15T11:05:00Z",
                                            "url": "https://github.com/owner/repo/pull/1#r2",
                                            "path": "file1.py",
                                            "line": 10,
                                            "diffHunk": "@@ -8,3 +8,5 @@",
                                            "author": {
                                                "__typename": "User",
                                                "login": "author",
                                                "databaseId": 200,
                                            },
                                        },
                                    ]
                                }
                            },
                            {
                                "comments": {
                                    "nodes": [
                                        {
                                            "databaseId": 3,
                                            "body": "Thread 2 Comment 1",
                                            "createdAt": "2024-01-15T12:00:00Z",
                                            "updatedAt": "2024-01-15T12:00:00Z",
                                            "url": "https://github.com/owner/repo/pull/1#r3",
                                            "path": "file2.py",
                                            "line": 20,
                                            "diffHunk": "@@ -18,3 +18,5 @@",
                                            "author": {
                                                "__typename": "User",
                                                "login": "reviewer2",
                                                "databaseId": 300,
                                            },
                                        },
                                        {
                                            "databaseId": 4,
                                            "body": "Thread 2 Comment 2",
                                            "createdAt": "2024-01-15T12:05:00Z",
                                            "updatedAt": "2024-01-15T12:05:00Z",
                                            "url": "https://github.com/owner/repo/pull/1#r4",
                                            "path": "file2.py",
                                            "line": 20,
                                            "diffHunk": "@@ -18,3 +18,5 @@",
                                            "author": {
                                                "__typename": "User",
                                                "login": "reviewer1",
                                                "databaseId": 100,
                                            },
                                        },
                                    ]
                                }
                            },
                        ],
                    },
                    "reviews": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                }
            },
        }

        with patch.object(github_client, "_execute_graphql", return_value=mock_response):
            result = github_client.get_pull_request_with_comments_graphql("owner/repo", 1)

        assert result is not None
        assert len(result["comments"]) == 4  # All 4 review comments
        # Verify all are review comments
        for comment in result["comments"]:
            assert comment["comment_type"] == "review"
        # Verify IDs
        assert [c["id"] for c in result["comments"]] == [1, 2, 3, 4]

    def test_graphql_pr_validation_error(self, github_client):
        """Test that Pydantic validation catches malformed responses."""
        from pydantic import ValidationError

        # Invalid response: missing required field 'number'
        invalid_response = {
            "rateLimit": {"cost": 1, "remaining": 4999},
            "repository": {
                "pullRequest": {
                    "id": "PR_123",
                    # Missing 'number' field (required)
                    "title": "Test PR",
                    "state": "OPEN",
                }
            },
        }

        with patch.object(github_client, "_execute_graphql", return_value=invalid_response):
            with pytest.raises(ValidationError) as exc_info:
                github_client.get_pull_request_with_comments_graphql("owner/repo", 1)

            # Verify the error mentions the missing field
            assert "number" in str(exc_info.value).lower()
