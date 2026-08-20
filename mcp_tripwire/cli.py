"""Tripwire command line interface.

The `run` command exits non-zero when the agent regresses against a baseline.
That exit code is the whole point: it is what makes this CI rather than a
dashboard, and it is what blocks a pull request.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import typer

from mcp_tripwire.logging import configure, get_logger
from mcp_tripwire.scoring import scorecard

app = typer.Typer(
    help="Safety testing and reliability CI for AI agents using MCP servers.",
    no_args_is_help=True,
)
log = get_logger(__name__)


@app.command()
def version() -> None:
    """Print the installed version."""
    typer.echo("mcp-tripwire 0.1.0", err=True)


@app.command()
def discover(
    target: str = typer.Option(..., help="command line of the MCP server to inspect"),
) -> None:
    """List a server's tools with their risk classification."""
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    from mcp_tripwire.proxy.transport import split_command
    from mcp_tripwire.risk.taxonomy import classify

    configure()
    argv = split_command(target)

    async def go() -> None:
        params = StdioServerParameters(command=argv[0], args=argv[1:])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools

        typer.echo("", err=True)
        typer.echo(f"  {'TOOL':<24} {'RISK':<14} RATIONALE", err=True)
        typer.echo(f"  {'-' * 74}", err=True)
        for tool in sorted(tools, key=lambda t: t.name):
            risk = classify(tool.name, tool.description, tool.inputSchema or {})
            typer.echo(
                f"  {tool.name:<24} {risk.risk_class.value:<14} {risk.rationale}", err=True
            )
        typer.echo("", err=True)

    asyncio.run(go())


@app.command()
def report(
    scorecard_path: Path = typer.Option(..., "--scorecard", help="scorecard JSON to render"),
    baseline: Path = typer.Option(None, help="baseline scorecard to compare against"),
    fail_on_regression: bool = typer.Option(
        False, help="exit non-zero if any scenario regressed against the baseline"
    ),
    min_score: float = typer.Option(
        None, help="exit non-zero if the safety score falls below this threshold"
    ),
) -> None:
    """Render a scorecard and optionally gate the build on it."""
    configure()
    card = scorecard.load(scorecard_path)
    typer.echo(scorecard.render(card), err=True)

    failed = False

    if baseline is not None:
        base = scorecard.load(baseline)
        regressed = scorecard.regressions(base, card)
        if regressed:
            typer.echo(f"  REGRESSIONS vs {base.label}:", err=True)
            for line in regressed:
                typer.echo(f"    {line}", err=True)
            typer.echo("", err=True)
            if fail_on_regression:
                failed = True
        else:
            typer.echo(f"  no regressions vs {base.label}\n", err=True)

    if min_score is not None and card.safety_score < min_score:
        typer.echo(
            f"  safety score {card.safety_score}% is below threshold {min_score}%\n", err=True
        )
        failed = True

    if failed:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()