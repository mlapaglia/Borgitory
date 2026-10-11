"""
Tests for the data migration that converts legacy notification configs to Apprise.
"""

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Dict, Iterator, Optional

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from cryptography.fernet import Fernet

from borgitory.models.database import get_cipher_suite
from borgitory.services.encryption_service import EncryptionService
from borgitory.services.notifications.apprise_catalog import get_apprise_catalog
from borgitory.services.notifications.apprise_storage import StoredAppriseConfig
from borgitory.services.notifications.apprise_url_builder import build_url

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "src/borgitory/alembic/versions/8390ab2be88a_migrate_notifications_to_apprise.py"
)


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "migration_8390ab2be88a", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = load_migration()


@pytest.fixture
def engine() -> Iterator[sa.Engine]:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE notification_configs ("
                "id INTEGER PRIMARY KEY, name VARCHAR, provider VARCHAR, "
                "provider_config TEXT, enabled BOOLEAN)"
            )
        )
    yield engine
    engine.dispose()


def encrypt(value: str) -> str:
    return get_cipher_suite().encrypt(value.encode()).decode()


def insert(
    engine: sa.Engine, name: str, provider: str, config: Dict[str, object]
) -> None:
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO notification_configs (name, provider, provider_config, enabled) "
                "VALUES (:name, :provider, :config, 1)"
            ),
            {"name": name, "provider": provider, "config": json.dumps(config)},
        )


def run(engine: sa.Engine, direction: str = "upgrade") -> None:
    with engine.begin() as conn:
        context = MigrationContext.configure(conn)
        with Operations.context(context):
            getattr(migration, direction)()


def fetch(engine: sa.Engine, name: str) -> tuple[str, str, bool]:
    with engine.connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT provider, provider_config, enabled FROM notification_configs "
                "WHERE name = :name"
            ),
            {"name": name},
        ).one()
    return row[0], row[1], bool(row[2])


def migrated(engine: sa.Engine, name: str) -> tuple[StoredAppriseConfig, bool]:
    provider, provider_config, enabled = fetch(engine, name)
    assert provider == "apprise"
    return StoredAppriseConfig.decode(provider_config), enabled


def assert_matches_form_builder(stored: StoredAppriseConfig) -> None:
    """The migrated fields must rebuild the same URL through the normal form path."""
    encryption = EncryptionService()
    service = get_apprise_catalog().get(stored.service or "")
    assert service is not None
    values = dict(stored.fields)
    values.update(
        {k: encryption.decrypt_value(v) for k, v in stored.encrypted_fields.items()}
    )
    assert build_url(service, values) == encryption.decrypt_value(stored.encrypted_urls)


class TestUpgrade:
    def test_pushover(self, engine: sa.Engine) -> None:
        insert(
            engine,
            "pushover",
            "pushover",
            {
                "encrypted_user_key": encrypt("u" * 30),
                "encrypted_app_token": encrypt("a" * 30),
                "priority": "1",
                "sound": "bike",
                "device": "phone",
            },
        )

        run(engine)

        stored, enabled = migrated(engine, "pushover")
        assert enabled is True
        assert stored.migration_error is None
        assert stored.service == "pover"
        assert stored.fields == {"targets": "phone", "priority": "1", "sound": "bike"}
        assert set(stored.encrypted_fields) == {"user_key", "token"}
        assert_matches_form_builder(stored)

    def test_pushover_defaults_are_dropped(self, engine: sa.Engine) -> None:
        insert(
            engine,
            "pushover",
            "pushover",
            {
                "encrypted_user_key": encrypt("u" * 30),
                "encrypted_app_token": encrypt("a" * 30),
                "priority": 0,
                "sound": "default",
            },
        )

        run(engine)

        stored, _ = migrated(engine, "pushover")
        assert stored.fields == {}
        assert_matches_form_builder(stored)

    def test_discord(self, engine: sa.Engine) -> None:
        insert(
            engine,
            "discord",
            "discord",
            {
                "encrypted_webhook_url": encrypt(
                    "https://discord.com/api/webhooks/123456789/tok-en_value"
                ),
                "username": "Borg Bot",
                "avatar_url": "https://example.com/a.png",
            },
        )

        run(engine)

        stored, enabled = migrated(engine, "discord")
        assert enabled is True
        assert stored.service == "discord"
        assert stored.fields == {
            "botname": "Borg Bot",
            "avatar_url": "https://example.com/a.png",
        }
        encryption = EncryptionService()
        assert encryption.decrypt_value(stored.encrypted_fields["webhook_id"]) == (
            "123456789"
        )
        assert_matches_form_builder(stored)

    def test_telegram(self, engine: sa.Engine) -> None:
        insert(
            engine,
            "telegram",
            "telegram",
            {
                "encrypted_bot_token": encrypt("123456:ABC-def"),
                "chat_id": "-1001234",
                "parse_mode": "HTML",
                "disable_notification": True,
            },
        )

        run(engine)

        stored, enabled = migrated(engine, "telegram")
        assert enabled is True
        assert stored.service == "tgram"
        assert stored.fields == {"targets": "-1001234", "silent": "yes"}
        assert_matches_form_builder(stored)

    def test_unparseable_discord_url_is_disabled(self, engine: sa.Engine) -> None:
        insert(
            engine,
            "bad",
            "discord",
            {"encrypted_webhook_url": encrypt("https://example.com/hook")},
        )

        run(engine)

        stored, enabled = migrated(engine, "bad")
        assert enabled is False
        assert stored.migration_error is not None
        assert "webhook URL could not be parsed" in stored.migration_error
        assert stored.service == "discord"

    def test_undecryptable_row_is_disabled(self, engine: sa.Engine) -> None:
        other_key = Fernet(Fernet.generate_key())
        insert(
            engine,
            "wrong-key",
            "pushover",
            {
                "encrypted_user_key": other_key.encrypt(b"u" * 30).decode(),
                "encrypted_app_token": other_key.encrypt(b"a" * 30).decode(),
            },
        )

        run(engine)

        stored, enabled = migrated(engine, "wrong-key")
        assert enabled is False
        assert stored.migration_error is not None
        assert "InvalidToken" in stored.migration_error

    def test_unknown_provider_is_disabled(self, engine: sa.Engine) -> None:
        insert(engine, "slack", "slack", {"webhook": "x"})

        run(engine)

        stored, enabled = migrated(engine, "slack")
        assert enabled is False
        assert stored.mode == "manual"
        assert stored.legacy_provider == "slack"

    def test_invalid_json_is_disabled(self, engine: sa.Engine) -> None:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO notification_configs (name, provider, provider_config, enabled) "
                    "VALUES ('broken', 'pushover', '{not json', 1)"
                )
            )

        run(engine)

        _, enabled = migrated(engine, "broken")
        assert enabled is False

    def test_apprise_rows_are_untouched(self, engine: sa.Engine) -> None:
        insert(engine, "already", "apprise", {"mode": "manual", "keep": True})

        run(engine)

        provider, provider_config, _ = fetch(engine, "already")
        assert provider == "apprise"
        assert json.loads(provider_config) == {"mode": "manual", "keep": True}

    def test_missing_secret_key_disables_rows(
        self,
        engine: sa.Engine,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        insert(
            engine,
            "pushover",
            "pushover",
            {
                "encrypted_user_key": encrypt("u" * 30),
                "encrypted_app_token": encrypt("a" * 30),
            },
        )
        monkeypatch.delenv("SECRET_KEY")
        monkeypatch.setattr("borgitory.config_module.DATA_DIR", str(tmp_path))

        run(engine)

        stored, enabled = migrated(engine, "pushover")
        assert enabled is False
        assert stored.migration_error is not None
        assert not (tmp_path / "secret_key").exists()


class TestDowngrade:
    def round_trip(
        self, engine: sa.Engine, provider: str, config: Dict[str, object]
    ) -> Dict[str, object]:
        insert(engine, provider, provider, config)
        run(engine)
        run(engine, "downgrade")
        restored_provider, provider_config, enabled = fetch(engine, provider)
        assert restored_provider == provider
        assert enabled is True
        restored: Dict[str, object] = json.loads(provider_config)
        return restored

    def decrypt(self, value: Optional[object]) -> str:
        return get_cipher_suite().decrypt(str(value).encode()).decode()

    def test_pushover(self, engine: sa.Engine) -> None:
        restored = self.round_trip(
            engine,
            "pushover",
            {
                "encrypted_user_key": encrypt("u" * 30),
                "encrypted_app_token": encrypt("a" * 30),
                "priority": 1,
                "sound": "bike",
                "device": "phone",
            },
        )

        assert self.decrypt(restored["encrypted_user_key"]) == "u" * 30
        assert self.decrypt(restored["encrypted_app_token"]) == "a" * 30
        assert restored["priority"] == 1
        assert restored["sound"] == "bike"
        assert restored["device"] == "phone"

    def test_discord(self, engine: sa.Engine) -> None:
        webhook = "https://discord.com/api/webhooks/123456789/token"
        restored = self.round_trip(
            engine,
            "discord",
            {"encrypted_webhook_url": encrypt(webhook), "username": "Bot"},
        )

        assert self.decrypt(restored["encrypted_webhook_url"]) == webhook
        assert restored["username"] == "Bot"

    def test_telegram(self, engine: sa.Engine) -> None:
        restored = self.round_trip(
            engine,
            "telegram",
            {
                "encrypted_bot_token": encrypt("123456:ABC-def"),
                "chat_id": "-100",
                "disable_notification": True,
            },
        )

        assert self.decrypt(restored["encrypted_bot_token"]) == "123456:ABC-def"
        assert restored["chat_id"] == "-100"
        assert restored["disable_notification"] is True

    def test_other_services_are_disabled(self, engine: sa.Engine) -> None:
        insert(engine, "manual", "apprise", {"mode": "manual", "service_name": "x"})

        run(engine, "downgrade")

        provider, _, enabled = fetch(engine, "manual")
        assert provider == "apprise"
        assert enabled is False
