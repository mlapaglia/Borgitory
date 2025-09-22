"""Integration tests for application startup and basic health checks."""

import pytest
import subprocess
import time
import requests
import os
from typing import Optional


class AppRunner:
    """Helper class to manage app startup and shutdown for testing."""

    def __init__(
        self,
        data_dir: str,
        port: Optional[int] = None,
        db_filename: Optional[str] = None,
    ):
        self.data_dir = data_dir
        # Use a different port for each test to avoid conflicts
        if port is None:
            import random

            port = random.randint(8001, 8999)
        self.port = port

        # Use unique database filename if not provided
        if db_filename is None:
            import uuid

            db_filename = f"test_borgitory_{uuid.uuid4().hex}.db"
        self.db_filename = db_filename

        self.process: Optional[subprocess.Popen] = None
        self.base_url = f"http://localhost:{port}"

    def start(self, timeout: int = 30) -> bool:
        """Start the application and wait for it to be ready."""
        # Set up environment
        env = os.environ.copy()
        import uuid

        secret_key = f"test-secret-key-{uuid.uuid4().hex}"
        env.update(
            {
                "BORGITORY_DATA_DIR": self.data_dir,
                "BORGITORY_DATABASE_URL": f"sqlite:///{os.path.join(self.data_dir, self.db_filename)}",
                "BORGITORY_SECRET_KEY": secret_key,
            }
        )

        # Start the application using the CLI
        self.process = subprocess.Popen(
            ["borgitory", "serve", "--host", "0.0.0.0", "--port", str(self.port)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.getcwd(),
        )

        # Wait for app to be ready
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.is_ready():
                return True

            # Check if process crashed
            if self.process.poll() is not None:
                # Process died, get logs and fail immediately
                stdout, stderr = self.get_logs()
                print("Process crashed during startup!")
                print(f"Exit code: {self.process.poll()}")
                print(f"STDOUT: {stdout}")
                print(f"STDERR: {stderr}")
                return False

            time.sleep(0.5)

        # If we get here, startup timed out
        print(f"App startup timed out after {timeout} seconds")
        if self.process and self.process.poll() is None:
            print("Process is still running but not responding to health checks")
        stdout, stderr = self.get_logs()
        print(f"STDOUT: {stdout}")
        print(f"STDERR: {stderr}")
        self.stop()
        return False

    def is_ready(self) -> bool:
        """Check if the application is ready to receive requests."""
        try:
            # Try to connect to the debug endpoint (doesn't require auth)
            response = requests.get(f"{self.base_url}/api/debug/info", timeout=2)
            return response.status_code in [
                200,
                401,
                403,
            ]  # Any response means app is running
        except (requests.ConnectionError, requests.Timeout):
            return False

    def stop(self):
        """Stop the application process."""
        if self.process:
            try:
                # Try graceful shutdown first
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill if graceful shutdown fails
                    self.process.kill()
                    self.process.wait()
            except Exception:
                pass
            finally:
                self.process = None

    def get_logs(self) -> tuple[str, str]:
        """Get stdout and stderr logs from the process."""
        if self.process:
            try:
                # If process has finished, get all logs
                if self.process.poll() is not None:
                    stdout, stderr = self.process.communicate()
                    return stdout.decode(), stderr.decode()
                else:
                    # Process is still running, terminate it to get logs
                    self.process.terminate()
                    try:
                        stdout, stderr = self.process.communicate(timeout=5)
                        return stdout.decode(), stderr.decode()
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        stdout, stderr = self.process.communicate()
                        return stdout.decode(), stderr.decode()
            except Exception as e:
                return f"Error reading logs: {e}", ""
        return "", ""


@pytest.fixture
def app_runner_module(temp_data_dir):
    """Create a single AppRunner instance for all tests in this module."""
    # Changed from module scope to function scope to ensure test isolation
    runner = AppRunner(temp_data_dir)

    # Start the app once for all tests
    success = runner.start(timeout=30)
    if not success:
        # Get logs for debugging if startup fails
        try:
            stdout, stderr = runner.get_logs()
            print(f"App startup failed!\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}")
        except Exception as e:
            print(f"Could not get logs: {e}")
        pytest.fail("Application failed to start for module-level tests")

    yield runner
    runner.stop()


@pytest.fixture
def app_runner(temp_data_dir):
    """Create an AppRunner instance for individual tests that need their own instance."""
    runner = AppRunner(temp_data_dir)
    yield runner
    runner.stop()


def test_app_starts_successfully(app_runner):
    """Test that the application starts without crashing."""
    success = app_runner.start(timeout=30)

    if not success:
        # Get logs for debugging
        try:
            stdout, stderr = app_runner.get_logs()
            print(f"STDOUT:\n{stdout}")
            print(f"STDERR:\n{stderr}")
        except Exception as e:
            print(f"Could not get logs: {e}")

        # Check if process is still running
        if app_runner.process:
            print(f"Process poll result: {app_runner.process.poll()}")

    assert success, "Application failed to start within 30 seconds"

    # Verify the process is still running
    assert app_runner.process is not None
    assert app_runner.process.poll() is None, "Application process died after startup"


def test_app_responds_to_health_check(app_runner_module):
    """Test that the application responds to basic health check requests."""
    # App is already started by the module fixture

    # Test debug endpoint (should work without auth)
    response = requests.get(f"{app_runner_module.base_url}/api/debug/info", timeout=5)

    # We expect either 200 (if no auth required) or 401/403 (if auth required)
    # The important thing is that we get a response, not a connection error
    assert response.status_code in [200, 401, 403], (
        f"Unexpected status code: {response.status_code}"
    )

    # Verify response has some content
    assert len(response.text) > 0, "Response body is empty"


def test_app_serves_main_page(app_runner_module):
    """Test that the application serves the main page."""
    # App is already started by the module fixture

    # Test main page
    response = requests.get(f"{app_runner_module.base_url}/", timeout=5)

    # Should get some HTML response (might redirect to login)
    assert response.status_code in [200, 302, 401, 403], (
        f"Unexpected status code: {response.status_code}"
    )

    # If we get HTML, verify it looks like a web page
    if response.headers.get("content-type", "").startswith("text/html"):
        assert "html" in response.text.lower() or "<!DOCTYPE" in response.text


def test_app_handles_auth_check_endpoint(app_runner_module):
    """Test that the auth check endpoint works."""
    # App is already started by the module fixture

    # Test auth check endpoint (note: /auth not /api/auth)
    response = requests.get(f"{app_runner_module.base_url}/auth/check-users", timeout=5)

    # Should return HTML for login/register form
    assert response.status_code == 200, (
        f"Auth check failed with status: {response.status_code}"
    )

    # Should return HTML content
    content_type = response.headers.get("content-type", "")
    assert "text/html" in content_type, f"Expected HTML response, got: {content_type}"

    # Should contain form elements (either login or register)
    response_text = response.text.lower()
    assert any(
        keyword in response_text for keyword in ["form", "input", "login", "register"]
    ), "Response doesn't appear to contain a form"


def test_app_startup_with_fresh_database(app_runner):
    """Test that the application can start with a completely fresh database."""
    # App should start and create database automatically (migration handles this)
    assert app_runner.start(timeout=30), (
        "Application failed to start with fresh database"
    )

    # Verify app is responsive
    response = requests.get(f"{app_runner.base_url}/auth/check-users", timeout=5)
    assert response.status_code == 200, (
        "App not responsive after fresh database creation"
    )


def test_app_shutdown_gracefully(app_runner):
    """Test that the application shuts down gracefully."""
    assert app_runner.start(timeout=30), "Application failed to start"

    # Verify app is running
    assert app_runner.process.poll() is None, "Process not running"

    # Stop the app
    app_runner.stop()

    # Verify process has stopped
    assert app_runner.process is None or app_runner.process.poll() is not None, (
        "Process did not stop after shutdown"
    )
