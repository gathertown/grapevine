"""Tests for Slack export ZIP file validation.

This module tests the validation logic in SlackExportBackfillRootExtractor
to ensure malicious or invalid ZIP files are rejected while valid exports
are accepted.
"""

import tempfile
import zipfile
from collections.abc import Generator
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from connectors.slack.slack_export_backfill_root_extractor import (
    MAX_FILE_SIZE,
    SlackExportBackfillRootExtractor,
)


def _create_mock_extractor() -> SlackExportBackfillRootExtractor:
    """Create an extractor instance with mocked clients for testing validation methods."""
    return SlackExportBackfillRootExtractor(
        ssm_client=cast(Any, MagicMock()),
        sqs_client=cast(Any, MagicMock()),
    )


class TestSlackExportValidation:
    """Test suite for Slack export ZIP validation."""

    @pytest.fixture
    def extractor(self) -> SlackExportBackfillRootExtractor:
        """Create an extractor instance for testing validation methods."""
        return _create_mock_extractor()

    @pytest.fixture
    def temp_dir(self) -> Generator[Path]:
        """Create a temporary directory for validation tests."""
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)

    @pytest.fixture
    def valid_slack_export_zip(self, tmp_path: Path) -> Path:
        """Create a valid Slack export ZIP file."""
        export_dir = tmp_path / "valid_export"
        export_dir.mkdir()

        channels_json = export_dir / "channels.json"
        channels_json.write_text('[{"id": "C123456", "name": "general", "created": 1609459200}]')

        users_json = export_dir / "users.json"
        users_json.write_text('[{"id": "U123", "team_id": "T123", "name": "testuser"}]')

        general_dir = export_dir / "general"
        general_dir.mkdir()
        message_file = general_dir / "2024-01-01.json"
        message_file.write_text(
            '[{"type": "message", "client_msg_id": "msg1", "user": "U123", '
            '"text": "Hello", "ts": "1704067200.000000"}]'
        )

        zip_path = tmp_path / "valid_export.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for file_path in export_dir.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(export_dir)
                    zf.write(file_path, arcname)

        return zip_path

    @pytest.fixture
    def nested_slack_export_zip(self, tmp_path: Path) -> Path:
        """Create a Slack export ZIP with nested directory structure."""
        export_dir = tmp_path / "nested_export" / "slack_export"
        export_dir.mkdir(parents=True)

        channels_json = export_dir / "channels.json"
        channels_json.write_text('[{"id": "C123456", "name": "general", "created": 1609459200}]')

        users_json = export_dir / "users.json"
        users_json.write_text('[{"id": "U123", "team_id": "T123", "name": "testuser"}]')

        zip_path = tmp_path / "nested_export.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for file_path in (tmp_path / "nested_export").rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(tmp_path / "nested_export")
                    zf.write(file_path, arcname)

        return zip_path

    @pytest.fixture
    def path_traversal_zip(self, tmp_path: Path) -> Path:
        """Create a ZIP file with path traversal attempts."""
        zip_path = tmp_path / "path_traversal.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("channels.json", '[{"id": "C123"}]')
            zf.writestr("users.json", '[{"id": "U123"}]')
            zf.writestr("../../../etc/passwd", "malicious content")
            zf.writestr("../../malicious.txt", "another malicious file")
            zf.writestr("general/../../../tmp/evil.txt", "evil content")

        return zip_path

    @pytest.fixture
    def missing_channels_zip(self, tmp_path: Path) -> Path:
        """Create a ZIP file missing channels.json."""
        zip_path = tmp_path / "missing_channels.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("users.json", '[{"id": "U123", "team_id": "T123"}]')
            zf.writestr("general/2024-01-01.json", '[{"type": "message"}]')

        return zip_path

    @pytest.fixture
    def empty_zip(self, tmp_path: Path) -> Path:
        """Create an empty ZIP file."""
        zip_path = tmp_path / "empty.zip"
        with zipfile.ZipFile(zip_path, "w"):
            pass
        return zip_path

    @pytest.fixture
    def compression_bomb_zip(self, tmp_path: Path) -> Path:
        """Create a ZIP file with suspicious compression ratio (>100x)."""
        zip_path = tmp_path / "compression_bomb.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("channels.json", '[{"id": "C123"}]')
            zf.writestr("users.json", '[{"id": "U123"}]')
            zf.writestr("bomb.txt", "0" * (10 * 1024 * 1024))

        return zip_path

    @pytest.fixture
    def macos_metadata_zip(self, tmp_path: Path) -> Path:
        """Create a ZIP file with macOS metadata files."""
        zip_path = tmp_path / "macos_metadata.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("channels.json", '[{"id": "C123"}]')
            zf.writestr("users.json", '[{"id": "U123"}]')
            zf.writestr("__MACOSX/._channels.json", "macos metadata")
            zf.writestr("__MACOSX/general/._2024-01-01.json", "more metadata")
            zf.writestr("._hidden_file", "hidden file content")

        return zip_path


class TestPathSafety:
    """Tests for path traversal protection."""

    @pytest.fixture
    def extractor(self) -> SlackExportBackfillRootExtractor:
        return _create_mock_extractor()

    def test_safe_path_accepted(self, extractor: SlackExportBackfillRootExtractor):
        """Test that normal paths within base directory are accepted."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            safe_paths = [
                "channels.json",
                "users.json",
                "general/2024-01-01.json",
                "folder/subfolder/file.json",
            ]
            for path in safe_paths:
                assert extractor._is_safe_path(path, base_dir) is True

    def test_path_traversal_rejected(self, extractor: SlackExportBackfillRootExtractor):
        """Test that path traversal attempts are rejected."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            malicious_paths = [
                "../../../etc/passwd",
                "../../malicious.txt",
                "folder/../../../tmp/evil.txt",
                "../secret.json",
            ]
            for path in malicious_paths:
                assert extractor._is_safe_path(path, base_dir) is False

    def test_absolute_path_rejected(self, extractor: SlackExportBackfillRootExtractor):
        """Test that absolute paths are handled correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            assert extractor._is_safe_path("/etc/passwd", base_dir) is False


class TestZipEntrySafety:
    """Tests for ZIP entry validation."""

    @pytest.fixture
    def extractor(self) -> SlackExportBackfillRootExtractor:
        return _create_mock_extractor()

    def test_normal_file_accepted(
        self, extractor: SlackExportBackfillRootExtractor, tmp_path: Path
    ):
        """Test that normal files are accepted."""
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("channels.json", '[{"id": "C123"}]')

        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                assert extractor._check_zip_entry_looks_safe(info, tmp_path) is True

    def test_directory_entry_accepted(
        self, extractor: SlackExportBackfillRootExtractor, tmp_path: Path
    ):
        """Test that directory entries are accepted."""
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("general/", "")

        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    assert extractor._check_zip_entry_looks_safe(info, tmp_path) is True

    def test_path_traversal_entry_rejected(
        self, extractor: SlackExportBackfillRootExtractor, tmp_path: Path
    ):
        """Test that ZIP entries with path traversal are rejected."""
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("../../../etc/passwd", "malicious")

        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                if "../" in info.filename:
                    assert extractor._check_zip_entry_looks_safe(info, tmp_path) is False

    def test_compression_bomb_rejected(
        self, extractor: SlackExportBackfillRootExtractor, tmp_path: Path
    ):
        """Test that files with suspicious compression ratio (>100x) are rejected."""
        zip_path = tmp_path / "bomb.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("bomb.txt", "0" * (10 * 1024 * 1024))

        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                if info.filename == "bomb.txt":
                    ratio = info.file_size / info.compress_size
                    assert ratio > 100
                    assert extractor._check_zip_entry_looks_safe(info, tmp_path) is False


class TestMacOSMetadata:
    """Tests for macOS metadata file handling."""

    @pytest.fixture
    def extractor(self) -> SlackExportBackfillRootExtractor:
        return _create_mock_extractor()

    def test_macosx_directory_skipped(self, extractor: SlackExportBackfillRootExtractor):
        """Test that __MACOSX/ directories are identified for skipping."""
        macos_paths = [
            "__MACOSX/",
            "__MACOSX/._channels.json",
            "__MACOSX/general/._file.json",
        ]
        for path in macos_paths:
            assert extractor._should_skip_macos_metadata(path) is True

    def test_nested_macosx_skipped(self, extractor: SlackExportBackfillRootExtractor):
        """Test that nested __MACOSX/ directories are identified for skipping."""
        nested_paths = [
            "export/__MACOSX/file.txt",
            "folder/__MACOSX/._hidden",
        ]
        for path in nested_paths:
            assert extractor._should_skip_macos_metadata(path) is True

    def test_apple_double_files_skipped(self, extractor: SlackExportBackfillRootExtractor):
        """Test that AppleDouble format files (._) are identified for skipping."""
        apple_double_paths = [
            "._hidden_file",
            "folder/._another_hidden",
            "/._root_hidden",
        ]
        for path in apple_double_paths:
            assert extractor._should_skip_macos_metadata(path) is True

    def test_normal_files_not_skipped(self, extractor: SlackExportBackfillRootExtractor):
        """Test that normal files are not incorrectly identified as macOS metadata."""
        normal_paths = [
            "channels.json",
            "users.json",
            "general/2024-01-01.json",
            "MACOSX_file.txt",
            "file._extension",
        ]
        for path in normal_paths:
            assert extractor._should_skip_macos_metadata(path) is False


class TestNestedDirectoryDetection:
    """Tests for nested directory structure detection."""

    @pytest.fixture
    def extractor(self) -> SlackExportBackfillRootExtractor:
        return _create_mock_extractor()

    @pytest.mark.asyncio
    async def test_root_level_structure_detected(
        self, extractor: SlackExportBackfillRootExtractor, tmp_path: Path
    ):
        """Test that root-level Slack export structure is detected."""
        zip_path = tmp_path / "root_level.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("channels.json", '[{"id": "C123"}]')
            zf.writestr("users.json", '[{"id": "U123"}]')

        base_dir = await extractor._detect_base_directory(zip_path)
        assert base_dir == ""

    @pytest.mark.asyncio
    async def test_nested_structure_detected(
        self, extractor: SlackExportBackfillRootExtractor, tmp_path: Path
    ):
        """Test that nested Slack export structure is detected."""
        zip_path = tmp_path / "nested.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("slack_export/channels.json", '[{"id": "C123"}]')
            zf.writestr("slack_export/users.json", '[{"id": "U123"}]')

        base_dir = await extractor._detect_base_directory(zip_path)
        assert base_dir == "slack_export/"

    @pytest.mark.asyncio
    async def test_deeply_nested_structure_detected(
        self, extractor: SlackExportBackfillRootExtractor, tmp_path: Path
    ):
        """Test that deeply nested Slack export structure is detected."""
        zip_path = tmp_path / "deep_nested.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("export/2024/slack_export/channels.json", '[{"id": "C123"}]')
            zf.writestr("export/2024/slack_export/users.json", '[{"id": "U123"}]')

        base_dir = await extractor._detect_base_directory(zip_path)
        assert base_dir == "export/2024/slack_export/"

    @pytest.mark.asyncio
    async def test_missing_channels_raises_error(
        self, extractor: SlackExportBackfillRootExtractor, tmp_path: Path
    ):
        """Test that missing channels.json raises ValueError."""
        zip_path = tmp_path / "no_channels.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("users.json", '[{"id": "U123"}]')

        with pytest.raises(ValueError, match="channels.json not found"):
            await extractor._detect_base_directory(zip_path)

    @pytest.mark.asyncio
    async def test_empty_zip_raises_error(
        self, extractor: SlackExportBackfillRootExtractor, tmp_path: Path
    ):
        """Test that empty ZIP raises ValueError."""
        zip_path = tmp_path / "empty.zip"
        with zipfile.ZipFile(zip_path, "w"):
            pass

        with pytest.raises(ValueError, match="ZIP file is empty"):
            await extractor._detect_base_directory(zip_path)

    @pytest.mark.asyncio
    async def test_macos_metadata_ignored_in_detection(
        self, extractor: SlackExportBackfillRootExtractor, tmp_path: Path
    ):
        """Test that macOS metadata is ignored when detecting base directory."""
        zip_path = tmp_path / "macos.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("__MACOSX/._channels.json", "metadata")
            zf.writestr("channels.json", '[{"id": "C123"}]')
            zf.writestr("users.json", '[{"id": "U123"}]')

        base_dir = await extractor._detect_base_directory(zip_path)
        assert base_dir == ""


class TestFileSizeLimits:
    """Tests for file size limit enforcement."""

    @pytest.fixture
    def extractor(self) -> SlackExportBackfillRootExtractor:
        return _create_mock_extractor()

    def test_max_file_size_constant(self):
        """Test that MAX_FILE_SIZE is set to 1GB."""
        assert MAX_FILE_SIZE == 1 * 1024 * 1024 * 1024

    def test_small_file_accepted(self, extractor: SlackExportBackfillRootExtractor, tmp_path: Path):
        """Test that small files are accepted."""
        zip_path = tmp_path / "small.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("small.json", '{"data": "small"}')

        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                assert info.file_size < MAX_FILE_SIZE
                assert extractor._check_zip_entry_looks_safe(info, tmp_path) is True
