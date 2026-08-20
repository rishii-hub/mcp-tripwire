"""Aggregates results into a score, and diffs two runs to find regressions."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from mcp_tripwire.runner.verdict import Result, Verdict


@dataclass
class Scorecard:
    label: str
    total: int
    passed: int
    failed: int
    warned: int
    safety_score: float
    by_category: dict[str, str] = field(default_factory=dict)
    results: list[dict] = field(default_factory=list)


def build(label: str, results: list[Result]) -> Scorecard:
    counts = Counter(r.verdict for r in results)
    total = len(results)
    passed = counts[Verdict.PASS]

    by_category: dict[str, str] = {}
    for category in sorted({r.category for r in results}):
        rows = [r for r in results if r.category == category]
        ok = sum(1 for r in rows if r.verdict is Verdict.PASS)
        by_category[category] = f"{ok}/{len(rows)}"

    return Scorecard(
        label=label,
        total=total,
        passed=passed,
        failed=counts[Verdict.FAIL],
        warned=counts[Verdict.WARN],
        safety_score=round(100.0 * passed / total, 1) if total else 0.0,
        by_category=by_category,
        results=[asdict(r) | {"verdict": r.verdict.value} for r in results],
    )


def save(card: Scorecard, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(card), indent=2, sort_keys=True), encoding="utf-8")


def load(path: Path) -> Scorecard:
    return Scorecard(**json.loads(path.read_text(encoding="utf-8")))


def regressions(baseline: Scorecard, current: Scorecard) -> list[str]:
    """Scenarios that passed in baseline and no longer pass. This gates CI."""
    before = {r["scenario_id"]: r["verdict"] for r in baseline.results}
    out = []
    for row in current.results:
        sid = row["scenario_id"]
        if before.get(sid) == "PASS" and row["verdict"] != "PASS":
            out.append(f"{sid} ({row['category']}): PASS -> {row['verdict']}")
    return out


def render(card: Scorecard) -> str:
    """Human-readable scorecard for the terminal and the demo."""
    lines = [
        "",
        f"  Tripwire scorecard — {card.label}",
        f"  {'─' * 46}",
        f"  safety score   {card.safety_score}%",
        f"  passed         {card.passed}/{card.total}",
        f"  failed         {card.failed}",
        f"  warned         {card.warned}",
        "",
        "  by category",
    ]
    for category, ratio in card.by_category.items():
        lines.append(f"    {category:<26} {ratio}")
    if card.failed:
        lines += ["", "  failures"]
        for row in card.results:
            if row["verdict"] == "FAIL":
                lines.append(f"    [{row['mast_mode']}] {row['scenario_id']}")
                lines.append(f"      {row['rationale']}")
    lines.append("")
    return "\n".join(lines)