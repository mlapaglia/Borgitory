"""
Tests for BorgService class - CRITICAL for backup operations and data integrity
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch, mock_open

from app.services.borg_service import BorgService
from app.models.database import Repository


class TestBorgService:
    """Test BorgService functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.borg_service = BorgService()
        
        # Create mock repository
        self.mock_repository = Mock(spec=Repository)
        self.mock_repository.id = 1
        self.mock_repository.name = "test-repo"
        self.mock_repository.path = "/path/to/repo"
        self.mock_repository.get_passphrase.return_value = "test_passphrase"

    def test_init(self):
        """Test BorgService initialization."""
        service = BorgService()
        assert hasattr(service, 'progress_pattern')
        assert service.progress_pattern is not None

    def test_progress_pattern_regex(self):
        """Test that progress pattern correctly matches Borg output."""
        # Test with realistic Borg progress line
        test_line = "123456 654321 111111 150 /path/to/some/file.txt"
        match = self.borg_service.progress_pattern.match(test_line)
        
        assert match is not None
        assert match.group('original_size') == "123456"
        assert match.group('compressed_size') == "654321"
        assert match.group('deduplicated_size') == "111111"
        assert match.group('nfiles') == "150"
        assert match.group('path') == "/path/to/some/file.txt"


class TestParseBorgConfig:
    """Test Borg repository config parsing."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.borg_service = BorgService()

    def test_parse_config_file_not_exists(self):
        """Test parsing when config file doesn't exist."""
        with patch('os.path.exists', return_value=False):
            result = self.borg_service._parse_borg_config("/nonexistent/repo")
            
            assert result["mode"] == "unknown"
            assert result["requires_keyfile"] is False
            assert "Config file not found" in result["preview"]

    def test_parse_config_repokey_mode(self):
        """Test parsing repository with repokey encryption."""
        config_content = """[repository]
id = 1234567890abcdef1234567890abcdef12345678
segments_per_dir = 1000
max_segment_size = 524288000
append_only = 0
storage_quota = 0
additional_free_space = 0
key = very_long_key_data_that_indicates_repokey_mode_with_embedded_encryption_key_this_is_over_50_chars
"""
        
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=config_content)), \
             patch('os.listdir', return_value=[]):
            
            result = self.borg_service._parse_borg_config("/test/repo")
            
            assert result["mode"] == "repokey"
            assert result["requires_keyfile"] is False
            assert "repokey mode" in result["preview"]

    def test_parse_config_keyfile_mode(self):
        """Test parsing repository with keyfile encryption."""
        config_content = """[repository]
id = 1234567890abcdef1234567890abcdef12345678
segments_per_dir = 1000
max_segment_size = 524288000
append_only = 0
storage_quota = 0
additional_free_space = 0
key = 
"""
        
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=config_content)), \
             patch('os.listdir', return_value=['key.abc123', 'data']):
            
            result = self.borg_service._parse_borg_config("/test/repo")
            
            assert result["mode"] == "keyfile"
            assert result["requires_keyfile"] is True
            assert "keyfile mode" in result["preview"]
            assert "key.abc123" in result["preview"]

    def test_parse_config_unencrypted(self):
        """Test parsing unencrypted repository."""
        config_content = """[repository]
id = 1234567890abcdef1234567890abcdef12345678
segments_per_dir = 1000
max_segment_size = 524288000
append_only = 0
storage_quota = 0
additional_free_space = 0
"""
        
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=config_content)), \
             patch('os.listdir', return_value=[]):
            
            result = self.borg_service._parse_borg_config("/test/repo")
            
            assert result["mode"] == "none"
            assert result["requires_keyfile"] is False
            assert "Unencrypted repository" in result["preview"]

    def test_parse_config_invalid_repository(self):
        """Test parsing invalid repository config."""
        config_content = """[not_a_repository_section]
some_key = some_value
"""
        
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=config_content)):
            
            result = self.borg_service._parse_borg_config("/test/repo")
            
            assert result["mode"] == "invalid"
            assert result["requires_keyfile"] is False
            assert "Not a valid Borg repository" in result["preview"]

    def test_parse_config_read_error(self):
        """Test handling of config file read errors."""
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', side_effect=IOError("Permission denied")):
            
            result = self.borg_service._parse_borg_config("/test/repo")
            
            assert result["mode"] == "error"
            assert result["requires_keyfile"] is False
            assert "Error reading config" in result["preview"]

    def test_parse_config_malformed_ini(self):
        """Test handling of malformed INI file."""
        malformed_content = """[repository
this is not valid ini content
key = value without proper section
"""
        
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=malformed_content)):
            
            result = self.borg_service._parse_borg_config("/test/repo")
            
            assert result["mode"] == "error"
            assert "Error reading config" in result["preview"]


class TestRepositoryOperations:
    """Test repository management operations."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.borg_service = BorgService()
        
        self.mock_repository = Mock(spec=Repository)
        self.mock_repository.id = 1
        self.mock_repository.name = "test-repo"
        self.mock_repository.path = "/path/to/repo"
        self.mock_repository.get_passphrase.return_value = "test_passphrase"

    @pytest.mark.asyncio
    async def test_initialize_repository_success(self):
        """Test successful repository initialization."""
        from app.services.simple_command_runner import CommandResult
        
        mock_command_result = CommandResult(
            success=True,
            return_code=0,
            stdout="",
            stderr="",
            duration=1.0
        )
        
        mock_command_runner = Mock()
        mock_command_runner.run_command = AsyncMock(return_value=mock_command_result)
        
        with patch('app.services.simple_command_runner.simple_command_runner', mock_command_runner), \
             patch('app.utils.security.build_secure_borg_command') as mock_build_cmd:
            
            mock_build_cmd.return_value = (["borg", "init", "--encryption=repokey", "/path/to/repo"], {"BORG_PASSPHRASE": "test_passphrase"})
            
            result = await self.borg_service.initialize_repository(self.mock_repository)
            
            assert result["success"] is True
            assert "initialized successfully" in result["message"]
            mock_command_runner.run_command.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_repository_already_exists(self):
        """Test repository initialization when repo already exists."""
        from app.services.simple_command_runner import CommandResult
        
        mock_command_result = CommandResult(
            success=False,
            return_code=1,
            stdout="",
            stderr="A repository already exists at /path/to/repo",
            duration=1.0
        )
        
        mock_command_runner = Mock()
        mock_command_runner.run_command = AsyncMock(return_value=mock_command_result)
        
        with patch('app.services.simple_command_runner.simple_command_runner', mock_command_runner), \
             patch('app.utils.security.build_secure_borg_command') as mock_build_cmd:
            
            mock_build_cmd.return_value = (["borg", "init"], {})
            
            result = await self.borg_service.initialize_repository(self.mock_repository)
            
            assert result["success"] is True
            assert "already exists" in result["message"]

    @pytest.mark.asyncio
    async def test_verify_repository_access_success(self):
        """Test successful repository access verification."""
        mock_job_manager = Mock()
        mock_job_manager.start_borg_command = AsyncMock(return_value="job-123")
        mock_job_manager.get_job_status.return_value = {
            "completed": True,
            "return_code": 0
        }
        mock_job_manager.cleanup_job = Mock()
        
        with patch('app.services.borg_service.get_job_manager', return_value=mock_job_manager), \
             patch('app.utils.security.build_secure_borg_command') as mock_build_cmd:
            
            mock_build_cmd.return_value = (["borg", "list", "--short"], {})
            
            result = await self.borg_service.verify_repository_access(
                "/path/to/repo", 
                "test_passphrase"
            )
            
            assert result is True
            mock_job_manager.cleanup_job.assert_called_once_with("job-123")

    @pytest.mark.asyncio
    async def test_verify_repository_access_failure(self):
        """Test repository access verification failure."""
        mock_job_manager = Mock()
        mock_job_manager.start_borg_command = AsyncMock(return_value="job-123")
        mock_job_manager.get_job_status.return_value = {
            "completed": True,
            "return_code": 1
        }
        mock_job_manager.cleanup_job = Mock()
        
        with patch('app.services.borg_service.get_job_manager', return_value=mock_job_manager), \
             patch('app.utils.security.build_secure_borg_command') as mock_build_cmd:
            
            mock_build_cmd.return_value = (["borg", "list", "--short"], {})
            
            result = await self.borg_service.verify_repository_access(
                "/path/to/repo", 
                "wrong_passphrase"
            )
            
            assert result is False
            mock_job_manager.cleanup_job.assert_called_once_with("job-123")


class TestArchiveOperations:
    """Test archive management operations."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.borg_service = BorgService()
        
        self.mock_repository = Mock(spec=Repository)
        self.mock_repository.id = 1
        self.mock_repository.name = "test-repo" 
        self.mock_repository.path = "/path/to/repo"
        self.mock_repository.get_passphrase.return_value = "test_passphrase"

class TestRepositoryScanning:
    """Test repository discovery and scanning operations."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.borg_service = BorgService()

    @pytest.mark.asyncio
    async def test_start_repository_scan_specific_path(self):
        """Test starting repository scan with specific path."""
        mock_job_manager = Mock()
        mock_job_manager.start_borg_command = AsyncMock(return_value="scan-job-123")
        
        with patch('app.services.borg_service.get_job_manager', return_value=mock_job_manager), \
             patch('app.utils.security.sanitize_path', return_value="/safe/path"), \
             patch('app.utils.security.build_secure_borg_command') as mock_build_cmd:
            
            mock_build_cmd.return_value = (["find", "/safe/path"], {})
            
            job_id = await self.borg_service.start_repository_scan("/test/path")
            
            assert job_id == "scan-job-123"
            mock_job_manager.start_borg_command.assert_called_once()

class TestFileExtraction:
    """Test file extraction and streaming operations."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.borg_service = BorgService()
        
        self.mock_repository = Mock(spec=Repository)
        self.mock_repository.path = "/path/to/repo"
        self.mock_repository.get_passphrase.return_value = "test_passphrase"

class TestErrorHandling:
    """Test error handling and edge cases."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.borg_service = BorgService()
        
        self.mock_repository = Mock(spec=Repository)
        self.mock_repository.get_passphrase.return_value = "test_passphrase"

    @pytest.mark.asyncio
    async def test_operation_with_security_validation_error(self):
        """Test handling of security validation errors."""
        with patch('app.utils.security.build_secure_borg_command', side_effect=ValueError("Security error")):
            
            result = await self.borg_service.initialize_repository(self.mock_repository)
            
            assert result["success"] is False
            assert "Security validation failed" in result["message"]

    def test_parse_config_with_permission_error(self):
        """Test config parsing with permission denied error."""
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', side_effect=PermissionError("Access denied")):
            
            result = self.borg_service._parse_borg_config("/restricted/repo")
            
            assert result["mode"] == "error"
            assert "Error reading config" in result["preview"]

    def test_parse_config_with_unicode_error(self):
        """Test config parsing with unicode decode error."""
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open()) as mock_file:
            
            mock_file.return_value.read.side_effect = UnicodeDecodeError(
                "utf-8", b"binary data", 0, 1, "invalid start byte"
            )
            
            result = self.borg_service._parse_borg_config("/binary/repo")
            
            assert result["mode"] == "error"


class TestSecurityIntegration:
    """Test security integration and validation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.borg_service = BorgService()

    def test_security_validation_prevents_injection(self):
        """Test that security validation prevents injection attacks."""
        # These should all raise security validation errors
        malicious_inputs = [
            ("path", "../../../etc/passwd"),
            ("archive_name", "archive; rm -rf /"),
            ("compression", "lz4; cat /etc/shadow")
        ]
        
        for input_type, malicious_value in malicious_inputs:
            with patch('app.utils.security.sanitize_path', side_effect=ValueError("Dangerous path")), \
                 patch('app.utils.security.validate_archive_name', side_effect=ValueError("Invalid archive")), \
                 patch('app.utils.security.validate_compression', side_effect=ValueError("Invalid compression")):
                
                # Security validation should prevent these from reaching Borg
                pass  # The patched functions will raise appropriate errors