"""Tests for GitHub File Backfill Root extractor."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from connectors.github import GitHubFileBackfillRootExtractor
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient


class TestListRepositoryFiles:
    """Test the _list_repository_files method with real git repos."""

    @pytest.fixture
    def extractor(self):
        """Create extractor with mocked SSMClient."""
        mock_ssm = MagicMock(spec=SSMClient)
        mock_sqs = MagicMock(spec=SQSClient)
        return GitHubFileBackfillRootExtractor(mock_ssm, mock_sqs)

    def create_git_repo(self, tmp_path: Path, file_structure: dict[str, str]) -> Path:
        """
        Create a real git repository with the given file structure.

        Args:
            tmp_path: pytest tmp_path fixture
            file_structure: Dict mapping file paths to content
                           e.g., {"src/main.py": "print('hello')", ...}

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

        # Create files
        for file_path, content in file_structure.items():
            full_path = repo_path / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)

        # Commit all files
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        return repo_path

    @pytest.mark.asyncio
    async def test_list_valid_python_files(self, extractor, tmp_path):
        """Test listing valid Python files."""
        file_structure = {
            "src/main.py": "print('hello')",
            "src/utils/helper.py": "def help(): pass",
            "tests/test_main.py": "def test(): pass",
            "README.md": "# Project",
        }

        repo_path = self.create_git_repo(tmp_path, file_structure)
        result = await extractor._list_repository_files(repo_path)

        assert sorted(result) == sorted(
            ["src/main.py", "src/utils/helper.py", "tests/test_main.py", "README.md"]
        )

    @pytest.mark.asyncio
    async def test_filter_node_modules(self, extractor, tmp_path):
        """Test that node_modules directory is filtered."""
        file_structure = {
            "src/index.js": "console.log('app')",
            "node_modules/package/index.js": "// dependency",
            "node_modules/package/lib/util.js": "// more dependency",
            "package.json": "{}",
        }

        repo_path = self.create_git_repo(tmp_path, file_structure)
        result = await extractor._list_repository_files(repo_path)

        assert sorted(result) == ["package.json", "src/index.js"]
        assert not any("node_modules" in path for path in result)

    @pytest.mark.asyncio
    async def test_filter_pycache_and_pyc(self, extractor, tmp_path):
        """Test that __pycache__ and .pyc files are filtered."""
        file_structure = {
            "src/main.py": "print('hello')",
            "src/__pycache__/main.cpython-39.pyc": "binary",
            "src/utils/__pycache__/helper.cpython-39.pyc": "binary",
            "build/output.pyc": "binary",
            "dist/compiled.pyo": "binary",
        }

        repo_path = self.create_git_repo(tmp_path, file_structure)
        result = await extractor._list_repository_files(repo_path)

        assert result == ["src/main.py"]
        assert not any("__pycache__" in path for path in result)
        assert not any(path.endswith(".pyc") for path in result)
        assert not any(path.endswith(".pyo") for path in result)

    @pytest.mark.asyncio
    async def test_filter_venv_directories(self, extractor, tmp_path):
        """Test that venv/.venv directories are filtered."""
        file_structure = {
            "main.py": "import sys",
            "venv/lib/python3.9/site-packages/pkg.py": "# dependency",
            ".venv/bin/python": "#!/usr/bin/python",
            "requirements.txt": "requests==2.28.0",
        }

        repo_path = self.create_git_repo(tmp_path, file_structure)
        result = await extractor._list_repository_files(repo_path)

        assert sorted(result) == ["main.py", "requirements.txt"]
        assert not any("venv" in path for path in result)

    @pytest.mark.asyncio
    async def test_filter_dotfiles(self, extractor, tmp_path):
        """Test that .DS_Store, .env, .coverage are filtered."""
        file_structure = {
            "src/app.py": "app code",
            ".DS_Store": "mac metadata",
            "src/.DS_Store": "mac metadata",
            ".env": "SECRET=key",
            "config/.env": "CONFIG=value",
            ".coverage": "coverage data",
        }

        repo_path = self.create_git_repo(tmp_path, file_structure)
        result = await extractor._list_repository_files(repo_path)

        assert result == ["src/app.py"]
        assert not any(".DS_Store" in path for path in result)
        assert not any(".env" in path for path in result)
        assert not any(".coverage" in path for path in result)

    @pytest.mark.asyncio
    async def test_filter_build_and_dist(self, extractor, tmp_path):
        """Test that build/ and dist/ directories are filtered."""
        file_structure = {
            "src/main.py": "code",
            "build/output.js": "compiled",
            "dist/bundle.js": "bundled",
            "dist/index.html": "html",
        }

        repo_path = self.create_git_repo(tmp_path, file_structure)
        result = await extractor._list_repository_files(repo_path)

        assert result == ["src/main.py"]
        assert not any("build" in path for path in result)
        assert not any("dist" in path for path in result)

    @pytest.mark.asyncio
    async def test_filter_ide_directories(self, extractor, tmp_path):
        """Test that .idea, .vscode, etc. are filtered."""
        file_structure = {
            "src/main.py": "code",
            ".idea/workspace.xml": "intellij config",
            ".vscode/settings.json": "vscode config",
            ".github/workflows/ci.yml": "github actions",
        }

        repo_path = self.create_git_repo(tmp_path, file_structure)
        result = await extractor._list_repository_files(repo_path)

        assert result == ["src/main.py"]
        assert not any(".idea" in path for path in result)
        assert not any(".vscode" in path for path in result)
        assert not any(".github" in path for path in result)

    @pytest.mark.asyncio
    async def test_mixed_valid_and_filtered(self, extractor, tmp_path):
        """Test repository with mix of valid and filtered files."""
        file_structure = {
            "src/main.py": "valid",
            "src/test.pyc": "filtered",
            "lib/util.py": "valid",
            "node_modules/dep.js": "filtered",
            "README.md": "valid",
            ".DS_Store": "filtered",
            "tests/test_app.py": "valid",
            "build/output.js": "filtered",
        }

        repo_path = self.create_git_repo(tmp_path, file_structure)
        result = await extractor._list_repository_files(repo_path)

        expected = ["src/main.py", "lib/util.py", "README.md", "tests/test_app.py"]
        assert sorted(result) == sorted(expected)

    @pytest.mark.asyncio
    async def test_empty_repository(self, extractor, tmp_path):
        """Test empty repository returns empty list."""
        repo_path = tmp_path / "empty_repo"
        repo_path.mkdir()

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

        # Create empty commit
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "Empty"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        result = await extractor._list_repository_files(repo_path)
        assert result == []

    @pytest.mark.asyncio
    async def test_deeply_nested_paths(self, extractor, tmp_path):
        """Test deeply nested file paths work correctly."""
        file_structure = {
            "a/b/c/d/e/f/file.py": "deep file",
            "x/y/z/data.json": "data",
        }

        repo_path = self.create_git_repo(tmp_path, file_structure)
        result = await extractor._list_repository_files(repo_path)

        assert sorted(result) == sorted(["a/b/c/d/e/f/file.py", "x/y/z/data.json"])
