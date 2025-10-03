import re
import fnmatch
import os.path
import sys
import unicodedata
from enum import Enum
from typing import Tuple, Optional, List, Union, Dict, Any


def normalize_path(path: str) -> str:
    """Normalize paths for MacOS (but do nothing on other platforms)"""
    return unicodedata.normalize("NFD", path) if sys.platform == "darwin" else path


class IECommand(Enum):
    """Include/Exclude command types"""

    Include = 3
    Exclude = 4
    ExcludeNoRecurse = 5


class ValidationError(Exception):
    """Raised when pattern validation fails"""

    pass


class PatternValidator:
    """Base class for pattern validation"""

    PREFIX: str = ""

    def __init__(self, pattern: str):
        self.pattern_orig = pattern
        pattern = normalize_path(pattern)
        try:
            self._prepare(pattern)
        except Exception as e:
            raise ValidationError(f"Invalid pattern: {e}")

    def _prepare(self, pattern: str) -> None:
        """Prepare the pattern for validation. Should set self.pattern"""
        raise NotImplementedError

    def get_warnings(self) -> List[str]:
        """Return any warnings for this pattern"""
        return []


class PathFullPattern(PatternValidator):
    """Full match of a path - pf:"""

    PREFIX = "pf"

    def _prepare(self, pattern: str) -> None:
        # Check for wildcards which aren't allowed
        if any(c in pattern for c in "*?[]"):
            raise ValidationError("Path full match (pf:) cannot contain wildcards")

        self.pattern = os.path.normpath(pattern).lstrip(os.path.sep)

    def get_warnings(self) -> List[str]:
        warnings = []
        if "/" not in self.pattern and self.pattern:
            warnings.append(
                "Full paths usually contain '/' (e.g., 'home/user/file.txt')"
            )
        return warnings


class PathPrefixPattern(PatternValidator):
    """Path prefix match - pp:"""

    PREFIX = "pp"

    def _prepare(self, pattern: str) -> None:
        # Check for wildcards which aren't allowed
        if any(c in pattern for c in "*?[]"):
            raise ValidationError("Path prefix (pp:) cannot contain wildcards")

        sep = os.path.sep
        self.pattern = (os.path.normpath(pattern).rstrip(sep) + sep).lstrip(sep)

    def get_warnings(self) -> List[str]:
        warnings = []
        if self.pattern_orig.endswith("/"):
            warnings.append("Trailing '/' not needed for path prefix")
        return warnings


class FnmatchPattern(PatternValidator):
    """Fnmatch pattern - fm:"""

    PREFIX = "fm"

    def _prepare(self, pattern: str) -> None:
        # Check for ** which isn't supported in fnmatch
        if "**" in pattern:
            raise ValidationError(
                "Fnmatch (fm:) doesn't support '**'. Use shell-style (sh:) instead"
            )

        # Check for unmatched brackets
        open_brackets = pattern.count("[")
        close_brackets = pattern.count("]")
        if open_brackets != close_brackets:
            raise ValidationError("Unmatched brackets in pattern")

        if pattern.endswith(os.path.sep):
            pattern = (
                os.path.normpath(pattern).rstrip(os.path.sep)
                + os.path.sep
                + "*"
                + os.path.sep
            )
        else:
            pattern = os.path.normpath(pattern) + os.path.sep + "*"

        self.pattern = pattern.lstrip(os.path.sep)

        # Validate that fnmatch can compile this
        try:
            self.regex = re.compile(fnmatch.translate(self.pattern))
        except re.error as e:
            raise ValidationError(f"Invalid fnmatch pattern: {e}")

    def get_warnings(self) -> List[str]:
        warnings = []
        if self.pattern_orig.startswith("/"):
            warnings.append("Leading '/' will be removed automatically")
        return warnings


class ShellPattern(PatternValidator):
    """Shell pattern - sh:"""

    PREFIX = "sh"

    def _prepare(self, pattern: str) -> None:
        # Check for common mistakes
        if "***" in pattern:
            raise ValidationError("Use '**' not '***' for recursive matching")

        sep = os.path.sep
        if pattern.endswith(sep):
            pattern = (
                os.path.normpath(pattern).rstrip(sep) + sep + "**" + sep + "*" + sep
            )
        else:
            pattern = os.path.normpath(pattern) + sep + "**" + sep + "*"

        self.pattern = pattern.lstrip(sep)

        # Validate using shellpattern translation
        try:
            # We need the shellpattern module from Borg
            from borgitory.services.borg import shell_pattern

            self.regex = re.compile(shell_pattern.translate(self.pattern))
        except ImportError:
            # Fallback validation without the shellpattern module
            self._validate_without_shellpattern(pattern)
        except re.error as e:
            raise ValidationError(f"Invalid shell pattern: {e}")

    def _validate_without_shellpattern(self, pattern: str) -> None:
        """Basic validation when shellpattern module isn't available"""
        # Convert to a simplified regex for validation purposes
        regex_pattern = re.escape(pattern)
        regex_pattern = regex_pattern.replace(r"\*\*/", "(?:.*/)?")
        regex_pattern = regex_pattern.replace(r"\*\*", ".*")
        regex_pattern = regex_pattern.replace(r"\*", "[^/]*")
        regex_pattern = regex_pattern.replace(r"\?", "[^/]")

        try:
            self.regex = re.compile("^" + regex_pattern)
        except re.error as e:
            raise ValidationError(f"Invalid shell pattern: {e}")

    def get_warnings(self) -> List[str]:
        warnings = []
        if self.pattern_orig.startswith("/"):
            warnings.append("Leading '/' will be removed automatically")
        if "**" in self.pattern_orig and "**/" not in self.pattern_orig:
            warnings.append(
                "'**' should typically be followed by '/' for directory recursion"
            )
        return warnings


class RegexPattern(PatternValidator):
    """Regular expression - re:"""

    PREFIX = "re"

    def _prepare(self, pattern: str) -> None:
        self.pattern = pattern  # sep at beginning is NOT removed for regex
        try:
            self.regex = re.compile(pattern)
        except re.error as e:
            raise ValidationError(f"Invalid regex: {e}")

    def get_warnings(self) -> List[str]:
        warnings = []
        if not self.pattern.startswith("^") and not self.pattern.endswith("$"):
            warnings.append("Consider anchoring with ^ or $ for precise matching")
        if "\\" in self.pattern and "\\/" not in self.pattern:
            warnings.append("Use '/' for path separators, not backslashes")
        return warnings


# Pattern class mapping
PATTERN_CLASSES = {
    "fm": FnmatchPattern,
    "pf": PathFullPattern,
    "pp": PathPrefixPattern,
    "re": RegexPattern,
    "sh": ShellPattern,
}


def validate_pattern(
    pattern_str: str, style: str = "", action: str = "+", fallback_style: str = "sh"
) -> Tuple[bool, Optional[str], List[str]]:
    """
    Validate a Borg pattern.

    Args:
        pattern_str: The pattern string (can include style prefix like "sh:pattern")
        style: Override style ('fm', 'pf', 'pp', 're', 'sh'). If None, detect from pattern.
        action: '+' for include, '-' for exclude, '!' for exclude no-recurse
        fallback_style: Default style if none specified (default: 'sh')

    Returns:
        (valid: bool, error: Optional[str], warnings: List[str])

    Examples:
        >>> validate_pattern("**/*.tmp", style="sh")
        (True, None, [])

        >>> validate_pattern("home/*/.cache", style="fm")
        (True, None, [])

        >>> validate_pattern("**/*.tmp", style="fm")
        (False, "Fnmatch (fm:) doesn't support '**'. Use shell-style (sh:) instead", [])
    """
    warnings: List[str] = []

    # Validate action
    if action not in ["+", "-", "!"]:
        return False, f"Invalid action: {action}. Must be '+', '-', or '!'", warnings

    # Empty pattern check
    if not pattern_str:
        return False, "Pattern cannot be empty", warnings

    # Extract style from pattern if not explicitly provided
    if style is None:
        if (
            len(pattern_str) > 2
            and pattern_str[2] == ":"
            and pattern_str[:2] in PATTERN_CLASSES
        ):
            style = pattern_str[:2]
            pattern_str = pattern_str[3:]
        else:
            style = fallback_style

    # Validate style
    if style not in PATTERN_CLASSES:
        return (
            False,
            f"Unknown pattern style: {style}. Valid: {', '.join(PATTERN_CLASSES.keys())}",
            warnings,
        )

    # Get the appropriate validator class
    validator_class = PATTERN_CLASSES[style]

    try:
        # Create validator instance (this will validate the pattern)
        validator = validator_class(pattern_str)

        # Get any warnings
        warnings.extend(validator.get_warnings())

        return True, None, warnings

    except ValidationError as e:
        return False, str(e), warnings
    except Exception as e:
        return False, f"Unexpected error: {e}", warnings


def validate_pattern_list(
    patterns: List[Union[str, Tuple[str, str, str]]],
) -> List[Dict[str, Any]]:
    """
    Validate a list of patterns.

    Args:
        patterns: List of either:
            - pattern strings (e.g., "**/*.tmp" or "sh:**/*.tmp")
            - tuples of (pattern, style, action)

    Returns:
        List of dicts with keys: 'pattern', 'valid', 'error', 'warnings'

    Example:
        >>> patterns = [
        ...     "**/*.tmp",
        ...     ("home/*/.cache", "fm", "-"),
        ...     ("^/etc/", "re", "+"),
        ... ]
        >>> results = validate_pattern_list(patterns)
    """
    results = []

    for item in patterns:
        if isinstance(item, str):
            pattern = item
            style = ""
            action = "-"  # Default to exclude
        elif isinstance(item, tuple) and len(item) == 3:
            pattern, style, action = item
        else:
            results.append(
                {
                    "pattern": str(item),
                    "valid": False,
                    "error": "Invalid pattern format",
                    "warnings": [],
                }
            )
            continue

        valid, error, warnings = validate_pattern(pattern, style, action)
        results.append(
            {
                "pattern": pattern,
                "style": style,
                "action": action,
                "valid": valid,
                "error": error,
                "warnings": warnings,
            }
        )

    return results


# Simplified shellpattern translation if the borg helper module isn't available
def shellpattern_translate_simple(pattern: str) -> str:
    """
    Simplified shell pattern to regex translation.
    This is a basic implementation when the full Borg shellpattern module isn't available.
    """
    # Escape the pattern
    regex = re.escape(pattern)

    # Replace shell wildcards with regex equivalents
    # Order matters here!
    regex = regex.replace(r"\*\*/", "(?:.*/)?")  # **/ matches zero or more directories
    regex = regex.replace(r"\*\*", ".*")  # ** matches anything
    regex = regex.replace(r"\*", "[^/]*")  # * matches anything except /
    regex = regex.replace(r"\?", "[^/]")  # ? matches single char except /

    # Handle character classes [...]
    regex = re.sub(
        r"\\(\[[^\]]*\])", lambda m: fnmatch.translate(m.group(1))[:-2], regex
    )

    return "^" + regex + "$"


if __name__ == "__main__":
    # Example usage
    test_patterns = [
        ("**/*.tmp", "sh", "-"),
        ("home/*/.cache", "fm", "-"),
        ("^home/[^/]+\\.tmp/$", "re", "-"),
        ("home/user/documents", "pp", "+"),
        ("home/user/file.txt", "pf", "+"),
        ("***/*.txt", "sh", "-"),  # Invalid
        ("home/**/.cache", "sh", "-"),
        ("**/*.iso", "fm", "-"),  # Invalid - fm doesn't support **
    ]

    print("Pattern Validation Results:")
    print("-" * 80)

    for pattern, style, action in test_patterns:
        valid, error, warnings = validate_pattern(pattern, style, action)

        print(f"Pattern: {pattern}")
        print(f"  Style: {style}, Action: {action}")
        print(f"  Valid: {valid}")
        if error:
            print(f"  Error: {error}")
        if warnings:
            print(f"  Warnings: {', '.join(warnings)}")
        print()
