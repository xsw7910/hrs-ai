"""Interactive first-time setup for BugPilot (`bugpilot setup`).

Collects the Jira email and API token, checks local tooling, validates the
credentials against the fixed company Jira site, and saves them to the user
config file. Prompt/secret input is injectable so the flow is unit-testable;
tool checks and Jira validation are delegated to existing modules to avoid
duplicating logic.
"""

from __future__ import annotations

import getpass
import sys
from typing import Callable

from . import git_ops, jira, user_config

_CHECK = "✓"  # ✓
_MAX_PROMPT_ATTEMPTS = 3

PromptFn = Callable[[str], str]
OutFn = Callable[[str], None]


def run_setup(
    prompt: PromptFn = input,
    prompt_secret: PromptFn = getpass.getpass,
    out: OutFn = print,
) -> int:
    """Run the interactive setup. Returns a process exit code (0 = success)."""
    _enable_unicode_output()
    base_url = user_config.DEFAULT_JIRA_BASE_URL

    out("=========================================")
    out("            BugPilot Setup")
    out("=========================================")
    out("")
    out("Jira URL:")
    out("")
    out(f"  {base_url}")
    out("")
    out("(Company default)")
    out("")

    try:
        email = _read_required(prompt, "Jira Email:", out)
        if email is None:
            return _abort(out, "No Jira email provided.")

        out("")
        out("Jira API Token")
        out("")
        out("If you don't have an API token yet, create one here:")
        out("  https://id.atlassian.com/manage-profile/security/api-tokens")
        out("")
        out("Create a new API token and paste it below.")
        token = _read_required(prompt_secret, "Jira API Token:", out)
        if token is None:
            return _abort(out, "No Jira API token provided.")
    except KeyboardInterrupt:
        return _abort(out, "Setup cancelled.")

    # Local tooling: informational. Missing tools warn but never block setup;
    # only Jira authentication gates completion.
    out("")
    out("Checking configuration...")
    out("")
    _report_tool(out, "Git", "git")
    _report_tool(out, "ripgrep", "rg")
    _report_tool(out, "GitHub Copilot CLI", "copilot")

    out("")
    out("Connecting to Jira...")
    out("")
    result = jira.validate_credentials(base_url, email, token)
    if not result.ok:
        out("Authentication failed.")
        out("")
        out("Please check your Jira email or API token.")
        out("")
        out("Run:")
        out("")
        out("    bugpilot setup")
        out("")
        out("to try again.")
        return 1
    out(f"{_CHECK} Login successful")

    # Persist only after a successful login so we never store bad credentials.
    path = user_config.save_user_config(email, token)

    out("")
    out(f"Configuration saved to: {path}")
    out("")
    out("Setup completed!")
    out("")
    out("You can now run:")
    out("")
    out("    bugpilot HR-26609")
    out("")
    return 0


def _read_required(reader: PromptFn, label: str, out: OutFn) -> str | None:
    """Prompt for a required value; return it stripped, or None if abandoned."""
    out(label)
    for _ in range(_MAX_PROMPT_ATTEMPTS):
        try:
            value = (reader("> ") or "").strip()
        except EOFError:
            return None
        if value:
            return value
        out("  This value is required. Please try again.")
    return None


def _report_tool(out: OutFn, label: str, command: str) -> None:
    if git_ops.command_available(command):
        out(f"{_CHECK} {label}")
    else:
        out(f"! {label} not found (optional now; install it before running fixes).")


def _abort(out: OutFn, message: str) -> int:
    out("")
    out(message)
    out("Run 'bugpilot setup' to try again.")
    return 1


def _enable_unicode_output() -> None:
    # Ensure the ✓ mark prints on legacy Windows consoles (cp1252) without error.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass
