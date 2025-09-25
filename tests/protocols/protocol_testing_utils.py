"""
Protocol Testing Utilities

This module provides utilities for testing protocol-based services,
including enhanced mocking capabilities and validation helpers.
"""

from typing import Type, Any, Dict, List, Callable
from unittest.mock import Mock, AsyncMock
import inspect


class ProtocolMockFactory:
    """Factory for creating protocol-compliant mocks."""

    @staticmethod
    def create_protocol_mock(protocol_class: Type[Any]) -> Mock:
        """Create a mock that satisfies a protocol interface."""
        mock = Mock(spec=protocol_class)

        # Get all protocol methods
        protocol_methods = {}
        for name, method in inspect.getmembers(protocol_class):
            if not name.startswith("_") and callable(method):
                protocol_methods[name] = method

        # Set up async mocks for async methods
        for method_name, method in protocol_methods.items():
            if inspect.iscoroutinefunction(method):
                setattr(mock, method_name, AsyncMock())
            else:
                # Regular mock is already set up by spec
                pass

        return mock

    @staticmethod
    def create_command_runner_mock() -> Mock:
        """Create a mock CommandRunnerProtocol."""
        from borgitory.protocols import CommandRunnerProtocol, CommandResult

        mock = Mock(spec=CommandRunnerProtocol)
        mock.run_command = AsyncMock(
            return_value=CommandResult(
                success=True, return_code=0, stdout="success", stderr="", duration=0.1
            )
        )
        return mock

    @staticmethod
    def create_volume_service_mock() -> Mock:
        """Create a mock VolumeServiceProtocol."""
        from borgitory.protocols import VolumeServiceProtocol

        mock = Mock(spec=VolumeServiceProtocol)
        mock.get_mounted_volumes = AsyncMock(return_value=["/mock/volume"])
        mock.get_volume_info = Mock(return_value={"mock": "info"})
        return mock

    @staticmethod
    def create_backup_service_mock() -> Mock:
        """Create a mock BackupServiceProtocol."""
        from borgitory.protocols import BackupServiceProtocol

        mock = Mock(spec=BackupServiceProtocol)
        mock.create_backup = AsyncMock(return_value="mock-job-123")
        mock.list_archives = AsyncMock(return_value=[])
        mock.scan_for_repositories = AsyncMock(return_value=[])
        mock.initialize_repository = AsyncMock(return_value={"success": True})
        mock.verify_repository_access = AsyncMock(return_value={"success": True})
        return mock

    @staticmethod
    def create_job_manager_mock() -> Mock:
        """Create a mock JobManagerProtocol."""
        from borgitory.protocols import JobManagerProtocol

        mock = Mock(spec=JobManagerProtocol)
        mock.list_jobs = Mock(return_value=[])
        mock.get_job_status = Mock(return_value=None)
        mock.start_backup_job = AsyncMock(return_value="mock-job-456")
        mock.cancel_job = AsyncMock(return_value=True)
        mock.stream_all_job_updates = AsyncMock()
        return mock

    @staticmethod
    def create_notification_service_mock() -> Mock:
        """Create a mock NotificationServiceProtocol."""
        from borgitory.protocols import NotificationServiceProtocol

        mock = Mock(spec=NotificationServiceProtocol)
        mock.send_notification = AsyncMock(return_value=True)
        mock.is_configured = Mock(return_value=True)
        mock.get_service_name = Mock(return_value="MockNotificationService")
        return mock


class ProtocolValidator:
    """Utilities for validating protocol compliance."""

    @staticmethod
    def validate_service_implements_protocol(
        service_instance: Any, protocol_class: Type[Any]
    ) -> Dict[str, Any]:
        """Validate that a service instance implements a protocol."""

        validation_result = {
            "compliant": True,
            "missing_methods": [],
            "incorrect_signatures": [],
            "details": [],
        }

        # Get protocol methods
        protocol_methods = []
        for name, method in inspect.getmembers(protocol_class):
            if not name.startswith("_") and callable(method):
                protocol_methods.append((name, method))

        # Check each protocol method
        for method_name, protocol_method in protocol_methods:
            if not hasattr(service_instance, method_name):
                validation_result["compliant"] = False
                validation_result["missing_methods"].append(method_name)
                validation_result["details"].append(f"Missing method: {method_name}")
                continue

            # Get service method
            service_method = getattr(service_instance, method_name)

            # Basic signature validation
            try:
                protocol_sig = inspect.signature(protocol_method)
                service_sig = inspect.signature(service_method)

                # Compare parameter names (excluding 'self')
                protocol_params = [
                    p for p in protocol_sig.parameters.keys() if p != "self"
                ]
                service_params = [
                    p for p in service_sig.parameters.keys() if p != "self"
                ]

                if len(protocol_params) != len(service_params):
                    validation_result["compliant"] = False
                    validation_result["incorrect_signatures"].append(method_name)
                    validation_result["details"].append(
                        f"Parameter count mismatch in {method_name}: "
                        f"protocol expects {len(protocol_params)}, service has {len(service_params)}"
                    )

            except Exception as e:
                validation_result["details"].append(
                    f"Could not validate signature for {method_name}: {e}"
                )

        return validation_result

    @staticmethod
    def print_validation_report(
        validation_result: Dict[str, Any], service_name: str
    ) -> None:
        """Print a formatted validation report."""
        print(f"\n📋 Protocol Compliance Report for {service_name}")
        print("=" * 50)

        if validation_result["compliant"]:
            print("✅ COMPLIANT: Service satisfies protocol requirements")
        else:
            print("❌ NON-COMPLIANT: Service has protocol violations")

            if validation_result["missing_methods"]:
                print(
                    f"\n🔴 Missing Methods ({len(validation_result['missing_methods'])}):"
                )
                for method in validation_result["missing_methods"]:
                    print(f"  - {method}")

            if validation_result["incorrect_signatures"]:
                print(
                    f"\n🟡 Signature Mismatches ({len(validation_result['incorrect_signatures'])}):"
                )
                for method in validation_result["incorrect_signatures"]:
                    print(f"  - {method}")

        if validation_result["details"]:
            print("\n📝 Details:")
            for detail in validation_result["details"]:
                print(f"  - {detail}")


def create_protocol_test_suite(
    service_class: Type[Any], protocol_class: Type[Any]
) -> List[Callable[..., None]]:
    """Create a standard test suite for protocol compliance."""

    def test_service_has_protocol_methods() -> None:
        """Test that service has all protocol methods."""
        validator = ProtocolValidator()
        service_instance = service_class()
        result = validator.validate_service_implements_protocol(
            service_instance, protocol_class
        )

        if not result["compliant"]:
            validator.print_validation_report(result, service_class.__name__)

        assert result["compliant"], (
            f"{service_class.__name__} does not fully implement {protocol_class.__name__}"
        )

    def test_service_can_be_used_as_protocol() -> None:
        """Test that service instance can be used where protocol is expected."""

        def use_protocol_service(service: protocol_class) -> None:
            assert service is not None

        service_instance = service_class()
        use_protocol_service(service_instance)  # Should not raise type errors

    def test_protocol_mock_compatibility() -> None:
        """Test that protocol mocks work with service-using code."""
        mock = ProtocolMockFactory.create_protocol_mock(protocol_class)

        def use_protocol_service(service: protocol_class) -> None:
            assert service is not None

        use_protocol_service(mock)  # Should work with mocks too

    return [
        test_service_has_protocol_methods,
        test_service_can_be_used_as_protocol,
        test_protocol_mock_compatibility,
    ]


# Convenience functions for common protocol mocks
def get_all_protocol_mocks() -> Dict[str, Mock]:
    """Get mocks for all major protocols."""
    return {
        "command_runner": ProtocolMockFactory.create_command_runner_mock(),
        "volume_service": ProtocolMockFactory.create_volume_service_mock(),
        "backup_service": ProtocolMockFactory.create_backup_service_mock(),
        "job_manager": ProtocolMockFactory.create_job_manager_mock(),
        "notification_service": ProtocolMockFactory.create_notification_service_mock(),
    }
