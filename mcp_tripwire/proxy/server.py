"""Tripwire's transparent MCP proxy.

    agent  <--MCP-->  tripwire  <--MCP-->  target server

Tripwire presents itself as an MCP server to the agent, and acts as an MCP
client toward the real server. It mirrors the target's identity and tool list
so the agent cannot tell it is talking to a proxy.

Because every ``tools/call`` passes through one function, recording, mocking and
replay all fall out of the same interception point rather than needing three
separate mechanisms.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp import ClientSession, types
from mcp.client.stdio import stdio_client
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from mcp_tripwire.logging import get_logger
from mcp_tripwire.proxy.interceptor import Interceptor, Mode, Recorder, load_trace
from mcp_tripwire.proxy.transport import build_target_params

log = get_logger(__name__)


async def run_proxy(
    target: str,
    mode: Mode = Mode.PASSTHROUGH,
    record_path: Path | None = None,
    replay_path: Path | None = None,
    cwd: str | Path | None = None,
) -> str:
    """Run the proxy until the agent disconnects. Returns the trace digest.

    Args:
        target: Command line for the MCP server being proxied.
        mode: passthrough, mock or replay.
        record_path: JSONL file to append trace events to.
        replay_path: JSONL file to serve recorded responses from.
        cwd: Working directory for the target process.
    """
    params = build_target_params(target, cwd=cwd)
    recorder = Recorder(record_path)
    replay_table = load_trace(replay_path) if replay_path else None

    async with (
        stdio_client(params) as (target_read, target_write),
        ClientSession(target_read, target_write) as session,
    ):
        init = await session.initialize()
        upstream_name = init.serverInfo.name

        # Strip outputSchema when mirroring. FastMCP derives one from the
        # target's return annotations, but mock and replay modes cannot
        # synthesise schema-valid structured output for an arbitrary tool.
        # Name, description and inputSchema pass through untouched — those
        # are what the agent reasons over and what we classify risk from.
        tools = [
            t.model_copy(update={"outputSchema": None})
            for t in (await session.list_tools()).tools
        ]
        log.info("connected to %r, %d tools", upstream_name, len(tools))

        interceptor = Interceptor(session, mode, recorder, replay_table)
        server = _build_server(upstream_name, tools, interceptor)

        # Opened only after the target is live: if the upstream connection
        # fails we must not present ourselves to the agent at all.
        async with stdio_server() as (agent_read, agent_write):
            log.info("proxy listening on stdio, mode=%s", mode.value)
            await server.run(
                agent_read,
                agent_write,
                server.create_initialization_options(),
            )

    log.info("trace digest %s (%d calls)", recorder.digest, len(interceptor.attempted))
    return recorder.digest


def _build_server(
    upstream_name: str,
    tools: list[types.Tool],
    interceptor: Interceptor,
) -> Server:
    """Construct the agent-facing MCP server, mirroring the upstream identity."""
    server: Server = Server(upstream_name)

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        # Served from the snapshot taken at startup so the agent sees a stable
        # tool surface for the whole session, which is what makes a run
        # reproducible.
        return tools

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[types.ContentBlock]:
        return await interceptor.call(name, arguments)

    return server