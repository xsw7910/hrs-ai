# Usage Guide

Run commands from the target repository root. Generated files are written under `.ai/<issue>/` and `.ai_memory/bugs/`.

## Command Reference

### `hrs-ai doctor`
Purpose: Report local environment, git status, ripgrep, Jira env vars, and Copilot CLI availability.
Generated files: None.
Read-only: Yes.
Modifies source code: No.

### `hrs-ai copilot-check`
Purpose: Check Copilot CLI and GitHub CLI availability and explain that automatic invocation is not enabled.
Generated files: None.
Read-only: Yes.
Modifies source code: No.

### `hrs-ai clean <ISSUE>`
Purpose: Remove generated workflow artifacts for one issue.
Generated files: None.
Read-only: No; deletes generated `.ai/<issue>/` artifacts only.
Modifies source code: No.

Memory is preserved by default. This command does not delete product source files, update Jira, or run git commands.

### `hrs-ai clean <ISSUE> --include-memory`
Purpose: Remove generated workflow artifacts and that issue's shared memory entry.
Generated files: None.
Read-only: No; deletes `.ai/<issue>/` and `.ai_memory/bugs/<issue>.md` only.
Modifies source code: No.

Other memory entries are preserved.

### `hrs-ai fetch <ISSUE>`
Purpose: Fetch Jira data when configured, or generate clearly marked mock/demo data.
Generated files: `.ai/<issue>/jira.json`, `.ai/<issue>/jira_summary.md`.
Read-only: Writes generated artifacts only.
Modifies source code: No.

Jira Cloud ADF descriptions and comments are converted into readable Markdown in `jira_summary.md`. Attachment metadata is listed when available, but attachment content is not downloaded. Raw fetched Jira data remains in `jira.json`.

Mock fallback is allowed by default for demos. Generated files clearly state `Data Source: mock/demo fallback` when fallback is used.

### `hrs-ai fetch <ISSUE> --allow-mock`
Purpose: Explicitly allow mock/demo fallback when Jira fetch fails.
Generated files: `.ai/<issue>/jira.json`, `.ai/<issue>/jira_summary.md`.
Read-only: Writes generated artifacts only.
Modifies source code: No.

### `hrs-ai fetch <ISSUE> --no-mock`
Purpose: Require real Jira data and fail if Jira fetch fails.
Generated files: `workflow_status.json` and `execution.log` may be written to record failure; no mock Jira files are generated.
Read-only: Writes generated status/log artifacts only.
Modifies source code: No.

### `hrs-ai parse <ISSUE>`
Purpose: Parse Jira data into structured markdown for downstream context.
Generated files: `.ai/<issue>/jira_parsed.md`.
Read-only: Writes generated artifacts only.
Modifies source code: No.

ADF descriptions and comments are converted before parsed context is written.

### `hrs-ai keywords <ISSUE>`
Purpose: Extract high-value, normal, and dropped keywords from parsed Jira context.
Generated files: `.ai/<issue>/extracted_keywords.json`.
Read-only: Writes generated artifacts only.
Modifies source code: No.

### `hrs-ai search <ISSUE>`
Purpose: Run ripgrep-based code search, rank related files, and assess search confidence.
Generated files: `.ai/<issue>/code_search.md`, `.ai/<issue>/related_files.json`, `.ai/<issue>/search_quality.json`.
Read-only: Writes generated artifacts only.
Modifies source code: No.

`search_quality.json` reports `high`, `medium`, or `low` confidence, reasons, likely high-confidence files, low-confidence false positives, and noise indicators such as CI/build/license/vendor/docs/generated paths.

### `hrs-ai memory search <ISSUE or query>`
Purpose: Search shared markdown memory by issue keywords or free-text query.
Generated files: `.ai/<issue>/memory_search.md` when an issue key is provided.
Read-only: Writes generated artifacts only for issue searches.
Modifies source code: No.

### `hrs-ai memory add <ISSUE>`
Purpose: Create or refresh a shared memory entry for the issue.
Generated files: `.ai/<issue>/memory_entry.md`, `.ai_memory/bugs/<issue>.md`.
Read-only: Writes generated memory only.
Modifies source code: No.

### `hrs-ai memory update <ISSUE>`
Purpose: Update shared memory with final result information after Copilot work.
Generated files: Updates `.ai_memory/bugs/<issue>.md`.
Read-only: Writes generated memory only.
Modifies source code: No.

### `hrs-ai git-context <ISSUE>`
Purpose: Capture branch, working tree status, and recent git history for related files.
Generated files: `.ai/<issue>/git_context.md`.
Read-only: Writes generated artifacts only.
Modifies source code: No.

### `hrs-ai context <ISSUE>`
Purpose: Build the enriched bug context package for Copilot CLI.
Generated files: `.ai/<issue>/bug_context.md`.
Read-only: Writes generated artifacts only.
Modifies source code: No.

### `hrs-ai prompt <ISSUE>`
Purpose: Generate prompt and task files for Copilot and review workflows.
Generated files: `.ai/<issue>/copilot_task.md`, `.ai/<issue>/copilot_handoff.md`, `.ai/<issue>/copilot_analysis_prompt.md`, `.ai/<issue>/copilot_fix_prompt.md`, `.ai/<issue>/review_prompt.md`, `.ai/<issue>/test_plan.md`.
Read-only: Writes generated artifacts only.
Modifies source code: No.

### `hrs-ai copilot-task <ISSUE>`
Purpose: Regenerate Copilot task and handoff files from existing bug context.
Generated files: `.ai/<issue>/copilot_task.md`, `.ai/<issue>/copilot_handoff.md`, `.ai/<issue>/copilot_team_instructions.md`, `.ai/<issue>/copilot_fix_prompt.md`, `.ai/<issue>/review_prompt.md`.
Read-only: Writes generated artifacts only.
Modifies source code: No.

### `hrs-ai copilot-instructions <ISSUE>`
Purpose: Generate or refresh per-issue Copilot team instructions.
Generated files: `.ai/<issue>/copilot_team_instructions.md`.
Read-only: Writes generated artifacts only.
Modifies source code: No.

This does not fetch Jira, rerun code search, or modify product source. It copies the reusable `docs/copilot_team_instructions.md` template, or uses a built-in fallback if the docs file is unavailable.

### `hrs-ai check-results <ISSUE>`
Purpose: Check whether Copilot result files exist.
Generated files: None.
Read-only: Yes.
Modifies source code: No.

### `hrs-ai check-results <ISSUE> --strict`
Purpose: Check result files and return nonzero if any are missing.
Generated files: None.
Read-only: Yes.
Modifies source code: No.

### `hrs-ai summarize-results <ISSUE>`
Purpose: Concatenate Copilot result files into a final result summary and manual validation guide.
Generated files: `.ai/<issue>/result_summary.md`, `.ai/<issue>/manual_validation.md`.
Read-only: Writes generated artifacts only.
Modifies source code: No.

### `hrs-ai review-package <ISSUE>`
Purpose: Generate a final review prompt for Copilot, Claude, Codex, or a human reviewer.
Generated files: `.ai/<issue>/final_review_prompt.md`.
Read-only: Writes generated artifacts only.
Modifies source code: No.

### `hrs-ai delivery-check <ISSUE>`
Purpose: Check whether the issue package looks ready for manual delivery.
Generated files: Updates workflow status and execution log when present.
Read-only: Writes generated status/log artifacts only.
Modifies source code: No.

### `hrs-ai commit-plan <ISSUE>`
Purpose: Generate a manual commit plan using read-only git commands.
Generated files: `.ai/<issue>/commit_plan.md`.
Read-only: Writes generated artifacts only.
Modifies source code: No.

### `hrs-ai push-plan <ISSUE>`
Purpose: Generate a manual push plan using read-only git commands.
Generated files: `.ai/<issue>/push_plan.md`.
Read-only: Writes generated artifacts only.
Modifies source code: No.

### `hrs-ai commit <ISSUE> --execute`
Purpose: Disabled prototype placeholder for future commit automation.
Generated files: None.
Read-only: Yes.
Modifies source code: No.

This intentionally does not run a real `git commit`. Use `commit-plan`, review the generated plan, and manually run git commands after review.

### `hrs-ai push <ISSUE> --execute`
Purpose: Disabled prototype placeholder for future push automation.
Generated files: None.
Read-only: Yes.
Modifies source code: No.

This intentionally does not run a real `git push`. Use `push-plan`, review the generated plan, and manually run git commands after review.

### `hrs-ai status <ISSUE>`
Purpose: Show workflow status and generated files for an issue.
Generated files: None.
Read-only: Yes.
Modifies source code: No.

### `hrs-ai bug <ISSUE>`
Purpose: Run the main end-to-end prepare-only workflow.
Generated files: Full issue package under `.ai/<issue>/` and shared memory entry `.ai_memory/bugs/<issue>.md`.
Read-only: Writes generated artifacts only.
Modifies source code: No.

This command fetches or prepares Jira data, parses it, extracts keywords, runs code search, searches memory, captures git context, builds `bug_context.md`, generates Copilot task and handoff files, creates test and review artifacts, and writes the memory entry.

`bug_context.md` includes Code Search Quality. If search confidence is low, the Copilot task tells the coding agent to verify the feature exists before editing and to write a no-op analysis when no real implementation is found.

The workflow also generates `.ai/<issue>/copilot_team_instructions.md`, a per-issue copy of stable team rules for legacy C++/Qt codebases.

It does not modify source code, commit, push, merge, create PRs, update Jira, or automatically invoke Copilot.

Mock fallback is allowed by default. If Jira env vars are missing or Jira fetch fails, the workflow uses clearly marked mock/demo Jira data.

### `hrs-ai bug <ISSUE> --allow-mock`
Purpose: Explicitly allow mock/demo Jira fallback.
Generated files: Full issue package under `.ai/<issue>/` and memory entry `.ai_memory/bugs/<issue>.md`.
Read-only: Writes generated artifacts only.
Modifies source code: No.

### `hrs-ai bug <ISSUE> --no-mock`
Purpose: Require real Jira data.
Generated files: `workflow_status.json` and `execution.log` may be written if Jira fetch fails.
Read-only: Writes generated status/log artifacts only when failing.
Modifies source code: No.

When Jira fetch fails, this stops the workflow before parse, keyword extraction, code search, context generation, prompts, or memory add.

### `hrs-ai bug <ISSUE> --fresh`
Purpose: Remove old `.ai/<issue>/` workflow artifacts, then run the main prepare-only workflow.
Generated files: Fresh issue package under `.ai/<issue>/` and memory entry `.ai_memory/bugs/<issue>.md`.
Read-only: No; deletes generated `.ai/<issue>/` artifacts before regenerating them.
Modifies source code: No.

Memory is preserved before the rerun unless `--include-memory` is also provided. This is useful for demos where older result summaries, review prompts, or commit/push plans should not appear in a new prepare-only run.

### `hrs-ai bug <ISSUE> --fresh --include-memory`
Purpose: Remove old `.ai/<issue>/` artifacts and that issue's memory entry, then run the main prepare-only workflow.
Generated files: Fresh issue package under `.ai/<issue>/` and a newly generated `.ai_memory/bugs/<issue>.md`.
Read-only: No; deletes generated artifacts for the requested issue only.
Modifies source code: No.

Other memory entries and product source files are preserved.

## Jira Environment
Set these variables for real Jira usage:

```powershell
$env:JIRA_BASE_URL="https://your-company.atlassian.net"
$env:JIRA_EMAIL="you@example.com"
$env:JIRA_TOKEN="your_jira_api_token"
```

Demo usage:

```powershell
hrs-ai bug HR-12345 --allow-mock
```

Real Jira usage:

```powershell
hrs-ai bug HR-12345 --no-mock
```
