"""Integration tests for GitHub PR backfill extractor with GraphQL."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from connectors.github import GitHubPRBackfillExtractor
from connectors.github.github_models import GitHubPRBatch
from src.clients.github import GitHubClient
from src.clients.ssm import SSMClient


@pytest.fixture
def mock_db_pool():
    """Create a mock database pool."""
    pool = MagicMock()
    conn = AsyncMock()

    # Mock connection context manager
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    # Mock transaction
    conn.transaction.return_value.__aenter__ = AsyncMock()
    conn.transaction.return_value.__aexit__ = AsyncMock()

    # Mock execute and executemany
    conn.execute = AsyncMock()
    conn.executemany = AsyncMock()

    return pool


@pytest.fixture
def mock_graphql_pr_data():
    """Mock PR data returned from GraphQL."""
    return {
        "id": 123,
        "number": 42,
        "title": "Test PR",
        "body": "Test description",
        "state": "open",
        "draft": False,
        "merged": False,
        "created_at": "2024-01-15T10:00:00Z",
        "updated_at": "2024-01-15T10:00:00Z",
        "closed_at": None,
        "merged_at": None,
        "html_url": "https://github.com/owner/repo/pull/42",
        "commits": 5,
        "additions": 100,
        "deletions": 20,
        "changed_files": 3,
        "user": {"login": "author", "id": 1000, "type": "User"},
        "assignees": [{"login": "reviewer", "id": 2000}],
        "labels": ["bug", "priority-high"],
        "head": {"ref": "feature-branch", "sha": "abc123"},
        "base": {"ref": "main", "sha": "def456"},
        "comments": [
            {
                "id": 111,
                "body": "Looks good!",
                "created_at": "2024-01-15T11:00:00Z",
                "updated_at": "2024-01-15T11:00:00Z",
                "url": "https://github.com/owner/repo/pull/42#issuecomment-111",
                "user": {"login": "reviewer", "id": 2000},
                "comment_type": "issue",
            },
            {
                "id": 222,
                "body": "Fix this line",
                "created_at": "2024-01-15T12:00:00Z",
                "updated_at": "2024-01-15T12:00:00Z",
                "url": "https://github.com/owner/repo/pull/42#discussion_r222",
                "path": "src/main.py",
                "line": 42,
                "diff_hunk": "@@ -40,3 +40,5 @@",
                "user": {"login": "reviewer", "id": 2000},
                "comment_type": "review",
            },
        ],
        "reviews": [
            {
                "id": 333,
                "body": "Approved",
                "state": "APPROVED",
                "submitted_at": "2024-01-15T13:00:00Z",
                "url": "https://github.com/owner/repo/pull/42#pullrequestreview-333",
                "commit_id": "abc123",
                "user": {"login": "reviewer", "id": 2000},
            }
        ],
    }


class TestGitHubPRBackfillIntegration:
    """Integration tests for GitHub PR backfill with GraphQL."""

    @pytest.mark.asyncio
    async def test_process_pr_batch_with_graphql(self, mock_db_pool, mock_graphql_pr_data):
        """Test full flow from _process_pr_batch to artifact creation."""
        # Setup mocks
        mock_ssm = MagicMock(spec=SSMClient)
        extractor = GitHubPRBackfillExtractor(mock_ssm)

        # Create mock GitHub client
        mock_github_client = MagicMock(spec=GitHubClient)

        # Mock GraphQL calls to return PR data
        def mock_graphql_call(repo_spec, pr_number):
            # Return different PR data for each PR number
            data = mock_graphql_pr_data.copy()
            data["number"] = pr_number
            data["id"] = pr_number * 10
            return data

        mock_github_client.get_pull_request_with_comments_graphql = MagicMock(
            side_effect=mock_graphql_call
        )

        # Create PR batch with 3 PRs
        pr_batch = GitHubPRBatch(
            org_or_owner="owner", repo_name="repo", repo_id=12345, pr_numbers=[1, 2, 3]
        )

        job_id = str(uuid4())

        # Process the batch
        entity_ids = await extractor._process_pr_batch(
            job_id, mock_github_client, pr_batch, mock_db_pool
        )

        # Assertions
        # 1. GraphQL method called 3 times (once per PR)
        assert mock_github_client.get_pull_request_with_comments_graphql.call_count == 3
        mock_github_client.get_pull_request_with_comments_graphql.assert_any_call("owner/repo", 1)
        mock_github_client.get_pull_request_with_comments_graphql.assert_any_call("owner/repo", 2)
        mock_github_client.get_pull_request_with_comments_graphql.assert_any_call("owner/repo", 3)

        # 2. Returns 3 entity IDs
        assert len(entity_ids) == 3

        # 3. Database executemany was called to store artifacts
        assert mock_db_pool.acquire.return_value.__aenter__.called

    def test_create_pr_artifact_with_reviews(self, mock_graphql_pr_data):
        """Test _create_pr_artifact now includes reviews."""
        # Setup
        mock_ssm = MagicMock(spec=SSMClient)
        extractor = GitHubPRBackfillExtractor(mock_ssm)

        job_id = str(uuid4())

        # Create artifact with empty files list
        artifact = extractor._create_pr_artifact(
            job_id=job_id,
            pr_data=mock_graphql_pr_data.copy(),
            organization="owner",
            repository="repo",
            repo_id=12345,
            raw_files=[],
        )

        # Assertions
        assert artifact is not None
        assert artifact.entity_id == "12345_pr_42"

        # Comments populated
        assert len(artifact.content.comments) == 2
        assert artifact.content.comments[0].body == "Looks good!"
        assert artifact.content.comments[1].body == "Fix this line"

        # Reviews populated (not empty!)
        assert len(artifact.content.reviews) == 1
        assert artifact.content.reviews[0].body == "Approved"
        assert artifact.content.reviews[0].state == "APPROVED"
        assert artifact.content.reviews[0].id == 333

        # PR data populated
        assert artifact.content.pr_data.number == 42
        assert artifact.content.pr_data.title == "Test PR"

        # Metadata populated
        assert artifact.metadata.pr_number == 42
        assert artifact.metadata.repository == "repo"
        assert artifact.metadata.organization == "owner"

    @pytest.mark.asyncio
    async def test_process_pr_batch_handles_graphql_failure(
        self, mock_db_pool, mock_graphql_pr_data, caplog
    ):
        """Test error handling when GraphQL fails for one PR - should fail entire batch."""
        # Setup mocks
        mock_ssm = MagicMock(spec=SSMClient)
        extractor = GitHubPRBackfillExtractor(mock_ssm)

        # Create mock GitHub client
        mock_github_client = MagicMock(spec=GitHubClient)

        # Mock GraphQL to fail for PR #2, succeed for #1 and #3
        def mock_graphql_call(repo_spec, pr_number):
            if pr_number == 2:
                return None  # PR not found
            data = mock_graphql_pr_data.copy()
            data["number"] = pr_number
            data["id"] = pr_number * 10
            return data

        mock_github_client.get_pull_request_with_comments_graphql = MagicMock(
            side_effect=mock_graphql_call
        )

        # Create PR batch with 3 PRs
        pr_batch = GitHubPRBatch(
            org_or_owner="owner", repo_name="repo", repo_id=12345, pr_numbers=[1, 2, 3]
        )

        job_id = str(uuid4())

        # Process the batch - should raise RuntimeError when PR #2 fails
        with pytest.raises(RuntimeError, match="Could not fetch PR #2 from owner/repo"):
            await extractor._process_pr_batch(job_id, mock_github_client, pr_batch, mock_db_pool)

        # Assertions
        # 1. GraphQL method called only twice (PR #1 succeeds, PR #2 fails and raises)
        assert mock_github_client.get_pull_request_with_comments_graphql.call_count == 2

        # 2. Error logged for PR #2
        assert "Could not fetch PR #2" in caplog.text
