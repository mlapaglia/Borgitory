"""
Dataclasses for Borg command output structures.

These provide strongly typed representations of data returned by Borg commands,
replacing generic Dict[str, object] return types.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime


@dataclass
class RepositoryInfo:
    """Repository-level information from 'borg info' command."""

    # Core repository identification
    id: str
    location: str

    # Security and encryption
    encrypted: bool = True
    key_type: Optional[str] = None

    # Repository statistics (if available)
    original_size: Optional[int] = None
    compressed_size: Optional[int] = None
    deduplicated_size: Optional[int] = None
    unique_chunks: Optional[int] = None
    total_chunks: Optional[int] = None

    # Cache information
    cache_path: Optional[str] = None
    cache_id: Optional[str] = None

    # Additional metadata that might be present
    additional_info: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BorgRepositoryInfoResponse:
    """Complete response from 'borg info --json' command."""

    repository: RepositoryInfo
    cache: Optional[Dict[str, Any]] = None

    @classmethod
    def from_borg_json(cls, json_data: Dict[str, Any]) -> "BorgRepositoryInfoResponse":
        """Create instance from Borg JSON output."""
        repo_data = json_data.get("repository", {})
        cache_data = json_data.get("cache")

        # Extract repository info
        repository = RepositoryInfo(
            id=repo_data.get("id", ""),
            location=repo_data.get("location", ""),
            encrypted=repo_data.get("encrypted", True),
            key_type=repo_data.get("key_type"),
            original_size=repo_data.get("original_size"),
            compressed_size=repo_data.get("compressed_size"),
            deduplicated_size=repo_data.get("deduplicated_size"),
            unique_chunks=repo_data.get("unique_chunks"),
            total_chunks=repo_data.get("total_chunks"),
            cache_path=repo_data.get("cache", {}).get("path")
            if isinstance(repo_data.get("cache"), dict)
            else None,
            cache_id=repo_data.get("cache", {}).get("id")
            if isinstance(repo_data.get("cache"), dict)
            else None,
            additional_info={
                k: v
                for k, v in repo_data.items()
                if k
                not in {
                    "id",
                    "location",
                    "encrypted",
                    "key_type",
                    "original_size",
                    "compressed_size",
                    "deduplicated_size",
                    "unique_chunks",
                    "total_chunks",
                    "cache",
                }
            },
        )

        return cls(repository=repository, cache=cache_data)


@dataclass
class BorgArchive:
    """Individual archive from 'borg list --json' command."""

    # Core archive identification
    name: str
    id: str

    # Timestamps
    start: str  # ISO format timestamp
    end: str  # ISO format timestamp
    duration: float  # Duration in seconds

    # Statistics (if available)
    original_size: Optional[int] = None
    compressed_size: Optional[int] = None
    deduplicated_size: Optional[int] = None
    nfiles: Optional[int] = None

    # Archive metadata
    hostname: Optional[str] = None
    username: Optional[str] = None
    comment: Optional[str] = None
    command_line: Optional[List[str]] = None

    # Additional fields that might be present
    additional_info: Dict[str, Any] = field(default_factory=dict)

    @property
    def started_at(self) -> Optional[datetime]:
        """Convert start timestamp to datetime object."""
        try:
            return datetime.fromisoformat(self.start.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

    @property
    def ended_at(self) -> Optional[datetime]:
        """Convert end timestamp to datetime object."""
        try:
            return datetime.fromisoformat(self.end.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None


@dataclass
class BorgArchiveListResponse:
    """Complete response from 'borg list --json' command."""

    archives: List[BorgArchive]
    repository: Optional[Dict[str, Any]] = None
    encryption: Optional[Dict[str, Any]] = None

    @classmethod
    def from_borg_json(cls, json_data: Dict[str, Any]) -> "BorgArchiveListResponse":
        """Create instance from Borg JSON output."""
        archives_data = json_data.get("archives", [])
        repository_data = json_data.get("repository")
        encryption_data = json_data.get("encryption")

        # Convert each archive
        archives = []
        for archive_data in archives_data:
            archive = BorgArchive(
                name=archive_data.get("name", ""),
                id=archive_data.get("id", ""),
                start=archive_data.get("start", ""),
                end=archive_data.get("end", ""),
                duration=archive_data.get("duration", 0.0),
                original_size=archive_data.get("stats", {}).get("original_size")
                if "stats" in archive_data
                else None,
                compressed_size=archive_data.get("stats", {}).get("compressed_size")
                if "stats" in archive_data
                else None,
                deduplicated_size=archive_data.get("stats", {}).get("deduplicated_size")
                if "stats" in archive_data
                else None,
                nfiles=archive_data.get("stats", {}).get("nfiles")
                if "stats" in archive_data
                else None,
                hostname=archive_data.get("hostname"),
                username=archive_data.get("username"),
                comment=archive_data.get("comment"),
                command_line=archive_data.get("command_line"),
                additional_info={
                    k: v
                    for k, v in archive_data.items()
                    if k
                    not in {
                        "name",
                        "id",
                        "start",
                        "end",
                        "duration",
                        "stats",
                        "hostname",
                        "username",
                        "comment",
                        "command_line",
                    }
                },
            )
            archives.append(archive)

        return cls(
            archives=archives, repository=repository_data, encryption=encryption_data
        )


@dataclass
class BorgScannedRepository:
    """Information about a repository discovered during Borg scanning."""

    # Core repository identification
    path: str
    id: str

    # Encryption and security information
    encryption_mode: str
    requires_keyfile: bool

    # Discovery metadata
    detected: bool
    config_preview: str

    # Additional fields that might be present
    additional_info: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RepositoryScanResponse:
    """Complete response from repository scanning operation."""

    repositories: List[BorgScannedRepository]
    scan_paths: Optional[List[str]] = None
    total_found: Optional[int] = None

    def __post_init__(self) -> None:
        """Initialize computed fields."""
        if self.total_found is None:
            self.total_found = len(self.repositories)

    @classmethod
    def from_scan_results(
        cls, scan_results: List[Dict[str, Any]], scan_paths: Optional[List[str]] = None
    ) -> "RepositoryScanResponse":
        """Create instance from scan results."""
        repositories = []

        for result in scan_results:
            repo = BorgScannedRepository(
                path=result.get("path", ""),
                id=result.get("id", ""),
                encryption_mode=result.get("encryption_mode", "unknown"),
                requires_keyfile=bool(result.get("requires_keyfile", False)),
                detected=bool(result.get("detected", True)),
                config_preview=result.get("config_preview", ""),
                additional_info={
                    k: v
                    for k, v in result.items()
                    if k
                    not in {
                        "path",
                        "id",
                        "encryption_mode",
                        "requires_keyfile",
                        "detected",
                        "config_preview",
                    }
                },
            )
            repositories.append(repo)

        return cls(
            repositories=repositories,
            scan_paths=scan_paths,
            total_found=len(repositories),
        )


@dataclass
class BorgRepositoryConfig:
    """Parsed Borg repository configuration information."""

    mode: (
        str  # "repokey", "keyfile", "none", "encrypted", "unknown", "invalid", "error"
    )
    requires_keyfile: bool
    preview: str

    @classmethod
    def unknown_config(cls) -> "BorgRepositoryConfig":
        """Create config for unknown repository."""
        return cls(
            mode="unknown", requires_keyfile=False, preview="Config file not found"
        )

    @classmethod
    def invalid_config(cls) -> "BorgRepositoryConfig":
        """Create config for invalid repository."""
        return cls(
            mode="invalid",
            requires_keyfile=False,
            preview="Not a valid Borg repository (no [repository] section)",
        )

    @classmethod
    def error_config(cls, error_message: str) -> "BorgRepositoryConfig":
        """Create config for error during parsing."""
        return cls(
            mode="error",
            requires_keyfile=False,
            preview=f"Error reading config: {error_message}",
        )


@dataclass
class RepositoryInitializationResult:
    """Result of repository initialization operation."""

    success: bool
    message: str
    repository_path: Optional[str] = None
    encryption_mode: Optional[str] = None
    created_at: Optional[datetime] = None

    @classmethod
    def success_result(
        cls,
        message: str,
        repository_path: Optional[str] = None,
        encryption_mode: str = "repokey",
    ) -> "RepositoryInitializationResult":
        """Create a successful initialization result."""
        return cls(
            success=True,
            message=message,
            repository_path=repository_path,
            encryption_mode=encryption_mode,
            created_at=datetime.now(),
        )

    @classmethod
    def failure_result(cls, message: str) -> "RepositoryInitializationResult":
        """Create a failed initialization result."""
        return cls(success=False, message=message)
