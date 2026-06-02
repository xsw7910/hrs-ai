"""Prompt and task artifact generation."""

from __future__ import annotations

from pathlib import Path

from .git_ops import branch_name


def generate_prompts(issue_key: str, summary: str | None = None) -> dict[str, str]:
    branch = branch_name(issue_key, summary)
    return {
        "copilot_task.md": _copilot_task(issue_key, branch),
        "copilot_handoff.md": _copilot_handoff(issue_key),
        "copilot_team_instructions.md": copilot_team_instructions(),
        "copilot_analysis_prompt.md": _analysis_prompt(issue_key),
        "copilot_fix_prompt.md": _fix_prompt(issue_key),
        "review_prompt.md": _review_prompt(issue_key),
        "test_plan.md": _test_plan(issue_key),
    }


def generate_copilot_task_files(issue_key: str, summary: str | None = None) -> dict[str, str]:
    branch = branch_name(issue_key, summary)
    return {
        "copilot_task.md": _copilot_task(issue_key, branch),
        "copilot_handoff.md": _copilot_handoff(issue_key),
        "copilot_team_instructions.md": copilot_team_instructions(),
        "copilot_fix_prompt.md": _fix_prompt(issue_key),
        "review_prompt.md": _review_prompt(issue_key),
    }


def copilot_team_instructions() -> str:
    path = Path(__file__).resolve().parents[2] / "docs" / "copilot_team_instructions.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return _fallback_team_instructions()


def _copilot_task(issue_key: str, branch: str) -> str:
    return (
        f"# Copilot CLI Task: {issue_key}\n\n"
        "## Execution Location\n\n"
        "- Run Copilot CLI from the target repo root (the target repository root).\n"
        "- Do not run Copilot CLI from the hrs-ai tool source directory.\n"
        f"- `.ai/{issue_key}/` files are relative to the target repo root.\n\n"
        "## Team Instructions\n\n"
        "Before editing code, read:\n"
        f"`.ai/{issue_key}/copilot_team_instructions.md`\n\n"
        "Follow these instructions together with the issue-specific context.\n"
        "- Issue-specific task instructions override general team instructions only when necessary.\n"
        "- Safety rules always apply.\n"
        "- If team instructions and task instructions conflict, choose the safer option and document the conflict in `review_notes.md`.\n\n"
        "## Branch Instructions\n\n"
        f"- Branch name: `{branch}`\n"
        "- Check the current branch before editing.\n"
        "- Do not work directly on main/master.\n"
        "- Do not edit files on main/master.\n"
        "- Create or switch to the feature branch before editing files.\n\n"
        "## Required Input Files\n\n"
        f"- Read `.ai/{issue_key}/bug_context.md`.\n"
        f"- Read `.ai/{issue_key}/copilot_team_instructions.md`.\n"
        f"- Read and inspect `.ai/{issue_key}/code_search.md` if present.\n"
        f"- Read and inspect `.ai/{issue_key}/related_files.json` if present.\n"
        f"- Read search quality from `.ai/{issue_key}/search_quality.json` if present.\n"
        f"- Read and inspect `.ai/{issue_key}/memory_search.md` if present.\n"
        f"- Read and inspect `.ai/{issue_key}/git_context.md` if present.\n"
        f"- Read `.ai/{issue_key}/jira_parsed.md` for reproduction steps, actual/expected results, environment, errors, and missing information.\n\n"
        "## Analysis Workflow\n\n"
        "- Summarize the problem in your own words.\n"
        "- Read Jira comments in `bug_context.md` as potentially newer than the original description.\n"
        "- Review Jira attachment metadata in `bug_context.md`.\n"
        "- Do not claim to have inspected attachment contents unless the content is present in repository files or artifact files.\n"
        "- If attachment metadata suggests logs, screenshots, or crash dumps, mention follow-up review if needed.\n"
        "- Use reproduction steps, actual/expected results, environment, and error messages from jira_parsed.md.\n"
        "- Do not invent reproduction steps or error messages not present in the Jira data.\n"
        "- If required bug information is missing, document your assumptions in bug_analysis.md.\n"
        "- If missing information prevents a safe fix, write a no-op analysis or request follow-up information.\n"
        "- Identify likely root cause hypotheses.\n"
        "- Inspect top related files from `related_files.json`.\n"
        "- Read search quality from `bug_context.md` or `code_search.md`.\n"
        "- If search confidence is Low, verify whether the feature exists before editing.\n"
        "- If search confidence is Low, do not assume the matched files are the correct implementation.\n"
        "- Do not modify code based only on low-confidence keyword matches.\n"
        "- If no real implementation is found, write a no-op analysis explaining why no code fix was applied.\n"
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
        "Read these files before editing:\n"
        f"- `.ai/{issue_key}/copilot_task.md`\n"
        f"- `.ai/{issue_key}/copilot_team_instructions.md`\n\n"
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


# This fallback should mirror docs/copilot_team_instructions.md.
def _fallback_team_instructions() -> str:
    return """# Copilot Team Instructions

## Purpose

This document gives Copilot CLI stable team rules for working in a legacy C++/Qt desktop codebase.

## Core Principles

- Prefer small, targeted fixes.
- Do not refactor unrelated code.
- Do not mass-format files.
- Do not rename public APIs unless required.
- Do not change product behavior outside the Jira scope.
- Preserve existing architecture and coding style.
- Ask for clarification or write no-op analysis if context is insufficient.

## Legacy C++ Guidelines

- Be careful with object ownership and lifetime.
- Avoid introducing raw owning pointers unless consistent with surrounding code.
- Prefer existing project ownership patterns.
- Avoid broad exception handling changes.
- Avoid global state changes unless clearly required.
- Be careful with copy/move behavior in existing classes.
- Avoid changing ABI-sensitive public headers unless necessary.

## Qt Guidelines

- Respect QObject parent/child ownership.
- Avoid UI updates from non-UI threads.
- Be careful with signal/slot connections and duplicate connections.
- Avoid blocking the UI thread.
- Preserve existing translation/localization patterns.
- Preserve existing widget layout and object names unless required.
- Be careful with model/view updates and stale data.
- Use existing Qt version/style patterns in nearby code.

## Legacy Codebase Guidelines

- Prefer local fixes near the identified root cause.
- Read surrounding code before editing.
- Follow nearby naming and formatting style.
- Do not modernize unrelated code.
- Do not replace existing frameworks or patterns.
- Do not change file organization unless required.
- Do not assume all tests are available.

## Testing Expectations

- Run focused tests if available.
- If automated tests are unavailable, document manual validation.
- Include regression risk.
- Include commands attempted and results.
- Do not claim tests passed if they were not run.

## Git Safety

- Do not work directly on main/master.
- Do not run git reset --hard.
- Do not run git clean -fd.
- Do not delete files.
- Do not merge.
- Do not push unless explicitly instructed.
- Always summarize changed files.

## Output Expectations

When completing an hrs-ai Copilot task, generate:
- .ai/<issue>/bug_analysis.md
- .ai/<issue>/fix_summary.md
- .ai/<issue>/test_result.md
- .ai/<issue>/diff_summary.md
- .ai/<issue>/review_notes.md

## No-Op Fix Guidance

If the issue is mock/demo, search confidence is low, or no real implementation exists:
- Do not invent a code fix.
- Do not modify unrelated files.
- Write a clear no-op analysis.
- Explain what was searched.
- Explain why no source change was applied.
- Recommend what information is needed next.
"""
