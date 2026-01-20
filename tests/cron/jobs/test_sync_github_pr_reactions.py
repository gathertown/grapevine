"""Tests for GitHub PR reactions sync cron job.

This module tests the sync_github_pr_reactions cron job including:
- GitHub token retrieval from SSM
- Fetching comments needing sync from database
- Fetching reactions from GitHub GraphQL API
- Syncing reactions to database
- Error handling and logging
- Rate limiting behavior
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.cron.jobs.sync_github_pr_reactions import (
    fetch_batch_pr_reactions,
    get_comments_needing_sync,
    get_github_token_for_tenant,
    sync_github_pr_reactions,
    sync_reactions_for_comment,
)


class TestGetGitHubToken:
    """Test suite for GitHub token retrieval."""

    @pytest.mark.asyncio
    async def test_get_token_success(self):
        """Test successful GitHub token retrieval."""
        mock_ssm = MagicMock()
        mock_ssm.get_github_app_token = AsyncMock(return_value="ghs_test_token_12345")

        with patch("src.cron.jobs.sync_github_pr_reactions.SSMClient", return_value=mock_ssm):
            token = await get_github_token_for_tenant("test_tenant_id")

            assert token == "ghs_test_token_12345"
            mock_ssm.get_github_app_token.assert_called_once_with("test_tenant_id")

    @pytest.mark.asyncio
    async def test_get_token_not_found(self):
        """Test handling when GitHub token is not found."""
        mock_ssm = MagicMock()
        mock_ssm.get_github_app_token = AsyncMock(return_value=None)

        with patch("src.cron.jobs.sync_github_pr_reactions.SSMClient", return_value=mock_ssm):
            token = await get_github_token_for_tenant("test_tenant_id")

            assert token is None


class TestGetCommentsNeedingSync:
    """Test suite for fetching comments that need reaction syncing."""

    @pytest.mark.asyncio
    async def test_get_comments_success(self):
        """Test successful retrieval of comments needing sync."""
        mock_rows = [
            {
                "id": "comment-1",
                "github_comment_id": 12345,
                "github_review_id": 67890,
                "github_pr_number": 100,
                "github_repo_owner": "test-org",
                "github_repo_name": "test-repo",
                "last_synced_at": None,
            },
            {
                "id": "comment-2",
                "github_comment_id": 12346,
                "github_review_id": 67891,
                "github_pr_number": 100,
                "github_repo_owner": "test-org",
                "github_repo_name": "test-repo",
                "last_synced_at": datetime.now(UTC) - timedelta(hours=2),
            },
        ]

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=mock_rows)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock()

        mock_pool_manager = MagicMock()
        mock_pool_manager.acquire_pool = MagicMock()
        mock_pool_manager.acquire_pool.return_value.__aenter__ = AsyncMock(return_value=mock_pool)
        mock_pool_manager.acquire_pool.return_value.__aexit__ = AsyncMock()

        with patch("src.cron.jobs.sync_github_pr_reactions.tenant_db_manager", mock_pool_manager):
            comments = await get_comments_needing_sync("test_tenant", days=14)

            assert len(comments) == 2
            assert comments[0]["id"] == "comment-1"
            assert comments[0]["github_comment_id"] == 12345
            assert comments[1]["id"] == "comment-2"

            # Verify SQL query was called with correct cutoff date
            mock_conn.fetch.assert_called_once()
            call_args = mock_conn.fetch.call_args
            cutoff_date = call_args[0][1]
            expected_cutoff = datetime.now(UTC) - timedelta(days=14)
            assert abs((cutoff_date - expected_cutoff).total_seconds()) < 5

    @pytest.mark.asyncio
    async def test_get_comments_empty(self):
        """Test when no comments need syncing."""
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock()

        mock_pool_manager = MagicMock()
        mock_pool_manager.acquire_pool = MagicMock()
        mock_pool_manager.acquire_pool.return_value.__aenter__ = AsyncMock(return_value=mock_pool)
        mock_pool_manager.acquire_pool.return_value.__aexit__ = AsyncMock()

        with patch("src.cron.jobs.sync_github_pr_reactions.tenant_db_manager", mock_pool_manager):
            comments = await get_comments_needing_sync("test_tenant", days=7)

            assert comments == []


class TestFetchBatchPRReactions:
    """Test suite for fetching PR reactions from GitHub GraphQL API."""

    @pytest.mark.asyncio
    async def test_fetch_reactions_success(self):
        """Test successful fetching of PR reactions."""
        mock_response = {
            "data": {
                "repository": {
                    "pr0": {
                        "number": 100,
                        "reviews": {
                            "nodes": [
                                {
                                    "id": "review-1",
                                    "databaseId": 67890,
                                    "comments": {
                                        "nodes": [
                                            {
                                                "databaseId": 12345,
                                                "reactions": {
                                                    "nodes": [
                                                        {
                                                            "content": "THUMBS_UP",
                                                            "user": {"login": "user1"},
                                                            "createdAt": "2024-01-15T10:00:00Z",
                                                        },
                                                        {
                                                            "content": "THUMBS_UP",
                                                            "user": {"login": "user2"},
                                                            "createdAt": "2024-01-15T11:00:00Z",
                                                        },
                                                        {
                                                            "content": "HOORAY",
                                                            "user": {"login": "user3"},
                                                            "createdAt": "2024-01-15T12:00:00Z",
                                                        },
                                                    ]
                                                },
                                            }
                                        ]
                                    },
                                }
                            ]
                        },
                    }
                }
            }
        }

        mock_httpx_response = MagicMock()
        mock_httpx_response.json = MagicMock(return_value=mock_response)
        mock_httpx_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_httpx_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_client):
            reactions = await fetch_batch_pr_reactions("test-org", "test-repo", [100], "test_token")

            assert 100 in reactions
            assert 12345 in reactions[100]
            assert len(reactions[100][12345]) == 3
            assert reactions[100][12345][0]["user"] == "user1"
            assert reactions[100][12345][0]["reaction_type"] == "thumbs_up"
            assert reactions[100][12345][1]["user"] == "user2"
            assert reactions[100][12345][1]["reaction_type"] == "thumbs_up"
            assert reactions[100][12345][2]["user"] == "user3"
            assert reactions[100][12345][2]["reaction_type"] == "hooray"

    @pytest.mark.asyncio
    async def test_fetch_reactions_multiple_comments(self):
        """Test fetching reactions for multiple comments in one PR."""
        mock_response = {
            "data": {
                "repository": {
                    "pr0": {
                        "number": 100,
                        "reviews": {
                            "nodes": [
                                {
                                    "id": "review-1",
                                    "databaseId": 67890,
                                    "comments": {
                                        "nodes": [
                                            {
                                                "databaseId": 100,
                                                "reactions": {
                                                    "nodes": [
                                                        {
                                                            "content": "THUMBS_UP",
                                                            "user": {"login": "alice"},
                                                            "createdAt": "2024-01-15T10:00:00Z",
                                                        }
                                                    ]
                                                },
                                            },
                                            {
                                                "databaseId": 200,
                                                "reactions": {
                                                    "nodes": [
                                                        {
                                                            "content": "LAUGH",
                                                            "user": {"login": "bob"},
                                                            "createdAt": "2024-01-15T11:00:00Z",
                                                        }
                                                    ]
                                                },
                                            },
                                        ]
                                    },
                                }
                            ]
                        },
                    }
                }
            }
        }

        mock_httpx_response = MagicMock()
        mock_httpx_response.json = MagicMock(return_value=mock_response)
        mock_httpx_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_httpx_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_client):
            reactions = await fetch_batch_pr_reactions("test-org", "test-repo", [100], "test_token")

            assert 100 in reactions
            assert len(reactions[100]) == 2
            assert 100 in reactions[100]
            assert 200 in reactions[100]
            assert reactions[100][100][0]["user"] == "alice"
            assert reactions[100][100][0]["reaction_type"] == "thumbs_up"
            assert reactions[100][200][0]["user"] == "bob"
            assert reactions[100][200][0]["reaction_type"] == "laugh"

    @pytest.mark.asyncio
    async def test_fetch_reactions_no_reactions(self):
        """Test fetching when there are no reactions."""
        mock_response = {
            "data": {
                "repository": {
                    "pr0": {
                        "number": 100,
                        "reviews": {
                            "nodes": [
                                {
                                    "id": "review-1",
                                    "databaseId": 67890,
                                    "comments": {
                                        "nodes": [
                                            {
                                                "databaseId": 12345,
                                                "reactions": {"nodes": []},
                                            }
                                        ]
                                    },
                                }
                            ]
                        },
                    }
                }
            }
        }

        mock_httpx_response = MagicMock()
        mock_httpx_response.json = MagicMock(return_value=mock_response)
        mock_httpx_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_httpx_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_client):
            reactions = await fetch_batch_pr_reactions("test-org", "test-repo", [100], "test_token")

            assert reactions[100] == {}

    @pytest.mark.asyncio
    async def test_fetch_reactions_missing_user(self):
        """Test handling reactions with missing user data."""
        mock_response = {
            "data": {
                "repository": {
                    "pr0": {
                        "number": 100,
                        "reviews": {
                            "nodes": [
                                {
                                    "id": "review-1",
                                    "databaseId": 67890,
                                    "comments": {
                                        "nodes": [
                                            {
                                                "databaseId": 12345,
                                                "reactions": {
                                                    "nodes": [
                                                        {
                                                            "content": "THUMBS_UP",
                                                            "user": None,
                                                            "createdAt": "2024-01-15T10:00:00Z",
                                                        },
                                                        {
                                                            "content": "THUMBS_UP",
                                                            "user": {"login": "user2"},
                                                            "createdAt": "2024-01-15T11:00:00Z",
                                                        },
                                                    ]
                                                },
                                            }
                                        ]
                                    },
                                }
                            ]
                        },
                    }
                }
            }
        }

        mock_httpx_response = MagicMock()
        mock_httpx_response.json = MagicMock(return_value=mock_response)
        mock_httpx_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_httpx_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_client):
            reactions = await fetch_batch_pr_reactions("test-org", "test-repo", [100], "test_token")

            # Should only include the reaction with a valid user
            assert len(reactions[100][12345]) == 1
            assert reactions[100][12345][0]["user"] == "user2"

    @pytest.mark.asyncio
    async def test_fetch_reactions_graphql_error(self):
        """Test handling GraphQL errors in response."""
        mock_response = {
            "errors": [{"message": "Resource not accessible by integration", "type": "FORBIDDEN"}]
        }

        mock_httpx_response = MagicMock()
        mock_httpx_response.json = MagicMock(return_value=mock_response)
        mock_httpx_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_httpx_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)  # Don't suppress exceptions

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            pytest.raises(Exception, match="GitHub GraphQL errors"),
        ):
            await fetch_batch_pr_reactions("test-org", "test-repo", [100], "test_token")

    @pytest.mark.asyncio
    async def test_fetch_reactions_no_repository_data(self):
        """Test handling when repository data is missing."""
        mock_response: dict[str, dict[str, str]] = {"data": {}}

        mock_httpx_response = MagicMock()
        mock_httpx_response.json = MagicMock(return_value=mock_response)
        mock_httpx_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_httpx_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)  # Don't suppress exceptions

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            pytest.raises(Exception, match="No repository data returned"),
        ):
            await fetch_batch_pr_reactions("test-org", "test-repo", [100], "test_token")

    @pytest.mark.asyncio
    async def test_fetch_reactions_http_error(self):
        """Test handling HTTP errors from GitHub API."""
        mock_httpx_response = MagicMock()
        mock_httpx_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Rate limit exceeded", request=MagicMock(), response=MagicMock()
            )
        )

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_httpx_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)  # Don't suppress exceptions

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            pytest.raises(httpx.HTTPStatusError),
        ):
            await fetch_batch_pr_reactions("test-org", "test-repo", [100], "test_token")

    @pytest.mark.asyncio
    async def test_fetch_batch_multiple_prs(self):
        """Test fetching reactions for multiple PRs in a batch."""
        mock_response = {
            "data": {
                "repository": {
                    "pr0": {
                        "number": 10,
                        "reviews": {
                            "nodes": [
                                {
                                    "id": "review-1",
                                    "databaseId": 1000,
                                    "comments": {
                                        "nodes": [
                                            {
                                                "databaseId": 100,
                                                "reactions": {
                                                    "nodes": [
                                                        {
                                                            "content": "THUMBS_UP",
                                                            "user": {"login": "alice"},
                                                            "createdAt": "2024-01-15T10:00:00Z",
                                                        }
                                                    ]
                                                },
                                            }
                                        ]
                                    },
                                }
                            ]
                        },
                    },
                    "pr1": {
                        "number": 20,
                        "reviews": {
                            "nodes": [
                                {
                                    "id": "review-2",
                                    "databaseId": 2000,
                                    "comments": {
                                        "nodes": [
                                            {
                                                "databaseId": 200,
                                                "reactions": {
                                                    "nodes": [
                                                        {
                                                            "content": "HEART",
                                                            "user": {"login": "bob"},
                                                            "createdAt": "2024-01-15T11:00:00Z",
                                                        }
                                                    ]
                                                },
                                            }
                                        ]
                                    },
                                }
                            ]
                        },
                    },
                }
            }
        }

        mock_httpx_response = MagicMock()
        mock_httpx_response.json = MagicMock(return_value=mock_response)
        mock_httpx_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_httpx_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_client):
            reactions = await fetch_batch_pr_reactions(
                "test-org", "test-repo", [10, 20], "test_token"
            )

            # Should have reactions for both PRs
            assert 10 in reactions
            assert 20 in reactions
            assert reactions[10][100][0]["user"] == "alice"
            assert reactions[10][100][0]["reaction_type"] == "thumbs_up"
            assert reactions[20][200][0]["user"] == "bob"
            assert reactions[20][200][0]["reaction_type"] == "heart"


class TestSyncReactionsForComment:
    """Test suite for syncing reactions for a single comment."""

    @pytest.mark.asyncio
    async def test_sync_reactions_success(self):
        """Test successful syncing of reactions."""
        reactions = [
            {"user": "alice", "reaction_type": "thumbs_up", "created_at": "2024-01-15T10:00:00Z"},
            {"user": "bob", "reaction_type": "heart", "created_at": "2024-01-15T11:00:00Z"},
        ]

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_transaction = MagicMock()
        mock_transaction.__aenter__ = AsyncMock()
        mock_transaction.__aexit__ = AsyncMock()
        mock_conn.transaction = MagicMock(return_value=mock_transaction)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock()

        mock_pool_manager = MagicMock()
        mock_pool_manager.acquire_pool = MagicMock()
        mock_pool_manager.acquire_pool.return_value.__aenter__ = AsyncMock(return_value=mock_pool)
        mock_pool_manager.acquire_pool.return_value.__aexit__ = AsyncMock()

        with patch("src.cron.jobs.sync_github_pr_reactions.tenant_db_manager", mock_pool_manager):
            await sync_reactions_for_comment("test_tenant", "comment-1", 12345, reactions)

            # Verify DELETE was called once
            delete_calls = [
                call
                for call in mock_conn.execute.call_args_list
                if call[0][0].strip().startswith("DELETE")
            ]
            assert len(delete_calls) == 1

            # Verify INSERT was called for each reaction (2 reactions)
            insert_calls = [
                call
                for call in mock_conn.execute.call_args_list
                if call[0][0].strip().startswith("INSERT")
            ]
            assert len(insert_calls) == 2

            # Verify UPDATE was called once (to update last_synced_at)
            update_calls = [
                call
                for call in mock_conn.execute.call_args_list
                if call[0][0].strip().startswith("UPDATE")
            ]
            assert len(update_calls) == 1

    @pytest.mark.asyncio
    async def test_sync_reactions_empty_list(self):
        """Test syncing with empty reactions list."""
        reactions: list[dict[str, str]] = []

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_transaction = MagicMock()
        mock_transaction.__aenter__ = AsyncMock()
        mock_transaction.__aexit__ = AsyncMock()
        mock_conn.transaction = MagicMock(return_value=mock_transaction)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock()

        mock_pool_manager = MagicMock()
        mock_pool_manager.acquire_pool = MagicMock()
        mock_pool_manager.acquire_pool.return_value.__aenter__ = AsyncMock(return_value=mock_pool)
        mock_pool_manager.acquire_pool.return_value.__aexit__ = AsyncMock()

        with patch("src.cron.jobs.sync_github_pr_reactions.tenant_db_manager", mock_pool_manager):
            await sync_reactions_for_comment("test_tenant", "comment-1", 12345, reactions)

            # Verify DELETE was called once
            delete_calls = [
                call
                for call in mock_conn.execute.call_args_list
                if call[0][0].strip().startswith("DELETE")
            ]
            assert len(delete_calls) == 1

            # Verify no INSERT calls (empty reactions)
            insert_calls = [
                call
                for call in mock_conn.execute.call_args_list
                if call[0][0].strip().startswith("INSERT")
            ]
            assert len(insert_calls) == 0

            # Verify UPDATE was called once (to update last_synced_at)
            update_calls = [
                call
                for call in mock_conn.execute.call_args_list
                if call[0][0].strip().startswith("UPDATE")
            ]
            assert len(update_calls) == 1


class TestSyncGitHubPRReactionsJob:
    """Test suite for the main sync job."""

    @pytest.mark.asyncio
    async def test_job_no_token(self):
        """Test job exits early when no GitHub token is found."""
        with (
            patch(
                "src.cron.jobs.sync_github_pr_reactions.get_github_token_for_tenant",
                return_value=None,
            ),
            patch("src.cron.jobs.sync_github_pr_reactions.logger") as mock_logger,
        ):
            await sync_github_pr_reactions()

            mock_logger.warning.assert_called_once()
            assert "No GitHub app token found" in mock_logger.warning.call_args[0][0]

    @pytest.mark.asyncio
    async def test_job_no_comments(self):
        """Test job exits early when no comments need syncing."""
        with (
            patch(
                "src.cron.jobs.sync_github_pr_reactions.get_github_token_for_tenant",
                return_value="test_token",
            ),
            patch(
                "src.cron.jobs.sync_github_pr_reactions.get_comments_needing_sync",
                return_value=[],
            ),
            patch("src.cron.jobs.sync_github_pr_reactions.logger") as mock_logger,
        ):
            await sync_github_pr_reactions()

            info_calls = [call[0][0] for call in mock_logger.info.call_args_list]
            assert any("No comments found needing sync" in msg for msg in info_calls)

    @pytest.mark.asyncio
    async def test_job_success_single_pr(self):
        """Test successful sync for a single PR."""
        comments = [
            {
                "id": "comment-1",
                "github_comment_id": 12345,
                "github_review_id": 67890,
                "github_pr_number": 100,
                "github_repo_owner": "test-org",
                "github_repo_name": "test-repo",
                "last_synced_at": None,
            }
        ]

        # Batched response: pr_number -> comment_id -> reactions
        reactions_map = {
            100: {
                12345: [
                    {
                        "user": "alice",
                        "reaction_type": "thumbs_up",
                        "created_at": "2024-01-15T10:00:00Z",
                    }
                ]
            }
        }

        with (
            patch(
                "src.cron.jobs.sync_github_pr_reactions.get_github_token_for_tenant",
                return_value="test_token",
            ),
            patch(
                "src.cron.jobs.sync_github_pr_reactions.get_comments_needing_sync",
                return_value=comments,
            ),
            patch(
                "src.cron.jobs.sync_github_pr_reactions.fetch_batch_pr_reactions",
                return_value=reactions_map,
            ) as mock_fetch,
            patch("src.cron.jobs.sync_github_pr_reactions.sync_reactions_for_comment") as mock_sync,
            patch("src.cron.jobs.sync_github_pr_reactions.asyncio.sleep") as mock_sleep,
            patch("src.cron.jobs.sync_github_pr_reactions.logger") as mock_logger,
        ):
            await sync_github_pr_reactions()

            # Verify fetch_batch_pr_reactions was called with list of PRs
            mock_fetch.assert_called_once_with("test-org", "test-repo", [100], "test_token")

            # Verify sync_reactions_for_comment was called
            mock_sync.assert_called_once()

            # Verify rate limiting sleep was called
            mock_sleep.assert_called_once_with(0.5)

            # Verify success log
            info_calls = [call[0][0] for call in mock_logger.info.call_args_list]
            assert any("sync complete" in msg.lower() for msg in info_calls)
            assert any("1 comments synced" in msg for msg in info_calls)

    @pytest.mark.asyncio
    async def test_job_success_multiple_prs(self):
        """Test successful sync for multiple PRs."""
        comments = [
            {
                "id": "comment-1",
                "github_comment_id": 100,
                "github_review_id": 1000,
                "github_pr_number": 10,
                "github_repo_owner": "org1",
                "github_repo_name": "repo1",
                "last_synced_at": None,
            },
            {
                "id": "comment-2",
                "github_comment_id": 200,
                "github_review_id": 2000,
                "github_pr_number": 20,
                "github_repo_owner": "org1",
                "github_repo_name": "repo1",
                "last_synced_at": None,
            },
            {
                "id": "comment-3",
                "github_comment_id": 300,
                "github_review_id": 3000,
                "github_pr_number": 30,
                "github_repo_owner": "org2",
                "github_repo_name": "repo2",
                "last_synced_at": None,
            },
        ]

        async def mock_fetch_batch_reactions(owner, repo, pr_numbers, token):
            # Return empty reactions for all PRs in the batch
            return {pr_num: {} for pr_num in pr_numbers}

        with (
            patch(
                "src.cron.jobs.sync_github_pr_reactions.get_github_token_for_tenant",
                return_value="test_token",
            ),
            patch(
                "src.cron.jobs.sync_github_pr_reactions.get_comments_needing_sync",
                return_value=comments,
            ),
            patch(
                "src.cron.jobs.sync_github_pr_reactions.fetch_batch_pr_reactions",
                side_effect=mock_fetch_batch_reactions,
            ) as mock_fetch,
            patch("src.cron.jobs.sync_github_pr_reactions.sync_reactions_for_comment") as mock_sync,
            patch("src.cron.jobs.sync_github_pr_reactions.asyncio.sleep") as mock_sleep,
            patch("src.cron.jobs.sync_github_pr_reactions.logger") as mock_logger,
        ):
            await sync_github_pr_reactions()

            # Should fetch reactions for 2 batches (one per repo)
            assert mock_fetch.call_count == 2

            # Should sync all 3 comments
            assert mock_sync.call_count == 3

            # Should sleep 2 times (once per batch)
            assert mock_sleep.call_count == 2

            # Verify success log
            info_calls = [call[0][0] for call in mock_logger.info.call_args_list]
            assert any("3 comments synced" in msg for msg in info_calls)

    @pytest.mark.asyncio
    async def test_job_handles_fetch_error(self):
        """Test job handles fetch errors gracefully."""
        comments = [
            {
                "id": "comment-1",
                "github_comment_id": 12345,
                "github_review_id": 67890,
                "github_pr_number": 100,
                "github_repo_owner": "test-org",
                "github_repo_name": "test-repo",
                "last_synced_at": None,
            }
        ]

        with (
            patch(
                "src.cron.jobs.sync_github_pr_reactions.get_github_token_for_tenant",
                return_value="test_token",
            ),
            patch(
                "src.cron.jobs.sync_github_pr_reactions.get_comments_needing_sync",
                return_value=comments,
            ),
            patch(
                "src.cron.jobs.sync_github_pr_reactions.fetch_batch_pr_reactions",
                side_effect=Exception("GitHub API error"),
            ),
            patch("src.cron.jobs.sync_github_pr_reactions.sync_reactions_for_comment") as mock_sync,
            patch("src.cron.jobs.sync_github_pr_reactions.logger") as mock_logger,
        ):
            await sync_github_pr_reactions()

            # Should not call sync_reactions_for_comment on error
            mock_sync.assert_not_called()

            # Should log error
            mock_logger.error.assert_called_once()
            error_msg = mock_logger.error.call_args[0][0]
            assert "Error syncing reactions" in error_msg
            assert "test-org/test-repo" in error_msg

            # Should log summary with errors
            info_calls = [call[0][0] for call in mock_logger.info.call_args_list]
            assert any("0 comments synced, 1 PRs with errors" in msg for msg in info_calls)

    @pytest.mark.asyncio
    async def test_job_groups_comments_by_pr(self):
        """Test job groups comments by PR correctly."""
        comments = [
            {
                "id": "comment-1",
                "github_comment_id": 100,
                "github_review_id": 1000,
                "github_pr_number": 50,
                "github_repo_owner": "test-org",
                "github_repo_name": "test-repo",
                "last_synced_at": None,
            },
            {
                "id": "comment-2",
                "github_comment_id": 200,
                "github_review_id": 2000,
                "github_pr_number": 50,
                "github_repo_owner": "test-org",
                "github_repo_name": "test-repo",
                "last_synced_at": None,
            },
            {
                "id": "comment-3",
                "github_comment_id": 300,
                "github_review_id": 3000,
                "github_pr_number": 50,
                "github_repo_owner": "test-org",
                "github_repo_name": "test-repo",
                "last_synced_at": None,
            },
        ]

        with (
            patch(
                "src.cron.jobs.sync_github_pr_reactions.get_github_token_for_tenant",
                return_value="test_token",
            ),
            patch(
                "src.cron.jobs.sync_github_pr_reactions.get_comments_needing_sync",
                return_value=comments,
            ),
            patch(
                "src.cron.jobs.sync_github_pr_reactions.fetch_batch_pr_reactions",
                return_value={50: {}},
            ) as mock_fetch,
            patch("src.cron.jobs.sync_github_pr_reactions.sync_reactions_for_comment"),
            patch("src.cron.jobs.sync_github_pr_reactions.asyncio.sleep"),
            patch("src.cron.jobs.sync_github_pr_reactions.logger") as mock_logger,
        ):
            await sync_github_pr_reactions()

            # Should only fetch once for the same PR, passing list with single PR
            assert mock_fetch.call_count == 1
            mock_fetch.assert_called_once_with("test-org", "test-repo", [50], "test_token")

            # Verify log shows syncing 1 PR
            info_calls = [call[0][0] for call in mock_logger.info.call_args_list]
            assert any("Syncing reactions for 1 PRs" in msg for msg in info_calls)

    @pytest.mark.asyncio
    async def test_job_partial_success(self):
        """Test job continues on partial errors."""
        comments = [
            {
                "id": "comment-1",
                "github_comment_id": 100,
                "github_review_id": 1000,
                "github_pr_number": 10,
                "github_repo_owner": "org1",
                "github_repo_name": "repo1",
                "last_synced_at": None,
            },
            {
                "id": "comment-2",
                "github_comment_id": 200,
                "github_review_id": 2000,
                "github_pr_number": 20,
                "github_repo_owner": "org2",
                "github_repo_name": "repo2",
                "last_synced_at": None,
            },
        ]

        async def mock_fetch_batch_reactions(owner, repo, pr_numbers, token):
            if owner == "org1":
                raise Exception("API error for org1/repo1")
            return {pr_num: {} for pr_num in pr_numbers}

        with (
            patch(
                "src.cron.jobs.sync_github_pr_reactions.get_github_token_for_tenant",
                return_value="test_token",
            ),
            patch(
                "src.cron.jobs.sync_github_pr_reactions.get_comments_needing_sync",
                return_value=comments,
            ),
            patch(
                "src.cron.jobs.sync_github_pr_reactions.fetch_batch_pr_reactions",
                side_effect=mock_fetch_batch_reactions,
            ),
            patch("src.cron.jobs.sync_github_pr_reactions.sync_reactions_for_comment") as mock_sync,
            patch("src.cron.jobs.sync_github_pr_reactions.asyncio.sleep"),
            patch("src.cron.jobs.sync_github_pr_reactions.logger") as mock_logger,
        ):
            await sync_github_pr_reactions()

            # Should sync 1 comment successfully (from org2/repo2)
            assert mock_sync.call_count == 1

            # Should log summary with partial success
            info_calls = [call[0][0] for call in mock_logger.info.call_args_list]
            assert any("1 comments synced, 1 PRs with errors" in msg for msg in info_calls)
