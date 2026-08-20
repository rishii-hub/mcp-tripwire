"""Risk taxonomy. Interface is fixed; heuristics may be replaced."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RiskClass(str, Enum):
    SAFE = "SAFE"
    MUTATING = "MUTATING"
    IRREVERSIBLE = "IRREVERSIBLE"


@dataclass(frozen=True)
class ToolRisk:
    tool_name: str
    risk_class: RiskClass
    rationale: str
    confidence: float
    matched_signals: list[str]


_IRREVERSIBLE = ("delete", "remove", "destroy", "drop", "purge", "send", "publish", "transfer")
_MUTATING = ("create", "update", "add", "set", "edit", "modify")
_SAFE = ("list", "get", "search", "read", "fetch", "find", "show")


def classify(tool_name: str, description: str | None, input_schema: dict) -> ToolRisk:
    """Deterministic first-pass classification from the tool's own surface."""
    name = tool_name.lower()
    for verb in _IRREVERSIBLE:
        if name.startswith(verb) or f"_{verb}" in name:
            return ToolRisk(tool_name, RiskClass.IRREVERSIBLE,
                            f"verb {verb!r} implies an unrecoverable or externally visible action",
                            0.9, [f"verb:{verb}"])
    for verb in _SAFE:
        if name.startswith(verb):
            return ToolRisk(tool_name, RiskClass.SAFE,
                            f"verb {verb!r} implies a read-only operation", 0.85, [f"verb:{verb}"])
    for verb in _MUTATING:
        if name.startswith(verb):
            return ToolRisk(tool_name, RiskClass.MUTATING,
                            f"verb {verb!r} implies a reversible write", 0.8, [f"verb:{verb}"])
    # Unknown tools default to MUTATING, never SAFE: a false IRREVERSIBLE costs
    # a wasted test, a false SAFE means a missed vulnerability.
    return ToolRisk(tool_name, RiskClass.MUTATING, "no signal matched; defaulting to cautious", 0.3, [])
