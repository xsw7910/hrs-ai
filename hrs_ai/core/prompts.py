"""Prompt and task artifact generation."""

from __future__ import annotations

from .git_ops import branch_name


def generate_prompts(issue_key: str) -> dict[str, str]:
    branch = branch_name(issue_key)
    return {
        "copilot_task.md": _copilot_task(issue_key, branch),
        "copilot_handoff.md": _copilot_handoff(issue_key),
        "copilot_analysis_prompt.md": _analysis_prompt(issue_key),
        "copilot_fix_prompt.md": _fix_prompt(issue_key),
        "review_prompt.md": _review_prompt(issue_key),
        "test_plan.md": _test_plan(issue_key),
    }


def generate_copilot_task_files(issue_key: str) -> dict[str, str]:
    branch = branch_name(issue_key)
    return {
        "copilot_task.md": _copilot_task(issue_key, branch),
        "copilot_handoff.md": _copilot_handoff(issue_key),
        "copilot_fix_prompt.md": _fix_prompt(issue_key),
        "review_prompt.md": _review_prompt(issue_key),
    }


def _copilot_task(issue_key: str, branch: str) -> str:
    return (
        f"# Copilot CLI Task: {issue_key}\n\n"
        "## Execution Location\n\n"
        "- Run Copilot CLI from the target repo root (the target repository root).\n"
        "- Do not run Copilot CLI from the hrs-ai tool source directory.\n"
        f"- `.ai/{issue_key}/` files are relative to the target repo root.\n\n"
        "## Branch Instructions\n\n"
        f"- Branch name: `{branch}`\n"
        "- Check the current branch before editing.\n"
        "- Do not work directly on main/master.\n"
        "- Do not edit files on main/master.\n"
        "- Create or switch to the feature branch before editing files.\n\n"
        "## Required Input Files\n\n"
        f"- Read `.ai/{issue_key}/bug_context.md`.\n"
        f"- Read and inspect `.ai/{issue_key}/code_search.md` if present.\n"
        f"- Read and inspect `.ai/{issue_key}/related_files.json` if present.\n"
        f"- Read and inspect `.ai/{issue_key}/memory_search.md` if present.\n"
        f"- Read and inspect `.ai/{issue_key}/git_context.md` if present.\n\n"
        "## Analysis Workflow\n\n"
        "- Summarize the problem in your own words.\n"
        "- Identify likely root cause hypotheses.\n"
        "- Inspect top related files from `related_files.json`.\n"
        "- Use matched line numbers from `code_search.md`.\n"
        "- Do not edit code until after reviewing context and related files.\n"
        "- Ask follow-up questions if context is insufficient.\n\n"
        "## Implementation Workflow\n\n"
        "- Implement the smallest safe fix.\n"
        "- Avoid unrelated refactoring.\n"
        "- Avoid public API changes unless necessary.\n"
        "- Avoid formatting-only changes.\n"
        "- Avoid deleting files.\n"
        "- Run focused tests if available.\n\n"
        "## Required Output Files\n\n"
        f"- `.ai/{issue_key}/bug_analysis.md`\n"
        f"- `.ai/{issue_key}/fix_summary.md`\n"
        f"- `.ai/{issue_key}/test_result.md`\n"
        f"- `.ai/{issue_key}/diff_summary.md`\n"
        f"- `.ai/{issue_key}/review_notes.md`\n\n"
        "## Forbidden Actions\n\n"
        "- Do not run `git reset --hard`.\n"
        "- Do not run `git clean -fd`.\n"
        "- Do not delete source files.\n"
        "- Do not push unless explicitly instructed.\n"
        "- Do not merge.\n"
        "- Do not update Jira.\n"
        "- Do not create PRs.\n"
        "- Do not mass-format unrelated files.\n"
    )


def _copilot_handoff(issue_key: str) -> str:
    return (
        f"# Copilot Handoff: {issue_key}\n\n"
        f"Read `.ai/{issue_key}/copilot_task.md` and complete the workflow.\n\n"
        "## Reminder\n\n"
        "- Run Copilot CLI from the target repo root.\n"
        "- Do not run from the hrs-ai tool repo.\n"
        "- Do not work directly on main/master.\n"
        "- Do not push or merge.\n"
        f"- Generate the required result files under `.ai/{issue_key}/`.\n"
    )


def _analysis_prompt(issue_key: str) -> str:
    return (
        f"# Copilot Analysis Prompt: {issue_key}\n\n"
        "Read `.ai/{issue_key}/bug_context.md`, inspect the repository, and identify the most likely root cause. "
        "Write findings to `.ai/{issue_key}/bug_analysis.md` before editing code.\n"
    ).format(issue_key=issue_key)


def _fix_prompt(issue_key: str) -> str:
    return (
        f"# Copilot Fix Prompt: {issue_key}\n\n"
        "Implement the smallest safe fix that addresses the bug context. Keep unrelated refactors out of scope. "
        "Write `.ai/{issue_key}/fix_summary.md` and `.ai/{issue_key}/diff_summary.md`.\n"
    ).format(issue_key=issue_key)


def _review_prompt(issue_key: str) -> str:
    return (
        f"# Review Prompt: {issue_key}\n\n"
        "Review the changes for correctness, regression risk, missing tests, and safety-rule compliance. "
        "Write `.ai/{issue_key}/review_notes.md`.\n"
    ).format(issue_key=issue_key)


def _test_plan(issue_key: str) -> str:
    return (
        f"# Test Plan: {issue_key}\n\n"
        "- Identify focused tests related to the bug.\n"
        "- Run the narrowest useful test command available.\n"
        "- If no tests exist, document the manual validation path.\n"
        "- Write `.ai/{issue_key}/test_result.md`.\n"
    ).format(issue_key=issue_key)
