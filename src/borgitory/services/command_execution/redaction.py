"""Redact secrets from command lines before they are logged."""

import re
from typing import Sequence

_SENSITIVE_NAME = re.compile(r"pass|secret|token|key", re.IGNORECASE)
_SHELL_EXPORT = re.compile(
    r"(export\s+\w*(?:PASS|SECRET|TOKEN|KEY)\w*=)('[^']*'|\"[^\"]*\"|\S+)",
    re.IGNORECASE,
)
MASK = "***"


def redact_command(command: Sequence[str]) -> str:
    """Join a command for logging, masking values of credential-like options.

    Handles ``--opt value``, ``--opt=value`` and ``export NAME=value`` (as used
    in shell strings built for WSL).
    """
    parts: list[str] = []
    mask_next = False
    for part in command:
        if mask_next:
            parts.append(MASK)
            mask_next = False
            continue
        if part.startswith("--") and _SENSITIVE_NAME.search(part.split("=", 1)[0]):
            if "=" in part:
                parts.append(f"{part.split('=', 1)[0]}={MASK}")
            else:
                parts.append(part)
                mask_next = True
            continue
        parts.append(_SHELL_EXPORT.sub(rf"\g<1>{MASK}", part))
    return " ".join(parts)
