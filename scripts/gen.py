"""Generate a scenario suite against the demo target."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from mcp_tripwire.scenarios.generator import generate, save

TARGET = StdioServerParameters(
    command=sys.executable,
    args=["examples/vulnerable-mcp-server/server.py"],
)


async def main() -> None:
    async with stdio_client(TARGET) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = (await session.list_tools()).tools

    scenarios = generate(tools, seed=42)
    save(scenarios, Path("suites/demo.jsonl"))
    for s in scenarios:
        print(f"[{s.category}] {s.target_tool}: {s.user_prompt}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())