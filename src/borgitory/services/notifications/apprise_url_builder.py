"""
Builds and validates Apprise URLs from form field values.
"""

import logging
import re
import threading
from typing import List, Mapping, Optional
from urllib.parse import quote, urlencode

import apprise

from borgitory.services.notifications.apprise_catalog import (
    AppriseField,
    AppriseService,
    template_keys,
)

logger = logging.getLogger(__name__)

_LIST_SPLIT_RE = re.compile(r"[,\s]+")
_TRUE_VALUES = frozenset({"yes", "true", "1", "on"})
_FALSE_VALUES = frozenset({"no", "false", "0", "off"})

# LogCapture attaches to the shared apprise logger, so serialize its use
_log_capture_lock = threading.Lock()


class UrlBuildError(ValueError):
    """Raised when the supplied values cannot produce a valid Apprise URL"""


def _split_list(value: str) -> List[str]:
    return [item for item in _LIST_SPLIT_RE.split(value.strip()) if item]


def _normalize_bool(value: str) -> Optional[str]:
    lowered = value.strip().lower()
    if lowered in _TRUE_VALUES:
        return "yes"
    if lowered in _FALSE_VALUES:
        return "no"
    return None


def _encode_token(field: Optional[AppriseField], value: str) -> str:
    if field is not None and field.kind == "list":
        return field.delim.join(quote(item, safe="") for item in _split_list(value))
    return quote(value.strip(), safe="")


def _arg_value(field: AppriseField, value: str) -> Optional[str]:
    value = value.strip()
    if not value:
        return None
    if field.kind == "bool":
        normalized = _normalize_bool(value)
        if normalized is None:
            raise UrlBuildError(f"{field.label} must be yes or no")
        value = normalized
    elif field.kind == "list":
        value = ",".join(_split_list(value))
    if field.default is not None and value == field.default:
        return None
    return value


def build_url(service: AppriseService, values: Mapping[str, str]) -> str:
    """
    Build an Apprise URL for a service from field values.

    The template that uses the most of the provided tokens is chosen, so optional
    tokens (e.g. a Discord bot name) are included when they are filled in.
    """
    filled = {k for k, v in values.items() if isinstance(v, str) and v.strip()}

    best_template: Optional[str] = None
    best_score = -1
    closest_missing: List[str] = []
    for template in service.templates:
        keys = template_keys(template)
        missing = [k for k in keys if k not in filled]
        if missing:
            if not closest_missing or len(missing) < len(closest_missing):
                closest_missing = missing
            continue
        if len(keys) > best_score:
            best_template, best_score = template, len(keys)

    if best_template is None:
        labels = []
        for key in closest_missing:
            field = service.get_field(key)
            labels.append(field.label if field else key)
        raise UrlBuildError(f"Missing required fields: {', '.join(labels)}")

    schema = values.get("schema", "").strip() or service.default_schema
    if schema not in service.schemas:
        raise UrlBuildError(f"Unsupported protocol: {schema}")

    url = best_template.replace("{schema}", schema)
    for key in template_keys(best_template):
        url = url.replace(
            "{" + key + "}", _encode_token(service.get_field(key), values[key])
        )

    query = {}
    for arg in service.args:
        raw = values.get(arg.key)
        if isinstance(raw, str):
            arg_value = _arg_value(arg, raw)
            if arg_value is not None:
                query[arg.key] = arg_value

    if query:
        url = f"{url}?{urlencode(query, quote_via=quote)}"
    return url


def split_urls(urls: str) -> List[str]:
    """Split a block of user-provided URLs, one per line"""
    return [u.strip() for u in re.split(r"[\r\n]+", urls) if u.strip()]


def validate_url(url: str) -> Optional[str]:
    """
    Validate an Apprise URL.

    Returns None when the URL is valid, otherwise a human readable error.
    """
    with _log_capture_lock:
        with apprise.LogCapture(  # type: ignore[no-untyped-call]
            level=logging.WARNING, fmt="%(message)s"
        ) as logs:
            plugin = apprise.Apprise.instantiate(url, suppress_exceptions=True)
            captured = str(logs.getvalue()).strip()

    if plugin is not None:
        return None

    lines = [line.strip() for line in captured.splitlines() if line.strip()]
    if lines:
        return lines[-1]
    return "Apprise does not recognize this URL"


def mask_url(url: str) -> str:
    """Return a privacy-safe version of an Apprise URL for display"""
    plugin = apprise.Apprise.instantiate(url, suppress_exceptions=True)
    if plugin is None:
        scheme, _, _ = url.partition("://")
        return f"{scheme}://…"
    return str(plugin.url(privacy=True))  # type: ignore[no-untyped-call]
