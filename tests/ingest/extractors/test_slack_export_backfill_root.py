import contextlib
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from connectors.slack import SlackExportBackfillRootExtractor
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient


class TestSlackExportBackfillRootZipDetection:
    """Test the ZIP directory structure detection logic."""

    @pytest.fixture
    def extractor(self):
        """Create extractor with mocked SSMClient."""
        mock_ssm = MagicMock(spec=SSMClient)
        mock_sqs = MagicMock(spec=SQSClient)
        return SlackExportBackfillRootExtractor(mock_ssm, mock_sqs)

    def create_zip_with_structure(self, file_structure: dict) -> bytes:
        """
        Create an in-memory ZIP file with the given structure.

        Args:
            file_structure: Dict mapping file paths to content
                           e.g., {"channels.json": {...}, "general/2024-01-01.json": [...]}

        Returns:
            Bytes of the ZIP file
        """
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for file_path, content in file_structure.items():
                if isinstance(content, (dict, list)):
                    content = json.dumps(content)
                elif content is None:
                    content = ""

                # Add file to ZIP
                zip_file.writestr(file_path, content)

        return zip_buffer.getvalue()

    @pytest.mark.asyncio
    async def test_standard_zip_structure(self, extractor, tmp_path):
        """Test ZIP with files at root level (standard Slack export)."""
        file_structure = {
            "channels.json": [{"id": "C123", "name": "general"}],
            "users.json": [{"id": "U123", "name": "Test User"}],
            "general/2024-01-01.json": [{"type": "message", "text": "Hello"}],
            "random/2024-01-01.json": [{"type": "message", "text": "World"}],
        }

        zip_bytes = self.create_zip_with_structure(file_structure)
        zip_path = tmp_path / "test_export.zip"
        zip_path.write_bytes(zip_bytes)

        base_dir = await extractor._detect_base_directory(zip_path)
        assert base_dir == "", (
            f"Expected empty base directory for standard structure, got '{base_dir}'"
        )

    @pytest.mark.asyncio
    async def test_nested_single_directory(self, extractor, tmp_path):
        """Test ZIP where all contents are in a single directory (common user error)."""
        file_structure = {
            "slack_export/": None,  # Directory entry
            "slack_export/channels.json": [{"id": "C123", "name": "general"}],
            "slack_export/users.json": [{"id": "U123", "name": "Test User"}],
            "slack_export/general/2024-01-01.json": [{"type": "message", "text": "Hello"}],
        }

        zip_bytes = self.create_zip_with_structure(file_structure)
        zip_path = tmp_path / "test_export.zip"
        zip_path.write_bytes(zip_bytes)

        base_dir = await extractor._detect_base_directory(zip_path)
        assert base_dir == "slack_export/", (
            f"Expected 'slack_export/' base directory, got '{base_dir}'"
        )

    @pytest.mark.asyncio
    async def test_mixed_structure_with_root_files(self, extractor, tmp_path):
        """Test ZIP with both files and directories at root level."""
        file_structure = {
            "README.txt": "This is a Slack export",
            "channels.json": [{"id": "C123", "name": "general"}],
            "users.json": [{"id": "U123", "name": "Test User"}],
            "general/2024-01-01.json": [{"type": "message", "text": "Hello"}],
        }

        zip_bytes = self.create_zip_with_structure(file_structure)
        zip_path = tmp_path / "test_export.zip"
        zip_path.write_bytes(zip_bytes)

        base_dir = await extractor._detect_base_directory(zip_path)
        # Should use root level when there are files at root
        assert base_dir == "", (
            f"Expected empty base directory for mixed structure, got '{base_dir}'"
        )

    @pytest.mark.asyncio
    async def test_multiple_root_directories(self, extractor, tmp_path):
        """Test ZIP with multiple directories at root level."""
        file_structure = {
            "export1/": None,
            "export1/channels.json": [{"id": "C123", "name": "general"}],
            "export2/": None,
            "export2/data.json": {"some": "data"},
        }

        zip_bytes = self.create_zip_with_structure(file_structure)
        zip_path = tmp_path / "test_export.zip"
        zip_path.write_bytes(zip_bytes)

        base_dir = await extractor._detect_base_directory(zip_path)
        # Should find channels.json via fallback
        assert base_dir == "export1/", (
            f"Expected 'export1/' after finding channels.json, got '{base_dir}'"
        )

    @pytest.mark.asyncio
    async def test_deeply_nested_channels_json(self, extractor, tmp_path):
        """Test ZIP where channels.json is deeply nested."""
        file_structure = {
            "exports/": None,
            "exports/slack/": None,
            "exports/slack/channels.json": [{"id": "C123", "name": "general"}],
            "exports/slack/users.json": [{"id": "U123", "name": "Test User"}],
            "exports/slack/general/2024-01-01.json": [{"type": "message", "text": "Hello"}],
        }

        zip_bytes = self.create_zip_with_structure(file_structure)
        zip_path = tmp_path / "test_export.zip"
        zip_path.write_bytes(zip_bytes)

        base_dir = await extractor._detect_base_directory(zip_path)
        # Should find channels.json and use its parent directory
        assert base_dir == "exports/slack/", (
            f"Expected 'exports/slack/' base directory, got '{base_dir}'"
        )

    @pytest.mark.asyncio
    async def test_empty_zip_file(self, extractor, tmp_path):
        """Test that empty ZIP file raises an appropriate error."""
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED):
            pass  # Create empty ZIP

        zip_path = tmp_path / "empty.zip"
        zip_path.write_bytes(zip_buffer.getvalue())

        with pytest.raises(ValueError, match="ZIP file is empty"):
            await extractor._detect_base_directory(zip_path)

    @pytest.mark.asyncio
    async def test_no_channels_json_error(self, extractor, tmp_path):
        """Test ZIP without channels.json - should raise an error."""
        file_structure = {
            "data/": None,
            "data/users.json": [{"id": "U123", "name": "Test User"}],
            "data/general/2024-01-01.json": [{"type": "message", "text": "Hello"}],
        }

        zip_bytes = self.create_zip_with_structure(file_structure)
        zip_path = tmp_path / "test_export.zip"
        zip_path.write_bytes(zip_bytes)

        with pytest.raises(ValueError, match="channels.json not found in Slack export ZIP file"):
            await extractor._detect_base_directory(zip_path)

    @pytest.mark.asyncio
    async def test_case_sensitive_channels_json(self, extractor, tmp_path):
        """Test that channels.json detection is case-sensitive."""
        file_structure = {
            "Channels.JSON": [{"id": "C123", "name": "general"}],  # Wrong case
            "slack/channels.json": [
                {"id": "C456", "name": "random"}
            ],  # Correct case in subdirectory
        }

        zip_bytes = self.create_zip_with_structure(file_structure)
        zip_path = tmp_path / "test_export.zip"
        zip_path.write_bytes(zip_bytes)

        base_dir = await extractor._detect_base_directory(zip_path)
        # Should find the correctly cased channels.json in subdirectory
        assert base_dir == "slack/", f"Expected 'slack/' base directory, got '{base_dir}'"

    @pytest.mark.asyncio
    async def test_windows_style_paths(self, extractor, tmp_path):
        """Test that the detection works even if ZIP was created on Windows."""
        # Note: ZIP standard always uses forward slashes, but test just in case
        file_structure = {
            "export/channels.json": [{"id": "C123", "name": "general"}],
            "export/users.json": [{"id": "U123", "name": "Test User"}],
            "export/general/2024-01-01.json": [{"type": "message", "text": "Hello"}],
        }

        zip_bytes = self.create_zip_with_structure(file_structure)
        zip_path = tmp_path / "test_export.zip"
        zip_path.write_bytes(zip_bytes)

        base_dir = await extractor._detect_base_directory(zip_path)
        assert base_dir == "export/", f"Expected 'export/' base directory, got '{base_dir}'"

    @pytest.mark.asyncio
    async def test_macos_metadata_files(self, extractor, tmp_path):
        """Test that __MACOSX metadata files are properly ignored."""
        file_structure = {
            # The actual Slack export in a nested folder
            "Slack export Sep 10 2025 - Sep 17 2025/": None,
            "Slack export Sep 10 2025 - Sep 17 2025/channels.json": [
                {"id": "C123", "name": "general"}
            ],
            "Slack export Sep 10 2025 - Sep 17 2025/users.json": [
                {"id": "U123", "name": "Test User"}
            ],
            "Slack export Sep 10 2025 - Sep 17 2025/general/2025-09-11.json": [
                {"type": "message", "text": "Hello"}
            ],
            # macOS metadata files
            "__MACOSX/": None,
            "__MACOSX/Slack export Sep 10 2025 - Sep 17 2025/": None,
            "__MACOSX/Slack export Sep 10 2025 - Sep 17 2025/._channels.json": b"\x00\x05\x16\x07",  # Binary metadata
            "__MACOSX/Slack export Sep 10 2025 - Sep 17 2025/._users.json": b"\x00\x05\x16\x07",
            "__MACOSX/Slack export Sep 10 2025 - Sep 17 2025/general/._2025-09-11.json": b"\x00\x05\x16\x07",
        }

        zip_bytes = self.create_zip_with_structure(file_structure)
        zip_path = tmp_path / "test_export.zip"
        zip_path.write_bytes(zip_bytes)

        # Should detect the Slack export directory by finding the real channels.json
        # (macOS metadata files don't interfere because they don't end with "channels.json")
        base_dir = await extractor._detect_base_directory(zip_path)
        assert base_dir == "Slack export Sep 10 2025 - Sep 17 2025/", (
            f"Expected 'Slack export Sep 10 2025 - Sep 17 2025/' base directory, got '{base_dir}'"
        )

    @pytest.mark.asyncio
    async def test_macos_metadata_with_standard_structure(self, extractor, tmp_path):
        """Test standard structure with __MACOSX metadata at root level."""
        file_structure = {
            # Standard Slack export at root
            "channels.json": [{"id": "C123", "name": "general"}, {"id": "C456", "name": "random"}],
            "users.json": [{"id": "U123", "name": "Test User"}],
            "general/2025-09-11.json": [{"type": "message", "text": "Hello"}],
            "random/2025-09-12.json": [{"type": "message", "text": "World"}],
            # macOS metadata
            "__MACOSX/": None,
            "__MACOSX/._channels.json": b"\x00\x05\x16\x07",
            "__MACOSX/._users.json": b"\x00\x05\x16\x07",
            "__MACOSX/general/._2025-09-11.json": b"\x00\x05\x16\x07",
            "__MACOSX/random/._2025-09-12.json": b"\x00\x05\x16\x07",
        }

        zip_bytes = self.create_zip_with_structure(file_structure)
        zip_path = tmp_path / "test_export.zip"
        zip_path.write_bytes(zip_bytes)

        # Should detect standard structure by finding channels.json at root
        # (macOS metadata files don't interfere because they don't end with "channels.json")
        base_dir = await extractor._detect_base_directory(zip_path)
        assert base_dir == "", (
            f"Expected empty base directory for standard structure, got '{base_dir}'"
        )

    @pytest.mark.asyncio
    async def test_prefixed_channels_json_ignored(self, extractor, tmp_path):
        """Test that files with channels.json as suffix but not exact match are ignored."""
        file_structure = {
            "backup_channels.json": [{"id": "C123", "name": "backup"}],  # Should be ignored
            "old_channels.json": [{"id": "C456", "name": "old"}],  # Should be ignored
            "export/channels.json": [{"id": "C789", "name": "general"}],  # Should be found
            "export/users.json": [{"id": "U123", "name": "Test User"}],
            "export/general/2024-01-01.json": [{"type": "message", "text": "Hello"}],
        }

        zip_bytes = self.create_zip_with_structure(file_structure)
        zip_path = tmp_path / "test_export.zip"
        zip_path.write_bytes(zip_bytes)

        base_dir = await extractor._detect_base_directory(zip_path)
        # Should find the real channels.json in export/ directory, not the prefixed ones
        assert base_dir == "export/", f"Expected 'export/' base directory, got '{base_dir}'"

    @pytest.mark.asyncio
    async def test_multiple_channels_json_first_wins(self, extractor, tmp_path):
        """Test that when multiple valid channels.json exist, the first one found is used."""
        file_structure = {
            "channels.json": [{"id": "C123", "name": "root"}],  # Should be found first
            "backup/channels.json": [{"id": "C456", "name": "backup"}],  # Should be ignored
            "users.json": [{"id": "U123", "name": "Test User"}],
            "general/2024-01-01.json": [{"type": "message", "text": "Hello"}],
        }

        zip_bytes = self.create_zip_with_structure(file_structure)
        zip_path = tmp_path / "test_export.zip"
        zip_path.write_bytes(zip_bytes)

        base_dir = await extractor._detect_base_directory(zip_path)
        # Should find the root channels.json first
        assert base_dir == "", (
            f"Expected empty base directory for root channels.json, got '{base_dir}'"
        )


class TestSlackExportSecurityValidation:
    """Test security validation for dangerous ZIP file scenarios."""

    @pytest.fixture
    def extractor(self):
        """Create extractor with mocked SSMClient."""
        mock_ssm = MagicMock(spec=SSMClient)
        mock_sqs = MagicMock(spec=SQSClient)
        return SlackExportBackfillRootExtractor(mock_ssm, mock_sqs)

    def create_zip_with_structure(self, file_structure: dict, zip_path: Path) -> None:
        """
        Create a ZIP file with the given structure on disk.

        Args:
            file_structure: Dict mapping file paths to content
            zip_path: Path where to write the ZIP file
        """
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for file_path, content in file_structure.items():
                if isinstance(content, (dict, list)):
                    content = json.dumps(content)
                elif content is None:
                    content = ""
                elif isinstance(content, bytes):
                    pass  # Keep binary content as-is
                else:
                    content = str(content)

                # Add file to ZIP with proper encoding
                if isinstance(content, bytes):
                    zip_file.writestr(file_path, content)
                else:
                    zip_file.writestr(file_path, content.encode("utf-8"))

    def create_zip_with_symlink(self, zip_path: Path) -> None:
        """Create a ZIP file containing symbolic links."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create normal files
            channels_file = tmppath / "channels.json"
            channels_file.write_text(json.dumps([{"id": "C123", "name": "general"}]))

            users_file = tmppath / "users.json"
            users_file.write_text(
                json.dumps([{"id": "U123", "name": "Test User", "team_id": "T123"}])
            )

            # Create a symlink pointing to /etc/passwd
            evil_link = tmppath / "evil_link"
            evil_link.symlink_to("/etc/passwd")

            # Create a symlink in a channel directory
            channel_dir = tmppath / "general"
            channel_dir.mkdir()
            channel_link = channel_dir / "2024-01-01.json"
            channel_link.symlink_to("/etc/shadow")

            # Create ZIP preserving symlinks (using external zip command)
            # Note: Python's zipfile doesn't easily preserve symlinks
            os.system(
                f"cd {tmpdir} && zip -y {zip_path} channels.json users.json evil_link general/2024-01-01.json 2>/dev/null"
            )

    @pytest.mark.asyncio
    async def test_path_traversal_in_channels_json(self, extractor, tmp_path):
        """Test that path traversal in channels.json path is rejected."""
        file_structure = {
            "../../../etc/channels.json": [{"id": "C123", "name": "evil"}],
            "users.json": [{"id": "U123", "name": "Test", "team_id": "T123"}],
        }

        zip_path = tmp_path / "traversal.zip"
        self.create_zip_with_structure(file_structure, zip_path)

        # Should raise error because channels.json is in unsafe location
        with pytest.raises(ValueError, match="channels.json not found"):
            await extractor._detect_base_directory(zip_path)

    @pytest.mark.asyncio
    async def test_path_traversal_in_channel_files(self, extractor, tmp_path):
        """Test that path traversal in channel day files is rejected."""
        file_structure = {
            "channels.json": [{"id": "C123", "name": "general"}],
            "users.json": [{"id": "U123", "name": "Test", "team_id": "T123"}],
            "general/../../../etc/passwd": "evil content",
            "general/2024-01-01.json": [{"type": "message", "text": "normal"}],
        }

        zip_path = tmp_path / "traversal_channel.zip"
        self.create_zip_with_structure(file_structure, zip_path)

        # Load channels data first
        extractor._base_directory = ""
        await extractor._load_channels_data(zip_path)

        # Analyze channel files - should skip the traversal attempt
        channel_files = await extractor._analyze_channel_day_files(zip_path)

        # Should only find the safe file
        assert len(channel_files) == 1
        assert channel_files[0].filename == "2024-01-01.json"

    @pytest.mark.asyncio
    async def test_absolute_path_in_zip(self, extractor, tmp_path):
        """Test that absolute paths in ZIP are rejected."""
        # Create a ZIP with absolute paths using ZipInfo
        zip_path = tmp_path / "absolute.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            # Normal files
            zf.writestr("channels.json", json.dumps([{"id": "C123", "name": "general"}]))
            zf.writestr(
                "users.json", json.dumps([{"id": "U123", "name": "Test", "team_id": "T123"}])
            )

            # File with absolute path
            info = zipfile.ZipInfo(filename="/etc/evil.conf")
            zf.writestr(info, "evil config")

            # Another absolute path attempt
            info2 = zipfile.ZipInfo(filename="/tmp/extracted.txt")
            zf.writestr(info2, "should not extract")

        # Should still find base directory (ignoring absolute paths)
        base_dir = await extractor._detect_base_directory(zip_path)
        assert base_dir == ""

        # Load channels and analyze - absolute paths should be skipped
        extractor._base_directory = base_dir
        await extractor._load_channels_data(zip_path)
        channel_files = await extractor._analyze_channel_day_files(zip_path)

        # Should find no channel files (absolute paths were skipped)
        assert len(channel_files) == 0

    @pytest.mark.asyncio
    async def test_large_file_rejection(self, extractor, tmp_path):
        """Test that files exceeding MAX_FILE_SIZE are rejected."""
        # Create a large file (just over the limit for testing)
        # We'll mock MAX_FILE_SIZE to a smaller value for testing
        with patch(
            "connectors.slack.slack_export_backfill_root_extractor.MAX_FILE_SIZE", 1024
        ):  # 1KB for testing
            file_structure = {
                "channels.json": [{"id": "C123", "name": "general"}],
                "users.json": [{"id": "U123", "name": "Test", "team_id": "T123"}],
                "general/huge.json": "X" * 2000,  # 2KB, exceeds our test limit
                "general/normal.json": [{"type": "message", "text": "normal"}],
            }

            zip_path = tmp_path / "large_file.zip"
            self.create_zip_with_structure(file_structure, zip_path)

            # Set up extractor
            extractor._base_directory = ""
            await extractor._load_channels_data(zip_path)

            # Analyze should skip the large file
            channel_files = await extractor._analyze_channel_day_files(zip_path)

            # Should only find the normal file
            assert len(channel_files) == 1
            assert channel_files[0].filename == "normal.json"

    @pytest.mark.asyncio
    async def test_compression_bomb_detection(self, extractor, tmp_path):
        """Test that files with suspicious compression ratios are rejected."""
        # Create a highly compressible file (potential zip bomb indicator)
        zip_path = tmp_path / "compression_bomb.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            # Normal files
            zf.writestr("channels.json", json.dumps([{"id": "C123", "name": "general"}]))
            zf.writestr(
                "users.json", json.dumps([{"id": "U123", "name": "Test", "team_id": "T123"}])
            )

            # Create a highly compressible file (10MB of zeros)
            huge_data = "0" * (10 * 1024 * 1024)  # 10MB of zeros
            info = zipfile.ZipInfo("general/suspicious.json")
            zf.writestr(info, huge_data, compress_type=zipfile.ZIP_DEFLATED)

            # Normal file
            zf.writestr("general/normal.json", json.dumps([{"type": "message", "text": "normal"}]))

        # Set up extractor
        extractor._base_directory = ""
        await extractor._load_channels_data(zip_path)

        # Analyze should detect high compression ratio and skip
        with patch("connectors.slack.slack_export_backfill_root_extractor.logger") as mock_logger:
            channel_files = await extractor._analyze_channel_day_files(zip_path)

            # Check that error was logged for suspicious compression
            errors = [
                call
                for call in mock_logger.error.call_args_list
                if "compression ratio" in str(call)
            ]
            assert len(errors) > 0, "Should have logged compression ratio error"

        # Should only find the normal file
        assert len(channel_files) == 1
        assert channel_files[0].filename == "normal.json"

    @pytest.mark.asyncio
    async def test_symlink_in_zip(self, extractor, tmp_path):
        """Test that symbolic links in ZIP are handled safely."""
        zip_path = tmp_path / "symlink.zip"

        # Only run this test if we can create symlinks (Unix-like systems)
        if os.name == "nt":  # Windows
            pytest.skip("Symlink test requires Unix-like system")

        # Create ZIP with symlinks
        self.create_zip_with_symlink(zip_path)

        # If the ZIP was created successfully with symlinks
        if zip_path.exists():
            extractor._base_directory = ""
            await extractor._load_channels_data(zip_path)

            # Analyze should process files safely
            channel_files = await extractor._analyze_channel_day_files(zip_path)

            # The symlink in general/ directory might be read as regular file
            # (our code reads content, doesn't follow symlinks)
            # But it won't match the expected JSON structure
            assert len(channel_files) <= 1

    @pytest.mark.asyncio
    async def test_nested_traversal_attempts(self, extractor, tmp_path):
        """Test complex nested path traversal attempts."""
        file_structure = {
            "export/channels.json": [{"id": "C123", "name": "general"}],
            "export/users.json": [{"id": "U123", "name": "Test", "team_id": "T123"}],
            "export/general/../../etc/passwd": "should not work",
            "export/general/../../../etc/shadow": "also should not work",
            "export/general/2024-01-01.json": [{"type": "message", "text": "normal"}],
        }

        zip_path = tmp_path / "nested_traversal.zip"
        self.create_zip_with_structure(file_structure, zip_path)

        # Detect base directory
        base_dir = await extractor._detect_base_directory(zip_path)
        assert base_dir == "export/"

        # Set up and analyze
        extractor._base_directory = base_dir
        await extractor._load_channels_data(zip_path)
        channel_files = await extractor._analyze_channel_day_files(zip_path)

        # Should only find the safe file
        assert len(channel_files) == 1
        assert channel_files[0].filename == "2024-01-01.json"

    @pytest.mark.asyncio
    async def test_windows_path_traversal(self, extractor, tmp_path):
        """Test Windows-style path traversal attempts."""
        file_structure = {
            "channels.json": [{"id": "C123", "name": "general"}],
            "users.json": [{"id": "U123", "name": "Test", "team_id": "T123"}],
            "general\\..\\..\\windows\\system32\\config": "evil",
            r"general\normal.json": [{"type": "message", "text": "normal"}],
        }

        zip_path = tmp_path / "windows_traversal.zip"
        self.create_zip_with_structure(file_structure, zip_path)

        extractor._base_directory = ""
        await extractor._load_channels_data(zip_path)

        # Should handle Windows paths safely
        channel_files = await extractor._analyze_channel_day_files(zip_path)

        # Depending on OS, might find the normal.json or not
        assert len(channel_files) <= 1

    @pytest.mark.asyncio
    async def test_unicode_path_traversal(self, extractor, tmp_path):
        """Test Unicode/encoded path traversal attempts."""
        file_structure = {
            "channels.json": [{"id": "C123", "name": "general"}],
            "users.json": [{"id": "U123", "name": "Test", "team_id": "T123"}],
            # Unicode path traversal attempts
            "general/\u002e\u002e/\u002e\u002e/etc/passwd": "unicode traversal",
            "general/normal.json": [{"type": "message", "text": "normal"}],
        }

        zip_path = tmp_path / "unicode_traversal.zip"
        self.create_zip_with_structure(file_structure, zip_path)

        extractor._base_directory = ""
        await extractor._load_channels_data(zip_path)
        channel_files = await extractor._analyze_channel_day_files(zip_path)

        # Should handle Unicode safely and only find normal file
        assert len(channel_files) == 1
        assert channel_files[0].filename == "normal.json"

    @pytest.mark.asyncio
    async def test_null_byte_injection(self, extractor, tmp_path):
        """Test null byte injection attempts in paths."""
        zip_path = tmp_path / "null_byte.zip"

        # Create ZIP with null bytes in filenames
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("channels.json", json.dumps([{"id": "C123", "name": "general"}]))
            zf.writestr(
                "users.json", json.dumps([{"id": "U123", "name": "Test", "team_id": "T123"}])
            )

            # Try null byte injection (some systems reject null bytes in filenames)
            with contextlib.suppress(ValueError):
                zf.writestr("general/evil.json\x00.txt", "null byte injection")

            zf.writestr("general/normal.json", json.dumps([{"type": "message", "text": "ok"}]))

        extractor._base_directory = ""
        await extractor._load_channels_data(zip_path)
        channel_files = await extractor._analyze_channel_day_files(zip_path)

        # Should handle null bytes safely
        assert all("\x00" not in f.filename for f in channel_files)
