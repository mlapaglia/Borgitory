"""
Unit tests for path prefix utilities
"""
import pytest

from app.utils.path_prefix import (
    normalize_path_with_mnt_prefix,
    parse_path_for_autocomplete,
    remove_mnt_prefix_for_display,
)


class TestNormalizePathWithMntPrefix:
    """Test normalize_path_with_mnt_prefix function."""

    def test_empty_input(self):
        """Test empty input returns /mnt/."""
        assert normalize_path_with_mnt_prefix("") == "/mnt/"

    def test_relative_path(self):
        """Test relative paths get /mnt/ prepended."""
        assert normalize_path_with_mnt_prefix("data") == "/mnt/data"
        assert normalize_path_with_mnt_prefix("data/subfolder") == "/mnt/data/subfolder"
        assert normalize_path_with_mnt_prefix("folder/subfolder/deep") == "/mnt/folder/subfolder/deep"

    def test_absolute_path_without_mnt(self):
        """Test absolute paths without /mnt/ get /mnt prepended."""
        assert normalize_path_with_mnt_prefix("/data") == "/mnt/data"
        assert normalize_path_with_mnt_prefix("/data/subfolder") == "/mnt/data/subfolder"
        assert normalize_path_with_mnt_prefix("/folder/subfolder/deep") == "/mnt/folder/subfolder/deep"

    def test_path_already_has_mnt_prefix(self):
        """Test paths that already have /mnt/ prefix remain unchanged."""
        assert normalize_path_with_mnt_prefix("/mnt/") == "/mnt/"
        assert normalize_path_with_mnt_prefix("/mnt/data") == "/mnt/data"
        assert normalize_path_with_mnt_prefix("/mnt/data/subfolder") == "/mnt/data/subfolder"

    def test_root_path(self):
        """Test root path gets converted to /mnt/."""
        assert normalize_path_with_mnt_prefix("/") == "/mnt/"

    def test_edge_cases(self):
        """Test edge cases."""
        # Multiple slashes
        assert normalize_path_with_mnt_prefix("//data") == "/mnt//data"
        assert normalize_path_with_mnt_prefix("/data//subfolder") == "/mnt/data//subfolder"
        
        # Special characters
        assert normalize_path_with_mnt_prefix("data-folder") == "/mnt/data-folder"
        assert normalize_path_with_mnt_prefix("data_folder") == "/mnt/data_folder"
        assert normalize_path_with_mnt_prefix("data.folder") == "/mnt/data.folder"


class TestParsePathForAutocomplete:
    """Test parse_path_for_autocomplete function."""

    def test_empty_or_invalid_input(self):
        """Test empty or invalid input."""
        assert parse_path_for_autocomplete("") == ("/mnt/", "")
        assert parse_path_for_autocomplete("relative") == ("/mnt/", "")

    def test_root_path_with_search_term(self):
        """Test root path with search term."""
        assert parse_path_for_autocomplete("/search") == ("/", "search")
        assert parse_path_for_autocomplete("/mnt") == ("/", "mnt")

    def test_directory_path_with_search_term(self):
        """Test directory path with search term."""
        assert parse_path_for_autocomplete("/mnt/data") == ("/mnt/", "data")
        assert parse_path_for_autocomplete("/mnt/data/search") == ("/mnt/data", "search")
        assert parse_path_for_autocomplete("/mnt/data/folder/sub") == ("/mnt/data/folder", "sub")

    def test_directory_path_with_trailing_slash(self):
        """Test directory path with trailing slash (no search term)."""
        assert parse_path_for_autocomplete("/mnt/") == ("/mnt/", "")
        assert parse_path_for_autocomplete("/mnt/data/") == ("/mnt/data", "")
        assert parse_path_for_autocomplete("/mnt/data/folder/") == ("/mnt/data/folder", "")

    def test_complex_paths(self):
        """Test complex path scenarios."""
        assert parse_path_for_autocomplete("/mnt/backup/daily") == ("/mnt/backup", "daily")
        assert parse_path_for_autocomplete("/mnt/documents/projects/myproject") == ("/mnt/documents/projects", "myproject")


class TestRemoveMntPrefixForDisplay:
    """Test remove_mnt_prefix_for_display function."""

    def test_paths_with_mnt_prefix(self):
        """Test paths that have /mnt/ prefix get it removed."""
        assert remove_mnt_prefix_for_display("/mnt/data/folder") == "data/folder"
        assert remove_mnt_prefix_for_display("/mnt/") == ""
        assert remove_mnt_prefix_for_display("/mnt/data") == "data"
        assert remove_mnt_prefix_for_display("/mnt/documents/projects") == "documents/projects"

    def test_paths_without_mnt_prefix(self):
        """Test paths without /mnt/ prefix remain unchanged."""
        assert remove_mnt_prefix_for_display("/data/folder") == "/data/folder"
        assert remove_mnt_prefix_for_display("data/folder") == "data/folder"
        assert remove_mnt_prefix_for_display("/") == "/"
        assert remove_mnt_prefix_for_display("") == ""

    def test_edge_cases(self):
        """Test edge cases."""
        # Path that starts with /mnt but not /mnt/
        assert remove_mnt_prefix_for_display("/mntdata") == "/mntdata"
        
        # Path with /mnt/ in the middle
        assert remove_mnt_prefix_for_display("/data/mnt/folder") == "/data/mnt/folder"


class TestIntegrationScenarios:
    """Test integration scenarios combining multiple functions."""

    def test_full_autocomplete_flow(self):
        """Test the full flow from user input to parsed components."""
        # User types "data" in the input
        user_input = "data"
        
        # Step 1: Normalize with /mnt/ prefix
        normalized = normalize_path_with_mnt_prefix(user_input)
        assert normalized == "/mnt/data"
        
        # Step 2: Parse for autocomplete
        dir_path, search_term = parse_path_for_autocomplete(normalized)
        assert dir_path == "/mnt/"
        assert search_term == "data"

    def test_nested_path_flow(self):
        """Test flow with nested path."""
        # User types "data/backup" in the input
        user_input = "data/backup"
        
        # Step 1: Normalize with /mnt/ prefix
        normalized = normalize_path_with_mnt_prefix(user_input)
        assert normalized == "/mnt/data/backup"
        
        # Step 2: Parse for autocomplete
        dir_path, search_term = parse_path_for_autocomplete(normalized)
        assert dir_path == "/mnt/data"
        assert search_term == "backup"

    def test_display_path_flow(self):
        """Test flow for displaying paths in dropdown."""
        # Backend returns full path
        full_path = "/mnt/data/documents"
        
        # Remove prefix for display
        display_path = remove_mnt_prefix_for_display(full_path)
        assert display_path == "data/documents"

    def test_already_normalized_input(self):
        """Test flow when user input is already normalized."""
        # User somehow enters full path
        user_input = "/mnt/data/search"
        
        # Step 1: Normalize (should remain unchanged)
        normalized = normalize_path_with_mnt_prefix(user_input)
        assert normalized == "/mnt/data/search"
        
        # Step 2: Parse for autocomplete
        dir_path, search_term = parse_path_for_autocomplete(normalized)
        assert dir_path == "/mnt/data"
        assert search_term == "search"
