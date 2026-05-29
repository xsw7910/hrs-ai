"""Copilot CLI checks and Phase 1 guidance."""

from __future__ import annotations

from pathlib import Path

from .config import load_config
from .git_ops import command_available


def print_copilot_check() -> None:
    config = load_config(Path.cwd())
    print("hrs-ai copilot-check")
    print(f"copilot_command: {config.copilot_command}")
    print(f"copilot_available: {command_available(config.copilot_command)}")
    print(f"gh_available: {command_available('gh')}")
    print("automatic_invocation: experimental and not implemented in Phase 1")
    print("default_mode: prepare-only")


def print_auto_invocation_not_implemented(issue_key: str) -> None:
    print("--copilot-fix requested.")
    print("Automatic Copilot invocation is not implemented yet in Phase 1.")
    print(f"Manual instruction: run Copilot CLI from the target repo root and read .ai/{issue_key}/copilot_task.md.")
