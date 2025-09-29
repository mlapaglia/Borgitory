"""
Core tests for BorgService - focusing on critical security and functionality
"""

from unittest.mock import Mock

from borgitory.services.borg_service import BorgService
from borgitory.models.database import Repository


def create_test_borg_service(
    job_executor=None,
    command_runner=None,
    job_manager=None,
    archive_service=None,
) -> BorgService:
    """Helper function to create BorgService with all required dependencies for testing."""
    return BorgService(
        job_executor=job_executor or Mock(),
        command_runner=command_runner or Mock(),
        job_manager=job_manager or Mock(),
        archive_service=archive_service or Mock(),
    )


class TestBorgServiceCore:
    """Test core BorgService functionality and security."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.borg_service = create_test_borg_service()

        # Create mock repository
        self.mock_repository = Mock(spec=Repository)
        self.mock_repository.id = 1
        self.mock_repository.name = "test-repo"
        self.mock_repository.path = "/path/to/repo"
        self.mock_repository.get_passphrase.return_value = "test_passphrase"
        self.mock_repository.get_keyfile_content.return_value = None

    def test_service_initialization(self) -> None:
        """Test BorgService initializes correctly."""
        service = create_test_borg_service()
        assert hasattr(service, "progress_pattern")
        assert service.progress_pattern is not None

    def test_progress_pattern_matching(self) -> None:
        """Test that progress pattern correctly matches Borg output."""
        # Test valid Borg progress line
        test_line = "1234567 654321 111111 150 /path/to/some/important/file.txt"
        match = self.borg_service.progress_pattern.match(test_line)

        assert match is not None
        assert match.group("original_size") == "1234567"
        assert match.group("compressed_size") == "654321"
        assert match.group("deduplicated_size") == "111111"
        assert match.group("nfiles") == "150"
        assert match.group("path") == "/path/to/some/important/file.txt"

        # Test invalid line doesn't match
        invalid_line = "This is not a progress line"
        assert self.borg_service.progress_pattern.match(invalid_line) is None
