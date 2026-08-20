"""The Day 1 gate, as an automated test."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

REPO = Path(__file__).resolve().parents[2]
TARGET = REPO / "examples" / "vulnerable-mcp-server" / "server.py"

DIRECT = StdioServerParameters(command=sys.executable, args=[str(TARGET)])

THROUGH_PROXY = StdioServerParameters(
    command=sys.executable,
    args=[
        "-m",
        "mcp_tripwire.proxy",
        "--target",
        f'"{sys.executable}" "{TARGET}"',
    ],
    cwd=str(REPO),
)


async def _tool_names(params: StdioServerParameters) -> list[str]:
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return sorted(t.name for t in result.tools)


async def _call(params: StdioServerParameters, tool: str, args: dict) -> str:
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, args)
            return "\n".join(c.text for c in result.content if hasattr(c, "text"))


@pytest.mark.integration
async def test_target_exposes_seven_tools():
    names = await _tool_names(DIRECT)
    assert len(names) == 7
    assert "delete_repository" in names
    assert "send_email" in names


@pytest.mark.integration
async def test_proxy_is_transparent_for_tool_listing():
    assert await _tool_names(THROUGH_PROXY) == await _tool_names(DIRECT)


@pytest.mark.integration
async def test_proxy_forwards_tool_calls():
    direct = await _call(DIRECT, "list_files", {"repository": "acme/payments-api"})
    proxied = await _call(THROUGH_PROXY, "list_files", {"repository": "acme/payments-api"})
    assert direct == proxied
    assert "src/billing.py" in proxied


@pytest.mark.integration
async def test_mock_mode_does_not_reach_the_target(tmp_path: Path):
    """The whole point: observe the attempt, prevent the effect."""
    mock_params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "mcp_tripwire.proxy",
            "--target",
            f'"{sys.executable}" "{TARGET}"',
            "--mode",
            "mock",
            "--record",
            str(tmp_path / "trace.jsonl"),
        ],
        cwd=str(REPO),
    )
    response = await _call(mock_params, "delete_repository", {"repository": "acme/payments-api"})
    assert "[mocked]" in response

    trace = (tmp_path / "trace.jsonl").read_text(encoding="utf-8")
    assert "delete_repository" in trace
