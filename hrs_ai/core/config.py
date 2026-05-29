"""Configuration helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


WORKFLOW_STEPS = [
    "doctor",
    "fetch",
    "parse",
    "keywords",
    "memory_search",
    "code_search",
    "git_context",
    "context",
    "prompt",
    "memory_add",
    "copilot_fix",
    "result_summary",
    "manual_validation",
    "final_review_prompt",
    "memory_update",
]


@dataclass(frozen=True)
class AppConfig:
    repo_root: Path
    jira_base_url: str | None
    jira_email: str | None
    jira_token: str | None
    copilot_command: str

    @property
    def has_jira_credentials(self) -> bool:
        return bool(self.jira_base_url and self.jira_email and self.jira_token)


def load_config(repo_root: Path) -> AppConfig:
    return AppConfig(
        repo_root=repo_root,
        jira_base_url=os.getenv("JIRA_BASE_URL"),
        jira_email=os.getenv("JIRA_EMAIL"),
        jira_token=os.getenv("JIRA_TOKEN"),
        copilot_command=os.getenv("HRS_AI_COPILOT_COMMAND", "copilot"),
    )


def issue_dir(repo_root: Path, issue_key: str) -> Path:
    return repo_root / ".ai" / issue_key


def memory_dir(repo_root: Path) -> Path:
    return repo_root / ".ai_memory" / "bugs"
