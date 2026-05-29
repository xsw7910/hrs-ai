"""Shared markdown memory helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def build_memory_entry(issue_key: str, parsed: dict[str, object], context_path: str) -> str:
    now = datetime.now(timezone.utc).isoformat()
    return (
        f"# {issue_key} AI Bug Workflow Memory\n\n"
        f"- Created: {now}\n"
        f"- Mode: prepare-only\n"
        f"- Summary: {parsed.get('summary', '')}\n"
        f"- Mock/demo Jira data: {parsed.get('is_mock', False)}\n"
        f"- Context: {context_path}\n\n"
        "## Investigation State\n\n"
        "Phase 1 generated this memory entry during preparation. No code fix has been attempted by hrs-ai.\n"
    )


def add_memory_entry(repo_root: Path, issue_key: str, content: str) -> Path:
    memory_path = repo_root / ".ai_memory" / "bugs" / f"{issue_key}.md"
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text(content, encoding="utf-8")
    return memory_path
