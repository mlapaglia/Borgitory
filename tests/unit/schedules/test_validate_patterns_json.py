"""
Tests for validate_patterns_json function from schemas.py.
"""

import json

from borgitory.models.schemas import validate_patterns_json


class TestValidatePatternsJsonBasic:
    """Test basic functionality of validate_patterns_json."""

    def test_empty_string_valid(self) -> None:
        """Test that empty string is considered valid."""
        is_valid, error = validate_patterns_json("")
        assert is_valid is True
        assert error is None

    def test_whitespace_only_valid(self) -> None:
        """Test that whitespace-only string is considered valid."""
        is_valid, error = validate_patterns_json("   \n\t  ")
        assert is_valid is True
        assert error is None

    def test_none_like_empty_valid(self) -> None:
        """Test that None-like empty values are valid."""
        test_cases = ["", "   ", "\n", "\t"]
        for test_case in test_cases:
            is_valid, error = validate_patterns_json(test_case)
            assert is_valid is True, f"Should be valid for '{repr(test_case)}'"
            assert error is None


class TestValidatePatternsJsonValidCases:
    """Test valid pattern JSON configurations."""

    def test_single_valid_pattern(self) -> None:
        """Test validation with a single valid pattern."""
        patterns = [
            {
                "name": "Exclude logs",
                "expression": "**/*.log",
                "pattern_type": "exclude",
                "style": "sh",
            }
        ]
        patterns_json = json.dumps(patterns)

        is_valid, error = validate_patterns_json(patterns_json)
        assert is_valid is True
        assert error is None

    def test_multiple_valid_patterns(self) -> None:
        """Test validation with multiple valid patterns."""
        patterns = [
            {
                "name": "Include documents",
                "expression": "**/*.pdf",
                "pattern_type": "include",
                "style": "sh",
            },
            {
                "name": "Exclude cache",
                "expression": "**/__pycache__/**",
                "pattern_type": "exclude",
                "style": "sh",
            },
            {
                "name": "Exclude no-recurse temp",
                "expression": "*.tmp",
                "pattern_type": "exclude_norec",
                "style": "fm",
            },
        ]
        patterns_json = json.dumps(patterns)

        is_valid, error = validate_patterns_json(patterns_json)
        assert is_valid is True
        assert error is None

    def test_all_pattern_types_valid(self) -> None:
        """Test all valid pattern types."""
        pattern_types = ["include", "exclude", "exclude_norec"]

        for pattern_type in pattern_types:
            patterns = [
                {
                    "name": f"Test {pattern_type}",
                    "expression": "*.txt",
                    "pattern_type": pattern_type,
                    "style": "sh",
                }
            ]
            patterns_json = json.dumps(patterns)

            is_valid, error = validate_patterns_json(patterns_json)
            assert is_valid is True, f"Pattern type '{pattern_type}' should be valid"
            assert error is None

    def test_all_pattern_styles_valid(self) -> None:
        """Test all valid pattern styles."""
        pattern_styles = ["sh", "fm", "re", "pp", "pf"]

        for style in pattern_styles:
            # Use appropriate expressions for each style
            expression_map = {
                "sh": "**/*.txt",
                "fm": "*.txt",
                "re": r".*\.txt$",
                "pp": "home/user",
                "pf": "home/user/file.txt",
            }

            patterns = [
                {
                    "name": f"Test {style}",
                    "expression": expression_map[style],
                    "pattern_type": "include",
                    "style": style,
                }
            ]
            patterns_json = json.dumps(patterns)

            is_valid, error = validate_patterns_json(patterns_json)
            assert is_valid is True, f"Pattern style '{style}' should be valid"
            assert error is None

    def test_complex_valid_patterns(self) -> None:
        """Test complex but valid pattern configurations."""
        patterns = [
            {
                "name": "Include user documents",
                "expression": "home/*/documents/**",
                "pattern_type": "include",
                "style": "sh",
            },
            {
                "name": "Exclude git directories",
                "expression": "**/.git/**",
                "pattern_type": "exclude",
                "style": "sh",
            },
            {
                "name": "Regex exclude logs",
                "expression": r".*\.log$",
                "pattern_type": "exclude",
                "style": "re",
            },
            {
                "name": "Path prefix include",
                "expression": "var/backups",
                "pattern_type": "include",
                "style": "pp",
            },
            {
                "name": "Exact file match",
                "expression": "etc/important.conf",
                "pattern_type": "include",
                "style": "pf",
            },
        ]
        patterns_json = json.dumps(patterns)

        is_valid, error = validate_patterns_json(patterns_json)
        assert is_valid is True
        assert error is None


class TestValidatePatternsJsonInvalidJson:
    """Test invalid JSON format cases."""

    def test_invalid_json_syntax(self) -> None:
        """Test invalid JSON syntax."""
        invalid_json_cases = [
            "{invalid json}",
            "[{name: 'test'}]",  # Missing quotes
            "[{'name': 'test',}]",  # Trailing comma
            "{'single': 'quotes'}",  # Single quotes
            '[{"name": "test"]',  # Missing closing brace
        ]

        for invalid_json in invalid_json_cases:
            is_valid, error = validate_patterns_json(invalid_json)
            assert is_valid is False, f"Should be invalid for: {invalid_json}"
            assert error == "Invalid JSON format"

    def test_non_list_json(self) -> None:
        """Test JSON that's not a list."""
        non_list_cases = [
            "{}",  # Empty object
            '{"name": "test"}',  # Single object
            '"string"',  # String
            "123",  # Number
            "true",  # Boolean
        ]

        for non_list in non_list_cases:
            is_valid, error = validate_patterns_json(non_list)
            assert is_valid is False, f"Should be invalid for: {non_list}"
            assert error == "Patterns must be a list"


class TestValidatePatternsJsonMissingFields:
    """Test cases with missing required fields."""

    def test_missing_name_field(self) -> None:
        """Test pattern missing name field."""
        patterns = [{"expression": "*.txt", "pattern_type": "include", "style": "sh"}]
        patterns_json = json.dumps(patterns)

        is_valid, error = validate_patterns_json(patterns_json)
        assert is_valid is False
        assert error == "Pattern 1 missing required field: name"

    def test_missing_expression_field(self) -> None:
        """Test pattern missing expression field."""
        patterns = [{"name": "Test pattern", "pattern_type": "include", "style": "sh"}]
        patterns_json = json.dumps(patterns)

        is_valid, error = validate_patterns_json(patterns_json)
        assert is_valid is False
        assert error == "Pattern 1 missing required field: expression"

    def test_missing_pattern_type_field(self) -> None:
        """Test pattern missing pattern_type field."""
        patterns = [{"name": "Test pattern", "expression": "*.txt", "style": "sh"}]
        patterns_json = json.dumps(patterns)

        is_valid, error = validate_patterns_json(patterns_json)
        assert is_valid is False
        assert error == "Pattern 1 missing required field: pattern_type"

    def test_missing_style_field(self) -> None:
        """Test pattern missing style field."""
        patterns = [
            {"name": "Test pattern", "expression": "*.txt", "pattern_type": "include"}
        ]
        patterns_json = json.dumps(patterns)

        is_valid, error = validate_patterns_json(patterns_json)
        assert is_valid is False
        assert error == "Pattern 1 missing required field: style"

    def test_missing_multiple_fields(self) -> None:
        """Test pattern missing multiple fields - should report first missing."""
        patterns = [{"expression": "*.txt"}]
        patterns_json = json.dumps(patterns)

        is_valid, error = validate_patterns_json(patterns_json)
        assert is_valid is False
        assert error is not None
        assert "Pattern 1 missing required field:" in error


class TestValidatePatternsJsonInvalidValues:
    """Test cases with invalid field values."""

    def test_invalid_pattern_type(self) -> None:
        """Test invalid pattern_type values."""
        invalid_types = ["invalid", "INCLUDE", "Include", "inc", "exc", ""]

        for invalid_type in invalid_types:
            patterns = [
                {
                    "name": "Test pattern",
                    "expression": "*.txt",
                    "pattern_type": invalid_type,
                    "style": "sh",
                }
            ]
            patterns_json = json.dumps(patterns)

            is_valid, error = validate_patterns_json(patterns_json)
            assert is_valid is False, (
                f"Should be invalid for pattern_type: {invalid_type}"
            )
            assert error is not None
            assert f"Pattern 1 has invalid pattern_type: {invalid_type}" in error

    def test_invalid_style(self) -> None:
        """Test invalid style values."""
        invalid_styles = ["invalid", "shell", "SH", "regex", "fnmatch", ""]

        for invalid_style in invalid_styles:
            patterns = [
                {
                    "name": "Test pattern",
                    "expression": "*.txt",
                    "pattern_type": "include",
                    "style": invalid_style,
                }
            ]
            patterns_json = json.dumps(patterns)

            is_valid, error = validate_patterns_json(patterns_json)
            assert is_valid is False, f"Should be invalid for style: {invalid_style}"
            assert error is not None
            assert f"Pattern 1 has invalid style: {invalid_style}" in error

    def test_non_dict_pattern_item(self) -> None:
        """Test pattern list containing non-dict items."""
        invalid_patterns = [
            ["string_item"],
            [123],
            [True],
            [None],
            [["nested", "list"]],
        ]

        for invalid_pattern in invalid_patterns:
            patterns_json = json.dumps(invalid_pattern)

            is_valid, error = validate_patterns_json(patterns_json)
            assert is_valid is False
            assert error == "Pattern 1 must be an object"


class TestValidatePatternsJsonPatternValidation:
    """Test actual pattern expression validation."""

    def test_invalid_shell_pattern(self) -> None:
        """Test invalid shell pattern expressions."""
        patterns = [
            {
                "name": "Invalid shell pattern",
                "expression": "***/*.txt",  # Triple asterisk not allowed
                "pattern_type": "exclude",
                "style": "sh",
            }
        ]
        patterns_json = json.dumps(patterns)

        is_valid, error = validate_patterns_json(patterns_json)
        assert is_valid is False
        assert error is not None
        assert "Pattern 1 (Invalid shell pattern) is invalid:" in error
        assert "Use '**' not '***' for recursive matching" in error

    def test_invalid_fnmatch_pattern(self) -> None:
        """Test invalid fnmatch pattern expressions."""
        patterns = [
            {
                "name": "Invalid fnmatch pattern",
                "expression": "**/*.txt",  # Double asterisk not supported in fnmatch
                "pattern_type": "exclude",
                "style": "fm",
            }
        ]
        patterns_json = json.dumps(patterns)

        is_valid, error = validate_patterns_json(patterns_json)
        assert is_valid is False
        assert error is not None
        assert "Pattern 1 (Invalid fnmatch pattern) is invalid:" in error
        assert "doesn't support '**'" in error

    def test_invalid_regex_pattern(self) -> None:
        """Test invalid regex pattern expressions."""
        patterns = [
            {
                "name": "Invalid regex pattern",
                "expression": "[invalid",  # Unmatched bracket
                "pattern_type": "exclude",
                "style": "re",
            }
        ]
        patterns_json = json.dumps(patterns)

        is_valid, error = validate_patterns_json(patterns_json)
        assert is_valid is False
        assert error is not None
        assert "Pattern 1 (Invalid regex pattern) is invalid:" in error
        assert "Invalid regex:" in error

    def test_invalid_path_full_pattern(self) -> None:
        """Test invalid path full pattern expressions."""
        patterns = [
            {
                "name": "Invalid path full pattern",
                "expression": "home/*/file.txt",  # Wildcards not allowed in pf
                "pattern_type": "include",
                "style": "pf",
            }
        ]
        patterns_json = json.dumps(patterns)

        is_valid, error = validate_patterns_json(patterns_json)
        assert is_valid is False
        assert error is not None
        assert "Pattern 1 (Invalid path full pattern) is invalid:" in error
        assert "cannot contain wildcards" in error

    def test_invalid_path_prefix_pattern(self) -> None:
        """Test invalid path prefix pattern expressions."""
        patterns = [
            {
                "name": "Invalid path prefix pattern",
                "expression": "home/user?",  # Wildcards not allowed in pp
                "pattern_type": "include",
                "style": "pp",
            }
        ]
        patterns_json = json.dumps(patterns)

        is_valid, error = validate_patterns_json(patterns_json)
        assert is_valid is False
        assert error is not None
        assert "Pattern 1 (Invalid path prefix pattern) is invalid:" in error
        assert "cannot contain wildcards" in error


class TestValidatePatternsJsonMultiplePatterns:
    """Test validation with multiple patterns."""

    def test_multiple_patterns_first_invalid(self) -> None:
        """Test multiple patterns where first is invalid."""
        patterns = [
            {
                "name": "Invalid pattern",
                "expression": "***/*.txt",  # Invalid
                "pattern_type": "exclude",
                "style": "sh",
            },
            {
                "name": "Valid pattern",
                "expression": "*.log",
                "pattern_type": "exclude",
                "style": "sh",
            },
        ]
        patterns_json = json.dumps(patterns)

        is_valid, error = validate_patterns_json(patterns_json)
        assert is_valid is False
        assert error is not None
        assert "Pattern 1 (Invalid pattern) is invalid:" in error

    def test_multiple_patterns_second_invalid(self) -> None:
        """Test multiple patterns where second is invalid."""
        patterns = [
            {
                "name": "Valid pattern",
                "expression": "*.log",
                "pattern_type": "exclude",
                "style": "sh",
            },
            {
                "name": "Invalid pattern",
                "expression": "***/*.txt",  # Invalid
                "pattern_type": "exclude",
                "style": "sh",
            },
        ]
        patterns_json = json.dumps(patterns)

        is_valid, error = validate_patterns_json(patterns_json)
        assert is_valid is False
        assert error is not None
        assert "Pattern 2 (Invalid pattern) is invalid:" in error

    def test_multiple_patterns_missing_field_in_second(self) -> None:
        """Test multiple patterns where second is missing a field."""
        patterns = [
            {
                "name": "Valid pattern",
                "expression": "*.log",
                "pattern_type": "exclude",
                "style": "sh",
            },
            {
                "name": "Invalid pattern",
                "expression": "*.txt",
                "pattern_type": "exclude",
                # Missing style field
            },
        ]
        patterns_json = json.dumps(patterns)

        is_valid, error = validate_patterns_json(patterns_json)
        assert is_valid is False
        assert error == "Pattern 2 missing required field: style"


class TestValidatePatternsJsonEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_list_valid(self) -> None:
        """Test that empty list is valid."""
        patterns_json = "[]"

        is_valid, error = validate_patterns_json(patterns_json)
        assert is_valid is True
        assert error is None

    def test_pattern_with_unicode_characters(self) -> None:
        """Test patterns with unicode characters."""
        patterns = [
            {
                "name": "Unicode pattern",
                "expression": "файл*.txt",
                "pattern_type": "include",
                "style": "sh",
            }
        ]
        patterns_json = json.dumps(patterns, ensure_ascii=False)

        is_valid, error = validate_patterns_json(patterns_json)
        assert is_valid is True
        assert error is None

    def test_pattern_with_special_characters_in_name(self) -> None:
        """Test patterns with special characters in name."""
        patterns = [
            {
                "name": "Pattern with special chars: !@#$%^&*()",
                "expression": "*.txt",
                "pattern_type": "include",
                "style": "sh",
            }
        ]
        patterns_json = json.dumps(patterns)

        is_valid, error = validate_patterns_json(patterns_json)
        assert is_valid is True
        assert error is None

    def test_very_long_pattern_name(self) -> None:
        """Test pattern with very long name."""
        long_name = "A" * 1000
        patterns = [
            {
                "name": long_name,
                "expression": "*.txt",
                "pattern_type": "include",
                "style": "sh",
            }
        ]
        patterns_json = json.dumps(patterns)

        is_valid, error = validate_patterns_json(patterns_json)
        assert is_valid is True
        assert error is None

    def test_very_long_pattern_expression(self) -> None:
        """Test pattern with very long expression."""
        long_expression = "a" * 1000 + "*.txt"
        patterns = [
            {
                "name": "Long expression pattern",
                "expression": long_expression,
                "pattern_type": "include",
                "style": "sh",
            }
        ]
        patterns_json = json.dumps(patterns)

        is_valid, error = validate_patterns_json(patterns_json)
        assert is_valid is True
        assert error is None


class TestValidatePatternsJsonRealWorldScenarios:
    """Test realistic scenarios that might occur in production."""

    def test_common_backup_exclusion_patterns(self) -> None:
        """Test common backup exclusion patterns."""
        patterns = [
            {
                "name": "Exclude git directories",
                "expression": "**/.git/**",
                "pattern_type": "exclude",
                "style": "sh",
            },
            {
                "name": "Exclude node modules",
                "expression": "**/node_modules/**",
                "pattern_type": "exclude",
                "style": "sh",
            },
            {
                "name": "Exclude Python cache",
                "expression": "**/__pycache__/**",
                "pattern_type": "exclude",
                "style": "sh",
            },
            {
                "name": "Exclude compiled Python files",
                "expression": "**/*.pyc",
                "pattern_type": "exclude",
                "style": "sh",
            },
            {
                "name": "Exclude temporary files",
                "expression": "**/*.tmp",
                "pattern_type": "exclude",
                "style": "sh",
            },
        ]
        patterns_json = json.dumps(patterns)

        is_valid, error = validate_patterns_json(patterns_json)
        assert is_valid is True
        assert error is None

    def test_mixed_include_exclude_patterns(self) -> None:
        """Test mixed include and exclude patterns."""
        patterns = [
            {
                "name": "Include documents",
                "expression": "**/*.{pdf,doc,docx,txt}",
                "pattern_type": "include",
                "style": "sh",
            },
            {
                "name": "Include images",
                "expression": "**/*.{jpg,jpeg,png,gif}",
                "pattern_type": "include",
                "style": "sh",
            },
            {
                "name": "Exclude large files",
                "expression": "**/*.{iso,dmg,img}",
                "pattern_type": "exclude",
                "style": "sh",
            },
            {
                "name": "Exclude system files",
                "expression": "**/.DS_Store",
                "pattern_type": "exclude_norec",
                "style": "sh",
            },
        ]
        patterns_json = json.dumps(patterns)

        is_valid, error = validate_patterns_json(patterns_json)
        assert is_valid is True
        assert error is None

    def test_advanced_regex_patterns(self) -> None:
        """Test advanced regex patterns."""
        patterns = [
            {
                "name": "Log files with date",
                "expression": r".*\.log\.\d{4}-\d{2}-\d{2}$",
                "pattern_type": "exclude",
                "style": "re",
            },
            {
                "name": "Backup files",
                "expression": r".*\.(bak|backup|old)$",
                "pattern_type": "exclude",
                "style": "re",
            },
        ]
        patterns_json = json.dumps(patterns)

        is_valid, error = validate_patterns_json(patterns_json)
        assert is_valid is True
        assert error is None
