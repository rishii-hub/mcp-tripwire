"""Entrypoint: ``python -m mcp_tripwire.proxy --target "<command>"``."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from mcp_tripwire.logging import configure, get_logger
from mcp_tripwire.proxy.interceptor import Mode
from mcp_tripwire.proxy.server import run_proxy

log = get_logger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mcp_tripwire.proxy",
        description="Transparent MCP proxy for agent safety testing.",
    )
    parser.add_argument("--target", required=True, help="command line of the MCP server to proxy")
    parser.add_argument(
        "--mode",
        default=Mode.PASSTHROUGH.value,
        choices=[m.value for m in Mode],
        help="passthrough forwards calls; mock intercepts them; replay serves a recorded trace",
    )
    parser.add_argument("--record", type=Path, default=None, help="write a JSONL trace here")
    parser.add_argument("--replay", type=Path, default=None, help="serve responses from this trace")
    parser.add_argument("--cwd", default=None, help="working directory for the target process")
    parser.add_argument("--log-level", default=None, help="DEBUG, INFO, WARNING, ERROR")
    args = parser.parse_args()

    configure(args.log_level)

    mode = Mode(args.mode)
    if mode is Mode.REPLAY and args.replay is None:
        parser.error("--replay is required when --mode replay")

    try:
        asyncio.run(
            run_proxy(
                target=args.target,
                mode=mode,
                record_path=args.record,
                replay_path=args.replay,
                cwd=args.cwd,
            )
        )
    except KeyboardInterrupt:
        log.info("interrupted")


if __name__ == "__main__":
    main()
