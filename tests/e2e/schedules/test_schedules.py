"""E2E tests for schedule management."""

import uuid

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import wait_for_htmx
from tests.e2e.repositories.test_repositories import create_repository

pytestmark = pytest.mark.e2e


def _navigate_to_schedules(page: Page) -> None:
    page.click("#nav-schedules")
    page.wait_for_load_state("networkidle")
    page.wait_for_url("**/schedules", timeout=10000)
    wait_for_htmx(page)


def test_create_schedule_with_multiple_source_paths(authenticated_page: Page) -> None:
    """Create a schedule using a new repository and multiple source paths."""
    page = authenticated_page
    repo_name, _ = create_repository(page)

    _navigate_to_schedules(page)

    schedule_form = page.locator("form[hx-post='/api/schedules/']")
    expect(schedule_form).to_be_visible(timeout=15000)

    schedule_name = f"e2e-schedule-{uuid.uuid4().hex[:8]}"
    schedule_form.locator("input[name='name']").fill(schedule_name)
    schedule_form.locator("select[name='repository_id']").select_option(label=repo_name)

    schedule_form.locator("button[hx-post*='source-paths-modal']").click()
    wait_for_htmx(page)

    source_paths_form = page.locator(
        "form[hx-post='/api/schedules/source-paths/save-source-paths']"
    )
    expect(source_paths_form).to_be_visible(timeout=10000)

    path_inputs = source_paths_form.locator("input[name='source_paths']")
    expect(path_inputs.first).to_be_visible(timeout=5000)
    path_inputs.nth(0).fill("/tmp/e2e-src1")

    source_paths_form.locator("button:has-text('+ Add Path')").click()
    wait_for_htmx(page)

    path_inputs = source_paths_form.locator("input[name='source_paths']")
    expect(path_inputs.nth(1)).to_be_visible(timeout=5000)
    path_inputs.nth(1).fill("/tmp/e2e-src2")

    source_paths_form.locator("button[type='submit']:has-text('Save & Close')").click()
    wait_for_htmx(page)

    expect(page.get_by_text("Source Paths Configuration")).not_to_be_visible(timeout=10000)

    schedule_form = page.locator("form[hx-post='/api/schedules/']")
    schedule_form.locator("#schedule-preset").select_option("0 2 * * *")
    wait_for_htmx(page)

    expect(schedule_form.locator("#cron-expression")).to_have_value("0 2 * * *", timeout=5000)

    schedule_form.locator("button[type='submit']:has-text('Create Schedule')").click()
    wait_for_htmx(page)

    schedules_list = page.locator("#schedules-list")
    expect(schedules_list).to_contain_text(schedule_name, timeout=15000)
    expect(schedules_list).to_contain_text(repo_name, timeout=5000)
