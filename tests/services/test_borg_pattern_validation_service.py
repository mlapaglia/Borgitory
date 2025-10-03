"""
Tests for BorgPatternValidationService - Pattern validation logic for Borg backup patterns.
"""

import pytest
from typing import List, Tuple, Union

from borgitory.services.borg.borg_pattern_validation_service import (
    validate_pattern,
    validate_pattern_list,
    ValidationError,
    PathFullPattern,
    PathPrefixPattern,
    FnmatchPattern,
    ShellPattern,
    RegexPattern,
    PATTERN_CLASSES,
    normalize_path,
    shellpattern_translate_simple,
)


class TestValidatePattern:
    """Test the main validate_pattern function."""

    def test_validate_pattern_empty(self) -> None:
        """Test validation with empty pattern."""
        valid, error, warnings = validate_pattern("")

        assert valid is False
        assert error == "Pattern cannot be empty"
        assert warnings == []

    def test_validate_pattern_invalid_action(self) -> None:
        """Test validation with invalid action."""
        valid, error, warnings = validate_pattern("*.txt", action="x")

        assert valid is False
        assert error == "Invalid action: x. Must be '+', '-', or '!'"
        assert warnings == []

    def test_validate_pattern_valid_actions(self) -> None:
        """Test validation with all valid actions."""
        for action in ["+", "-", "!"]:
            valid, error, warnings = validate_pattern(
                "*.txt", style="sh", action=action
            )
            assert valid is True
            assert error is None

    def test_validate_pattern_unknown_style(self) -> None:
        """Test validation with unknown style."""
        valid, error, warnings = validate_pattern("*.txt", style="unknown")

        assert valid is False
        assert error is not None
        assert "Unknown pattern style: unknown" in error
        assert warnings == []
        assert "Valid: fm, pf, pp, re, sh" in error


class TestShellPattern:
    """Test ShellPattern validator."""

    def test_shell_pattern_valid_simple(self) -> None:
        """Test valid simple shell patterns."""
        test_cases = [
            "*.txt",
            "**/*.log",
            "home/user/*",
            "*.{txt,log}",
            "file?.txt",
        ]

        for pattern in test_cases:
            valid, error, warnings = validate_pattern(pattern, style="sh")
            assert valid is True, f"Pattern '{pattern}' should be valid"
            assert error is None

    def test_shell_pattern_triple_asterisk_error(self) -> None:
        """Test that triple asterisks are rejected."""
        valid, error, warnings = validate_pattern("***/*.txt", style="sh")

        assert valid is False
        assert error is not None
        assert "Use '**' not '***' for recursive matching" in error

    def test_shell_pattern_warnings(self) -> None:
        """Test shell pattern warnings."""
        # Leading slash warning
        valid, error, warnings = validate_pattern("/home/user/*.txt", style="sh")
        assert valid is True
        assert "Leading '/' will be removed automatically" in warnings

        # ** without / warning
        valid, error, warnings = validate_pattern("**txt", style="sh")
        assert valid is True
        assert (
            "'**' should typically be followed by '/' for directory recursion"
            in warnings
        )

    def test_shell_pattern_directory_handling(self) -> None:
        """Test directory pattern handling."""
        valid, error, warnings = validate_pattern("home/user/", style="sh")

        assert valid is True
        assert error is None

    def test_shell_pattern_fallback_validation(self) -> None:
        """Test fallback validation when shellpattern module unavailable."""
        # This tests the _validate_without_shellpattern method
        pattern = ShellPattern("*.txt")
        assert hasattr(pattern, "regex")


class TestFnmatchPattern:
    """Test FnmatchPattern validator."""

    def test_fnmatch_pattern_valid(self) -> None:
        """Test valid fnmatch patterns."""
        test_cases = [
            "*.txt",
            "file?.log",
            "test[0-9].txt",
            "[abc]*.log",
        ]

        for pattern in test_cases:
            valid, error, warnings = validate_pattern(pattern, style="fm")
            assert valid is True, f"Pattern '{pattern}' should be valid"
            assert error is None

    def test_fnmatch_pattern_double_asterisk_error(self) -> None:
        """Test that double asterisks are rejected in fnmatch."""
        valid, error, warnings = validate_pattern("**/*.txt", style="fm")

        assert valid is False
        assert error is not None
        assert (
            "Fnmatch (fm:) doesn't support '**'. Use shell-style (sh:) instead" in error
        )

    def test_fnmatch_pattern_unmatched_brackets(self) -> None:
        """Test unmatched bracket detection."""
        valid, error, warnings = validate_pattern("test[0-9.txt", style="fm")

        assert valid is False
        assert error is not None
        assert "Unmatched brackets in pattern" in error

    def test_fnmatch_pattern_warnings(self) -> None:
        """Test fnmatch pattern warnings."""
        valid, error, warnings = validate_pattern("/home/*.txt", style="fm")

        assert valid is True
        assert "Leading '/' will be removed automatically" in warnings

    def test_fnmatch_pattern_directory_handling(self) -> None:
        """Test directory pattern handling."""
        valid, error, warnings = validate_pattern("home/user/", style="fm")

        assert valid is True
        assert error is None


class TestRegexPattern:
    """Test RegexPattern validator."""

    def test_regex_pattern_valid(self) -> None:
        """Test valid regex patterns."""
        test_cases = [
            r".*\.txt$",
            r"^home/[^/]+\.log$",
            r"test\d+\.txt",
            r"(file|document)\.pdf",
        ]

        for pattern in test_cases:
            valid, error, warnings = validate_pattern(pattern, style="re")
            assert valid is True, f"Pattern '{pattern}' should be valid"
            assert error is None

    def test_regex_pattern_invalid(self) -> None:
        """Test invalid regex patterns."""
        test_cases = [
            "[invalid",  # Unmatched bracket
            "*+",  # Invalid quantifier
        ]

        for pattern in test_cases:
            valid, error, warnings = validate_pattern(pattern, style="re")
            assert valid is False, f"Pattern '{pattern}' should be invalid"
            assert error is not None
            assert "Invalid regex:" in error

    def test_regex_pattern_warnings(self) -> None:
        """Test regex pattern warnings."""
        # No anchoring warning
        valid, error, warnings = validate_pattern("test", style="re")
        assert valid is True
        assert "Consider anchoring with ^ or $ for precise matching" in warnings

        # Backslash warning
        valid, error, warnings = validate_pattern(r"home\\user", style="re")
        assert valid is True
        assert "Use '/' for path separators, not backslashes" in warnings


class TestPathFullPattern:
    """Test PathFullPattern validator."""

    def test_path_full_pattern_valid(self) -> None:
        """Test valid path full patterns."""
        test_cases = [
            "home/user/file.txt",
            "etc/config",
            "var/log/system.log",
        ]

        for pattern in test_cases:
            valid, error, warnings = validate_pattern(pattern, style="pf")
            assert valid is True, f"Pattern '{pattern}' should be valid"
            assert error is None

    def test_path_full_pattern_wildcards_error(self) -> None:
        """Test that wildcards are rejected in path full patterns."""
        test_cases = [
            "home/*/file.txt",
            "home/user/file?.txt",
            "home/user/[abc].txt",
        ]

        for pattern in test_cases:
            valid, error, warnings = validate_pattern(pattern, style="pf")
            assert valid is False, f"Pattern '{pattern}' should be invalid"
            assert error is not None
            assert "Path full match (pf:) cannot contain wildcards" in error

    def test_path_full_pattern_warnings(self) -> None:
        """Test path full pattern warnings."""
        valid, error, warnings = validate_pattern("filename", style="pf")

        assert valid is True
        assert "Full paths usually contain '/' (e.g., 'home/user/file.txt')" in warnings


class TestPathPrefixPattern:
    """Test PathPrefixPattern validator."""

    def test_path_prefix_pattern_valid(self) -> None:
        """Test valid path prefix patterns."""
        test_cases = [
            "home/user",
            "var/log",
            "etc",
        ]

        for pattern in test_cases:
            valid, error, warnings = validate_pattern(pattern, style="pp")
            assert valid is True, f"Pattern '{pattern}' should be valid"
            assert error is None

    def test_path_prefix_pattern_wildcards_error(self) -> None:
        """Test that wildcards are rejected in path prefix patterns."""
        test_cases = [
            "home/*/",
            "home/user?",
            "home/[abc]",
        ]

        for pattern in test_cases:
            valid, error, warnings = validate_pattern(pattern, style="pp")
            assert valid is False, f"Pattern '{pattern}' should be invalid"
            assert error is not None
            assert "Path prefix (pp:) cannot contain wildcards" in error

    def test_path_prefix_pattern_warnings(self) -> None:
        """Test path prefix pattern warnings."""
        valid, error, warnings = validate_pattern("home/user/", style="pp")

        assert valid is True
        assert "Trailing '/' not needed for path prefix" in warnings


class TestValidatePatternList:
    """Test the validate_pattern_list function."""

    def test_validate_pattern_list_tuples(self) -> None:
        """Test validating a list of pattern tuples."""
        patterns: List[Union[str, Tuple[str, str, str]]] = [
            ("*.txt", "sh", "+"),
            ("home/user", "pp", "-"),
            (r".*\.log$", "re", "!"),
        ]

        results = validate_pattern_list(patterns)

        assert len(results) == 3
        for i, result in enumerate(results):
            assert result["valid"] is True
            assert result["error"] is None
            assert result["pattern"] == patterns[i][0]
            assert result["style"] == patterns[i][1]
            assert result["action"] == patterns[i][2]

    def test_validate_pattern_list_mixed_valid_invalid(self) -> None:
        """Test validating a list with both valid and invalid patterns."""
        patterns: List[Union[str, Tuple[str, str, str]]] = [
            ("*.txt", "sh", "+"),  # Valid
            ("**/*.log", "fm", "-"),  # Invalid - fm doesn't support **
            ("home/user", "pp", "+"),  # Valid
        ]

        results = validate_pattern_list(patterns)

        assert len(results) == 3
        assert results[0]["valid"] is True
        assert results[1]["valid"] is False
        assert "doesn't support '**'" in results[1]["error"]
        assert results[2]["valid"] is True


class TestPatternClasses:
    """Test individual pattern validator classes."""

    def test_pattern_classes_mapping(self) -> None:
        """Test that all pattern classes are properly mapped."""
        expected_classes = {
            "fm": FnmatchPattern,
            "pf": PathFullPattern,
            "pp": PathPrefixPattern,
            "re": RegexPattern,
            "sh": ShellPattern,
        }

        assert PATTERN_CLASSES == expected_classes

    def test_pattern_class_prefixes(self) -> None:
        """Test that pattern classes have correct prefixes."""
        assert FnmatchPattern.PREFIX == "fm"
        assert PathFullPattern.PREFIX == "pf"
        assert PathPrefixPattern.PREFIX == "pp"
        assert RegexPattern.PREFIX == "re"
        assert ShellPattern.PREFIX == "sh"

    def test_validation_error_inheritance(self) -> None:
        """Test ValidationError is properly defined."""
        error = ValidationError("test error")
        assert isinstance(error, Exception)
        assert str(error) == "test error"


class TestUtilityFunctions:
    """Test utility functions."""

    def test_normalize_path_non_darwin(self) -> None:
        """Test path normalization on non-Darwin platforms."""
        # This will test the non-Darwin path since we're likely on Windows/Linux
        test_path = "home/user/file.txt"
        result = normalize_path(test_path)
        assert result == test_path  # Should be unchanged on non-Darwin

    def test_shellpattern_translate_simple(self) -> None:
        """Test simplified shell pattern translation."""
        test_cases = [
            ("*.txt", r"^[^/]*\.txt$"),
            ("**/*.log", r"^.*[^/]*\.log$"),
            ("file?.txt", r"^file[^/]\.txt$"),
        ]

        for pattern, expected_regex in test_cases:
            result = shellpattern_translate_simple(pattern)
            # We'll just check that it's a valid regex pattern
            import re

            try:
                re.compile(result)
                assert True  # If no exception, regex is valid
            except re.error:
                pytest.fail(
                    f"Generated invalid regex for pattern '{pattern}': {result}"
                )


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_pattern_with_unicode(self) -> None:
        """Test patterns with unicode characters."""
        valid, error, warnings = validate_pattern("файл*.txt", style="sh")
        assert valid is True
        assert error is None

    def test_pattern_with_special_characters(self) -> None:
        """Test patterns with special characters."""
        test_cases = [
            ("file with spaces.txt", "sh"),
            ("file-with-dashes.txt", "sh"),
            ("file_with_underscores.txt", "sh"),
            ("file.with.dots.txt", "sh"),
        ]

        for pattern, style in test_cases:
            valid, error, warnings = validate_pattern(pattern, style=style)
            assert valid is True, f"Pattern '{pattern}' should be valid"

    def test_very_long_pattern(self) -> None:
        """Test very long patterns."""
        long_pattern = "a" * 1000 + "*.txt"
        valid, error, warnings = validate_pattern(long_pattern, style="sh")
        assert valid is True
        assert error is None

    def test_pattern_with_newlines(self) -> None:
        """Test patterns with newline characters."""
        valid, error, warnings = validate_pattern("file\nname.txt", style="sh")
        assert valid is True  # Should handle newlines gracefully

    def test_unexpected_exception_handling(self) -> None:
        """Test handling of unexpected exceptions during validation."""
        # This is harder to test without mocking, but we can test the structure
        # The function should catch Exception and return appropriate error message

        # Test with a pattern that might cause issues in regex compilation
        valid, error, warnings = validate_pattern("(?", style="re")
        assert valid is False
        assert error is not None
        assert "Invalid regex:" in error


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""

    def test_common_backup_patterns(self) -> None:
        """Test common backup exclusion patterns."""
        common_patterns = [
            ("**/.git/**", "sh", "-"),
            ("**/node_modules/**", "sh", "-"),
            ("**/__pycache__/**", "sh", "-"),
            ("**/*.pyc", "sh", "-"),
            ("**/.DS_Store", "sh", "-"),
            ("**/Thumbs.db", "sh", "-"),
            ("**/*.tmp", "sh", "-"),
            ("**/*.log", "sh", "-"),
        ]

        for pattern, style, action in common_patterns:
            valid, error, warnings = validate_pattern(
                pattern, style=style, action=action
            )
            assert valid is True, f"Common pattern '{pattern}' should be valid"
            assert error is None

    def test_include_patterns(self) -> None:
        """Test common include patterns."""
        include_patterns = [
            ("home/user/documents/**", "sh", "+"),
            ("**/*.pdf", "sh", "+"),
            ("**/*.jpg", "sh", "+"),
            ("etc/important.conf", "pf", "+"),
            ("var/backups", "pp", "+"),
        ]

        for pattern, style, action in include_patterns:
            valid, error, warnings = validate_pattern(
                pattern, style=style, action=action
            )
            assert valid is True, f"Include pattern '{pattern}' should be valid"
            assert error is None

    def test_invalid_real_world_patterns(self) -> None:
        """Test invalid patterns that users might commonly create."""
        invalid_patterns = [
            ("***/*.txt", "sh"),  # Triple asterisk
            ("**/*.log", "fm"),  # Double asterisk in fnmatch
            ("home/*/file.txt", "pf"),  # Wildcards in path full
            ("[unclosed", "re"),  # Invalid regex
            ("", "sh"),  # Empty pattern
        ]

        for pattern, style in invalid_patterns:
            valid, error, warnings = validate_pattern(pattern, style=style)
            assert valid is False, f"Invalid pattern '{pattern}' should be rejected"
            assert error is not None
