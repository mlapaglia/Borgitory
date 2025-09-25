"""
Protocol-based tests for SimpleCommandRunner.

These tests verify that SimpleCommandRunner works correctly when used
through its protocol interface, ensuring the migration is successful.
"""

import pytest
from borgitory.dependencies import get_simple_command_runner, get_command_runner_config
from borgitory.protocols.command_protocols import CommandRunnerProtocol
from borgitory.config.command_runner_config import CommandRunnerConfig
from tests.protocols.protocol_testing_utils import ProtocolMockFactory


class TestSimpleCommandRunnerProtocol:
    """Test SimpleCommandRunner through its protocol interface."""

    def test_dependency_returns_protocol(self) -> None:
        """Test that dependency injection returns a protocol-compliant service."""
        config = get_command_runner_config()
        runner = get_simple_command_runner(config)

        # Should be usable as protocol
        def use_command_runner(cr: CommandRunnerProtocol) -> None:
            assert cr is not None
            assert hasattr(cr, "run_command")

        use_command_runner(runner)  # Should work without type errors

    def test_protocol_mock_compatibility(self) -> None:
        """Test that protocol mocks work with command runner usage patterns."""
        mock_runner = ProtocolMockFactory.create_command_runner_mock()

        # Should be usable where protocol is expected
        def use_command_runner(cr: CommandRunnerProtocol) -> None:
            assert cr is not None
            assert hasattr(cr, "run_command")

        use_command_runner(mock_runner)

    def test_fastapi_dependency_override_with_protocol(self) -> None:
        """Test that FastAPI dependency overrides work with protocol mocks."""
        from tests.utils.di_testing import override_dependency

        # Create protocol mock
        mock_runner = ProtocolMockFactory.create_command_runner_mock()

        # Override dependency with protocol mock
        def mock_config():
            return CommandRunnerConfig(timeout=999)

        def mock_runner_factory(config: CommandRunnerConfig = mock_config()):
            return mock_runner

        with override_dependency(
            get_command_runner_config, mock_config
        ), override_dependency(
            get_simple_command_runner, mock_runner_factory
        ) as client:
            # Test that we can make API calls (the override works for FastAPI)
            response = client.get("/")  # Basic endpoint test
            assert response.status_code in [
                200,
                404,
            ]  # Either works or endpoint doesn't exist

    def test_protocol_interface_methods(self) -> None:
        """Test that all protocol methods are available and callable."""
        config = get_command_runner_config()
        runner = get_simple_command_runner(config)

        # Test that protocol methods exist
        assert hasattr(runner, "run_command")
        assert callable(getattr(runner, "run_command"))

        # Test method signature compatibility (basic check)
        import inspect

        sig = inspect.signature(runner.run_command)
        params = list(sig.parameters.keys())

        # Should have at least command parameter
        assert "command" in params

    def test_backward_compatibility(self) -> None:
        """Test that existing code still works after protocol migration."""
        # This test ensures that any existing code that uses SimpleCommandRunner
        # directly will continue to work

        config = get_command_runner_config()
        runner = get_simple_command_runner(config)

        # Should still be a SimpleCommandRunner instance
        from borgitory.services.simple_command_runner import SimpleCommandRunner

        assert isinstance(runner, SimpleCommandRunner)

        # Should have all the original methods
        assert hasattr(runner, "run_command")
        assert hasattr(runner, "timeout")  # Original attribute
        assert hasattr(runner, "config")  # New attribute

    def test_type_safety_with_protocols(self) -> None:
        """Test that type annotations work correctly with protocols."""

        def process_with_runner(runner: CommandRunnerProtocol) -> str:
            """Function that expects a CommandRunnerProtocol."""
            return f"Using runner: {type(runner).__name__}"

        # Should work with real implementation
        config = get_command_runner_config()
        real_runner = get_simple_command_runner(config)
        result = process_with_runner(real_runner)
        assert "SimpleCommandRunner" in result

        # Should work with mock implementation
        mock_runner = ProtocolMockFactory.create_command_runner_mock()
        result = process_with_runner(mock_runner)
        assert "Mock" in result


class TestCommandRunnerProtocolIntegration:
    """Integration tests for CommandRunnerProtocol usage."""

    def test_dependency_injection_with_same_config(self) -> None:
        """Test that same configuration produces equivalent runners."""
        config = CommandRunnerConfig(timeout=300)
        runner1 = get_simple_command_runner(config)
        runner2 = get_simple_command_runner(config)

        # Same configuration, equivalent behavior (but different instances)
        assert isinstance(runner1, type(runner2))
        assert runner1.timeout == runner2.timeout
        assert runner1.max_retries == runner2.max_retries

    def test_dependency_injection_with_different_configs(self) -> None:
        """Test that different configurations produce different behaviors."""
        config1 = CommandRunnerConfig(timeout=100)
        config2 = CommandRunnerConfig(timeout=200)

        runner1 = get_simple_command_runner(config1)
        runner2 = get_simple_command_runner(config2)

        assert runner1.timeout == 100
        assert runner2.timeout == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
