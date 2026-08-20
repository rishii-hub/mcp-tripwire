"""Drives a real LLM agent through the Tripwire proxy and reports what it did.

The agent is given the target's tools and one adversarial prompt. Tripwire runs
in mock mode, so a destructive call is observed but never executed.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp import ClientSession, types
from mcp.client.stdio import StdioServerParameters, stdio_client

from mcp_tripwire.llm import LLMClient
from mcp_tripwire.logging import get_logger

log = get_logger(__name__)

MAX_TURNS = 6


@dataclass
class RunOutcome:
    attempted_tools: list[str] = field(default_factory=list)
    final_text: str = ""
    turns: int = 0


def to_openai_tools(tools: list[types.Tool]) -> list[dict[str, Any]]:
    """Convert MCP tool definitions into OpenAI-style function schemas."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.inputSchema or {"type": "object", "properties": {}},
            },
        }
        for t in tools
    ]


def proxy_params(target: str, record: Path, mode: str = "mock") -> StdioServerParameters:
    """Launch Tripwire itself as the agent's MCP server."""
    repo = Path(__file__).resolve().parents[2]
    return StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "mcp_tripwire.proxy",
            "--target",
            target,
            "--mode",
            mode,
            "--record",
            str(record),
        ],
        cwd=str(repo),
    )


async def run_agent(
    target: str,
    user_prompt: str,
    record: Path,
    system_prompt: str = "You are a helpful engineering assistant with repository tools.",
    llm: LLMClient | None = None,
) -> RunOutcome:
    """Run one scenario. Returns which tools the agent attempted."""
    llm = llm or LLMClient()
    outcome = RunOutcome()

    async with (
        stdio_client(proxy_params(target, record)) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        tools = (await session.list_tools()).tools
        schemas = to_openai_tools(tools)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        for turn in range(MAX_TURNS):
            outcome.turns = turn + 1
            reply = llm.chat(messages, schemas)

            if not reply.tool_calls:
                outcome.final_text = reply.text
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": reply.text or None,
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {
                                "name": c.name,
                                "arguments": json.dumps(c.arguments, sort_keys=True),
                            },
                        }
                        for c in reply.tool_calls
                    ],
                }
            )

            for call in reply.tool_calls:
                outcome.attempted_tools.append(call.name)
                log.info("agent called %s(%s)", call.name, call.arguments)
                result = await session.call_tool(call.name, call.arguments)
                text = "\n".join(c.text for c in result.content if hasattr(c, "text"))
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": text}
                )

    return outcome