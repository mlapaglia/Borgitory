"""Data models for backup patterns configuration."""

from dataclasses import dataclass
from typing import List
from enum import Enum


class PatternType(str, Enum):
    """Type of backup pattern."""

    INCLUDE = "include"
    EXCLUDE = "exclude"
    EXCLUDE_NOREC = "exclude_norec"


class PatternStyle(str, Enum):
    """Style of pattern matching."""

    SHELL = "sh"  # Shell-style (default)
    FNMATCH = "fm"  # Fnmatch - Legacy style
    REGEX = "re"  # Regular expression - Advanced users
    PATH_PREFIX = "pp"  # Path prefix - Include/exclude entire directories
    PATH_FULL = "pf"  # Path full-match - Exact path matching


@dataclass
class BackupPattern:
    """Represents a single backup pattern configuration."""

    name: str
    expression: str
    pattern_type: PatternType = PatternType.INCLUDE
    style: PatternStyle = PatternStyle.SHELL

    def to_borg_pattern(self) -> str:
        """Convert to borg pattern format."""
        if self.pattern_type == PatternType.INCLUDE:
            prefix = "+"
        elif self.pattern_type == PatternType.EXCLUDE:
            prefix = "-"
        else:  # EXCLUDE_NOREC
            prefix = "!"

        # Add style prefix if not default shell style
        if self.style != PatternStyle.SHELL:
            return f"{prefix}{self.style.value}:{self.expression}"
        else:
            return f"{prefix}{self.expression}"


@dataclass
class PatternsConfiguration:
    """Complete patterns configuration for a backup schedule."""

    include_patterns: List[BackupPattern]
    exclude_patterns: List[BackupPattern]

    def get_all_patterns_ordered(self) -> List[BackupPattern]:
        """Get all patterns in the order they should be processed."""
        # Include patterns first, then exclude patterns
        return self.include_patterns + self.exclude_patterns

    def to_borg_patterns_list(self) -> List[str]:
        """Convert all patterns to borg format."""
        return [
            pattern.to_borg_pattern() for pattern in self.get_all_patterns_ordered()
        ]

    def get_pattern_count(self) -> int:
        """Get total number of patterns."""
        return len(self.include_patterns) + len(self.exclude_patterns)
