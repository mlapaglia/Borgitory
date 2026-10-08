"""
Catalog of notification services supported by Apprise.

Normalizes the metadata returned by ``apprise.Apprise().details()`` into a
small, template-friendly structure used to generate the notification forms.
"""

import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, FrozenSet, List, Literal, Mapping, Optional, Tuple

import apprise

logger = logging.getLogger(__name__)

FieldKind = Literal["string", "int", "float", "bool", "choice", "list"]
FieldPlacement = Literal["token", "arg"]

# Services that only work on a local desktop session and make no sense in a server app
EXCLUDED_SERVICES = frozenset(
    {"dbus", "kde", "qt", "glib", "gnome", "macosx", "windows"}
)

# Shown first in the service dropdown, in this order
POPULAR_SERVICES = (
    "discord",
    "tgram",
    "pover",
    "ntfy",
    "slack",
    "gotify",
    "mailto",
    "msteams",
    "matrix",
    "json",
    "apprise",
)

# Generic arguments every Apprise plugin accepts; hidden under "advanced"
ADVANCED_ARGS = frozenset(
    {
        "verify",
        "redirect",
        "rto",
        "cto",
        "overflow",
        "format",
        "emojis",
        "store",
        "tz",
        "retry",
        "wait",
        "optional",
    }
)

_PLACEHOLDER_RE = re.compile(r"{(\w+)}")
_GROUP_MEMBER_RE = re.compile(r"'([^']+)'")


@dataclass(frozen=True)
class AppriseField:
    """A single form field for an Apprise service (URL token or query argument)"""

    key: str
    label: str
    kind: FieldKind
    placement: FieldPlacement
    required: bool = False
    private: bool = False
    advanced: bool = False
    default: Optional[str] = None
    choices: Tuple[Tuple[str, str], ...] = ()
    min: Optional[float] = None
    max: Optional[float] = None
    delim: str = "/"


@dataclass(frozen=True)
class AppriseService:
    """An Apprise notification service and the fields needed to build its URL"""

    id: str
    name: str
    setup_url: Optional[str]
    service_url: Optional[str]
    schemas: Tuple[str, ...]
    default_schema: str
    templates: Tuple[str, ...]
    tokens: Tuple[AppriseField, ...] = field(default_factory=tuple)
    args: Tuple[AppriseField, ...] = field(default_factory=tuple)

    @property
    def private_keys(self) -> FrozenSet[str]:
        return frozenset(f.key for f in (*self.tokens, *self.args) if f.private)

    @property
    def basic_args(self) -> Tuple[AppriseField, ...]:
        return tuple(a for a in self.args if not a.advanced)

    @property
    def advanced_args(self) -> Tuple[AppriseField, ...]:
        return tuple(a for a in self.args if a.advanced)

    def get_field(self, key: str) -> Optional[AppriseField]:
        for f in (*self.tokens, *self.args):
            if f.key == key:
                return f
        return None


@dataclass(frozen=True)
class AppriseServiceGroup:
    """A labelled group of services for the dropdown"""

    label: str
    services: Tuple[AppriseService, ...]


def _as_tuple(value: object) -> Tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(str(v) for v in value)
    return ()


def template_keys(template: str) -> List[str]:
    return [k for k in _PLACEHOLDER_RE.findall(template) if k != "schema"]


def _parse_kind(raw_type: object) -> Tuple[FieldKind, str]:
    """Split Apprise types like 'choice:string' into (kind, subtype)"""
    type_str = str(raw_type or "string")
    prefix, _, subtype = type_str.partition(":")
    if prefix in ("choice", "list"):
        return prefix, subtype or "string"  # type: ignore[return-value]
    if prefix in ("int", "float", "bool"):
        return prefix, prefix  # type: ignore[return-value]
    return "string", "string"


def _format_default(value: object) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _group_members(raw_group: object) -> List[str]:
    if isinstance(raw_group, (set, frozenset, list, tuple)):
        return sorted(str(m) for m in raw_group)
    if isinstance(raw_group, str):
        return sorted(_GROUP_MEMBER_RE.findall(raw_group))
    return []


def _build_field(
    key: str,
    spec: Mapping[str, object],
    placement: FieldPlacement,
    required: bool,
    label_override: Optional[str] = None,
) -> AppriseField:
    kind, _ = _parse_kind(spec.get("type"))
    values = spec.get("values")
    choices: Tuple[Tuple[str, str], ...] = ()
    if kind == "choice" and isinstance(values, (list, tuple)):
        choices = tuple((str(v), str(v)) for v in values)

    delim_raw = spec.get("delim")
    delim = _as_tuple(delim_raw)[0] if _as_tuple(delim_raw) else "/"

    min_value = spec.get("min")
    max_value = spec.get("max")

    return AppriseField(
        key=key,
        label=label_override or str(spec.get("name") or key),
        kind=kind,
        placement=placement,
        required=required,
        private=bool(spec.get("private", False)),
        advanced=placement == "arg" and key in ADVANCED_ARGS,
        default=_format_default(spec.get("default")),
        choices=choices,
        min=float(min_value) if isinstance(min_value, (int, float)) else None,
        max=float(max_value) if isinstance(max_value, (int, float)) else None,
        delim=delim,
    )


def _build_service(schema: Mapping[str, object]) -> Optional[AppriseService]:
    protocols = _as_tuple(schema.get("protocols"))
    secure_protocols = _as_tuple(schema.get("secure_protocols"))
    all_schemas = protocols + tuple(p for p in secure_protocols if p not in protocols)
    if not all_schemas:
        return None

    service_id = all_schemas[0]
    if service_id in EXCLUDED_SERVICES:
        return None

    details = schema.get("details")
    if not isinstance(details, Mapping):
        return None

    templates = _as_tuple(details.get("templates"))
    raw_tokens = details.get("tokens")
    raw_args = details.get("args")
    tokens_spec: Mapping[str, Mapping[str, object]] = (
        raw_tokens if isinstance(raw_tokens, Mapping) else {}
    )
    args_spec: Mapping[str, Mapping[str, object]] = (
        raw_args if isinstance(raw_args, Mapping) else {}
    )
    if not templates:
        return None

    template_key_sets = [set(template_keys(t)) for t in templates]
    required_keys = set.intersection(*template_key_sets) if template_key_sets else set()

    ordered_keys: List[str] = []
    for template in templates:
        for key in template_keys(template):
            if key not in ordered_keys:
                ordered_keys.append(key)

    tokens: List[AppriseField] = []
    if len(all_schemas) > 1:
        default_schema = secure_protocols[0] if secure_protocols else all_schemas[0]
        tokens.append(
            AppriseField(
                key="schema",
                label="Protocol",
                kind="choice",
                placement="token",
                required=True,
                default=default_schema,
                choices=tuple((s, s) for s in all_schemas),
            )
        )
    else:
        default_schema = all_schemas[0]

    for key in sorted(
        ordered_keys, key=lambda k: (k not in required_keys, ordered_keys.index(k))
    ):
        spec = tokens_spec.get(key, {"name": key})
        label = None
        members = [
            str(tokens_spec[m].get("name") or m)
            for m in _group_members(spec.get("group"))
            if m in tokens_spec
        ]
        if members:
            label = f"{spec.get('name') or key} ({' / '.join(members)})"
        tokens.append(_build_field(key, spec, "token", key in required_keys, label))

    token_keys = {t.key for t in tokens}
    args: List[AppriseField] = []
    for key, spec in args_spec.items():
        if not isinstance(spec, Mapping) or "alias_of" in spec or key in token_keys:
            continue
        args.append(_build_field(key, spec, "arg", False))
    args.sort(key=lambda a: (a.advanced, a.label.lower()))

    setup_url = schema.get("setup_url")
    service_url = schema.get("service_url")
    return AppriseService(
        id=service_id,
        name=str(schema.get("service_name") or service_id),
        setup_url=str(setup_url) if setup_url else None,
        service_url=str(service_url) if service_url else None,
        schemas=all_schemas,
        default_schema=default_schema,
        templates=templates,
        tokens=tuple(tokens),
        args=tuple(args),
    )


class AppriseCatalog:
    """Searchable catalog of Apprise services built from ``Apprise().details()``"""

    def __init__(self, details: Mapping[str, object]) -> None:
        self._services: Dict[str, AppriseService] = {}
        self._aliases: Dict[str, str] = {}

        schemas = details.get("schemas")
        for schema in schemas if isinstance(schemas, list) else []:
            if not isinstance(schema, Mapping):
                continue
            try:
                service = _build_service(schema)
            except Exception as e:
                logger.warning(
                    f"Skipping Apprise service {schema.get('service_name')}: {e}"
                )
                continue
            if service is None or service.id in self._services:
                continue
            self._services[service.id] = service
            for alias in service.schemas:
                self._aliases.setdefault(alias, service.id)

        self.version = str(details.get("version", ""))

    def get(self, service_id: str) -> Optional[AppriseService]:
        canonical = self._aliases.get(service_id, service_id)
        return self._services.get(canonical)

    def services(self) -> List[AppriseService]:
        return sorted(self._services.values(), key=lambda s: s.name.lower())

    def grouped(self) -> List[AppriseServiceGroup]:
        popular = tuple(
            s for s in (self.get(sid) for sid in POPULAR_SERVICES) if s is not None
        )
        groups = []
        if popular:
            groups.append(AppriseServiceGroup(label="Popular", services=popular))
        groups.append(
            AppriseServiceGroup(label="All Services", services=tuple(self.services()))
        )
        return groups

    def __len__(self) -> int:
        return len(self._services)


@lru_cache(maxsize=1)
def get_apprise_catalog() -> AppriseCatalog:
    """Build the Apprise catalog once; loading plugin metadata is not free"""
    return AppriseCatalog(apprise.Apprise().details(show_disabled=False))
