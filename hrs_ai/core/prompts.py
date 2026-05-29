"""Prompt and task artifact generation."""

from __future__ import annotations

from .git_ops import branch_name


def generate_prompts(issue_key: str) -> dict[str, str]:
    branch = branch_name(issue_key)
    return {
        "copilot_task.md": _copilot_task(issue_key, branch),
        "copilot_analysis_prompt.md": _analysis_prompt(issue_key),
        "copilot_fix_prompt.md": _fix_prompt(issue_key),
        "review_prompt.md": _review_prompt(issue_key),
        "test_plan.md": _test_plan(issue_key),
    }


def _copilot_task(issue_key: str, branch: str) -> str:
    return (
        f"# Copilot CLI Task: {issue_key}\n\n"
        "Run Copilot CLI from the target repo root, not from the hrs-ai tool source directory.\n\n"
        f"Branch name: `{branch}`\n\n"
        "## Safety Rules\n\n"
        "- Do not work directly on main/master.\n"
        "- Do not run git reset --hard.\n"
        "- Do not run git clean -fd.\n"
        "- Do not delete files.\n"
        "- Do not push unless explicitly instructed.\n\n"
        "## Required Workflow\n\n"
        f"1. Read `.ai/{issue_key}/bug_context.md`.\n"
        "2. Read and inspect:\n"
        f"   `.ai/{issue_key}/code_search.md`\n\n"
        "   If this file exists, use it to identify related files, matched line numbers, "
        "and relevant snippets before editing code.\n"
        f"3. Use `.ai/{issue_key}/related_files.json` and matched line numbers to inspect the most relevant files.\n"
        "4. Do not edit code until after reviewing context and related files.\n"
        "5. Analyze likely root cause.\n"
        "6. Implement the smallest safe fix.\n"
        "7. Run focused tests if available.\n"
        "8. Generate:\n"
        f"   - `.ai/{issue_key}/bug_analysis.md`\n"
        f"   - `.ai/{issue_key}/fix_summary.md`\n"
        f"   - `.ai/{issue_key}/test_result.md`\n"
        f"   - `.ai/{issue_key}/diff_summary.md`\n"
        f"   - `.ai/{issue_key}/review_notes.md`\n"
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
