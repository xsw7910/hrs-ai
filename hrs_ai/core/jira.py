"""Jira fetch and parse helpers with mock fallback."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .config import load_config


def fetch_issue(repo_root: Path, issue_key: str) -> tuple[dict, bool, str]:
    config = load_config(repo_root)
    if not config.has_jira_credentials:
        return _mock_issue(issue_key, "Jira environment variables are missing."), True, (
            "Using mock/demo Jira data because Jira environment variables are missing."
        )

    url = f"{config.jira_base_url.rstrip('/')}/rest/api/3/issue/{issue_key}?expand=renderedFields"
    token = base64.b64encode(f"{config.jira_email}:{config.jira_token}".encode()).decode()
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Basic {token}",
            "Accept": "application/json",
            "User-Agent": "hrs-ai-prototype/0.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        payload["hrs_ai_fetch"] = {"mock": False, "source": url}
        return payload, False, "Fetched Jira data from configured Jira instance."
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return _mock_issue(issue_key, f"Jira fetch failed: {exc}"), True, (
            f"Using mock/demo Jira data because Jira fetch failed: {exc}"
        )


def parse_issue(issue: dict) -> dict[str, object]:
    fields = issue.get("fields", {})
    description = fields.get("description")
    if isinstance(description, dict):
        description_text = json.dumps(description, indent=2)
    else:
        description_text = str(description or "")

    comments = []
    comment_data = fields.get("comment", {}).get("comments", [])
    for comment in comment_data:
        body = comment.get("body", "")
        comments.append(json.dumps(body) if isinstance(body, dict) else str(body))

    text = "\n".join(
        [
            str(fields.get("summary", "")),
            description_text,
            "\n".join(comments),
        ]
    ).strip()

    return {
        "issue_key": issue.get("key"),
        "summary": fields.get("summary", ""),
        "issue_type": fields.get("issuetype", {}).get("name", ""),
        "status": fields.get("status", {}).get("name", ""),
        "priority": fields.get("priority", {}).get("name", ""),
        "description": description_text,
        "comments": comments,
        "combined_text": text,
        "is_mock": bool(issue.get("hrs_ai_fetch", {}).get("mock")),
    }


def jira_summary_markdown(issue: dict, fetch_message: str) -> str:
    parsed = parse_issue(issue)
    mock_line = (
        "**Mock/demo Jira data:** yes\n\n"
        if parsed["is_mock"]
        else "**Mock/demo Jira data:** no\n\n"
    )
    return (
        f"# Jira Summary: {parsed['issue_key']}\n\n"
        f"{mock_line}"
        f"- Fetch result: {fetch_message}\n"
        f"- Summary: {parsed['summary']}\n"
        f"- Type: {parsed['issue_type']}\n"
        f"- Status: {parsed['status']}\n"
        f"- Priority: {parsed['priority']}\n\n"
        "## Description\n\n"
        f"{parsed['description'] or '_No description available._'}\n"
    )


def parsed_markdown(parsed: dict[str, object]) -> str:
    comments = parsed.get("comments") or []
    comments_text = "\n\n".join(f"- {comment}" for comment in comments) or "_No comments available._"
    return (
        f"# Parsed Jira: {parsed['issue_key']}\n\n"
        f"- Summary: {parsed['summary']}\n"
        f"- Issue type: {parsed['issue_type']}\n"
        f"- Status: {parsed['status']}\n"
        f"- Priority: {parsed['priority']}\n"
        f"- Mock/demo data: {parsed['is_mock']}\n\n"
        "## Reproduction And Signals\n\n"
        f"{parsed['description'] or '_No reproduction details available yet._'}\n\n"
        "## Comments\n\n"
        f"{comments_text}\n"
    )


def _mock_issue(issue_key: str, reason: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "key": issue_key,
        "fields": {
            "summary": "Demo bug: employee search returns stale results after filter changes",
            "description": (
                "Mock/demo Jira content for Phase 1. Steps: open the HR employee search, "
                "apply a department filter, change the location filter, and observe stale "
                "results. Expected: results refresh for the new filter set. Actual: prior "
                "department results remain visible until page refresh."
            ),
            "issuetype": {"name": "Bug"},
            "status": {"name": "Open"},
            "priority": {"name": "Medium"},
            "comment": {
                "comments": [
                    {
                        "body": (
                            "Mock/demo note: suspected cache invalidation or query key issue "
                            "around employee search filters."
                        )
                    }
                ]
            },
        },
        "hrs_ai_fetch": {"mock": True, "reason": reason, "generated_at": now},
    }
