"""E2E test configuration and fixtures using Playwright."""

import tempfile
import shutil
from typing import Generator

import pytest
from playwright.sync_api import Page, BrowserContext, expect

from tests.integration.test_app_startup import AppRunner

E2E_USERNAME = "e2e_admin"
E2E_PASSWORD = "e2e_password_123"

HTMX_BUSY_SELECTOR = ".htmx-request, .htmx-settling, .htmx-swapping, .htmx-added"


def wait_for_htmx(page: Page, timeout: int = 10000) -> None:
    """Wait until HTMX has no in-flight requests or pending swaps."""
    expect(page.locator(HTMX_BUSY_SELECTOR)).to_have_count(0, timeout=timeout)


@pytest.fixture(scope="session")
def e2e_data_dir() -> Generator[str, None, None]:
    """Create a temporary data directory that persists for the entire test session."""
    data_dir = tempfile.mkdtemp(prefix="borgitory_e2e_")
    yield data_dir
    shutil.rmtree(data_dir, ignore_errors=True)


@pytest.fixture(scope="session")
def app_server(e2e_data_dir: str) -> Generator[AppRunner, None, None]:
    """Start the application server once for all E2E tests."""
    runner = AppRunner(e2e_data_dir)
    success = runner.start(timeout=30)
    if not success:
        try:
            stdout, stderr = runner.get_logs()
            print(f"E2E server startup failed!\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}")
        except Exception as e:
            print(f"Could not get logs: {e}")
        pytest.fail("Application failed to start for E2E tests")

    yield runner
    runner.stop()


@pytest.fixture(scope="session")
def register_user(app_server: AppRunner, browser: BrowserContext) -> None:
    """Register the first user (admin) via the browser. Runs once per session."""
    page = browser.new_page()
    try:
        page.goto(f"{app_server.base_url}/")
        page.wait_for_load_state("networkidle")

        page.locator("#reg-username").wait_for(timeout=10000)
        page.fill("#reg-username", E2E_USERNAME)
        page.fill("#reg-password", E2E_PASSWORD)
        page.click("#register-form button[type='submit']")

        # After successful registration the HX-Trigger reloads the auth form
        # container, replacing the register form with the login form.
        page.locator("#login-form").wait_for(timeout=15000)
    finally:
        page.close()


@pytest.fixture()
def authenticated_page(
    app_server: AppRunner,
    register_user: None,
    context: BrowserContext,
) -> Generator[Page, None, None]:
    """Provide a new browser page that is logged in and on the main app."""
    page = context.new_page()

    page.goto(f"{app_server.base_url}/")
    page.wait_for_load_state("networkidle")

    # Fill and submit the login form
    page.locator("#username").wait_for(timeout=10000)
    page.fill("#username", E2E_USERNAME)
    page.fill("#password", E2E_PASSWORD)
    page.click("#login-form button[type='submit']")

    # Wait for redirect to the main app (the sidebar nav should be present)
    page.locator("#nav-repositories").wait_for(timeout=15000)
    page.wait_for_load_state("networkidle")

    yield page

    page.close()
