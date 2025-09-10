"""
Tests for the virtual archive tree functionality.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from app.services.virtual_archive_tree import VirtualArchiveTree, ArchiveExplorer
from app.models.database import Repository


class TestVirtualArchiveTree:
    """Test the virtual archive tree building logic."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tree = VirtualArchiveTree()

    def test_add_entry_simple_file(self):
        """Test adding a simple root-level file."""
        entry = {"path": "file.txt", "type": "-", "size": 100}
        self.tree.add_entry(entry)
        
        contents = self.tree.get_directory_contents("")
        assert len(contents) == 1
        assert contents[0]["name"] == "file.txt"
        assert contents[0]["is_directory"] is False
        assert contents[0]["size"] == 100

    def test_add_entry_nested_file_creates_virtual_dirs(self):
        """Test that adding nested files creates virtual intermediate directories."""
        entry = {"path": "home/user/documents/file.pdf", "type": "-", "size": 500}
        self.tree.add_entry(entry)
        
        # Root should show 'home' as a virtual directory
        root_contents = self.tree.get_directory_contents("")
        assert len(root_contents) == 1
        assert root_contents[0]["name"] == "home"
        assert root_contents[0]["is_directory"] is True
        assert root_contents[0].get("virtual") is True
        
        # home should show 'user' as virtual directory
        home_contents = self.tree.get_directory_contents("home")
        assert len(home_contents) == 1
        assert home_contents[0]["name"] == "user"
        assert home_contents[0]["is_directory"] is True
        
        # home/user should show 'documents' as virtual directory
        user_contents = self.tree.get_directory_contents("home/user")
        assert len(user_contents) == 1
        assert user_contents[0]["name"] == "documents"
        assert user_contents[0]["is_directory"] is True
        
        # home/user/documents should show the actual file
        docs_contents = self.tree.get_directory_contents("home/user/documents")
        assert len(docs_contents) == 1
        assert docs_contents[0]["name"] == "file.pdf"
        assert docs_contents[0]["is_directory"] is False
        assert docs_contents[0]["size"] == 500

    def test_mixed_entries_with_explicit_and_virtual_dirs(self):
        """Test handling mix of explicit directories and files that create virtual dirs."""
        entries = [
            {"path": "data", "type": "d"},  # Explicit directory
            {"path": "data/file1.txt", "type": "-", "size": 100},
            {"path": "data/subdir/file2.txt", "type": "-", "size": 200},  # Creates virtual subdir
            {"path": "logs/app.log", "type": "-", "size": 1000},  # Creates virtual logs dir
        ]
        
        for entry in entries:
            self.tree.add_entry(entry)
        
        # Root should show both 'data' (explicit) and 'logs' (virtual)
        root_contents = self.tree.get_directory_contents("")
        assert len(root_contents) == 2
        names = [item["name"] for item in root_contents]
        assert "data" in names
        assert "logs" in names
        
        # data should show file1.txt and subdir
        data_contents = self.tree.get_directory_contents("data")
        assert len(data_contents) == 2
        names = [item["name"] for item in data_contents]
        assert "file1.txt" in names
        assert "subdir" in names
        
        # data/subdir should show file2.txt
        subdir_contents = self.tree.get_directory_contents("data/subdir")
        assert len(subdir_contents) == 1
        assert subdir_contents[0]["name"] == "file2.txt"

    def test_sorting_directories_first_then_files(self):
        """Test that results are sorted with directories first, then files."""
        entries = [
            {"path": "zebra.txt", "type": "-", "size": 100},
            {"path": "apple.txt", "type": "-", "size": 200},
            {"path": "beta", "type": "d"},
            {"path": "alpha", "type": "d"},
        ]
        
        for entry in entries:
            self.tree.add_entry(entry)
        
        contents = self.tree.get_directory_contents("")
        assert len(contents) == 4
        
        # Should be sorted: directories first (alpha, beta), then files (apple.txt, zebra.txt)
        expected_order = ["alpha", "beta", "apple.txt", "zebra.txt"]
        actual_order = [item["name"] for item in contents]
        assert actual_order == expected_order

    def test_field_mapping_for_template(self):
        """Test that fields are properly mapped for template consumption."""
        entry = {"path": "file.txt", "type": "-", "size": 100, "mtime": "2024-01-01T12:00:00"}
        self.tree.add_entry(entry)
        
        contents = self.tree.get_directory_contents("")
        item = contents[0]
        
        # Check all expected fields are present
        assert item["name"] == "file.txt"
        assert item["path"] == "file.txt"
        assert item["is_directory"] is False
        assert item["size"] == 100
        assert item["modified"] == "2024-01-01T12:00:00"  # mtime mapped to modified

    def test_path_needs_loading_tracking(self):
        """Test that path loading is properly tracked."""
        assert self.tree.path_needs_loading("") is True
        assert self.tree.path_needs_loading("subdir") is True
        
        self.tree.mark_path_loaded("")
        assert self.tree.path_needs_loading("") is False
        assert self.tree.path_needs_loading("subdir") is True  # Still needs loading
        
        self.tree.mark_path_loaded("subdir")
        assert self.tree.path_needs_loading("subdir") is False


class TestArchiveExplorer:
    """Test the archive explorer with dependency injection."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_repository = Mock(spec=Repository)
        self.mock_repository.path = "/test/repo"
        self.mock_repository.get_passphrase.return_value = "test_pass"
        
        self.mock_job_manager = Mock()
        self.explorer = ArchiveExplorer(job_manager=self.mock_job_manager)

    @pytest.mark.asyncio
    async def test_dependency_injection(self):
        """Test that job manager dependency injection works."""
        assert self.explorer.job_manager is self.mock_job_manager
        
        # Test default behavior (no DI)
        explorer_default = ArchiveExplorer()
        assert explorer_default.job_manager is None

    @pytest.mark.asyncio
    async def test_cache_per_archive(self):
        """Test that trees are cached per archive."""
        # Mock successful borg command
        self.mock_job_manager.start_borg_command = AsyncMock(return_value="job-123")
        self.mock_job_manager.get_job_status.return_value = {"completed": True, "return_code": 0}
        self.mock_job_manager.get_job_output_stream = AsyncMock(return_value={
            "lines": [{"text": '{"path": "file.txt", "type": "-", "size": 100}'}]
        })
        
        with patch('app.utils.security.build_secure_borg_command') as mock_build, \
             patch('app.utils.security.validate_archive_name'):
            mock_build.return_value = (["borg", "list"], {})
            
            # First call to archive1
            await self.explorer.list_archive_directory_contents(
                self.mock_repository, "archive1", ""
            )
            
            # Second call to archive1 (should use cache)
            await self.explorer.list_archive_directory_contents(
                self.mock_repository, "archive1", ""
            )
            
            # Call to archive2 (should create new cache entry)
            await self.explorer.list_archive_directory_contents(
                self.mock_repository, "archive2", ""
            )
        
        # Should have cached trees for both archives
        expected_keys = ["/test/repo::archive1", "/test/repo::archive2"]
        assert len(self.explorer.tree_cache) == 2
        for key in expected_keys:
            assert key in self.explorer.tree_cache

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test that errors are properly handled and propagated."""
        self.mock_job_manager.start_borg_command = AsyncMock(return_value="job-123")
        self.mock_job_manager.get_job_status.return_value = {"completed": True, "return_code": 1}
        self.mock_job_manager.get_job_output_stream = AsyncMock(return_value={
            "lines": [{"text": "Error: Archive not found"}]
        })
        
        with patch('app.utils.security.build_secure_borg_command') as mock_build, \
             patch('app.utils.security.validate_archive_name'):
            mock_build.return_value = (["borg", "list"], {})
            
            with pytest.raises(Exception) as exc_info:
                await self.explorer.list_archive_directory_contents(
                    self.mock_repository, "nonexistent", ""
                )
            
            assert "Borg list failed" in str(exc_info.value)

    def test_cache_clearing(self):
        """Test cache clearing functionality."""
        # Add some dummy cache entries
        self.explorer.tree_cache["key1"] = VirtualArchiveTree()
        self.explorer.tree_cache["key2"] = VirtualArchiveTree()
        
        # Clear specific key
        self.explorer.clear_cache("key1")
        assert "key1" not in self.explorer.tree_cache
        assert "key2" in self.explorer.tree_cache
        
        # Clear all
        self.explorer.clear_cache()
        assert len(self.explorer.tree_cache) == 0


class TestIntegrationWithBorgService:
    """Test integration between virtual tree and BorgService."""

    def setup_method(self):
        """Set up test fixtures."""
        from app.services.borg_service import BorgService
        self.borg_service = BorgService()
        self.mock_repository = Mock(spec=Repository)
        self.mock_repository.path = "/test/repo"
        self.mock_repository.get_passphrase.return_value = "test_pass"

    @pytest.mark.asyncio
    async def test_borg_service_uses_injected_job_manager(self):
        """Test that BorgService properly injects job manager into ArchiveExplorer."""
        mock_job_manager = Mock()
        mock_job_manager.start_borg_command = AsyncMock(return_value="job-123")
        mock_job_manager.get_job_status.return_value = {"completed": True, "return_code": 0}
        mock_job_manager.get_job_output_stream = AsyncMock(return_value={
            "lines": [{"text": '{"path": "test.txt", "type": "-", "size": 50}'}]
        })
        
        with patch('app.services.job_manager_modular.get_job_manager', return_value=mock_job_manager), \
             patch('app.utils.security.build_secure_borg_command') as mock_build, \
             patch('app.utils.security.validate_archive_name'):
            mock_build.return_value = (["borg", "list"], {})
            
            # This should create an explorer with the injected job manager
            contents = await self.borg_service.list_archive_directory_contents(
                self.mock_repository, "test-archive", ""
            )
            
            # Verify the explorer was created and uses the injected job manager
            assert hasattr(self.borg_service, '_archive_explorer')
            assert self.borg_service._archive_explorer.job_manager is mock_job_manager
            
            # Verify contents are returned correctly
            assert len(contents) == 1
            assert contents[0]["name"] == "test.txt"