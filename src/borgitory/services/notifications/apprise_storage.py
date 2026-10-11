"""
Storage format for Apprise notification configurations.

Stored in ``notification_configs.provider_config`` as JSON:

    {"version": 1, "mode": "service", "service": "discord", "service_name": "Discord",
     "fields": {...non-secret values...},
     "encrypted_fields": {...encrypted secret values...},
     "encrypted_urls": "<encrypted newline separated apprise urls>"}

Secret field values are kept so the edit form can be repopulated without parsing
URLs back into fields. The URL is what is actually sent, so a stored notification
keeps working even if Apprise changes a service's form fields in a later release.
"""

import json
from dataclasses import dataclass, field
from typing import Dict, Literal, Optional

APPRISE_PROVIDER = "apprise"
STORAGE_VERSION = 1

AppriseMode = Literal["service", "manual"]
MANUAL_SERVICE_ID = "__manual__"
MANUAL_SERVICE_NAME = "Custom Apprise URL"


@dataclass
class AppriseSubmission:
    """Notification settings as submitted from the add/edit form"""

    mode: AppriseMode
    service: Optional[str] = None
    values: Dict[str, str] = field(default_factory=dict)
    urls: str = ""


@dataclass
class StoredAppriseConfig:
    """Notification settings as persisted in the database"""

    mode: AppriseMode
    service_name: str
    service: Optional[str] = None
    fields: Dict[str, str] = field(default_factory=dict)
    encrypted_fields: Dict[str, str] = field(default_factory=dict)
    encrypted_urls: str = ""
    migration_error: Optional[str] = None
    legacy_provider: Optional[str] = None

    def encode(self) -> str:
        data: Dict[str, object] = {
            "version": STORAGE_VERSION,
            "mode": self.mode,
            "service_name": self.service_name,
            "encrypted_urls": self.encrypted_urls,
        }
        if self.mode == "service":
            data["service"] = self.service
            data["fields"] = self.fields
            data["encrypted_fields"] = self.encrypted_fields
        if self.migration_error:
            data["migration_error"] = self.migration_error
        if self.legacy_provider:
            data["legacy_provider"] = self.legacy_provider
        return json.dumps(data)

    @classmethod
    def decode(cls, raw: str) -> "StoredAppriseConfig":
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError as e:
            raise ValueError(f"Notification configuration is not valid JSON: {e}")

        if not isinstance(data, dict) or data.get("mode") not in ("service", "manual"):
            raise ValueError("Notification configuration is not in Apprise format")

        def str_dict(value: object) -> Dict[str, str]:
            if not isinstance(value, dict):
                return {}
            return {str(k): str(v) for k, v in value.items() if v is not None}

        service = data.get("service")
        migration_error = data.get("migration_error")
        legacy_provider = data.get("legacy_provider")
        return cls(
            mode=data["mode"],
            service_name=str(
                data.get("service_name") or service or MANUAL_SERVICE_NAME
            ),
            service=str(service) if service else None,
            fields=str_dict(data.get("fields")),
            encrypted_fields=str_dict(data.get("encrypted_fields")),
            encrypted_urls=str(data.get("encrypted_urls") or ""),
            migration_error=str(migration_error) if migration_error else None,
            legacy_provider=str(legacy_provider) if legacy_provider else None,
        )

    @classmethod
    def try_decode(cls, raw: str) -> Optional["StoredAppriseConfig"]:
        try:
            return cls.decode(raw)
        except ValueError:
            return None
