"""
Pattern Service - Business logic for handling backup patterns.

This service encapsulates all pattern-related operations including:
- Converting form data to pattern objects
- Validating patterns
- Converting patterns to JSON format
- Extracting patterns from various data sources
"""

import json
from typing import List, Dict, Any, Optional

from borgitory.models.patterns import BackupPattern, PatternType, PatternStyle
from borgitory.services.borg.borg_pattern_validation_service import validate_pattern


class PatternService:
    """Service for handling backup pattern operations."""

    @staticmethod
    def extract_patterns_from_form(form_data: Any) -> List[BackupPattern]:
        """
        Extract patterns from form data and return as list of BackupPattern objects.

        Args:
            form_data: Form data containing pattern fields

        Returns:
            List of BackupPattern objects
        """
        patterns = []

        # Get all pattern data (new compact structure)
        pattern_names = form_data.getlist("pattern_name")
        pattern_expressions = form_data.getlist("pattern_expression")
        pattern_actions = form_data.getlist("pattern_action")
        pattern_styles = form_data.getlist("pattern_style")

        # Pair them up by position
        for i in range(
            min(len(pattern_names), len(pattern_expressions), len(pattern_actions))
        ):
            name = str(pattern_names[i]).strip() if pattern_names[i] else ""
            expression = (
                str(pattern_expressions[i]).strip() if pattern_expressions[i] else ""
            )
            action_str = (
                str(pattern_actions[i]).strip() if pattern_actions[i] else "include"
            )
            style_str = (
                str(pattern_styles[i]).strip()
                if len(pattern_styles) > i and pattern_styles[i]
                else "sh"
            )

            # Map action string to PatternType
            if action_str == "exclude":
                pattern_type = PatternType.EXCLUDE
            elif action_str == "exclude_norec":
                pattern_type = PatternType.EXCLUDE_NOREC
            else:
                pattern_type = PatternType.INCLUDE

            # Map style string to PatternStyle
            style_map = {
                "sh": PatternStyle.SHELL,
                "fm": PatternStyle.FNMATCH,
                "re": PatternStyle.REGEX,
                "pp": PatternStyle.PATH_PREFIX,
                "pf": PatternStyle.PATH_FULL,
            }
            pattern_style = style_map.get(style_str, PatternStyle.SHELL)

            # Add all patterns, even if name or expression is empty (for reordering)
            patterns.append(
                BackupPattern(
                    name=name,
                    expression=expression,
                    pattern_type=pattern_type,
                    style=pattern_style,
                )
            )

        return patterns

    @staticmethod
    def convert_patterns_to_json(form_data: Any) -> Optional[str]:
        """
        Convert patterns to JSON format using unified structure.

        Args:
            form_data: Form data containing pattern fields

        Returns:
            JSON string of valid patterns or None if no valid patterns
        """
        patterns = PatternService.extract_patterns_from_form(form_data)

        # Filter out patterns that don't have both name and expression for JSON output
        valid_patterns = [
            {
                "name": pattern.name,
                "expression": pattern.expression,
                "pattern_type": pattern.pattern_type.value,
                "style": pattern.style.value,
            }
            for pattern in patterns
            if pattern.name and pattern.expression
        ]

        return json.dumps(valid_patterns) if valid_patterns else None

    @staticmethod
    def validate_patterns_for_save(form_data: Any) -> tuple[bool, Optional[str]]:
        """
        Validate that all patterns have both name and expression filled out.

        Args:
            form_data: Form data containing pattern fields

        Returns:
            Tuple of (is_valid, error_message)
        """
        errors = []

        patterns = PatternService.extract_patterns_from_form(form_data)
        for i, pattern in enumerate(patterns):
            if not pattern.name.strip() and not pattern.expression.strip():
                # Empty pattern - skip (will be filtered out)
                continue
            elif not pattern.name.strip():
                errors.append(f"Pattern #{i + 1}: Pattern name is required")
            elif not pattern.expression.strip():
                errors.append(f"Pattern #{i + 1}: Pattern expression is required")

        if errors:
            return False, "; ".join(errors)
        return True, None

    @staticmethod
    def convert_patterns_from_form_data(form_data: Dict[str, Any]) -> Optional[str]:
        """
        Convert patterns form data to JSON format.

        Args:
            form_data: Dictionary containing pattern form data

        Returns:
            JSON string of patterns or None if no patterns
        """
        patterns = []

        # Get all pattern field data (position-based)
        pattern_names = form_data.get("pattern_name", [])
        pattern_expressions = form_data.get("pattern_expression", [])
        pattern_actions = form_data.get("pattern_action", [])
        pattern_styles = form_data.get("pattern_style", [])

        # Ensure they are lists (in case there's only one item)
        if not isinstance(pattern_names, list):
            pattern_names = [pattern_names] if pattern_names else []
        if not isinstance(pattern_expressions, list):
            pattern_expressions = [pattern_expressions] if pattern_expressions else []
        if not isinstance(pattern_actions, list):
            pattern_actions = [pattern_actions] if pattern_actions else []
        if not isinstance(pattern_styles, list):
            pattern_styles = [pattern_styles] if pattern_styles else []

        # Pair them up by position
        max_length = max(
            len(pattern_names),
            len(pattern_expressions),
            len(pattern_actions),
            len(pattern_styles),
        )
        for i in range(max_length):
            name = (
                str(pattern_names[i]).strip()
                if i < len(pattern_names) and pattern_names[i]
                else ""
            )
            expression = (
                str(pattern_expressions[i]).strip()
                if i < len(pattern_expressions) and pattern_expressions[i]
                else ""
            )
            action = (
                str(pattern_actions[i]).strip()
                if i < len(pattern_actions) and pattern_actions[i]
                else "include"
            )
            style = (
                str(pattern_styles[i]).strip()
                if i < len(pattern_styles) and pattern_styles[i]
                else "sh"
            )

            # Only add patterns that have both name and expression
            if name and expression:
                patterns.append(
                    {
                        "name": name,
                        "expression": expression,
                        "pattern_type": action,
                        "style": style,
                    }
                )

        return json.dumps(patterns) if patterns else None

    @staticmethod
    def parse_patterns_from_json(patterns_json: str) -> List[BackupPattern]:
        """
        Parse patterns from JSON string into BackupPattern objects.

        Args:
            patterns_json: JSON string containing pattern data

        Returns:
            List of BackupPattern objects
        """
        if not patterns_json or patterns_json.strip() == "[]":
            return []

        try:
            patterns_data = json.loads(patterns_json)
            if not isinstance(patterns_data, list):
                return []

            patterns = []
            for pattern_data in patterns_data:
                if isinstance(pattern_data, dict):
                    patterns.append(
                        BackupPattern(
                            name=pattern_data.get("name", ""),
                            expression=pattern_data.get("expression", ""),
                            pattern_type=PatternType(
                                pattern_data.get("pattern_type", "include")
                            ),
                            style=PatternStyle(pattern_data.get("style", "sh")),
                        )
                    )
            return patterns
        except (json.JSONDecodeError, ValueError, TypeError):
            return []

    @staticmethod
    def validate_all_patterns(patterns: List[BackupPattern]) -> List[Dict[str, Any]]:
        """
        Validate all patterns and return validation results.

        Args:
            patterns: List of BackupPattern objects to validate

        Returns:
            List of validation result dictionaries
        """
        validation_results = []

        for i, pattern in enumerate(patterns):
            # Skip empty patterns
            if not pattern.name.strip() and not pattern.expression.strip():
                continue

            # Check for required fields
            if not pattern.expression.strip():
                validation_results.append(
                    {
                        "index": i,
                        "name": pattern.name or f"Pattern #{i + 1}",
                        "is_valid": False,
                        "error": "Pattern expression is required",
                        "warnings": [],
                    }
                )
                continue

            # Map action to validation format
            action_map = {
                PatternType.INCLUDE: "+",
                PatternType.EXCLUDE: "-",
                PatternType.EXCLUDE_NOREC: "!",
            }
            action = action_map.get(pattern.pattern_type, "+")

            # Validate the pattern
            is_valid, error, warnings = validate_pattern(
                pattern_str=pattern.expression, style=pattern.style.value, action=action
            )

            validation_results.append(
                {
                    "index": i,
                    "name": pattern.name or f"Pattern #{i + 1}",
                    "is_valid": is_valid,
                    "error": error,
                    "warnings": warnings,
                }
            )

        return validation_results

    @staticmethod
    def count_patterns_from_json(patterns_json: Optional[str]) -> int:
        """
        Count the number of patterns in a JSON string.

        Args:
            patterns_json: JSON string containing pattern data

        Returns:
            Number of patterns
        """
        if not patterns_json:
            return 0

        try:
            patterns_data = json.loads(patterns_json)
            return len(patterns_data) if isinstance(patterns_data, list) else 0
        except (json.JSONDecodeError, TypeError):
            return 0
