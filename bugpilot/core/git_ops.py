"""Small git and command helpers."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path


def command_available(command: str) -> bool:
    return shutil.which(command) is not None


def run_command(args: list[str], cwd: Path) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except FileNotFoundError:
        return 127, f"{args[0]} command not found"
    return completed.returncode, completed.stdout.strip()


def inside_git_repo(repo_root: Path) -> bool:
    code, output = run_command(["git", "rev-parse", "--is-inside-work-tree"], repo_root)
    return code == 0 and output.lower() == "true"


def current_branch(repo_root: Path) -> str | None:
    code, output = run_command(["git", "branch", "--show-current"], repo_root)
    return output if code == 0 and output else None


def working_tree_status(repo_root: Path) -> str | None:
    code, output = run_command(["git", "status", "--short"], repo_root)
    if code != 0:
        return None
    return output or "clean"


def generate_git_context(repo_root: Path, issue_key: str) -> str:
    lines = [f"# Git Context: {issue_key}", ""]
    if not command_available("git"):
        lines.extend(["## Warning", "", "git command is not available."])
        return "\n".join(lines).rstrip() + "\n"
    if not inside_git_repo(repo_root):
        lines.extend(["## Warning", "", "Current directory is not inside a git repository."])
        return "\n".join(lines).rstrip() + "\n"

    status = working_tree_status(repo_root) or "unknown"
    clean = status == "clean"
    lines.extend(
        [
            "## Repository",
            "",
            f"- Current branch: {current_branch(repo_root) or 'unknown'}",
            f"- Working tree: {'clean' if clean else 'dirty'}",
            "",
            "## Status",
            "",
            "```text",
            status,
            "```",
            "",
            "## Recent Commits For Related Files",
            "",
        ]
    )

    related_files = _related_files(repo_root, issue_key)
    if not related_files:
        lines.append("_No related files available yet._")
    for file_name in related_files:
        code, output = run_command(["git", "log", "--oneline", "-n", "5", "--", file_name], repo_root)
        lines.extend([f"### {file_name}", "", "```text"])
        lines.append(output if code == 0 and output else "No recent commits found.")
        lines.extend(["```", ""])
    return "\n".join(lines).rstrip() + "\n"


def branch_name(issue_key: str, description: str | None = None) -> str:
    slug = summary_slug(description)
    branch = f"feature/{issue_key}-{slug or 'jira-workflow'}"
    return branch[:120].rstrip("-")


def summary_slug(description: str | None, max_length: int = 80) -> str:
    if not description:
        return ""
    slug = re.sub(r"[^a-z0-9]+", "-", description.lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    words = [word for word in slug.split("-") if word and word not in {"are"}]
    capped: list[str] = []
    current_length = 0
    for word in words:
        next_length = current_length + len(word) + (1 if capped else 0)
        if next_length > max_length:
            break
        capped.append(word)
        current_length = next_length
    return "-".join(capped)


def _related_files(repo_root: Path, issue_key: str) -> list[str]:
    path = repo_root / ".ai" / issue_key / "related_files.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(item.get("file")) for item in data[:5] if isinstance(item, dict) and item.get("file")]
