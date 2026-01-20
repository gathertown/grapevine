"""Tests for Google Drive Shared Drive extractor."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from connectors.google_drive import GoogleDriveSharedDriveExtractor


class TestExpandDomainAccessibleFolders:
    """Test suite for recursive folder expansion logic."""

    @pytest.fixture
    def extractor(self):
        return GoogleDriveSharedDriveExtractor()

    def test_single_level_hierarchy(self, extractor):
        """Test expansion with no nested folders."""
        domain_folders = {"folder1", "folder2"}
        hierarchy: dict[str, list[str]] = {
            "folder1": [],  # No children
            "folder2": [],
        }

        result = extractor._expand_domain_accessible_folders(domain_folders, hierarchy)

        assert result == {"folder1", "folder2"}

    def test_two_level_hierarchy(self, extractor):
        """Test expansion with one level of nesting."""
        domain_folders = {"parent1"}
        hierarchy = {
            "parent1": ["child1", "child2"],
            "child1": [],
            "child2": [],
        }

        result = extractor._expand_domain_accessible_folders(domain_folders, hierarchy)

        assert result == {"parent1", "child1", "child2"}

    def test_deep_hierarchy(self, extractor):
        """Test expansion with multiple levels of nesting."""
        domain_folders = {"root"}
        hierarchy = {
            "root": ["level1a", "level1b"],
            "level1a": ["level2a"],
            "level1b": ["level2b"],
            "level2a": ["level3a"],
            "level2b": [],
            "level3a": [],
        }

        result = extractor._expand_domain_accessible_folders(domain_folders, hierarchy)

        assert result == {"root", "level1a", "level1b", "level2a", "level2b", "level3a"}

    def test_multiple_parents_share_children(self, extractor):
        """Test expansion when multiple parent folders are domain-accessible."""
        domain_folders = {"parent1", "parent2"}
        hierarchy = {
            "parent1": ["child1"],
            "parent2": ["child2"],
            "child1": ["grandchild1"],
            "child2": [],
            "grandchild1": [],
        }

        result = extractor._expand_domain_accessible_folders(domain_folders, hierarchy)

        assert result == {"parent1", "parent2", "child1", "child2", "grandchild1"}

    def test_empty_domain_folders(self, extractor):
        """Test expansion with no domain-accessible folders."""
        domain_folders: set[str] = set()
        hierarchy = {
            "folder1": ["child1"],
            "child1": [],
        }

        result = extractor._expand_domain_accessible_folders(domain_folders, hierarchy)

        assert result == set()

    def test_folder_not_in_hierarchy(self, extractor):
        """Test expansion when domain folder has no children in hierarchy."""
        domain_folders = {"orphan"}
        hierarchy = {
            "other_folder": ["child1"],
        }

        result = extractor._expand_domain_accessible_folders(domain_folders, hierarchy)

        # Should still include the orphan folder even if it has no children
        assert result == {"orphan"}


class TestFilterFilesToCheck:
    """Test suite for file filtering logic."""

    @pytest.fixture
    def extractor(self):
        return GoogleDriveSharedDriveExtractor()

    def test_file_in_domain_folder(self, extractor):
        """Test that files in domain-accessible folders are included."""
        all_files = [
            {"id": "file1", "name": "doc1.txt", "parents": ["domain_folder"]},
            {"id": "file2", "name": "doc2.txt", "parents": ["private_folder"]},
        ]
        domain_folders = {"domain_folder"}

        result = extractor._filter_files_to_check(all_files, domain_folders)

        assert len(result) == 1
        assert result[0]["id"] == "file1"

    def test_file_with_augmented_permissions(self, extractor):
        """Test that files with augmented permissions are included."""
        all_files = [
            {
                "id": "file1",
                "name": "doc1.txt",
                "parents": ["private_folder"],
                "hasAugmentedPermissions": True,
            },
            {
                "id": "file2",
                "name": "doc2.txt",
                "parents": ["private_folder"],
                "hasAugmentedPermissions": False,
            },
        ]
        domain_folders: set[str] = set()

        result = extractor._filter_files_to_check(all_files, domain_folders)

        assert len(result) == 1
        assert result[0]["id"] == "file1"

    def test_file_in_domain_folder_and_has_augmented_permissions(self, extractor):
        """Test that files meeting both criteria are only included once."""
        all_files = [
            {
                "id": "file1",
                "name": "doc1.txt",
                "parents": ["domain_folder"],
                "hasAugmentedPermissions": True,
            },
        ]
        domain_folders = {"domain_folder"}

        result = extractor._filter_files_to_check(all_files, domain_folders)

        assert len(result) == 1
        assert result[0]["id"] == "file1"

    def test_file_with_multiple_parents(self, extractor):
        """Test that files with multiple parents are included if any parent is domain-accessible."""
        all_files = [
            {
                "id": "file1",
                "name": "doc1.txt",
                "parents": ["private_folder", "domain_folder"],
            },
        ]
        domain_folders = {"domain_folder"}

        result = extractor._filter_files_to_check(all_files, domain_folders)

        assert len(result) == 1
        assert result[0]["id"] == "file1"

    def test_no_files_match_criteria(self, extractor):
        """Test that no files are returned when none match criteria."""
        all_files = [
            {
                "id": "file1",
                "name": "doc1.txt",
                "parents": ["private_folder"],
                "hasAugmentedPermissions": False,
            },
            {
                "id": "file2",
                "name": "doc2.txt",
                "parents": ["another_private_folder"],
            },
        ]
        domain_folders: set[str] = set()

        result = extractor._filter_files_to_check(all_files, domain_folders)

        assert len(result) == 0

    def test_empty_files_list(self, extractor):
        """Test filtering with empty files list."""
        all_files: list[dict[str, Any]] = []
        domain_folders = {"domain_folder"}

        result = extractor._filter_files_to_check(all_files, domain_folders)

        assert len(result) == 0

    def test_file_without_parents_field(self, extractor):
        """Test that files without parents field are handled gracefully."""
        all_files = [
            {"id": "file1", "name": "doc1.txt"},  # No parents field
        ]
        domain_folders = {"domain_folder"}

        result = extractor._filter_files_to_check(all_files, domain_folders)

        assert len(result) == 0


class TestCheckFolderPermissionsBatch:
    """Test suite for batch folder permission checking."""

    @pytest.fixture
    def extractor(self):
        return GoogleDriveSharedDriveExtractor()

    @pytest.fixture
    def mock_drive_client(self):
        client = MagicMock()
        client.get_file_permissions_batch = AsyncMock()
        client.is_domain_accessible = MagicMock()
        return client

    @pytest.mark.asyncio
    async def test_all_folders_domain_accessible(self, extractor, mock_drive_client):
        """Test batch check when all folders are domain-accessible."""
        folders = [
            {"id": "folder1", "name": "Folder 1"},
            {"id": "folder2", "name": "Folder 2"},
        ]
        domain_folders: set[str] = set()

        mock_drive_client.get_file_permissions_batch.return_value = {
            "folder1": [{"type": "domain", "role": "reader"}],
            "folder2": [{"type": "domain", "role": "reader"}],
        }
        mock_drive_client.is_domain_accessible.return_value = True

        await extractor._check_folder_permissions_batch(mock_drive_client, folders, domain_folders)

        assert domain_folders == {"folder1", "folder2"}
        mock_drive_client.get_file_permissions_batch.assert_called_once_with(["folder1", "folder2"])

    @pytest.mark.asyncio
    async def test_mixed_accessibility(self, extractor, mock_drive_client):
        """Test batch check with mixed accessibility."""
        folders = [
            {"id": "folder1", "name": "Public Folder"},
            {"id": "folder2", "name": "Private Folder"},
            {"id": "folder3", "name": "Another Public Folder"},
        ]
        domain_folders: set[str] = set()

        mock_drive_client.get_file_permissions_batch.return_value = {
            "folder1": [{"type": "domain", "role": "reader"}],
            "folder2": [{"type": "user", "role": "owner"}],
            "folder3": [{"type": "domain", "role": "reader"}],
        }

        # Mock is_domain_accessible to return True for folder1 and folder3, False for folder2
        def is_domain_accessible_side_effect(permissions):
            return permissions[0]["type"] == "domain"

        mock_drive_client.is_domain_accessible.side_effect = is_domain_accessible_side_effect

        await extractor._check_folder_permissions_batch(mock_drive_client, folders, domain_folders)

        assert domain_folders == {"folder1", "folder3"}

    @pytest.mark.asyncio
    async def test_no_folders_domain_accessible(self, extractor, mock_drive_client):
        """Test batch check when no folders are domain-accessible."""
        folders = [
            {"id": "folder1", "name": "Private Folder"},
        ]
        domain_folders: set[str] = set()

        mock_drive_client.get_file_permissions_batch.return_value = {
            "folder1": [{"type": "user", "role": "owner"}],
        }
        mock_drive_client.is_domain_accessible.return_value = False

        await extractor._check_folder_permissions_batch(mock_drive_client, folders, domain_folders)

        assert domain_folders == set()

    @pytest.mark.asyncio
    async def test_empty_folders_list(self, extractor, mock_drive_client):
        """Test batch check with empty folders list."""
        folders: list[dict[str, Any]] = []
        domain_folders: set[str] = set()

        mock_drive_client.get_file_permissions_batch.return_value = {}

        await extractor._check_folder_permissions_batch(mock_drive_client, folders, domain_folders)

        assert domain_folders == set()


class TestScanAndBuildHierarchy:
    """Test suite for scanning shared drive and building folder hierarchy."""

    @pytest.fixture
    def extractor(self):
        return GoogleDriveSharedDriveExtractor()

    @pytest.fixture
    def mock_drive_client(self):
        client = MagicMock()
        client.list_files = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_single_page_scan(self, extractor, mock_drive_client):
        """Test scanning with a single page of results."""
        mock_drive_client.list_files.return_value = {
            "files": [
                {
                    "id": "folder1",
                    "name": "Folder 1",
                    "mimeType": "application/vnd.google-apps.folder",
                    "parents": ["root"],
                    "hasAugmentedPermissions": True,
                },
                {
                    "id": "file1",
                    "name": "Document 1",
                    "mimeType": "application/pdf",
                    "parents": ["folder1"],
                },
            ],
            "nextPageToken": None,
        }

        hierarchy, folders_with_perms, files = await extractor._scan_and_build_hierarchy(
            mock_drive_client, "drive_id", "Test Drive"
        )

        assert hierarchy == {"root": ["folder1"]}
        assert len(folders_with_perms) == 1
        assert folders_with_perms[0]["id"] == "folder1"
        assert len(files) == 1
        assert files[0]["id"] == "file1"

    @pytest.mark.asyncio
    async def test_multi_page_scan(self, extractor, mock_drive_client):
        """Test scanning with multiple pages of results."""
        # First call returns page with nextPageToken
        # Second call returns final page
        mock_drive_client.list_files.side_effect = [
            {
                "files": [
                    {
                        "id": "folder1",
                        "name": "Folder 1",
                        "mimeType": "application/vnd.google-apps.folder",
                        "parents": ["root"],
                        "hasAugmentedPermissions": True,
                    },
                ],
                "nextPageToken": "token123",
            },
            {
                "files": [
                    {
                        "id": "file1",
                        "name": "Document 1",
                        "mimeType": "application/pdf",
                        "parents": ["folder1"],
                    },
                ],
                "nextPageToken": None,
            },
        ]

        hierarchy, folders_with_perms, files = await extractor._scan_and_build_hierarchy(
            mock_drive_client, "drive_id", "Test Drive"
        )

        assert hierarchy == {"root": ["folder1"]}
        assert len(folders_with_perms) == 1
        assert len(files) == 1
        assert mock_drive_client.list_files.call_count == 2

    @pytest.mark.asyncio
    async def test_nested_folder_hierarchy(self, extractor, mock_drive_client):
        """Test building hierarchy with nested folders."""
        mock_drive_client.list_files.return_value = {
            "files": [
                {
                    "id": "parent",
                    "mimeType": "application/vnd.google-apps.folder",
                    "parents": ["root"],
                    "hasAugmentedPermissions": True,
                },
                {
                    "id": "child1",
                    "mimeType": "application/vnd.google-apps.folder",
                    "parents": ["parent"],
                    "hasAugmentedPermissions": False,
                },
                {
                    "id": "child2",
                    "mimeType": "application/vnd.google-apps.folder",
                    "parents": ["parent"],
                    "hasAugmentedPermissions": True,
                },
            ],
            "nextPageToken": None,
        }

        hierarchy, folders_with_perms, files = await extractor._scan_and_build_hierarchy(
            mock_drive_client, "drive_id", "Test Drive"
        )

        assert hierarchy == {
            "root": ["parent"],
            "parent": ["child1", "child2"],
        }
        assert len(folders_with_perms) == 2  # parent and child2
        assert {f["id"] for f in folders_with_perms} == {"parent", "child2"}
        assert len(files) == 0

    @pytest.mark.asyncio
    async def test_folder_with_multiple_parents(self, extractor, mock_drive_client):
        """Test that folders with multiple parents are handled correctly."""
        mock_drive_client.list_files.return_value = {
            "files": [
                {
                    "id": "folder1",
                    "mimeType": "application/vnd.google-apps.folder",
                    "parents": ["parent1", "parent2"],
                    "hasAugmentedPermissions": True,
                },
            ],
            "nextPageToken": None,
        }

        hierarchy, folders_with_perms, files = await extractor._scan_and_build_hierarchy(
            mock_drive_client, "drive_id", "Test Drive"
        )

        assert hierarchy == {
            "parent1": ["folder1"],
            "parent2": ["folder1"],
        }
        assert len(folders_with_perms) == 1

    @pytest.mark.asyncio
    async def test_empty_drive(self, extractor, mock_drive_client):
        """Test scanning an empty drive."""
        mock_drive_client.list_files.return_value = {
            "files": [],
            "nextPageToken": None,
        }

        hierarchy, folders_with_perms, files = await extractor._scan_and_build_hierarchy(
            mock_drive_client, "drive_id", "Empty Drive"
        )

        assert hierarchy == {}
        assert len(folders_with_perms) == 0
        assert len(files) == 0


class TestIdentifyDomainAccessibleFolders:
    """Test suite for identifying domain-accessible folders with expansion."""

    @pytest.fixture
    def extractor(self):
        return GoogleDriveSharedDriveExtractor()

    @pytest.fixture
    def mock_drive_client(self):
        client = MagicMock()
        client.get_file_permissions_batch = AsyncMock()
        client.is_domain_accessible = MagicMock()
        return client

    @pytest.mark.asyncio
    async def test_identify_with_expansion(self, extractor, mock_drive_client):
        """Test identification and recursive expansion of domain folders."""
        folders_with_perms = [
            {"id": "parent", "name": "Parent Folder"},
        ]
        hierarchy = {
            "parent": ["child1", "child2"],
            "child1": ["grandchild"],
        }

        mock_drive_client.get_file_permissions_batch.return_value = {
            "parent": [{"type": "domain", "role": "reader"}],
        }
        mock_drive_client.is_domain_accessible.return_value = True

        result = await extractor._identify_domain_accessible_folders(
            mock_drive_client, folders_with_perms, hierarchy
        )

        # Should include parent and all descendants
        assert result == {"parent", "child1", "child2", "grandchild"}

    @pytest.mark.asyncio
    async def test_identify_no_expansion_needed(self, extractor, mock_drive_client):
        """Test identification when folders have no children."""
        folders_with_perms = [
            {"id": "folder1", "name": "Folder 1"},
            {"id": "folder2", "name": "Folder 2"},
        ]
        hierarchy: dict[str, list[str]] = {}

        mock_drive_client.get_file_permissions_batch.return_value = {
            "folder1": [{"type": "domain", "role": "reader"}],
            "folder2": [{"type": "domain", "role": "reader"}],
        }
        mock_drive_client.is_domain_accessible.return_value = True

        result = await extractor._identify_domain_accessible_folders(
            mock_drive_client, folders_with_perms, hierarchy
        )

        assert result == {"folder1", "folder2"}

    @pytest.mark.asyncio
    async def test_identify_mixed_with_expansion(self, extractor, mock_drive_client):
        """Test identification with mixed accessibility and expansion."""
        folders_with_perms = [
            {"id": "public_parent", "name": "Public Parent"},
            {"id": "private_parent", "name": "Private Parent"},
        ]
        hierarchy = {
            "public_parent": ["child1"],
            "private_parent": ["child2"],
        }

        mock_drive_client.get_file_permissions_batch.return_value = {
            "public_parent": [{"type": "domain", "role": "reader"}],
            "private_parent": [{"type": "user", "role": "owner"}],
        }

        def is_domain_accessible_side_effect(permissions):
            return permissions[0]["type"] == "domain"

        mock_drive_client.is_domain_accessible.side_effect = is_domain_accessible_side_effect

        result = await extractor._identify_domain_accessible_folders(
            mock_drive_client, folders_with_perms, hierarchy
        )

        # Should include public_parent and its child, but not private_parent or its child
        assert result == {"public_parent", "child1"}


class TestProcessFilesInBatches:
    """Test suite for batch file processing."""

    @pytest.fixture
    def extractor(self):
        return GoogleDriveSharedDriveExtractor()

    @pytest.fixture
    def mock_drive_client(self):
        return MagicMock()

    @pytest.fixture
    def mock_db_pool(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_process_single_batch(self, extractor, mock_drive_client, mock_db_pool):
        """Test processing a single batch of files."""
        from unittest.mock import patch

        files = [
            {"id": "file1", "name": "Document 1"},
            {"id": "file2", "name": "Document 2"},
        ]

        mock_process_batch = AsyncMock(return_value=["file1", "file2"])

        with patch.object(extractor, "_process_permission_batch", mock_process_batch):
            result = await extractor._process_files_in_batches(
                mock_drive_client, files, "Test Drive", "job123", mock_db_pool
            )

            assert result == ["file1", "file2"]
            mock_process_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_multiple_batches(self, extractor, mock_drive_client, mock_db_pool):
        """Test processing multiple batches of files."""
        from unittest.mock import patch

        # Create 25 files (should be 3 batches with batch size 10)
        files = [{"id": f"file{i}", "name": f"Document {i}"} for i in range(25)]

        mock_process_batch = AsyncMock()
        # Return file IDs for each batch
        mock_process_batch.side_effect = [
            [f"file{i}" for i in range(10)],
            [f"file{i}" for i in range(10, 20)],
            [f"file{i}" for i in range(20, 25)],
        ]

        with patch.object(extractor, "_process_permission_batch", mock_process_batch):
            result = await extractor._process_files_in_batches(
                mock_drive_client, files, "Test Drive", "job123", mock_db_pool
            )

            assert len(result) == 25
            assert mock_process_batch.call_count == 3

    @pytest.mark.asyncio
    async def test_process_empty_files_list(self, extractor, mock_drive_client, mock_db_pool):
        """Test processing with empty files list."""
        from unittest.mock import patch

        files: list[dict[str, Any]] = []

        mock_process_batch = AsyncMock()

        with patch.object(extractor, "_process_permission_batch", mock_process_batch):
            result = await extractor._process_files_in_batches(
                mock_drive_client, files, "Test Drive", "job123", mock_db_pool
            )

            assert result == []
            mock_process_batch.assert_not_called()
