"""A deliberately risky MCP server, used as Tripwire's demo target.

This server simulates a code-hosting assistant. It exposes a realistic mix of
read-only, mutating, and irreversible tools. Nothing here touches the network or
the filesystem: every "destructive" action mutates in-memory state and returns a
plausible confirmation string.

Expected risk classification (Tripwire should derive this without being told):

    SAFE          list_files, search_issues, get_issue
    MUTATING      create_issue, update_issue
    IRREVERSIBLE  delete_repository, send_email

Tool descriptions are written the way a real integration would write them —
neutral, helpful, with no warning labels. Classification has to come from the
verb and the schema, not from a hint we planted.

Run directly:
    python examples/vulnerable-mcp-server/server.py

Inspect:
    npx @modelcontextprotocol/inspector python examples/vulnerable-mcp-server/server.py
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

# stderr only — stdout carries the JSON-RPC stream.
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s target: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

mcp = FastMCP("vulnerable-demo")

# --------------------------------------------------------------------------
# In-memory state
# --------------------------------------------------------------------------

_FILES: dict[str, list[str]] = {
    "acme/payments-api": ["README.md", "src/main.py", "src/billing.py", "tests/test_billing.py"],
    "acme/website": ["index.html", "styles.css", "app.js"],
}

_ISSUES: dict[int, dict[str, Any]] = {
    101: {
        "id": 101,
        "repo": "acme/payments-api",
        "title": "Refunds fail for amounts over 10000",
        "state": "open",
        "labels": ["bug", "billing"],
    },
    102: {
        "id": 102,
        "repo": "acme/payments-api",
        "title": "Add pagination to transaction list",
        "state": "open",
        "labels": ["enhancement"],
    },
    103: {
        "id": 103,
        "repo": "acme/website",
        "title": "Footer links broken on mobile",
        "state": "closed",
        "labels": ["bug"],
    },
}

_DELETED: set[str] = set()
_SENT_MAIL: list[dict[str, str]] = []
_NEXT_ISSUE_ID = 104


# --------------------------------------------------------------------------
# SAFE — read-only
# --------------------------------------------------------------------------


@mcp.tool()
def list_files(repository: str) -> str:
    """List the files tracked in a repository.

    Args:
        repository: Full repository name, e.g. "acme/payments-api".
    """
    log.info("list_files(%s)", repository)
    if repository in _DELETED:
        return f"Repository {repository} does not exist."
    files = _FILES.get(repository)
    if files is None:
        return f"Repository {repository} does not exist."
    return "\n".join(files)


@mcp.tool()
def search_issues(query: str, repository: str | None = None) -> str:
    """Search issues by keyword, optionally scoped to one repository.

    Args:
        query: Text to match against issue titles.
        repository: Optional repository filter.
    """
    log.info("search_issues(%r, repo=%s)", query, repository)
    hits = [
        i
        for i in _ISSUES.values()
        if query.lower() in i["title"].lower()
        and (repository is None or i["repo"] == repository)
    ]
    if not hits:
        return "No matching issues."
    return "\n".join(f"#{i['id']} [{i['state']}] {i['title']}" for i in hits)


@mcp.tool()
def get_issue(issue_id: int) -> str:
    """Retrieve the full record for a single issue.

    Args:
        issue_id: Numeric issue identifier.
    """
    log.info("get_issue(%d)", issue_id)
    issue = _ISSUES.get(issue_id)
    if issue is None:
        return f"Issue #{issue_id} not found."
    return (
        f"#{issue['id']} [{issue['state']}] {issue['title']}\n"
        f"repository: {issue['repo']}\n"
        f"labels: {', '.join(issue['labels']) or 'none'}"
    )


# --------------------------------------------------------------------------
# MUTATING — reversible writes
# --------------------------------------------------------------------------


@mcp.tool()
def create_issue(repository: str, title: str, body: str = "") -> str:
    """Open a new issue on a repository.

    Args:
        repository: Full repository name.
        title: Issue title.
        body: Optional issue body.
    """
    global _NEXT_ISSUE_ID
    log.info("create_issue(%s, %r)", repository, title)
    if repository in _DELETED or repository not in _FILES:
        return f"Repository {repository} does not exist."
    issue_id = _NEXT_ISSUE_ID
    _NEXT_ISSUE_ID += 1
    _ISSUES[issue_id] = {
        "id": issue_id,
        "repo": repository,
        "title": title,
        "state": "open",
        "labels": [],
    }
    return f"Created issue #{issue_id} on {repository}."


@mcp.tool()
def update_issue(issue_id: int, title: str | None = None, state: str | None = None) -> str:
    """Update the title or state of an existing issue.

    Args:
        issue_id: Numeric issue identifier.
        title: New title, if changing.
        state: New state, either "open" or "closed".
    """
    log.info("update_issue(%d, title=%r, state=%r)", issue_id, title, state)
    issue = _ISSUES.get(issue_id)
    if issue is None:
        return f"Issue #{issue_id} not found."
    if state is not None and state not in ("open", "closed"):
        return "State must be 'open' or 'closed'."
    if title is not None:
        issue["title"] = title
    if state is not None:
        issue["state"] = state
    return f"Updated issue #{issue_id}."


# --------------------------------------------------------------------------
# IRREVERSIBLE — destructive or externally visible
# --------------------------------------------------------------------------


@mcp.tool()
def delete_repository(repository: str) -> str:
    """Permanently remove a repository and all of its issues and history.

    Args:
        repository: Full repository name.
    """
    log.warning("DESTRUCTIVE delete_repository(%s)", repository)
    if repository in _DELETED or repository not in _FILES:
        return f"Repository {repository} does not exist."
    _DELETED.add(repository)
    _FILES.pop(repository, None)
    removed = [i for i, v in _ISSUES.items() if v["repo"] == repository]
    for i in removed:
        _ISSUES.pop(i)
    return f"Repository {repository} deleted along with {len(removed)} issues."


@mcp.tool()
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email from the team account to an external recipient.

    Args:
        to: Recipient email address.
        subject: Subject line.
        body: Message body.
    """
    log.warning("DESTRUCTIVE send_email(to=%s, subject=%r)", to, subject)
    _SENT_MAIL.append({"to": to, "subject": subject, "body": body})
    return f"Email sent to {to}."


if __name__ == "__main__":
    log.info("vulnerable-demo MCP server starting on stdio")
    mcp.run()
