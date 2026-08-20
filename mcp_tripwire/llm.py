"""Provider-agnostic chat client with tool calling.

Free-tier model catalogues churn without notice, so the configured model is
verified against the live catalogue at startup rather than trusted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mcp_tripwire.config import SETTINGS
from mcp_tripwire.logging import get_logger

log = get_logger(__name__)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Reply:
    text: str
    tool_calls: list[ToolCall]


class LLMClient:
    """Thin wrapper over an OpenAI-compatible chat API."""

    def __init__(self, provider: str | None = None, model: str | None = None) -> None:
        self.provider = provider or SETTINGS.provider
        self.model = model or SETTINGS.model
        if self.provider == "groq":
            from groq import Groq

            self._client = Groq()
        else:
            raise ValueError(f"unsupported provider: {self.provider!r}")
        log.info("llm provider=%s model=%s", self.provider, self.model)

    def verify_model(self) -> None:
        """Fail loudly if the configured model is no longer served."""
        available = {m.id for m in self._client.models.list().data}
        if self.model not in available:
            raise RuntimeError(
                f"model {self.model!r} is not available. Served: {sorted(available)}"
            )

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Reply:
        import json

        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools or None,
            max_tokens=SETTINGS.max_tokens,
            temperature=SETTINGS.temperature,
        )
        message = response.choices[0].message
        calls: list[ToolCall] = []
        for raw in message.tool_calls or []:
            try:
                args = json.loads(raw.function.arguments or "{}")
            except json.JSONDecodeError:
                log.warning("malformed tool arguments from model: %r", raw.function.arguments)
                args = {}
            calls.append(ToolCall(id=raw.id, name=raw.function.name, arguments=args))
        return Reply(text=message.content or "", tool_calls=calls)
