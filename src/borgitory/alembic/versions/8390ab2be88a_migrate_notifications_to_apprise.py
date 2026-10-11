"""Migrate notification configs to Apprise

Converts Pushover, Discord and Telegram notification configs to the Apprise
storage format. Rows that cannot be converted are disabled and flagged so the
user can re-configure them; this migration never fails on bad data.

This migration is intentionally self-contained (no imports from the application's
notification code) so later refactors cannot change what it does.

Revision ID: 8390ab2be88a
Revises: 256b9fa9d31f
Create Date: 2026-10-08 14:00:00.000000

"""

import base64
import hashlib
import json
import logging
import os
import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union
from urllib.parse import quote, urlencode

from alembic import op
import sqlalchemy as sa
from cryptography.fernet import Fernet


# revision identifiers, used by Alembic.
revision: str = "8390ab2be88a"
down_revision: Union[str, Sequence[str], None] = "256b9fa9d31f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

APPRISE_PROVIDER = "apprise"
LEGACY_SECRET_FIELDS = {
    "pushover": ("user_key", "app_token"),
    "discord": ("webhook_url",),
    "telegram": ("bot_token",),
}
SERVICE_NAMES = {"pover": "Pushover", "discord": "Discord", "tgram": "Telegram"}
LEGACY_TO_SERVICE = {"pushover": "pover", "discord": "discord", "telegram": "tgram"}
DISCORD_WEBHOOK_RE = re.compile(
    r"^https?://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/(\d+)/([\w-]+)"
)


class ConversionError(Exception):
    pass


def _load_cipher() -> Optional[Fernet]:
    """Build the app's Fernet cipher without ever generating a new secret key"""
    secret_key = os.getenv("SECRET_KEY")
    if not secret_key:
        try:
            from borgitory.config_module import DATA_DIR

            secret_file = os.path.join(DATA_DIR, "secret_key")
            if os.path.exists(secret_file):
                with open(secret_file) as f:
                    secret_key = f.read().strip()
        except Exception as e:
            logger.warning(f"Could not read secret key file: {e}")
    if not secret_key:
        return None
    fernet_key = base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode()).digest())
    return Fernet(fernet_key)


def _q(value: str) -> str:
    return quote(value.strip(), safe="")


def _with_query(url: str, query: Dict[str, str]) -> str:
    return f"{url}?{urlencode(query, quote_via=quote)}" if query else url


def _is_true(value: object) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _str(value: object) -> str:
    return "" if value is None else str(value).strip()


def _convert_pushover(
    legacy: Dict[str, object],
) -> Tuple[Dict[str, str], Dict[str, str], str]:
    user_key, token = _str(legacy.get("user_key")), _str(legacy.get("app_token"))
    if not user_key or not token:
        raise ConversionError("Pushover user key and app token are required")

    fields: Dict[str, str] = {}
    query: Dict[str, str] = {}
    device = _str(legacy.get("device"))
    if device:
        fields["targets"] = device

    priority = _str(legacy.get("priority"))
    if priority and priority != "0":
        if priority not in ("-2", "-1", "1", "2"):
            raise ConversionError(f"Unsupported Pushover priority: {priority}")
        fields["priority"] = priority
        query["priority"] = priority

    sound = _str(legacy.get("sound"))
    if sound and sound != "default":
        fields["sound"] = sound
        query["sound"] = sound

    url = f"pover://{_q(user_key)}@{_q(token)}"
    if device:
        url += f"/{_q(device)}"
    return fields, {"user_key": user_key, "token": token}, _with_query(url, query)


def _convert_discord(
    legacy: Dict[str, object],
) -> Tuple[Dict[str, str], Dict[str, str], str]:
    webhook_url = _str(legacy.get("webhook_url"))
    match = DISCORD_WEBHOOK_RE.match(webhook_url)
    if not match:
        raise ConversionError("Discord webhook URL could not be parsed")
    webhook_id, webhook_token = match.group(1), match.group(2)

    fields: Dict[str, str] = {}
    query: Dict[str, str] = {}
    botname = _str(legacy.get("username"))
    if botname:
        fields["botname"] = botname
    avatar_url = _str(legacy.get("avatar_url"))
    if avatar_url:
        fields["avatar_url"] = avatar_url
        query["avatar_url"] = avatar_url

    url = "discord://"
    if botname:
        url += f"{_q(botname)}@"
    url += f"{_q(webhook_id)}/{_q(webhook_token)}"
    secrets = {"webhook_id": webhook_id, "webhook_token": webhook_token}
    return fields, secrets, _with_query(url, query)


def _convert_telegram(
    legacy: Dict[str, object],
) -> Tuple[Dict[str, str], Dict[str, str], str]:
    bot_token, chat_id = _str(legacy.get("bot_token")), _str(legacy.get("chat_id"))
    if not bot_token or not chat_id:
        raise ConversionError("Telegram bot token and chat ID are required")

    fields: Dict[str, str] = {"targets": chat_id}
    query: Dict[str, str] = {}
    if _is_true(legacy.get("disable_notification")):
        fields["silent"] = "yes"
        query["silent"] = "yes"

    url = f"tgram://{_q(bot_token)}/{_q(chat_id)}"
    return fields, {"bot_token": bot_token}, _with_query(url, query)


CONVERTERS: Dict[
    str, Callable[[Dict[str, object]], Tuple[Dict[str, str], Dict[str, str], str]]
] = {
    "pushover": _convert_pushover,
    "discord": _convert_discord,
    "telegram": _convert_telegram,
}


def _decrypt_legacy(
    provider: str, raw: Dict[str, object], cipher: Optional[Fernet]
) -> Dict[str, object]:
    legacy = dict(raw)
    for field in LEGACY_SECRET_FIELDS.get(provider, ()):
        encrypted = legacy.pop(f"encrypted_{field}", None)
        if encrypted:
            if cipher is None:
                raise ConversionError("Secret key unavailable; cannot decrypt settings")
            legacy[field] = cipher.decrypt(str(encrypted).encode()).decode()
    return legacy


def _validate(url: str) -> None:
    import apprise

    if apprise.Apprise.instantiate(url, suppress_exceptions=True) is None:
        raise ConversionError("Converted settings were rejected by Apprise")


def convert_row(
    provider: str, provider_config: str, cipher: Optional[Fernet]
) -> Tuple[Dict[str, object], bool]:
    """
    Convert a legacy row to the Apprise format.

    Returns:
        Tuple of (new provider_config dict, whether the row may stay enabled)
    """
    service = LEGACY_TO_SERVICE.get(provider)
    stored: Dict[str, object] = {
        "version": 1,
        "mode": "service" if service else "manual",
        "service_name": SERVICE_NAMES.get(service or "", provider.title()),
        "encrypted_urls": "",
        "legacy_provider": provider,
    }
    if service:
        stored.update({"service": service, "fields": {}, "encrypted_fields": {}})

    try:
        if not service:
            raise ConversionError(f"Unsupported notification provider: {provider}")
        if cipher is None:
            raise ConversionError("Secret key unavailable; cannot encrypt settings")

        raw = json.loads(provider_config) if provider_config else {}
        if not isinstance(raw, dict):
            raise ConversionError("Stored settings are not a JSON object")

        legacy = _decrypt_legacy(provider, raw, cipher)
        fields, secrets, url = CONVERTERS[provider](legacy)
        _validate(url)

        stored["fields"] = fields
        stored["encrypted_fields"] = {
            k: cipher.encrypt(v.encode()).decode() for k, v in secrets.items()
        }
        stored["encrypted_urls"] = cipher.encrypt(url.encode()).decode()
        return stored, True
    except Exception as e:
        reason = str(e) if isinstance(e, ConversionError) else type(e).__name__
        stored["migration_error"] = (
            f"Could not convert this {provider} notification automatically ({reason}). "
            "Edit it, re-enter its settings and save."
        )
        return stored, False


def upgrade() -> None:
    """Convert legacy notification configs to Apprise."""
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, name, provider, provider_config FROM notification_configs "
            "WHERE provider != :provider"
        ),
        {"provider": APPRISE_PROVIDER},
    ).fetchall()
    if not rows:
        return

    cipher = _load_cipher()
    for row_id, name, provider, provider_config in rows:
        stored, keep_enabled = convert_row(provider, provider_config, cipher)
        params: Dict[str, object] = {
            "id": row_id,
            "provider": APPRISE_PROVIDER,
            "provider_config": json.dumps(stored),
        }
        if keep_enabled:
            conn.execute(
                sa.text(
                    "UPDATE notification_configs SET provider = :provider, "
                    "provider_config = :provider_config WHERE id = :id"
                ),
                params,
            )
        else:
            logger.warning(
                f"Notification '{name}' could not be migrated to Apprise and was disabled: "
                f"{stored.get('migration_error')}"
            )
            conn.execute(
                sa.text(
                    "UPDATE notification_configs SET provider = :provider, "
                    "provider_config = :provider_config, enabled = 0 WHERE id = :id"
                ),
                params,
            )


def _revert_row(
    stored: Dict[str, object], cipher: Fernet
) -> Optional[Tuple[str, Dict[str, object]]]:
    """Best-effort conversion of an Apprise row back to the legacy format"""
    service = stored.get("service")
    raw_fields = stored.get("fields")
    raw_secrets = stored.get("encrypted_fields")
    if stored.get("mode") != "service" or not isinstance(raw_fields, dict):
        return None
    if not isinstance(raw_secrets, dict):
        return None

    fields = {str(k): str(v) for k, v in raw_fields.items()}
    secrets = {
        str(k): cipher.decrypt(str(v).encode()).decode() for k, v in raw_secrets.items()
    }

    def enc(value: str) -> str:
        return cipher.encrypt(value.encode()).decode()

    legacy: Dict[str, object]
    if service == "pover" and "user_key" in secrets and "token" in secrets:
        legacy = {
            "encrypted_user_key": enc(secrets["user_key"]),
            "encrypted_app_token": enc(secrets["token"]),
            "priority": int(fields.get("priority", "0")),
            "sound": fields.get("sound", "default"),
        }
        targets: List[str] = [
            t for t in re.split(r"[,\s/]+", fields.get("targets", "")) if t
        ]
        if targets:
            legacy["device"] = targets[0]
        return "pushover", legacy
    if service == "discord" and "webhook_id" in secrets and "webhook_token" in secrets:
        legacy = {
            "encrypted_webhook_url": enc(
                f"https://discord.com/api/webhooks/{secrets['webhook_id']}/{secrets['webhook_token']}"
            )
        }
        if fields.get("botname"):
            legacy["username"] = fields["botname"]
        if fields.get("avatar_url"):
            legacy["avatar_url"] = fields["avatar_url"]
        return "discord", legacy
    if service == "tgram" and "bot_token" in secrets and fields.get("targets"):
        chat_id = [t for t in re.split(r"[,\s/]+", fields["targets"]) if t][0]
        legacy = {
            "encrypted_bot_token": enc(secrets["bot_token"]),
            "chat_id": chat_id,
            "parse_mode": "HTML",
            "disable_notification": fields.get("silent") == "yes",
        }
        return "telegram", legacy
    return None


def downgrade() -> None:
    """Convert Pushover, Discord and Telegram configs back; disable the rest."""
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, provider_config FROM notification_configs WHERE provider = :provider"
        ),
        {"provider": APPRISE_PROVIDER},
    ).fetchall()
    if not rows:
        return

    cipher = _load_cipher()
    for row_id, provider_config in rows:
        reverted = None
        try:
            stored = json.loads(provider_config) if provider_config else {}
            if cipher is not None and isinstance(stored, dict):
                reverted = _revert_row(stored, cipher)
        except Exception as e:
            logger.warning(f"Could not revert notification {row_id}: {e}")

        if reverted is None:
            conn.execute(
                sa.text("UPDATE notification_configs SET enabled = 0 WHERE id = :id"),
                {"id": row_id},
            )
            continue

        provider, legacy = reverted
        conn.execute(
            sa.text(
                "UPDATE notification_configs SET provider = :provider, "
                "provider_config = :provider_config WHERE id = :id"
            ),
            {"id": row_id, "provider": provider, "provider_config": json.dumps(legacy)},
        )
