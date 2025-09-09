"""
Tests for FastAPI dependency providers
"""
import pytest

from app.dependencies import get_simple_command_runner, get_borg_service
from app.services.simple_command_runner import SimpleCommandRunner
from app.services.borg_service import BorgService


class TestDependencies:
    """Test class for dependency providers."""

    def test_get_simple_command_runner(self):
        """Test SimpleCommandRunner dependency provider."""
        runner = get_simple_command_runner()
        
        assert isinstance(runner, SimpleCommandRunner)
        assert runner.timeout == 300  # Default timeout
        
        # Should return same instance due to lru_cache
        runner2 = get_simple_command_runner()
        assert runner is runner2

    def test_get_borg_service(self):
        """Test BorgService dependency provider."""
        service = get_borg_service()
        
        assert isinstance(service, BorgService)
        assert isinstance(service.command_runner, SimpleCommandRunner)
        
        # Should return same instance due to lru_cache
        service2 = get_borg_service()
        assert service is service2

    def test_borg_service_has_injected_command_runner(self):
        """Test that BorgService receives the proper command runner dependency."""
        service = get_borg_service()
        command_runner = get_simple_command_runner()
        
        # The command runner should be the same instance (singleton pattern)
        assert service.command_runner is command_runner

    def test_dependency_isolation_in_tests(self):
        """Test that dependencies can be properly mocked in tests."""
        from unittest.mock import Mock
        
        # This demonstrates how to inject mock dependencies for testing
        mock_runner = Mock(spec=SimpleCommandRunner)
        service = BorgService(command_runner=mock_runner)
        
        assert service.command_runner is mock_runner
        assert isinstance(mock_runner, Mock)

    def test_default_initialization_still_works(self):
        """Test that services can still be initialized without dependency injection."""
        # This ensures backward compatibility
        runner = SimpleCommandRunner()
        service = BorgService()
        
        assert isinstance(runner, SimpleCommandRunner)
        assert isinstance(service, BorgService)
        assert isinstance(service.command_runner, SimpleCommandRunner)
        
        # These should be different instances (not singletons)
        service2 = BorgService()
        assert service.command_runner is not service2.command_runner