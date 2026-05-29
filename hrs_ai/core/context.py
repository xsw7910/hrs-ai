"""Build AI-ready bug context."""

from __future__ import annotations

import json
from pathlib import Path


def build_context(repo_root: Path, issue_key: str, parsed: dict[str, object], keywords: dict[str, object]) -> str:
    keyword_text = ", ".join(keywords.get("high_value", [])) or "_No keywords extracted._"
    memory_path = repo_root / ".ai_memory" / "bugs" / f"{issue_key}.md"
    memory_note = (
        f"Existing memory entry found at `{memory_path}`."
        if memory_path.exists()
        else "No previous memory entry found for this issue."
    )
    quality = _quality_score(parsed, keywords)
    return (
        f"# Bug Context: {issue_key}\n\n"
        "## Scope\n\n"
        "This is a prepare-only context package. It does not implement a code fix or invoke Copilot automatically.\n\n"
        "## Jira\n\n"
        f"- Summary: {parsed.get('summary', '')}\n"
        f"- Type: {parsed.get('issue_type', '')}\n"
        f"- Status: {parsed.get('status', '')}\n"
        f"- Priority: {parsed.get('priority', '')}\n"
        f"- Mock/demo data: {parsed.get('is_mock', False)}\n\n"
        "## Description\n\n"
        f"{parsed.get('description') or '_No description available._'}\n\n"
        "## Keywords\n\n"
        f"{keyword_text}\n\n"
        "## Related Memory\n\n"
        f"{memory_note}\n\n"
        "## Context Quality\n\n"
        f"Score: {quality}/100\n\n"
        "## Raw Keyword Data\n\n"
        "```json\n"
        f"{json.dumps(keywords, indent=2, sort_keys=True)}\n"
        "```\n"
    )


def _quality_score(parsed: dict[str, object], keywords: dict[str, object]) -> int:
    score = 30
    if parsed.get("summary"):
        score += 20
    if parsed.get("description"):
        score += 25
    if keywords.get("high_value"):
        score += 15
    if parsed.get("comments"):
        score += 10
    return min(score, 100)
