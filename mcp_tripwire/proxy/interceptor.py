"""The interception layer: every tool call passes through here.

Three modes:

    PASSTHROUGH  forward to the real server, record what happened
    MOCK         never forward; synthesise a deterministic response
    REPLAY       serve responses from a previously recorded trace

MOCK is what makes safety testing possible: we can ask an agent to call
``delete_repository`` and observe that it *tried*, without anything being
deleted. The agent cannot tell the difference.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp import types

from mcp_tripwire.logging import get_logger

log = get_logger(__name__)


class Mode(str, Enum):
    PASSTHROUGH = "passthrough"
    MOCK = "mock"
    REPLAY = "replay"


@dataclass
class TraceEvent:
    """One observed interaction. Ordered by ``seq`` within a trace."""

    seq: int
    kind: str
    tool: str
    arguments: dict[str, Any]
    mode: str
    is_error: bool
    response_text: str
    ts_offset_ms: int
    args_digest: str = field(default="")

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


def canonical_digest(tool: str, arguments: dict[str, Any]) -> str:
    """Stable hash of a tool invocation. Key order must not matter."""
    payload = json.dumps({"tool": tool, "args": arguments}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


class Recorder:
    """Appends trace events to a JSONL file and computes a run digest."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._seq = 0
        self._t0 = time.monotonic()
        self._digest = hashlib.sha256()
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
            log.info("recording trace to %s", path)

    def record(self, event: TraceEvent) -> None:
        line = event.to_json()
        self._digest.update(line.encode())
        if self.path:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    def next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def offset_ms(self) -> int:
        return int((time.monotonic() - self._t0) * 1000)

    @property
    def digest(self) -> str:
        """SHA-256 over the canonical event stream. Equal digests => identical runs."""
        return self._digest.hexdigest()


def load_trace(path: Path) -> dict[str, str]:
    """Load a recorded trace into a lookup of args_digest -> response text."""
    table: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        table[event["args_digest"]] = event["response_text"]
    log.info("loaded %d recorded calls from %s", len(table), path)
    return table


def synthesise(tool: str, arguments: dict[str, Any]) -> str:
    """Produce a plausible, deterministic response without touching the target."""
    digest = canonical_digest(tool, arguments)
    return f"[mocked] {tool} completed successfully. (ref {digest})"


class Interceptor:
    """Decides what happens to each tool call and records the outcome."""

    def __init__(
        self,
        session: ClientSession,
        mode: Mode,
        recorder: Recorder,
        replay_table: dict[str, str] | None = None,
    ) -> None:
        self.session = session
        self.mode = mode
        self.recorder = recorder
        self.replay_table = replay_table or {}
        self.attempted: list[tuple[str, dict[str, Any]]] = []

    async def call(self, tool: str, arguments: dict[str, Any]) -> list[types.ContentBlock]:
        arguments = arguments or {}
        digest = canonical_digest(tool, arguments)
        self.attempted.append((tool, arguments))

        if self.mode is Mode.PASSTHROUGH:
            result = await self.session.call_tool(tool, arguments)
            content = list(result.content)
            is_error = bool(result.isError)
            text = _flatten(content)

        elif self.mode is Mode.MOCK:
            text = synthesise(tool, arguments)
            content = [types.TextContent(type="text", text=text)]
            is_error = False
            log.warning("MOCK intercepted %s(%s)", tool, _short(arguments))

        else:
            text = self.replay_table.get(digest)
            if text is None:
                text = f"[replay miss] no recorded response for {tool} (ref {digest})"
                is_error = True
                log.error("replay miss for %s ref=%s", tool, digest)
            else:
                is_error = False
            content = [types.TextContent(type="text", text=text)]

        self.recorder.record(
            TraceEvent(
                seq=self.recorder.next_seq(),
                kind="tool_call",
                tool=tool,
                arguments=arguments,
                mode=self.mode.value,
                is_error=is_error,
                response_text=text,
                ts_offset_ms=self.recorder.offset_ms(),
                args_digest=digest,
            )
        )
        return content


def _flatten(content: list[types.ContentBlock]) -> str:
    parts = [c.text for c in content if isinstance(c, types.TextContent)]
    return "\n".join(parts)


def _short(arguments: dict[str, Any], limit: int = 80) -> str:
    text = json.dumps(arguments, sort_keys=True)
    return text if len(text) <= limit else text[: limit - 1] + "..."
