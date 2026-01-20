"""Tests for GitHub File Backfill extractor."""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from connectors.github import GitHubFileBackfillExtractor
from connectors.github.github_models import GitHubFileBatch
from src.clients.ssm import SSMClient


class TestGitHubFileBackfillNullBytes:
    """Test handling of files with null bytes."""

    @pytest.fixture
    def extractor(self):
        """Create extractor with mocked SSMClient."""
        mock_ssm = MagicMock(spec=SSMClient)
        return GitHubFileBackfillExtractor(mock_ssm)

    def create_git_repo_with_binary_file(self, tmp_path: Path) -> tuple[Path, str]:
        """
        Create a git repository with a text file containing null bytes.

        Args:
            tmp_path: pytest tmp_path fixture

        Returns:
            Path to the git repository
        """
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Create a normal text file
        normal_file = repo_path / "normal.txt"
        normal_file.write_text("This is a normal text file")

        # Create a binary file with .txt extension (contains null bytes)
        binary_file = repo_path / "binary.txt"
        binary_file.write_bytes(b"Hello\x00World\x00Binary\x00Data")

        # Create another normal file
        markdown_file = repo_path / "README.md"
        markdown_file.write_text("# Normal markdown")

        # Commit all files
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Get commit SHA
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
        )
        commit_sha = result.stdout.strip()

        return repo_path, commit_sha

    @pytest.mark.asyncio
    async def test_file_with_null_bytes_treated_as_binary(self, extractor, tmp_path):
        """Test that files with null bytes are treated as binary and generate metadata content."""
        # Create test repository
        repo_path, commit_sha = self.create_git_repo_with_binary_file(tmp_path)

        # Mock GitHub client
        mock_github_client = AsyncMock()
        mock_github_client.get_installation_token.return_value = "test_token"

        # Mock database pool with proper context manager
        mock_conn = AsyncMock()
        mock_conn.executemany = AsyncMock()

        mock_acquire = AsyncMock()
        mock_acquire.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire.__aexit__ = AsyncMock(return_value=None)

        mock_db_pool = AsyncMock()
        mock_db_pool.acquire = MagicMock(return_value=mock_acquire)

        # Create file batch config
        file_batch = GitHubFileBatch(
            org_or_owner="test-org",
            repo_name="test-repo",
            branch="main",
            commit_sha=commit_sha,
            file_paths=["normal.txt", "binary.txt", "README.md"],
        )

        # Mock clone_repository to return our test repo
        with (
            patch(
                "connectors.github.github_file_backfill_extractor.clone_repository"
            ) as mock_clone,
            patch(
                "connectors.github.github_file_backfill_extractor.get_github_client_for_tenant"
            ) as mock_get_client,
        ):
            from connectors.github.github_repo_utils import CloneResult

            mock_clone.return_value = CloneResult(
                repo_path=repo_path, commit_sha=commit_sha, branch="main"
            )
            mock_get_client.return_value = mock_github_client

            # Create temporary directory for the extractor
            with tempfile.TemporaryDirectory() as temp_dir:
                extractor.temp_dir = temp_dir

                # Process the batch
                entity_ids = await extractor._process_file_batch(
                    job_id=str(uuid4()),
                    github_client=mock_github_client,
                    file_batch=file_batch,
                    db_pool=mock_db_pool,
                )

        # Verify results
        assert len(entity_ids) == 3, "Should process all three files"

        # Check that executemany was called to store artifacts
        assert mock_conn.executemany.called, "Should have called executemany"

        # Get the call args
        call_args = mock_conn.executemany.call_args
        artifacts_data = call_args[0][1]  # Second positional argument is the data rows
        assert len(artifacts_data) == 3, "Should store 3 artifacts"

        # Find the binary.txt and normal.txt artifacts
        import json

        binary_artifact = None
        normal_artifact = None
        for artifact_row in artifacts_data:
            # artifact_row is a tuple: (id, entity, entity_id, job_id, metadata, content, updated_at)
            content_json = artifact_row[5]  # content is the 6th element (index 5)
            content_dict = json.loads(content_json)
            file_path = content_dict.get("path", "")

            if file_path == "binary.txt":
                binary_artifact = content_dict
            elif file_path == "normal.txt":
                normal_artifact = content_dict

        assert binary_artifact is not None, "Should have artifact for binary.txt"
        assert normal_artifact is not None, "Should have artifact for normal.txt"

        # Verify binary.txt was treated as binary (metadata-only content)
        binary_content = binary_artifact.get("content", "")
        assert "Note: This is a non-text file" in binary_content, (
            "Binary file should have metadata-only content"
        )
        assert "binary.txt" in binary_content, "Should mention file name"
        assert "test-org/test-repo" in binary_content, "Should mention repository"

        # Verify normal.txt has actual text content
        normal_content = normal_artifact.get("content", "")
        assert normal_content == "This is a normal text file", (
            "Normal file should have actual text content"
        )
