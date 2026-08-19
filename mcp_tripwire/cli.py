"""Tripwire command line interface."""

from __future__ import annotations

import typer

app = typer.Typer(help="MCP safety testing and reliability CI for AI agents.")


@app.command()
def version() -> None:
    """Print the installed version."""
    typer.echo("mcp-tripwire 0.1.0", err=True)


if __name__ == "__main__":
    app()
