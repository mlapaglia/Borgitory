"""
Archive Models - Data structures for archive operations
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ArchiveEntry:
    """Individual archive entry (file/directory) structure"""

    # Required fields
    path: str
    name: str
    type: str  # 'f' for file, 'd' for directory, etc.
    size: int
    isdir: bool

    # Optional fields from Borg JSON output
    mtime: Optional[str] = None
    mode: Optional[str] = None
    uid: Optional[int] = None
    gid: Optional[int] = None
    healthy: Optional[bool] = None

    # Additional computed fields
    children_count: Optional[int] = None
