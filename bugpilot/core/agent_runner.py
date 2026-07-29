"""Optional, opt-in invocation of a coding agent to complete the workflow.

bugpilot stays prepare-only by default. When the developer passes --claude or
--copilot to `bugpilot bug`, this module launches that agent interactively in the
target repo with the standard handoff prompt so it reads agent_task.md and
completes the workflow (analyze, fix, write result files, post one Jira status
comment). The agent still stops at the commit gate and asks before committing.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig, load_config

HANDOFF_PROMPT = "Read .ai/{issue_key}/agent_task.md and complete the workflow."


@dataclass
class AgentRunResult:
    agent: str
    ran: bool
    command: list[str]
    returncode: int | None = None
    skipped_reason: str | None = None


def build_agent_command(agent: str, issue_key: str, config: AppConfig) -> list[str]:
    prompt = HANDOFF_PROMPT.format(issue_key=issue_key)
    if agent == "claude":
        base = [config.claude_command, *shlex.split(config.claude_args)]
    elif agent == "copilot":
        base = [config.copilot_command, *shlex.split(config.copilot_args)]
    else:
        raise ValueError(f"Unknown agent: {agent}")
    return [*base, prompt]


def run_agent(repo_root: Path, issue_key: str, agent: str, config: AppConfig | None = None) -> AgentRunResult:
    config = config if config is not None else load_config(repo_root)
    command = build_agent_command(agent, issue_key, config)
    launch = _resolve_launch_command(command)
    if launch is None:
        return AgentRunResult(
            agent=agent,
            ran=False,
            command=command,
            skipped_reason=f"{command[0]} was not found on PATH.",
        )
    # Inherit the terminal so the agent runs interactively and the developer can
    # watch it work. Run in the target repo root (the current working directory).
    completed = subprocess.run(launch, cwd=repo_root)
    return AgentRunResult(
        agent=agent,
        ran=True,
        command=command,
        returncode=completed.returncode,
    )


def _resolve_launch_command(command: list[str]) -> list[str] | None:
    """Resolve the executable to a runnable form for the current OS.

    shutil.which honors PATHEXT (so it finds `claude.cmd` on Windows), but
    CreateProcess cannot launch a bare name or a .cmd/.bat directly. Resolve the
    full path and, for Windows batch shims, run it through `cmd /c`.
    """
    resolved = shutil.which(command[0])
    if resolved is None:
        return None
    rest = command[1:]
    if sys.platform == "win32" and resolved.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", resolved, *rest]
    return [resolved, *rest]
