"""E2E tests for cloud sync provider form field loading."""

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import wait_for_htmx

pytestmark = pytest.mark.e2e

PROVIDERS = [
    (
        "s3",
        "#s3-fields",
        ["provider_config[bucket_name]", "provider_config[access_key]"],
    ),
    (
        "sftp",
        "#sftp-fields",
        ["provider_config[host]", "provider_config[port]", "provider_config[username]"],
    ),
    (
        "smb",
        "#smb-fields",
        ["provider_config[host]", "provider_config[share_name]"],
    ),
    (
        "pcloud",
        "#pcloud-fields",
        ["provider_config[token]", "provider_config[hostname]"],
    ),
]


def _navigate_to_cloud_sync(page: Page) -> None:
    page.click("#nav-cloud-sync")
    page.wait_for_load_state("networkidle")
    page.wait_for_url("**/cloud-sync", timeout=10000)
    wait_for_htmx(page)


@pytest.mark.parametrize("provider_value, fields_id, expected_inputs", PROVIDERS)
def test_provider_fields_load_on_select(
    authenticated_page: Page,
    provider_value: str,
    fields_id: str,
    expected_inputs: list[str],
) -> None:
    """Select a provider from the dropdown and verify its fields appear."""
    page = authenticated_page
    _navigate_to_cloud_sync(page)

    provider_select = page.locator("#provider-select")
    expect(provider_select).to_be_visible(timeout=10000)

    provider_select.select_option(provider_value)
    wait_for_htmx(page)

    fields_container = page.locator(fields_id)
    expect(fields_container).to_be_visible(timeout=10000)

    for input_name in expected_inputs:
        locator = page.locator(f"[name='{input_name}']")
        expect(locator).to_be_visible(timeout=5000)


def test_provider_dropdown_has_all_options(authenticated_page: Page) -> None:
    """The provider dropdown should list every registered provider."""
    page = authenticated_page
    _navigate_to_cloud_sync(page)

    provider_select = page.locator("#provider-select")
    expect(provider_select).to_be_visible(timeout=10000)

    options = provider_select.locator("option").all()
    option_values = [
        opt.get_attribute("value") for opt in options if opt.get_attribute("value")
    ]

    for provider_value, _, _ in PROVIDERS:
        assert provider_value in option_values, (
            f"Provider '{provider_value}' not found in dropdown options: {option_values}"
        )


def test_switching_providers_replaces_fields(authenticated_page: Page) -> None:
    """Switching from one provider to another should swap out the field set."""
    page = authenticated_page
    _navigate_to_cloud_sync(page)

    provider_select = page.locator("#provider-select")
    expect(provider_select).to_be_visible(timeout=10000)

    provider_select.select_option("s3")
    wait_for_htmx(page)
    expect(page.locator("#s3-fields")).to_be_visible(timeout=10000)

    provider_select.select_option("sftp")
    wait_for_htmx(page)
    expect(page.locator("#sftp-fields")).to_be_visible(timeout=10000)

    expect(page.locator("#s3-fields")).to_have_count(0)


def test_provider_fields_include_submit_button(authenticated_page: Page) -> None:
    """Selecting a provider should also render a submit button."""
    page = authenticated_page
    _navigate_to_cloud_sync(page)

    provider_select = page.locator("#provider-select")
    expect(provider_select).to_be_visible(timeout=10000)

    provider_select.select_option("s3")
    wait_for_htmx(page)

    submit_btn = page.locator("#submit-button")
    expect(submit_btn).to_be_visible(timeout=10000)
