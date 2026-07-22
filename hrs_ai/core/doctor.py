"""Environment diagnostics."""

from __future__ import annotations

import platform
import sys
from pathlib import Path

from .config import load_config, load_email_config, load_graph_config
from .git_ops import command_available, current_branch, inside_git_repo, working_tree_status


def collect_doctor_report(repo_root: Path) -> dict[str, str | bool | None]:
    config = load_config(repo_root)
    email_config = load_email_config()
    graph_config = load_graph_config()
    in_git = command_available("git") and inside_git_repo(repo_root)
    return {
        "python_version": platform.python_version(),
        "python_ok": sys.version_info >= (3, 10),
        "git_available": command_available("git"),
        "current_directory": str(repo_root),
        "inside_git_repo": in_git,
        "current_branch": current_branch(repo_root) if in_git else None,
        "working_tree_status": working_tree_status(repo_root) if in_git else None,
        "rg_available": command_available("rg"),
        "jira_base_url_present": bool(config.jira_base_url),
        "jira_email_present": bool(config.jira_email),
        "jira_token_present": bool(config.jira_token),
        "copilot_available": command_available(config.copilot_command),
        "claude_available": command_available(config.claude_command),
        "email_configured": email_config.is_configured,
        "email_graph_configured": graph_config.is_configured,
    }


def print_doctor_report(repo_root: Path) -> None:
    report = collect_doctor_report(repo_root)
    print("bugpilot doctor")
    for key, value in report.items():
        print(f"{key}: {value}")
