"""
Tests for the universal path service implementation.

This module tests the simplified path service to ensure it works
correctly across different environments.
"""

import os
import tempfile
import pytest
from unittest.mock import patch, Mock
from pathlib import Path

from borgitory.services.path.path_configuration_service import PathConfigurationService
from borgitory.services.path.universal_path_service import UniversalPathService
from borgitory.services.path.path_service_factory import create_path_service


class TestPathConfigurationService:
    """Test path configuration service."""

    def test_container_detection_dockerenv(self) -> None:
        """Test container detection using .dockerenv file."""
        with patch("os.path.exists") as mock_exists:
            mock_exists.return_value = True
            config = PathConfigurationService()
            assert config.is_container_environment() is True

    def test_container_detection_kubernetes(self) -> None:
        """Test container detection using Kubernetes environment."""
        with patch.dict(os.environ, {"KUBERNETES_SERVICE_HOST": "localhost"}), patch(
            "os.path.exists", return_value=False
        ):
            config = PathConfigurationService()
            assert config.is_container_environment() is True

    def test_container_detection_docker_env(self) -> None:
        """Test container detection using Docker environment variable."""
        with patch.dict(os.environ, {"DOCKER_CONTAINER": "true"}), patch(
            "os.path.exists", return_value=False
        ):
            config = PathConfigurationService()
            assert config.is_container_environment() is True

    def test_native_environment_detection(self) -> None:
        """Test native environment detection."""
        with patch("os.path.exists", return_value=False), patch.dict(
            os.environ, {}, clear=True
        ):
            config = PathConfigurationService()
            assert config.is_container_environment() is False

    def test_unix_platform_name(self) -> None:
        """Test Unix platform name detection."""
        with patch("os.path.exists", return_value=False), patch(
            "os.name", "posix"
        ), patch.dict(os.environ, {}, clear=True):
            config = PathConfigurationService()
            assert config.get_platform_name() == "unix"

    def test_container_platform_name(self) -> None:
        """Test container platform name detection."""
        with patch("os.path.exists", return_value=True):
            config = PathConfigurationService()
            assert config.get_platform_name() == "container"

    def test_data_dir_override(self) -> None:
        """Test data directory environment override."""
        with patch.dict(os.environ, {"BORGITORY_DATA_DIR": "/custom/data"}):
            config = PathConfigurationService()
            assert config.get_base_data_dir() == "/custom/data"

    def test_temp_dir_override(self) -> None:
        """Test temp directory environment override."""
        with patch.dict(os.environ, {"BORGITORY_TEMP_DIR": "/custom/temp"}):
            config = PathConfigurationService()
            assert config.get_base_temp_dir() == "/custom/temp"

    def test_cache_dir_override(self) -> None:
        """Test cache directory environment override."""
        with patch.dict(os.environ, {"BORGITORY_CACHE_DIR": "/custom/cache"}):
            config = PathConfigurationService()
            assert config.get_base_cache_dir() == "/custom/cache"


class TestUniversalPathService:
    """Test universal path service."""

    @pytest.fixture
    def mock_config(self) -> Mock:
        """Create mock configuration service."""
        config = Mock()
        config.get_base_data_dir.return_value = "/app/data"
        config.get_base_temp_dir.return_value = "/tmp/borgitory"
        config.get_base_cache_dir.return_value = "/cache/borgitory"
        config.get_platform_name.return_value = "test"
        return config

    @pytest.mark.asyncio
    async def test_directory_methods(self, mock_config: Mock) -> None:
        """Test basic directory methods."""
        service = UniversalPathService(mock_config)

        with patch.object(service, "ensure_directory") as mock_ensure:
            # Test that directory methods call ensure_directory
            data_dir = await service.get_data_dir()
            temp_dir = await service.get_temp_dir()
            cache_dir = await service.get_cache_dir()
            keyfiles_dir = await service.get_keyfiles_dir()
            mount_dir = await service.get_mount_base_dir()

            # All should return strings
            assert isinstance(data_dir, str)
            assert isinstance(temp_dir, str)
            assert isinstance(cache_dir, str)
            assert isinstance(keyfiles_dir, str)
            assert isinstance(mount_dir, str)

            # ensure_directory should have been called for each
            assert mock_ensure.call_count >= 5

    def test_secure_join_basic(self, mock_config: Mock) -> None:
        """Test basic secure path joining."""
        service = UniversalPathService(mock_config)

        with tempfile.TemporaryDirectory() as temp_dir:
            result = service.secure_join(temp_dir, "subdir", "file.txt")

            # Should contain all components (use Path.resolve() for comparison to handle short/long paths)
            temp_path_resolved = str(Path(temp_dir).resolve())
            result_resolved = str(Path(result).resolve())
            assert temp_path_resolved in result_resolved or Path(result).is_relative_to(
                Path(temp_dir)
            )
            assert "subdir" in result
            assert "file.txt" in result

    def test_secure_join_prevents_traversal(self, mock_config: Mock) -> None:
        """Test that secure_join prevents path traversal."""
        service = UniversalPathService(mock_config)

        with tempfile.TemporaryDirectory() as temp_dir:
            # Should raise ValueError for path traversal attempts
            with pytest.raises(ValueError, match="outside the allowed base directory"):
                service.secure_join(temp_dir, "..", "outside")

    def test_secure_join_empty_parts(self, mock_config: Mock) -> None:
        """Test secure_join with empty parts."""
        service = UniversalPathService(mock_config)

        with tempfile.TemporaryDirectory() as temp_dir:
            # Empty parts should be ignored
            result = service.secure_join(temp_dir, "", "subdir", "", "file.txt", "")
            assert "subdir" in result
            assert "file.txt" in result

    def test_secure_join_empty_base_raises(self, mock_config: Mock) -> None:
        """Test that secure_join raises on empty base."""
        service = UniversalPathService(mock_config)

        with pytest.raises(ValueError, match="Base path cannot be empty"):
            service.secure_join("", "subdir")

    @pytest.mark.asyncio
    async def test_ensure_directory_creates_path(self, mock_config: Mock) -> None:
        """Test directory creation."""
        service = UniversalPathService(mock_config)

        with tempfile.TemporaryDirectory() as temp_dir:
            test_path = os.path.join(temp_dir, "new", "nested", "directory")

            # Should create the directory
            await service.ensure_directory(test_path)
            assert os.path.exists(test_path)
            assert os.path.isdir(test_path)

    @pytest.mark.asyncio
    async def test_ensure_directory_empty_path(self, mock_config: Mock) -> None:
        """Test ensure_directory with empty path."""
        service = UniversalPathService(mock_config)

        # Should not raise error for empty path
        await service.ensure_directory("")

    def test_get_platform_name(self, mock_config: Mock) -> None:
        """Test platform name retrieval."""
        service = UniversalPathService(mock_config)

        # Call it once
        result = service.get_platform_name()
        assert result == "test"

        # Verify it was called at least once (may be called during init too)
        assert mock_config.get_platform_name.call_count >= 1


class TestPathServiceFactory:
    """Test path service factory."""

    def test_factory_creates_universal_service(self) -> None:
        """Test factory creates universal service."""
        service = create_path_service()
        assert isinstance(service, UniversalPathService)

    def test_factory_service_has_platform_name(self) -> None:
        """Test factory-created service has platform name."""
        service = create_path_service()
        platform = service.get_platform_name()
        assert platform in ["unix", "container", "wsl"]


class TestCrossPlatformFunctionality:
    """Test cross-platform functionality."""

    @pytest.mark.asyncio
    async def test_path_operations_work_across_platforms(self) -> None:
        """Test that basic path operations work regardless of platform."""
        service = create_path_service()

        # These should work on any platform
        data_dir = await service.get_data_dir()
        temp_dir = await service.get_temp_dir()
        cache_dir = await service.get_cache_dir()
        keyfiles_dir = await service.get_keyfiles_dir()
        mount_dir = await service.get_mount_base_dir()

        # All should return non-empty strings
        assert isinstance(data_dir, str) and len(data_dir) > 0
        assert isinstance(temp_dir, str) and len(temp_dir) > 0
        assert isinstance(cache_dir, str) and len(cache_dir) > 0
        assert isinstance(keyfiles_dir, str) and len(keyfiles_dir) > 0
        assert isinstance(mount_dir, str) and len(mount_dir) > 0

    def test_secure_join_prevents_traversal(self) -> None:
        """Test that secure_join prevents path traversal attacks."""
        service = create_path_service()

        with tempfile.TemporaryDirectory() as temp_dir:
            # Should raise ValueError for traversal attempts
            with pytest.raises(ValueError):
                service.secure_join(temp_dir, "..", "outside")

    @pytest.mark.asyncio
    async def test_directory_creation(self) -> None:
        """Test directory creation works cross-platform."""
        service = create_path_service()

        # For WSL service, use Unix-style paths; for others, use temp directory
        if service.get_platform_name() == "wsl":
            # Use a WSL-compatible path
            test_dir = "/tmp/borgitory-test-dir"
            await service.ensure_directory(test_dir)

            # For WSL, just trust that ensure_directory worked (it would raise on failure)
            # Cleanup via WSL service
            from borgitory.services.path.wsl_path_service import WSLPathService

            if isinstance(service, WSLPathService):
                await service.wsl_executor.execute_command(["rm", "-rf", test_dir])
        else:
            # Use regular temp directory for non-WSL services
            with tempfile.TemporaryDirectory() as temp_dir:
                test_dir = service.secure_join(temp_dir, "test_subdir")

                # Should create directory successfully
                await service.ensure_directory(test_dir)
                assert os.path.exists(test_dir)
                assert os.path.isdir(test_dir)
