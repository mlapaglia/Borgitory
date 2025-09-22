"""Integration tests for basic endpoint functionality."""

import threading
import pytest
import requests
import json
from .test_app_startup import AppRunner


@pytest.fixture
def app_runner(temp_data_dir):
    """Create an AppRunner instance for individual tests that need their own instance."""
    runner = AppRunner(temp_data_dir)

    # Start the app for each test
    success = runner.start(timeout=30)
    if not success:
        pytest.fail("Application failed to start.")

    yield runner
    runner.stop()


def test_auth_check_users_endpoint(app_runner):
    """Test the auth check-users endpoint returns proper response."""

    response = requests.get(f"{app_runner.base_url}/auth/check-users", timeout=10)

    # Should return 200 OK
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    # Should return HTML content
    content_type = response.headers.get("content-type", "")
    assert "text/html" in content_type, (
        f"Expected HTML content type, got: {content_type}"
    )

    # Should contain form elements for either login or register
    html_content = response.text.lower()
    form_indicators = [
        "<form",
        "input",
        "button",
        "login",
        "register",
        "username",
        "password",
    ]

    assert any(indicator in html_content for indicator in form_indicators), (
        f"Response doesn't appear to contain form elements. Content preview: {response.text[:200]}"
    )


def test_debug_info_endpoint(app_runner):
    """Test the debug info endpoint returns proper JSON structure."""

    response = requests.get(f"{app_runner.base_url}/api/debug/info", timeout=10)

    # Debug endpoint might require auth, so accept 200, 401, or 403
    assert response.status_code in [200, 401, 403], (
        f"Unexpected status code: {response.status_code}"
    )

    if response.status_code == 200:
        # If we get 200, it should be valid JSON
        try:
            debug_data = response.json()
            assert isinstance(debug_data, dict), "Debug info should be a JSON object"

            # Should contain some expected debug information keys
            expected_keys = ["version", "database", "system", "environment"]
            found_keys = list(debug_data.keys())

            # At least one expected key should be present
            assert any(key in found_keys for key in expected_keys), (
                f"Expected at least one of {expected_keys} in debug info, got keys: {found_keys}"
            )

        except json.JSONDecodeError:
            pytest.fail(f"Debug endpoint returned invalid JSON: {response.text[:200]}")


def test_login_endpoint_post(app_runner):
    """Test the login POST endpoint handles requests properly."""

    # Test login with invalid credentials (should fail gracefully)
    login_data = {"username": "nonexistent_user", "password": "wrong_password"}

    response = requests.post(
        f"{app_runner.base_url}/auth/login", data=login_data, timeout=10
    )

    # Should handle the request without crashing
    # Expect either 200 (with error message), 400, 401, or 422 (validation error)
    assert response.status_code in [200, 400, 401, 422], (
        f"Login endpoint returned unexpected status: {response.status_code}"
    )

    # Should return some content (error message or form)
    assert len(response.text) > 0, "Login endpoint should return some content"


def test_register_endpoint_post(app_runner):
    """Test the register POST endpoint handles requests properly."""

    # Test registration with valid data
    register_data = {"username": "testuser123", "password": "testpassword123"}

    response = requests.post(
        f"{app_runner.base_url}/auth/register", data=register_data, timeout=10
    )

    # Should handle the request without crashing
    # Expect 200 (success or error message), 400 (validation error), or 403 (registration closed)
    assert response.status_code in [200, 400, 403], (
        f"Register endpoint returned unexpected status: {response.status_code}"
    )

    # Should return some content
    assert len(response.text) > 0, "Register endpoint should return some content"


def test_root_endpoint(app_runner):
    """Test that the root endpoint serves the main application."""

    response = requests.get(f"{app_runner.base_url}/", timeout=10)

    # Should return some form of response (might redirect to login)
    assert response.status_code in [200, 302, 401, 403], (
        f"Root endpoint returned unexpected status: {response.status_code}"
    )

    # If we get HTML content, verify it looks like a web page
    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type:
        html_content = response.text.lower()
        web_indicators = ["<html", "<!doctype", "<head", "<body", "<title"]

        assert any(indicator in html_content for indicator in web_indicators), (
            f"Response doesn't appear to be valid HTML. Content preview: {response.text[:200]}"
        )


def test_static_assets_accessible(app_runner):
    """Test that static assets are accessible."""

    # Test common static asset paths
    static_paths = [
        "/static/css/styles.css",
        "/static/js/app.js",
        "/static/favicon/favicon.ico",
    ]

    for path in static_paths:
        response = requests.get(f"{app_runner.base_url}{path}", timeout=5)

        # Static assets might not exist, but server should handle requests gracefully
        # Accept 200 (found), 404 (not found), or 403 (forbidden)
        assert response.status_code in [200, 404, 403], (
            f"Static asset {path} returned unexpected status: {response.status_code}"
        )


def test_api_endpoints_return_proper_content_types(app_runner):
    """Test that API endpoints return appropriate content types."""

    # Test endpoints and their expected content types
    endpoint_tests = [
        ("/auth/check-users", ["text/html"]),
        (
            "/api/debug/info",
            ["application/json", "text/html"],
        ),  # Might redirect to login (HTML)
    ]

    for endpoint, expected_types in endpoint_tests:
        response = requests.get(f"{app_runner.base_url}{endpoint}", timeout=5)

        # Skip if endpoint requires auth and we get 401/403
        if response.status_code in [401, 403]:
            continue

        content_type = response.headers.get("content-type", "").lower()

        type_match = any(
            expected_type in content_type for expected_type in expected_types
        )
        assert type_match, (
            f"Endpoint {endpoint} returned unexpected content type: {content_type}. Expected one of: {expected_types}"
        )


def test_error_handling_graceful(app_runner):
    """Test that the application handles invalid requests gracefully."""

    # Test various invalid requests
    invalid_requests = [
        ("GET", "/nonexistent/endpoint"),
        ("POST", "/auth/login", {"invalid": "data"}),
        ("GET", "/api/nonexistent"),
        ("PUT", "/auth/check-users"),  # Wrong method
    ]

    for method, path, *args in invalid_requests:
        data = args[0] if args else None

        try:
            if method == "GET":
                response = requests.get(f"{app_runner.base_url}{path}", timeout=5)
            elif method == "POST":
                response = requests.post(
                    f"{app_runner.base_url}{path}", data=data, timeout=5
                )
            elif method == "PUT":
                response = requests.put(f"{app_runner.base_url}{path}", timeout=5)
            else:
                continue

            # Should return proper HTTP error codes, not crash
            assert 400 <= response.status_code < 600, (
                f"Request {method} {path} should return error status, got: {response.status_code}"
            )

        except requests.exceptions.RequestException as e:
            pytest.fail(f"Request {method} {path} caused connection error: {e}")


def test_concurrent_requests_handling(app_runner):
    """Test that the application can handle multiple concurrent requests."""

    results = []

    def make_request():
        try:
            response = requests.get(
                f"{app_runner.base_url}/auth/check-users", timeout=10
            )
            results.append(response.status_code)
        except Exception as e:
            results.append(f"Error: {e}")

    # Start multiple concurrent requests
    threads = []
    for _ in range(5):
        thread = threading.Thread(target=make_request)
        threads.append(thread)
        thread.start()

    # Wait for all requests to complete
    for thread in threads:
        thread.join(timeout=15)

    # All requests should have completed successfully
    assert len(results) == 5, f"Expected 5 results, got {len(results)}"

    # All should return valid HTTP status codes
    for result in results:
        assert isinstance(result, int), f"Got error instead of status code: {result}"
        assert 200 <= result < 600, f"Invalid status code: {result}"
