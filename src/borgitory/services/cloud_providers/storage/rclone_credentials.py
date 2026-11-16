"""
Helpers for handing credentials to rclone without exposing them.

Secrets must never be placed on the rclone command line: process arguments are
readable by every local user (``ps``, ``/proc/<pid>/cmdline``) and command lines
end up in logs. Instead, credentials are passed through rclone's
``RCLONE_<BACKEND>_<OPTION>`` environment variables, which apply to on-the-fly
``:backend:`` remotes exactly like the equivalent ``--backend-option`` flags.
"""

import os
from typing import Dict, Mapping, Optional

from borgitory.protocols.command_executor_protocol import CommandExecutorProtocol


class RcloneObscureError(RuntimeError):
    """Raised when rclone fails to obscure a password."""


def build_rclone_env(secrets: Mapping[str, Optional[str]]) -> Dict[str, str]:
    """Return the current environment extended with the given rclone secrets.

    Empty or ``None`` values are skipped so they don't override rclone defaults.
    """
    env = os.environ.copy()
    env.update({key: value for key, value in secrets.items() if value})
    return env


async def obscure_password(
    command_executor: CommandExecutorProtocol, password: str
) -> str:
    """Obscure a password the way rclone expects for ``*_PASS`` options.

    The plaintext is sent on stdin (``rclone obscure -``) so it never appears in
    the process arguments. Fails loudly rather than falling back to plaintext:
    rclone would reject an unobscured password anyway.
    """
    result = await command_executor.execute_command(
        command=["rclone", "obscure", "-"],
        input_data=password + "\n",
        timeout=10.0,
    )
    obscured = result.stdout.strip()
    if not result.success or not obscured:
        raise RcloneObscureError(
            f"rclone obscure failed (exit code {result.return_code}): "
            f"{result.stderr.strip() or 'no output'}"
        )
    return obscured
