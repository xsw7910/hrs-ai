"""Small git and command helpers."""

from __future__ import annotations

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
            text=True,
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


def branch_name(issue_key: str, description: str = "ai-assisted-jira-bug-workflow") -> str:
    slug_chars: list[str] = []
    previous_dash = False
    for char in description.lower():
        if char.isalnum():
            slug_chars.append(char)
            previous_dash = False
        elif not previous_dash:
            slug_chars.append("-")
            previous_dash = True
    slug = "".join(slug_chars).strip("-")[:60].strip("-")
    return f"feature/{issue_key}-{slug or 'bug-fix'}"
