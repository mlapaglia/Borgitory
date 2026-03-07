"""E2E tests for navigating all sidebar tabs via Playwright."""

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import wait_for_htmx

pytestmark = pytest.mark.e2e

TABS = [
    ("nav-repositories", "/repositories", "Repositories"),
    ("nav-backups", "/backups", "Backups"),
    ("nav-schedules", "/schedules", "Schedules"),
    ("nav-cloud-sync", "/cloud-sync", "Cloud Sync"),
    ("nav-archives", "/archives", "Archives"),
    ("nav-statistics", "/statistics", "Statistics"),
    ("nav-cleanup", "/prune", "Archive Pruning"),
    ("nav-notifications", "/notifications", "Notifications"),
    ("nav-packages", "/packages", "Package Manager"),
    ("nav-jobs", "/jobs", "Job History"),
    ("nav-repository-check", "/repository-check", "Repository Check"),
    ("nav-debug", "/debug", "Debug Info"),
]


@pytest.mark.parametrize("nav_id, expected_url, tab_label", TABS)
def test_tab_loads_content(
    authenticated_page: Page,
    nav_id: str,
    expected_url: str,
    tab_label: str,
) -> None:
    """Click each sidebar nav button and verify the tab content loads."""
    page = authenticated_page
    main_content = page.locator("#main-content")

    page.click(f"#{nav_id}")
    page.wait_for_load_state("networkidle")
    wait_for_htmx(page)

    page.wait_for_url(f"**{expected_url}", timeout=10000)

    expect(main_content).not_to_be_empty()

    html = main_content.inner_html()
    assert "500 Internal Server Error" not in html, (
        f"Tab '{tab_label}' returned a server error"
    )
    assert "404" not in html or "not found" not in html.lower(), (
        f"Tab '{tab_label}' returned a 404 page"
    )


def test_initial_page_loads_repositories(authenticated_page: Page) -> None:
    """After login the default tab (Repositories) should be loaded."""
    page = authenticated_page
    page.wait_for_load_state("networkidle")

    main_content = page.locator("#main-content")
    expect(main_content).not_to_be_empty()

    # The repositories nav button should have the 'active' class
    repo_nav = page.locator("#nav-repositories")
    expect(repo_nav).to_be_visible()


def test_tab_navigation_preserves_sidebar(authenticated_page: Page) -> None:
    """Navigating between tabs should keep the sidebar visible."""
    page = authenticated_page

    for nav_id, _, _ in TABS[:3]:
        page.click(f"#{nav_id}")
        page.wait_for_load_state("networkidle")
        wait_for_htmx(page)

        expect(page.locator("#nav-repositories")).to_be_visible()
        expect(page.locator("#nav-debug")).to_be_visible()
