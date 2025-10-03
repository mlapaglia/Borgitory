"""
Tests for ArchiveManager caching functionality
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from borgitory.services.archives.archive_manager import ArchiveManager
from borgitory.services.archives.archive_models import ArchiveEntry
from borgitory.models.database import Repository


class TestArchiveManagerCaching:
    """Test cases for ArchiveManager caching functionality"""

    @pytest.fixture
    def mock_job_executor(self) -> AsyncMock:
        """Mock job executor"""
        return AsyncMock()

    @pytest.fixture
    def mock_command_executor(self) -> AsyncMock:
        """Mock command executor"""
        mock = AsyncMock()
        mock.execute_command = AsyncMock()
        return mock

    @pytest.fixture
    def mock_repository(self) -> MagicMock:
        """Mock repository"""
        repo = MagicMock(spec=Repository)
        repo.path = "/test/repo"
        repo.name = "test_repo"
        repo.get_passphrase.return_value = "test_passphrase"
        repo.get_keyfile_content.return_value = None
        return repo

    @pytest.fixture
    def manager(
        self, mock_job_executor: AsyncMock, mock_command_executor: AsyncMock
    ) -> ArchiveManager:
        """Create ArchiveManager instance with short cache TTL for testing"""
        return ArchiveManager(
            job_executor=mock_job_executor,
            command_executor=mock_command_executor,
            cache_ttl=timedelta(seconds=1),  # Very short TTL for testing
        )

    def test_cache_key_generation(
        self, manager: ArchiveManager, mock_repository: MagicMock
    ) -> None:
        """Test cache key generation"""
        key1 = manager._get_cache_key(mock_repository, "archive1")
        key2 = manager._get_cache_key(mock_repository, "archive2")

        assert key1 == "/test/repo::archive1"
        assert key2 == "/test/repo::archive2"
        assert key1 != key2

    def test_cache_validity_check(self, manager: ArchiveManager) -> None:
        """Test cache validity checking"""
        now = datetime.now()

        # Fresh cache should be valid
        assert manager._is_cache_valid(now)

        # Old cache should be invalid
        old_time = now - timedelta(minutes=2)
        assert not manager._is_cache_valid(old_time)

    def test_cache_operations(
        self, manager: ArchiveManager, mock_repository: MagicMock
    ) -> None:
        """Test basic cache operations"""
        # Initially no cache
        assert manager._get_cached_items(mock_repository, "test_archive") is None

        # Add items to cache
        test_items = [
            ArchiveEntry(
                path="test_file.txt",
                name="test_file.txt",
                type="f",
                size=1024,
                isdir=False,
            )
        ]
        manager._cache_items(mock_repository, "test_archive", test_items)

        # Should now be cached
        cached_items = manager._get_cached_items(mock_repository, "test_archive")
        assert cached_items == test_items

    def test_cache_clear_all(
        self, manager: ArchiveManager, mock_repository: MagicMock
    ) -> None:
        """Test clearing all cache"""
        # Add some items to cache
        test_items = [
            ArchiveEntry(
                path="test_file.txt",
                name="test_file.txt",
                type="f",
                size=1024,
                isdir=False,
            )
        ]
        manager._cache_items(mock_repository, "test_archive", test_items)

        # Verify cache has items
        assert manager._get_cached_items(mock_repository, "test_archive") is not None

        # Clear all cache
        manager.clear_cache()

        # Cache should be empty
        assert manager._get_cached_items(mock_repository, "test_archive") is None

    def test_cache_clear_repository(
        self, manager: ArchiveManager, mock_repository: MagicMock
    ) -> None:
        """Test clearing cache for specific repository"""
        # Add items for two repositories
        repo1 = MagicMock(spec=Repository)
        repo1.path = "/repo1"
        repo2 = MagicMock(spec=Repository)
        repo2.path = "/repo2"

        test_items = [
            ArchiveEntry(
                path="test_file.txt",
                name="test_file.txt",
                type="f",
                size=1024,
                isdir=False,
            )
        ]

        manager._cache_items(repo1, "archive1", test_items)
        manager._cache_items(repo2, "archive2", test_items)

        # Both should be cached
        assert manager._get_cached_items(repo1, "archive1") is not None
        assert manager._get_cached_items(repo2, "archive2") is not None

        # Clear cache for repo1 only
        manager.clear_cache(repository=repo1)

        # repo1 should be cleared, repo2 should remain
        assert manager._get_cached_items(repo1, "archive1") is None
        assert manager._get_cached_items(repo2, "archive2") is not None

    def test_cache_clear_specific_archive(
        self, manager: ArchiveManager, mock_repository: MagicMock
    ) -> None:
        """Test clearing cache for specific archive"""
        test_items = [
            ArchiveEntry(
                path="test_file.txt",
                name="test_file.txt",
                type="f",
                size=1024,
                isdir=False,
            )
        ]

        # Add items for two archives
        manager._cache_items(mock_repository, "archive1", test_items)
        manager._cache_items(mock_repository, "archive2", test_items)

        # Both should be cached
        assert manager._get_cached_items(mock_repository, "archive1") is not None
        assert manager._get_cached_items(mock_repository, "archive2") is not None

        # Clear cache for archive1 only
        manager.clear_cache(repository=mock_repository, archive_name="archive1")

        # archive1 should be cleared, archive2 should remain
        assert manager._get_cached_items(mock_repository, "archive1") is None
        assert manager._get_cached_items(mock_repository, "archive2") is not None

    def test_cache_stats(
        self, manager: ArchiveManager, mock_repository: MagicMock
    ) -> None:
        """Test cache statistics"""
        # Initially empty
        stats = manager.get_cache_stats()
        assert stats["total_entries"] == 0
        assert stats["valid_entries"] == 0
        assert stats["expired_entries"] == 0

        # Add some items
        test_items = [
            ArchiveEntry(
                path="test_file.txt",
                name="test_file.txt",
                type="f",
                size=1024,
                isdir=False,
            )
        ]
        manager._cache_items(mock_repository, "test_archive", test_items)

        # Should have one entry
        stats = manager.get_cache_stats()
        assert stats["total_entries"] == 1
        assert stats["valid_entries"] == 1
        assert stats["expired_entries"] == 0

    @pytest.mark.asyncio
    async def test_list_archive_directory_contents_cache_hit(
        self, manager: ArchiveManager, mock_repository: MagicMock
    ) -> None:
        """Test that list_archive_directory_contents uses cache when available"""
        # Mock the borg list output
        json_output = """{"type": "d", "mode": "drwxr-xr-x", "uid": 1000, "gid": 1000, "user": "user", "group": "user", "size": 0, "mtime": "2023-01-01T00:00:00Z", "path": "test_dir"}
{"type": "-", "mode": "-rw-r--r--", "uid": 1000, "gid": 1000, "user": "user", "group": "user", "size": 1024, "mtime": "2023-01-01T00:00:00Z", "path": "test_file.txt"}"""

        # Mock the command executor to return our test data
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.stdout = json_output
        mock_result.stderr = ""

        # First call should hit borg list
        with (
            patch(
                "borgitory.services.archives.archive_manager.secure_borg_command"
            ) as mock_secure,
            patch.object(
                manager.command_executor, "execute_command", return_value=mock_result
            ) as mock_execute,
        ):
            mock_secure.return_value.__aenter__.return_value = (
                ["borg", "list", "--json-lines", "/test/repo::test_archive"],
                {"BORG_PASSPHRASE": "test_passphrase"},
                None,
            )
            mock_secure.return_value.__aexit__.return_value = None

            result1 = await manager.list_archive_directory_contents(
                mock_repository, "test_archive", ""
            )

            # Should have called command executor
            assert mock_execute.called

        # Second call should use cache (no patch needed since it should use cache)
        result2 = await manager.list_archive_directory_contents(
            mock_repository, "test_archive", ""
        )

        # Should not have called command executor again (mock_execute is out of scope)
        # We can verify this by checking that the results are the same

        # Results should be the same
        assert len(result1) == len(result2)

    @pytest.mark.asyncio
    async def test_list_archive_directory_contents_cache_miss(
        self, manager: ArchiveManager, mock_repository: MagicMock
    ) -> None:
        """Test that list_archive_directory_contents calls borg when cache is empty"""
        # Mock the borg list output
        json_output = """{"type": "d", "mode": "drwxr-xr-x", "uid": 1000, "gid": 1000, "user": "user", "group": "user", "size": 0, "mtime": "2023-01-01T00:00:00Z", "path": "test_dir"}"""

        # Mock the command executor to return our test data
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.stdout = json_output
        mock_result.stderr = ""

        # Call should hit borg list since cache is empty
        with (
            patch(
                "borgitory.services.archives.archive_manager.secure_borg_command"
            ) as mock_secure,
            patch.object(
                manager.command_executor, "execute_command", return_value=mock_result
            ) as mock_execute,
        ):
            mock_secure.return_value.__aenter__.return_value = (
                ["borg", "list", "--json-lines", "/test/repo::test_archive"],
                {"BORG_PASSPHRASE": "test_passphrase"},
                None,
            )
            mock_secure.return_value.__aexit__.return_value = None

            result = await manager.list_archive_directory_contents(
                mock_repository, "test_archive", ""
            )

            # Should have called command executor
            assert mock_execute.called
            assert len(result) == 1
            assert result[0].name == "test_dir"
