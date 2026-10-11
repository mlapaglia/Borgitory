"""
Tests for building and validating Apprise URLs from form values.
"""

import apprise
import pytest

from borgitory.services.notifications.apprise_catalog import (
    AppriseService,
    get_apprise_catalog,
)
from borgitory.services.notifications.apprise_url_builder import (
    UrlBuildError,
    build_url,
    mask_url,
    split_urls,
    validate_url,
)


def service(service_id: str) -> AppriseService:
    result = get_apprise_catalog().get(service_id)
    assert result is not None
    return result


class TestBuildUrl:
    def test_discord_without_botname(self) -> None:
        url = build_url(
            service("discord"), {"webhook_id": "123", "webhook_token": "abc"}
        )

        assert url == "discord://123/abc"

    def test_discord_with_botname_uses_longer_template(self) -> None:
        url = build_url(
            service("discord"),
            {"webhook_id": "123", "webhook_token": "abc", "botname": "Borg Bot"},
        )

        assert url == "discord://Borg%20Bot@123/abc"

    def test_special_characters_are_encoded(self) -> None:
        url = build_url(
            service("discord"), {"webhook_id": "1", "webhook_token": "a/b?c#d"}
        )

        assert url == "discord://1/a%2Fb%3Fc%23d"

    def test_list_tokens_use_delimiter(self) -> None:
        url = build_url(
            service("tgram"), {"bot_token": "123456:ABC-def", "targets": "-1001, 42"}
        )

        assert url == "tgram://123456%3AABC-def/-1001/42"

    def test_args_are_added_when_not_default(self) -> None:
        url = build_url(
            service("pover"),
            {"user_key": "u", "token": "t", "priority": "1", "sound": "bike"},
        )

        assert url == "pover://u@t?priority=1&sound=bike"

    def test_default_args_are_omitted(self) -> None:
        url = build_url(
            service("pover"),
            {"user_key": "u", "token": "t", "priority": "0", "sound": "pushover"},
        )

        assert url == "pover://u@t"

    def test_bool_args_are_normalized(self) -> None:
        url = build_url(
            service("tgram"),
            {"bot_token": "123456:ABC", "targets": "1", "silent": "true"},
        )

        assert url.endswith("?silent=yes")

    def test_invalid_bool_raises(self) -> None:
        with pytest.raises(UrlBuildError, match="yes or no"):
            build_url(
                service("tgram"),
                {"bot_token": "123456:ABC", "targets": "1", "silent": "maybe"},
            )

    def test_schema_choice(self) -> None:
        ntfy = service("ntfy")

        assert build_url(ntfy, {"topic": "alerts"}) == "ntfys://alerts"
        assert build_url(ntfy, {"schema": "ntfy", "topic": "alerts"}) == (
            "ntfy://alerts"
        )

    def test_unknown_schema_raises(self) -> None:
        with pytest.raises(UrlBuildError, match="Unsupported protocol"):
            build_url(service("ntfy"), {"schema": "http", "topic": "alerts"})

    def test_missing_required_tokens(self) -> None:
        with pytest.raises(UrlBuildError, match="Missing required fields: Webhook"):
            build_url(service("discord"), {"webhook_id": "123"})

    def test_whitespace_only_values_are_missing(self) -> None:
        with pytest.raises(UrlBuildError):
            build_url(service("discord"), {"webhook_id": "123", "webhook_token": " "})

    @pytest.mark.parametrize(
        "service_id,values",
        [
            ("discord", {"webhook_id": "123", "webhook_token": "abc", "botname": "b"}),
            ("tgram", {"bot_token": "123456:ABC-def", "targets": "-1001"}),
            ("pover", {"user_key": "ukey", "token": "tok", "targets": "phone"}),
            ("ntfy", {"host": "ntfy.local", "targets": "alerts", "token": "tk"}),
            ("json", {"host": "localhost", "port": "8080", "method": "PUT"}),
        ],
    )
    def test_built_urls_are_accepted_by_apprise(
        self,
        service_id: str,
        values: dict,  # type: ignore[type-arg]
    ) -> None:
        url = build_url(service(service_id), values)

        assert apprise.Apprise.instantiate(url) is not None
        assert validate_url(url) is None


class TestValidateUrl:
    def test_valid_url(self) -> None:
        assert validate_url("discord://123/abc") is None

    def test_invalid_url_returns_reason(self) -> None:
        error = validate_url("discord://onlyone")

        assert error is not None
        assert "Discord" in error

    def test_unknown_scheme(self) -> None:
        assert validate_url("notaservice://x") is not None


class TestHelpers:
    def test_split_urls(self) -> None:
        assert split_urls(" json://a \n\r\n ntfys://b\n") == ["json://a", "ntfys://b"]

    def test_mask_url_hides_secrets(self) -> None:
        masked = mask_url("pover://userkey1234@apptoken5678")

        assert masked.startswith("pover://")
        assert "userkey1234" not in masked
        assert "apptoken5678" not in masked
