"""
Tests for Unix path prefix utilities (WSL-first approach).
"""

import pytest
from unittest.mock import Mock
from borgitory.utils.path_prefix import parse_path_for_autocomplete


class TestPathPrefix:
    """Test Unix path prefix parsing for WSL-first approach."""

    @pytest.fixture
    def mock_path_service(self):
        """Create mock path service."""
        mock = Mock()
        mock.normalize_path.side_effect = (
            lambda x: x
        )  # Return input unchanged for simplicity
        return mock

    def test_parse_unix_path(self, mock_path_service):
        """Test parsing Unix-style paths."""
        # Test basic path
        dir_path, search_term = parse_path_for_autocomplete(
            "/home/user", mock_path_service
        )
        assert dir_path == "/home"
        assert search_term == "user"

    def test_parse_wsl_windows_path(self, mock_path_service):
        """Test parsing WSL-mounted Windows paths."""
        # Test WSL Windows path
        dir_path, search_term = parse_path_for_autocomplete(
            "/mnt/c/Users/test", mock_path_service
        )
        assert dir_path == "/mnt/c/Users"
        assert search_term == "test"

    def test_parse_path_with_trailing_separator(self, mock_path_service):
        """Test parsing paths with trailing separators."""
        # Test Unix path with trailing separator
        dir_path, search_term = parse_path_for_autocomplete("/home/", mock_path_service)
        assert dir_path == "/home"
        assert search_term == ""

        # Test WSL path with trailing separator
        dir_path, search_term = parse_path_for_autocomplete(
            "/mnt/c/Users/", mock_path_service
        )
        assert dir_path == "/mnt/c/Users"
        assert search_term == ""

    def test_parse_empty_path(self, mock_path_service):
        """Test parsing empty paths."""
        dir_path, search_term = parse_path_for_autocomplete("", mock_path_service)
        assert dir_path == "/"
        assert search_term == ""

    def test_parse_root_path(self, mock_path_service):
        """Test parsing root directory path."""
        # Test Unix root
        dir_path, search_term = parse_path_for_autocomplete("/", mock_path_service)
        assert dir_path == "/"
        assert search_term == ""

    def test_parse_root_level_paths(self, mock_path_service):
        """Test parsing paths at root level."""
        # Test root level path
        dir_path, search_term = parse_path_for_autocomplete("/data", mock_path_service)
        assert dir_path == "/"
        assert search_term == "data"

        # Test WSL mount point
        dir_path, search_term = parse_path_for_autocomplete("/mnt", mock_path_service)
        assert dir_path == "/"
        assert search_term == "mnt"

    def test_parse_deep_paths(self, mock_path_service):
        """Test parsing deeper directory structures."""
        # Test deep Unix path
        dir_path, search_term = parse_path_for_autocomplete(
            "/var/lib/borgitory/data", mock_path_service
        )
        assert dir_path == "/var/lib/borgitory"
        assert search_term == "data"

        # Test deep WSL path
        dir_path, search_term = parse_path_for_autocomplete(
            "/mnt/c/Program Files/app", mock_path_service
        )
        assert dir_path == "/mnt/c/Program Files"
        assert search_term == "app"

    def test_path_service_integration(self, mock_path_service):
        """Test that path service is properly integrated."""
        # Test that the function works with the path service
        dir_path, search_term = parse_path_for_autocomplete(
            "/home/test", mock_path_service
        )

        # Verify we get reasonable results
        assert isinstance(dir_path, str)
        assert isinstance(search_term, str)
        assert dir_path == "/home"
        assert search_term == "test"
