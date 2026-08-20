"""Transport helpers for launching the target MCP server."""

from __future__ import annotations

import os
import shlex
from pathlib import Path

from mcp.client.stdio import StdioServerParameters

from mcp_tripwire.logging import get_logger

log = get_logger(__name__)


def split_command(target: str) -> list[str]:
    """Split a shell-style command string into argv.

    On Windows we split non-POSIX so that backslash path separators survive
    (``.\\.venv\\Scripts\\python.exe`` must not become ``.venvScriptspython.exe``),
    then strip any surrounding quotes that non-POSIX mode leaves attached.
    """
    posix = os.name != "nt"
    parts = shlex.split(target, posix=posix)
    if not posix:
        parts = [p.strip('"').strip("'") for p in parts]
    if not parts:
        raise ValueError("target command is empty")
    return parts


def build_target_params(
    target: str,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
) -> StdioServerParameters:
    """Build stdio parameters for the MCP server we are proxying to."""
    argv = split_command(target)
    merged = {**os.environ, **(env or {})}
    log.info("target command: %s", argv)
    return StdioServerParameters(
        command=argv[0],
        args=argv[1:],
        cwd=str(cwd) if cwd else None,
        env=merged,
    )
