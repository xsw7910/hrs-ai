"""AI agent availability checks and safe handoff guidance."""

from __future__ import annotations

from pathlib import Path

from .config import load_config
from .git_ops import command_available


def print_copilot_check() -> None:
    config = load_config(Path.cwd())
    print("bugpilot agent-check")
    print(f"copilot_command: {config.copilot_command}")
    print(f"copilot_available: {command_available(config.copilot_command)}")
    print(f"gh_available: {command_available('gh')}")
    print(f"claude_available: {command_available(config.claude_command)}")
    print("automatic_invocation: opt-in via `bugpilot bug --claude` or `--copilot`")
    print("default_mode: prepare-only")


def print_auto_invocation_not_implemented(issue_key: str) -> None:
    print("Agent automatic invocation is not enabled.")
    print("Open your AI agent from the target repo root and run:")
    print(f"Read .ai/{issue_key}/agent_task.md and complete the workflow.")
