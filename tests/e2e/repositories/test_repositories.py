"""E2E tests for repository management."""

import uuid

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import wait_for_htmx

pytestmark = pytest.mark.e2e


def _navigate_to_repositories(page: Page) -> None:
    page.click("#nav-repositories")
    page.wait_for_load_state("networkidle")
    page.wait_for_url("**/repositories", timeout=10000)
    wait_for_htmx(page)


def create_repository(page: Page) -> tuple[str, str]:
    """Create a new repository via the UI. Returns (repo_name, repo_path)."""
    _navigate_to_repositories(page)

    form = page.locator("form[hx-post='/api/repositories/']")
    expect(form).to_be_visible(timeout=15000)

    repo_name = f"e2e-repo-{uuid.uuid4().hex[:8]}"
    repo_path = f"/tmp/borgitory-e2e-{uuid.uuid4().hex[:8]}"

    form.locator("input[name='name']").fill(repo_name)
    form.locator("input[name='path']").fill(repo_path)
    form.locator("select[name='encryption_type']").select_option("none")
    form.locator("button[type='submit']").click()
    wait_for_htmx(page)

    list_region = page.locator("#repository-list")
    expect(list_region).to_contain_text(repo_name, timeout=15000)
    expect(list_region).to_contain_text(repo_path, timeout=5000)

    return repo_name, repo_path


def test_create_new_repository(authenticated_page: Page) -> None:
    """Create a repository via the UI; new repo appears in the list."""
    page = authenticated_page
    create_repository(page)
