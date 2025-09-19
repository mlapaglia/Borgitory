"""
Examples of using the Protocol-based Service Factory system.

This demonstrates how the factory system enables dynamic service creation,
configuration management, and easy testing with different implementations.
"""

import asyncio
from borgitory.factories.service_factory import (
    get_service_registry,
    create_notification_service,
    create_command_runner,
)


async def example_1_basic_factory_usage():
    """Example 1: Basic factory usage for creating services."""
    print("🏭 Example 1: Basic Factory Usage")
    print("=" * 50)

    # Create services using convenience functions
    notification_service = create_notification_service("pushover")
    command_runner = create_command_runner("simple", timeout=60)

    print(f"✅ Created notification service: {notification_service.__class__.__name__}")
    print(f"✅ Created command runner: {command_runner.__class__.__name__}")
    print(f"   - Command runner timeout: {command_runner.timeout}")

    # Test that services work
    assert hasattr(notification_service, "send_notification")
    assert hasattr(command_runner, "run_command")
    assert command_runner.timeout == 60

    print("✅ All services created successfully!\n")


async def example_2_registry_usage():
    """Example 2: Using the service registry directly."""
    print("🏗️ Example 2: Service Registry Usage")
    print("=" * 50)

    # Get the global service registry
    registry = get_service_registry()

    # List all available factories
    factories = registry.list_factories()
    print(f"📋 Available factories: {list(factories.keys())}")

    # Get specific factories
    notification_factory = registry.get_notification_factory()
    command_factory = registry.get_command_runner_factory()
    backup_factory = registry.get_backup_service_factory()

    # List implementations for each factory
    print(
        f"🔔 Notification implementations: {list(notification_factory.list_implementations().keys())}"
    )
    print(
        f"⚡ Command runner implementations: {list(command_factory.list_implementations().keys())}"
    )
    print(
        f"💾 Backup service implementations: {list(backup_factory.list_implementations().keys())}"
    )

    print("✅ Registry exploration complete!\n")


async def example_3_custom_implementations():
    """Example 3: Registering custom service implementations."""
    print("🔧 Example 3: Custom Service Implementations")
    print("=" * 50)

    # Create a custom notification service
    class EmailNotificationService:
        def __init__(self, smtp_server: str = "localhost", port: int = 587):
            self.smtp_server = smtp_server
            self.port = port

        async def send_notification(self, **kwargs) -> bool:
            print(f"📧 Sending email via {self.smtp_server}:{self.port}")
            return True

        def get_service_name(self) -> str:
            return f"EmailService({self.smtp_server}:{self.port})"

    # Register the custom implementation
    registry = get_service_registry()
    notification_factory = registry.get_notification_factory()

    notification_factory.register_implementation(
        "email",
        EmailNotificationService,
        config={"smtp_server": "mail.example.com", "port": 465},
    )

    # Create services using both default and custom implementations
    pushover_service = notification_factory.create_notification_service("pushover")
    email_service = notification_factory.create_notification_service("email")

    print(f"✅ Pushover service: {pushover_service.__class__.__name__}")
    print(f"✅ Email service: {email_service.__class__.__name__}")
    print(f"   - SMTP server: {email_service.smtp_server}")
    print(f"   - Port: {email_service.port}")

    # Test the custom service
    result = await email_service.send_notification(
        title="Test", message="Factory system working!"
    )
    assert result is True

    print("✅ Custom implementation registered and working!\n")


async def example_4_configuration_management():
    """Example 4: Advanced configuration management."""
    print("⚙️ Example 4: Configuration Management")
    print("=" * 50)

    # Create a custom command runner with specific configuration
    class DebugCommandRunner:
        def __init__(
            self, timeout: int = 30, verbose: bool = False, log_commands: bool = True
        ):
            self.timeout = timeout
            self.verbose = verbose
            self.log_commands = log_commands

        async def run_command(self, command, env=None):
            if self.log_commands:
                print(f"🐛 DEBUG: Running command: {' '.join(command)}")
            if self.verbose:
                print(f"🐛 DEBUG: Timeout: {self.timeout}s, Env: {env}")
            # Mock successful execution
            from unittest.mock import Mock

            return Mock(success=True, stdout=b"debug output", stderr=b"")

    # Register with different configurations
    registry = get_service_registry()
    command_factory = registry.get_command_runner_factory()

    # Register development configuration
    command_factory.register_implementation(
        "debug-dev",
        DebugCommandRunner,
        config={"timeout": 120, "verbose": True, "log_commands": True},
    )

    # Register production configuration
    command_factory.register_implementation(
        "debug-prod",
        DebugCommandRunner,
        config={"timeout": 60, "verbose": False, "log_commands": False},
    )

    # Create services with different configurations
    dev_runner = command_factory.create_command_runner("debug-dev")
    prod_runner = command_factory.create_command_runner("debug-prod")

    print(
        f"🔧 Dev runner - Timeout: {dev_runner.timeout}, Verbose: {dev_runner.verbose}"
    )
    print(
        f"🚀 Prod runner - Timeout: {prod_runner.timeout}, Verbose: {prod_runner.verbose}"
    )

    # Test runtime configuration override
    custom_runner = command_factory.create_command_runner(
        "debug-dev",
        timeout=300,  # Override timeout
        verbose=False,  # Override verbose
    )
    print(
        f"⚡ Custom runner - Timeout: {custom_runner.timeout}, Verbose: {custom_runner.verbose}"
    )

    # Test the runners
    await dev_runner.run_command(["echo", "development"])
    await prod_runner.run_command(["echo", "production"])

    print("✅ Configuration management working perfectly!\n")


async def example_5_testing_with_factories():
    """Example 5: Using factories for testing."""
    print("🧪 Example 5: Testing with Factories")
    print("=" * 50)

    # Create mock services for testing
    class MockNotificationService:
        def __init__(self):
            self.sent_notifications = []

        async def send_notification(self, title: str, message: str, **kwargs) -> bool:
            self.sent_notifications.append(
                {"title": title, "message": message, **kwargs}
            )
            print(f"📧 MOCK: Notification sent - {title}: {message}")
            return True

        def get_sent_count(self) -> int:
            return len(self.sent_notifications)

    class MockCommandRunner:
        def __init__(self, should_succeed: bool = True):
            self.should_succeed = should_succeed
            self.commands_run = []

        async def run_command(self, command, env=None):
            self.commands_run.append(command)
            print(f"⚡ MOCK: Command run - {' '.join(command)}")
            from unittest.mock import Mock

            return Mock(
                success=self.should_succeed,
                stdout=b"mock success" if self.should_succeed else b"",
                stderr=b"" if self.should_succeed else b"mock error",
            )

    # Register mock implementations
    registry = get_service_registry()

    notification_factory = registry.get_notification_factory()
    notification_factory.register_implementation("mock", MockNotificationService)

    command_factory = registry.get_command_runner_factory()
    command_factory.register_implementation(
        "mock-success", MockCommandRunner, {"should_succeed": True}
    )
    command_factory.register_implementation(
        "mock-failure", MockCommandRunner, {"should_succeed": False}
    )

    # Create test services
    mock_notification = notification_factory.create_notification_service("mock")
    success_runner = command_factory.create_command_runner("mock-success")
    failure_runner = command_factory.create_command_runner("mock-failure")

    # Test the services
    await mock_notification.send_notification("Test", "This is a test")
    await success_runner.run_command(["test", "command"])
    result = await failure_runner.run_command(["failing", "command"])

    # Verify test results
    assert mock_notification.get_sent_count() == 1
    assert len(success_runner.commands_run) == 1
    assert not result.success

    print("✅ Mock services working perfectly for testing!\n")


async def main():
    """Run all examples."""
    print("🚀 Protocol-based Service Factory Examples")
    print("=" * 60)
    print()

    await example_1_basic_factory_usage()
    await example_2_registry_usage()
    await example_3_custom_implementations()
    await example_4_configuration_management()
    await example_5_testing_with_factories()

    print("🎉 All examples completed successfully!")
    print("=" * 60)
    print()
    print("💡 Key Benefits Demonstrated:")
    print("   ✅ Dynamic service creation")
    print("   ✅ Configuration management")
    print("   ✅ Easy testing with mocks")
    print("   ✅ Plugin-like extensibility")
    print("   ✅ Protocol-based type safety")
    print("   ✅ Runtime service selection")


if __name__ == "__main__":
    asyncio.run(main())
