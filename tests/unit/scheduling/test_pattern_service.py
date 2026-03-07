"""
Tests for PatternService - Business logic for handling backup patterns.
"""

import json
from typing import List, Dict
from unittest.mock import Mock, patch

from borgitory.services.scheduling.pattern_service import PatternService
from borgitory.models.patterns import BackupPattern, PatternType, PatternStyle


class MockFormData:
    """Mock form data for testing."""

    def __init__(self, data: Dict[str, List[str]]) -> None:
        self.data = data

    def getlist(self, key: str) -> List[str]:
        """Mock getlist method."""
        value = self.data.get(key, [])
        return value if isinstance(value, list) else [value] if value else []


class TestPatternService:
    """Test suite for PatternService."""

    def test_extract_patterns_from_form_empty(self) -> None:
        """Test extracting patterns from empty form data."""
        form_data = MockFormData({})
        patterns = PatternService.extract_patterns_from_form(form_data)
        assert patterns == []

    def test_extract_patterns_from_form_single_pattern(self) -> None:
        """Test extracting a single pattern from form data."""
        form_data = MockFormData(
            {
                "pattern_name": ["Test Pattern"],
                "pattern_expression": ["*.pdf"],
                "pattern_action": ["include"],
                "pattern_style": ["sh"],
            }
        )

        patterns = PatternService.extract_patterns_from_form(form_data)

        assert len(patterns) == 1
        pattern = patterns[0]
        assert pattern.name == "Test Pattern"
        assert pattern.expression == "*.pdf"
        assert pattern.pattern_type == PatternType.INCLUDE
        assert pattern.style == PatternStyle.SHELL

    def test_extract_patterns_from_form_multiple_patterns(self) -> None:
        """Test extracting multiple patterns from form data."""
        form_data = MockFormData(
            {
                "pattern_name": ["Include PDFs", "Exclude Temp"],
                "pattern_expression": ["*.pdf", "/tmp/*"],
                "pattern_action": ["include", "exclude"],
                "pattern_style": ["sh", "fm"],
            }
        )

        patterns = PatternService.extract_patterns_from_form(form_data)

        assert len(patterns) == 2

        # First pattern
        assert patterns[0].name == "Include PDFs"
        assert patterns[0].expression == "*.pdf"
        assert patterns[0].pattern_type == PatternType.INCLUDE
        assert patterns[0].style == PatternStyle.SHELL

        # Second pattern
        assert patterns[1].name == "Exclude Temp"
        assert patterns[1].expression == "/tmp/*"
        assert patterns[1].pattern_type == PatternType.EXCLUDE
        assert patterns[1].style == PatternStyle.FNMATCH

    def test_extract_patterns_from_form_all_pattern_types(self) -> None:
        """Test extracting patterns with all pattern types."""
        form_data = MockFormData(
            {
                "pattern_name": ["Include", "Exclude", "Exclude No Rec"],
                "pattern_expression": ["*.txt", "*.log", "*.tmp"],
                "pattern_action": ["include", "exclude", "exclude_norec"],
                "pattern_style": ["sh", "sh", "sh"],
            }
        )

        patterns = PatternService.extract_patterns_from_form(form_data)

        assert len(patterns) == 3
        assert patterns[0].pattern_type == PatternType.INCLUDE
        assert patterns[1].pattern_type == PatternType.EXCLUDE
        assert patterns[2].pattern_type == PatternType.EXCLUDE_NOREC

    def test_extract_patterns_from_form_all_pattern_styles(self) -> None:
        """Test extracting patterns with all pattern styles."""
        form_data = MockFormData(
            {
                "pattern_name": ["Shell", "Fnmatch", "Regex", "PathPrefix", "PathFull"],
                "pattern_expression": [
                    "*.txt",
                    "*.log",
                    ".*\\.tmp",
                    "/home/",
                    "/home/user/file.txt",
                ],
                "pattern_action": [
                    "include",
                    "include",
                    "include",
                    "include",
                    "include",
                ],
                "pattern_style": ["sh", "fm", "re", "pp", "pf"],
            }
        )

        patterns = PatternService.extract_patterns_from_form(form_data)

        assert len(patterns) == 5
        assert patterns[0].style == PatternStyle.SHELL
        assert patterns[1].style == PatternStyle.FNMATCH
        assert patterns[2].style == PatternStyle.REGEX
        assert patterns[3].style == PatternStyle.PATH_PREFIX
        assert patterns[4].style == PatternStyle.PATH_FULL

    def test_extract_patterns_from_form_empty_fields(self) -> None:
        """Test extracting patterns with some empty fields."""
        form_data = MockFormData(
            {
                "pattern_name": ["Valid Pattern", ""],
                "pattern_expression": ["*.pdf", ""],
                "pattern_action": ["include", "exclude"],
                "pattern_style": ["sh", "fm"],
            }
        )

        patterns = PatternService.extract_patterns_from_form(form_data)

        assert len(patterns) == 2
        assert patterns[0].name == "Valid Pattern"
        assert patterns[0].expression == "*.pdf"
        assert patterns[1].name == ""
        assert patterns[1].expression == ""

    def test_convert_patterns_to_json_empty(self) -> None:
        """Test converting empty patterns to JSON."""
        form_data = MockFormData({})
        result = PatternService.convert_patterns_to_json(form_data)
        assert result is None

    def test_convert_patterns_to_json_valid_patterns(self) -> None:
        """Test converting valid patterns to JSON."""
        form_data = MockFormData(
            {
                "pattern_name": ["Test Pattern", "Another Pattern"],
                "pattern_expression": ["*.pdf", "*.log"],
                "pattern_action": ["include", "exclude"],
                "pattern_style": ["sh", "fm"],
            }
        )

        result = PatternService.convert_patterns_to_json(form_data)

        assert result is not None
        patterns_data = json.loads(result)
        assert len(patterns_data) == 2

        assert patterns_data[0]["name"] == "Test Pattern"
        assert patterns_data[0]["expression"] == "*.pdf"
        assert patterns_data[0]["pattern_type"] == "include"
        assert patterns_data[0]["style"] == "sh"

        assert patterns_data[1]["name"] == "Another Pattern"
        assert patterns_data[1]["expression"] == "*.log"
        assert patterns_data[1]["pattern_type"] == "exclude"
        assert patterns_data[1]["style"] == "fm"

    def test_convert_patterns_to_json_filters_empty_patterns(self) -> None:
        """Test that empty patterns are filtered out when converting to JSON."""
        form_data = MockFormData(
            {
                "pattern_name": ["Valid Pattern", "", "Another Valid"],
                "pattern_expression": ["*.pdf", "", "*.txt"],
                "pattern_action": ["include", "exclude", "include"],
                "pattern_style": ["sh", "fm", "sh"],
            }
        )

        result = PatternService.convert_patterns_to_json(form_data)

        assert result is not None
        patterns_data = json.loads(result)
        assert len(patterns_data) == 2  # Empty pattern filtered out
        assert patterns_data[0]["name"] == "Valid Pattern"
        assert patterns_data[1]["name"] == "Another Valid"

    def test_validate_patterns_for_save_valid(self) -> None:
        """Test validation with valid patterns."""
        form_data = MockFormData(
            {
                "pattern_name": ["Test Pattern"],
                "pattern_expression": ["*.pdf"],
                "pattern_action": ["include"],
                "pattern_style": ["sh"],
            }
        )

        is_valid, error = PatternService.validate_patterns_for_save(form_data)

        assert is_valid is True
        assert error is None

    def test_validate_patterns_for_save_missing_name(self) -> None:
        """Test validation with missing pattern name."""
        form_data = MockFormData(
            {
                "pattern_name": [""],
                "pattern_expression": ["*.pdf"],
                "pattern_action": ["include"],
                "pattern_style": ["sh"],
            }
        )

        is_valid, error = PatternService.validate_patterns_for_save(form_data)

        assert is_valid is False
        assert error is not None
        assert "Pattern #1: Pattern name is required" in error

    def test_validate_patterns_for_save_missing_expression(self) -> None:
        """Test validation with missing pattern expression."""
        form_data = MockFormData(
            {
                "pattern_name": ["Test Pattern"],
                "pattern_expression": [""],
                "pattern_action": ["include"],
                "pattern_style": ["sh"],
            }
        )

        is_valid, error = PatternService.validate_patterns_for_save(form_data)

        assert is_valid is False
        assert error is not None
        assert "Pattern #1: Pattern expression is required" in error

    def test_validate_patterns_for_save_multiple_errors(self) -> None:
        """Test validation with multiple errors."""
        form_data = MockFormData(
            {
                "pattern_name": ["", "Valid", ""],
                "pattern_expression": ["*.pdf", "", "*.txt"],
                "pattern_action": ["include", "exclude", "include"],
                "pattern_style": ["sh", "fm", "sh"],
            }
        )

        is_valid, error = PatternService.validate_patterns_for_save(form_data)

        assert is_valid is False
        assert error is not None
        assert "Pattern #1: Pattern name is required" in error
        assert "Pattern #2: Pattern expression is required" in error
        assert "Pattern #3: Pattern name is required" in error

    def test_validate_patterns_for_save_ignores_empty_patterns(self) -> None:
        """Test that completely empty patterns are ignored during validation."""
        form_data = MockFormData(
            {
                "pattern_name": ["Valid Pattern", ""],
                "pattern_expression": ["*.pdf", ""],
                "pattern_action": ["include", "exclude"],
                "pattern_style": ["sh", "fm"],
            }
        )

        is_valid, error = PatternService.validate_patterns_for_save(form_data)

        assert is_valid is True
        assert error is None

    def test_convert_patterns_from_form_data_dict_format(self) -> None:
        """Test converting patterns from dictionary form data."""
        form_data = {
            "pattern_name": ["Test Pattern", "Another Pattern"],
            "pattern_expression": ["*.pdf", "*.log"],
            "pattern_action": ["include", "exclude"],
            "pattern_style": ["sh", "fm"],
        }

        result = PatternService.convert_patterns_from_form_data(form_data)

        assert result is not None
        patterns_data = json.loads(result)
        assert len(patterns_data) == 2
        assert patterns_data[0]["name"] == "Test Pattern"
        assert patterns_data[1]["name"] == "Another Pattern"

    def test_convert_patterns_from_form_data_single_values(self) -> None:
        """Test converting patterns from form data with single values (not lists)."""
        form_data = {
            "pattern_name": "Single Pattern",
            "pattern_expression": "*.pdf",
            "pattern_action": "include",
            "pattern_style": "sh",
        }

        result = PatternService.convert_patterns_from_form_data(form_data)

        assert result is not None
        patterns_data = json.loads(result)
        assert len(patterns_data) == 1
        assert patterns_data[0]["name"] == "Single Pattern"

    def test_parse_patterns_from_json_empty(self) -> None:
        """Test parsing patterns from empty JSON."""
        patterns = PatternService.parse_patterns_from_json("")
        assert patterns == []

        patterns = PatternService.parse_patterns_from_json("[]")
        assert patterns == []

    def test_parse_patterns_from_json_valid(self) -> None:
        """Test parsing patterns from valid JSON."""
        json_data = json.dumps(
            [
                {
                    "name": "Test Pattern",
                    "expression": "*.pdf",
                    "pattern_type": "include",
                    "style": "sh",
                },
                {
                    "name": "Exclude Pattern",
                    "expression": "*.log",
                    "pattern_type": "exclude",
                    "style": "fm",
                },
            ]
        )

        patterns = PatternService.parse_patterns_from_json(json_data)

        assert len(patterns) == 2
        assert patterns[0].name == "Test Pattern"
        assert patterns[0].expression == "*.pdf"
        assert patterns[0].pattern_type == PatternType.INCLUDE
        assert patterns[0].style == PatternStyle.SHELL

        assert patterns[1].name == "Exclude Pattern"
        assert patterns[1].expression == "*.log"
        assert patterns[1].pattern_type == PatternType.EXCLUDE
        assert patterns[1].style == PatternStyle.FNMATCH

    def test_parse_patterns_from_json_invalid(self) -> None:
        """Test parsing patterns from invalid JSON."""
        patterns = PatternService.parse_patterns_from_json("invalid json")
        assert patterns == []

        patterns = PatternService.parse_patterns_from_json('{"not": "a list"}')
        assert patterns == []

    @patch("borgitory.services.scheduling.pattern_service.validate_pattern")
    def test_validate_all_patterns_success(self, mock_validate: Mock) -> None:
        """Test validating all patterns successfully."""
        mock_validate.return_value = (True, None, [])

        patterns = [
            BackupPattern(
                name="Test Pattern",
                expression="*.pdf",
                pattern_type=PatternType.INCLUDE,
                style=PatternStyle.SHELL,
            )
        ]

        results = PatternService.validate_all_patterns(patterns)

        assert len(results) == 1
        assert results[0]["is_valid"] is True
        assert results[0]["name"] == "Test Pattern"
        assert results[0]["error"] is None
        assert results[0]["warnings"] == []

    @patch("borgitory.services.scheduling.pattern_service.validate_pattern")
    def test_validate_all_patterns_with_errors(self, mock_validate: Mock) -> None:
        """Test validating patterns with errors."""
        mock_validate.return_value = (False, "Invalid pattern", ["Warning message"])

        patterns = [
            BackupPattern(
                name="Bad Pattern",
                expression="[invalid",
                pattern_type=PatternType.INCLUDE,
                style=PatternStyle.REGEX,
            )
        ]

        results = PatternService.validate_all_patterns(patterns)

        assert len(results) == 1
        assert results[0]["is_valid"] is False
        assert results[0]["name"] == "Bad Pattern"
        assert results[0]["error"] == "Invalid pattern"
        assert results[0]["warnings"] == ["Warning message"]

    def test_validate_all_patterns_empty_expression(self) -> None:
        """Test validating patterns with empty expressions."""
        patterns = [
            BackupPattern(
                name="Empty Expression",
                expression="",
                pattern_type=PatternType.INCLUDE,
                style=PatternStyle.SHELL,
            )
        ]

        results = PatternService.validate_all_patterns(patterns)

        assert len(results) == 1
        assert results[0]["is_valid"] is False
        assert results[0]["error"] == "Pattern expression is required"

    def test_validate_all_patterns_skips_empty(self) -> None:
        """Test that completely empty patterns are skipped during validation."""
        patterns = [
            BackupPattern(
                name="",
                expression="",
                pattern_type=PatternType.INCLUDE,
                style=PatternStyle.SHELL,
            ),
            BackupPattern(
                name="Valid Pattern",
                expression="*.pdf",
                pattern_type=PatternType.INCLUDE,
                style=PatternStyle.SHELL,
            ),
        ]

        with patch(
            "borgitory.services.scheduling.pattern_service.validate_pattern"
        ) as mock_validate:
            mock_validate.return_value = (True, None, [])
            results = PatternService.validate_all_patterns(patterns)

        # Only the valid pattern should be in results
        assert len(results) == 1
        assert results[0]["name"] == "Valid Pattern"

    def test_count_patterns_from_json_empty(self) -> None:
        """Test counting patterns from empty JSON."""
        assert PatternService.count_patterns_from_json(None) == 0
        assert PatternService.count_patterns_from_json("") == 0
        assert PatternService.count_patterns_from_json("[]") == 0

    def test_count_patterns_from_json_valid(self) -> None:
        """Test counting patterns from valid JSON."""
        json_data = json.dumps(
            [
                {"name": "Pattern 1", "expression": "*.pdf"},
                {"name": "Pattern 2", "expression": "*.log"},
            ]
        )

        count = PatternService.count_patterns_from_json(json_data)
        assert count == 2

    def test_count_patterns_from_json_invalid(self) -> None:
        """Test counting patterns from invalid JSON."""
        assert PatternService.count_patterns_from_json("invalid json") == 0
        assert PatternService.count_patterns_from_json('{"not": "a list"}') == 0
