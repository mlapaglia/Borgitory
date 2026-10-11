"""
Tests for the Apprise service catalog, using the real Apprise plugin metadata.
"""

from borgitory.services.notifications.apprise_catalog import (
    AppriseCatalog,
    get_apprise_catalog,
)


def tokens_by_key(service_id: str) -> dict:  # type: ignore[type-arg]
    service = get_apprise_catalog().get(service_id)
    assert service is not None
    return {t.key: t for t in service.tokens}


class TestAppriseCatalog:
    def test_loads_many_services(self) -> None:
        assert len(get_apprise_catalog()) > 50

    def test_discord_tokens(self) -> None:
        tokens = tokens_by_key("discord")

        assert list(tokens) == ["webhook_id", "webhook_token", "botname"]
        assert tokens["webhook_id"].private and tokens["webhook_id"].required
        assert tokens["webhook_token"].private and tokens["webhook_token"].required
        assert not tokens["botname"].private and not tokens["botname"].required

    def test_pushover_fields(self) -> None:
        service = get_apprise_catalog().get("pover")
        assert service is not None
        tokens = {t.key: t for t in service.tokens}

        assert tokens["user_key"].private
        assert tokens["token"].private
        assert tokens["targets"].kind == "list"
        assert "Target Device" in tokens["targets"].label
        assert "target_device" not in tokens

        priority = service.get_field("priority")
        assert priority is not None
        assert priority.kind == "choice"
        assert ("2", "2") in priority.choices

    def test_alias_args_are_dropped(self) -> None:
        service = get_apprise_catalog().get("pover")
        assert service is not None

        assert service.get_field("to") is None

    def test_telegram_fields(self) -> None:
        tokens = tokens_by_key("tgram")

        assert tokens["bot_token"].private
        assert tokens["bot_token"].required
        assert not tokens["targets"].required

    def test_multiple_protocols_offer_schema_choice(self) -> None:
        service = get_apprise_catalog().get("ntfy")
        assert service is not None
        schema = service.get_field("schema")

        assert schema is not None
        assert schema.kind == "choice"
        assert service.default_schema == "ntfys"
        assert {v for v, _ in schema.choices} == {"ntfy", "ntfys"}

    def test_lookup_by_secure_protocol(self) -> None:
        catalog = get_apprise_catalog()

        assert catalog.get("jsons") is catalog.get("json")

    def test_advanced_args_are_flagged(self) -> None:
        service = get_apprise_catalog().get("json")
        assert service is not None

        assert "verify" in {a.key for a in service.advanced_args}
        assert "method" in {a.key for a in service.basic_args}

    def test_desktop_services_excluded(self) -> None:
        catalog = get_apprise_catalog()

        for service_id in ("dbus", "macosx", "windows", "gnome"):
            assert catalog.get(service_id) is None

    def test_grouped_puts_popular_first(self) -> None:
        groups = get_apprise_catalog().grouped()

        assert groups[0].label == "Popular"
        assert groups[0].services[0].id == "discord"
        all_names = [s.name.lower() for s in groups[-1].services]
        assert all_names == sorted(all_names)


class TestAppriseCatalogFromFixture:
    def test_skips_malformed_schemas(self) -> None:
        catalog = AppriseCatalog(
            {
                "version": "test",
                "schemas": [
                    {"service_name": "No protocols", "details": {}},
                    {
                        "service_name": "No templates",
                        "secure_protocols": ["notemplates"],
                        "details": {"templates": [], "tokens": {}, "args": {}},
                    },
                    "not a dict",
                    {
                        "service_name": "Example",
                        "protocols": "example",
                        "details": {
                            "templates": ["{schema}://{token}"],
                            "tokens": {
                                "token": {
                                    "name": "Token",
                                    "type": "string",
                                    "private": True,
                                }
                            },
                            "args": {"alias": {"alias_of": "token"}},
                        },
                    },
                ],
            }
        )

        assert len(catalog) == 1
        example = catalog.get("example")
        assert example is not None
        assert [t.key for t in example.tokens] == ["token"]
        assert example.tokens[0].required
        assert example.args == ()
