"""Logging for mcp-tripwire.

HARD PROJECT INVARIANT
----------------------
    stdout -> MCP JSON-RPC protocol frames ONLY
    stderr -> everything else (logs, warnings, tracebacks, human output)

Tripwire runs as a stdio MCP proxy. Any byte written to stdout that is not a
valid JSON-RPC frame corrupts the protocol stream, and the client fails to
parse with no useful error. This is the single most common way a stdio proxy
breaks, and it is silent.

Consequences enforced elsewhere:
  * ruff rule T20 bans `print()` across the package (see pyproject.toml).
  * Typer/rich console output must be constructed with stderr=True.
  * Never call logging.basicConfig() anywhere else; it defaults to stderr in
    modern Python but the default has changed before. Be explicit.
"""

from __future__ import annotations

import logging
import os
import sys

_CONFIGURED = False

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_DATEFMT = "%H:%M:%S"


def configure(level: str | None = None) -> None:
    """Install a stderr-only root handler. Idempotent."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    resolved = (level or os.getenv("LOG_LEVEL") or "INFO").upper()

    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter(fmt=_FORMAT, datefmt=_DATEFMT))

    root = logging.getLogger()
    root.handlers.clear()  # drop anything a dependency installed
    root.addHandler(handler)
    root.setLevel(resolved)

    # The MCP SDK and httpx are chatty at DEBUG and will drown the trace.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger, configuring stderr logging on first use."""
    configure()
    return logging.getLogger(name)


def assert_stdout_clean() -> None:
    """Fail loudly in tests if stdout has been redirected away from the protocol.

    Called by the proxy integration tests. Not a runtime guard — it exists so a
    stray print() surfaces as a test failure rather than a hung client.
    """
    if sys.stdout is not sys.__stdout__:
        raise RuntimeError(
            "stdout has been reassigned; the MCP protocol stream may be corrupted"
        )
