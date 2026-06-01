# hrs-ai

## What It Is
hrs-ai is a prototype CLI for an AI-assisted Jira bug workflow using GitHub Copilot CLI. It builds a deterministic development package from a Jira issue, local code search, shared memory, and git context so a developer can hand Copilot a clearer task.

## Why It Exists
AI-assisted bug work often starts with scattered context and ends with useful investigation notes disappearing into chat history. hrs-ai is intended to make that work repeatable.

- AI usage is currently scattered across tools and conversations.
- Developers manually copy Jira context into AI tools.
- Useful AI investigation is lost after the fix is done.
- Similar bugs are repeatedly analyzed from scratch.
- Legacy C++/Qt repositories need better context before AI tools can help safely.

## How It Works
```text
Jira issue -> code search -> memory search -> bug_context.md -> Copilot CLI task -> result summary -> memory update -> delivery plan
```

hrs-ai prepares files under `.ai/<issue>/` and shared memory under `.ai_memory/bugs/<issue>.md`. Jira Cloud ADF descriptions and comments are converted into readable Markdown for the issue package, and Jira attachment metadata is surfaced without downloading attachment content. Code search includes a confidence assessment so low-confidence false positives are visible before Copilot edits anything. Copilot CLI remains a manual handoff step, with reusable team instructions for legacy C++/Qt work.

## Installation
```powershell
python -m pip install -e .
```

## Jira Configuration
For real Jira fetches, set:

```powershell
$env:JIRA_BASE_URL="https://your-company.atlassian.net"
$env:JIRA_EMAIL="you@example.com"
$env:JIRA_TOKEN="your_jira_api_token"
```

The normal workflow uses real Jira only and does not fall back to mock data:

```powershell
hrs-ai bug HR-12345
```

Equivalent explicit form:

```powershell
hrs-ai bug HR-12345 --fresh --no-mock
```

Demo/testing fallback must be requested explicitly:

```powershell
hrs-ai bug HR-12345 --allow-mock
```

When mock fallback is used, `jira_summary.md`, `jira.json`, and `execution.log` clearly mark the data as mock/demo fallback.

## Important: Run From Target Repo Root
The hrs-ai source repo can be anywhere. Run `hrs-ai` from the target product repository root, because generated `.ai` and `.ai_memory` folders are written relative to the current working directory.

Copilot CLI should also be run from the target product repository root. Do not run the Copilot handoff from the hrs-ai tool source directory unless that is the repository you intend to modify.

Example:
```powershell
cd C:\sandbox\target-repo
hrs-ai bug HR-12345
```

## Quick Demo
```powershell
hrs-ai doctor
hrs-ai bug HR-12345
hrs-ai status HR-12345
hrs-ai clean HR-12345
hrs-ai bug HR-12345 --resume
hrs-ai copilot-task HR-12345
hrs-ai check-results HR-12345
hrs-ai summarize-results HR-12345
hrs-ai memory update HR-12345
hrs-ai review-package HR-12345
hrs-ai jira-comment-draft HR-12345
hrs-ai jira-comment HR-12345
hrs-ai delivery-check HR-12345
hrs-ai commit-plan HR-12345
hrs-ai push-plan HR-12345
```

## Main Commands
- `hrs-ai doctor`: report environment, git, ripgrep, Jira env vars, and Copilot CLI availability.
- `hrs-ai copilot-check`: check Copilot and GitHub CLI availability without invoking Copilot.
- `hrs-ai fetch <ISSUE>`: fetch real Jira data and fail clearly if Jira is unavailable.
- `hrs-ai fetch <ISSUE> --allow-mock`: allow clearly marked mock/demo fallback when Jira fetch fails.
- `hrs-ai fetch <ISSUE> --no-mock`: require real Jira data. This is the default.
- `hrs-ai parse <ISSUE>`: parse Jira data into a markdown summary.
- `hrs-ai keywords <ISSUE>`: extract high-value, normal, and dropped keywords.
- `hrs-ai search <ISSUE>`: run ripgrep-based code search and related file ranking.
- `hrs-ai memory search <ISSUE or query>`: search shared markdown memory.
- `hrs-ai memory add <ISSUE>`: create or refresh a shared memory entry.
- `hrs-ai memory update <ISSUE>`: update memory with final result information.
- `hrs-ai git-context <ISSUE>`: generate branch, status, and recent file history context.
- `hrs-ai context <ISSUE>`: generate enriched `bug_context.md`.
- `hrs-ai prompt <ISSUE>`: generate Copilot and review prompt files.
- `hrs-ai copilot-task <ISSUE>`: regenerate Copilot task and handoff files from existing context.
- `hrs-ai copilot-instructions <ISSUE>`: regenerate `.ai/<issue>/copilot_team_instructions.md` from the reusable team template.
- `hrs-ai check-results <ISSUE>`: check whether Copilot result files exist.
- `hrs-ai check-results <ISSUE> --strict`: return nonzero if required result files are missing.
- `hrs-ai summarize-results <ISSUE>`: generate result summary and manual validation files.
- `hrs-ai review-package <ISSUE>`: generate final review prompt.
- `hrs-ai jira-comment-draft <ISSUE>`: generate a local, reviewable Jira comment draft from existing hrs-ai artifacts.
- `hrs-ai jira-comment-draft <ISSUE> --strict`: require Copilot result files before generating the local draft.
- `hrs-ai jira-comment <ISSUE>`: preview the local Jira comment draft without posting to Jira.
- `hrs-ai jira-comment <ISSUE> --execute`: post exactly one Jira comment from the local draft.
- `hrs-ai delivery-check <ISSUE>`: check readiness for manual delivery.
- `hrs-ai commit-plan <ISSUE>`: generate a manual commit plan.
- `hrs-ai push-plan <ISSUE>`: generate a manual push plan.
- `hrs-ai clean <ISSUE>`: remove generated `.ai/<issue>/` workflow artifacts while preserving memory.
- `hrs-ai clean <ISSUE> --include-memory`: also remove `.ai_memory/bugs/<issue>.md` for that issue only.
- `hrs-ai status <ISSUE>`: show workflow status and generated files.
- `hrs-ai bug <ISSUE>`: run a fresh prepare-only workflow end to end with real Jira required and mock fallback disabled.
- `hrs-ai bug <ISSUE> --fresh`: same as the default; kept for compatibility.
- `hrs-ai bug <ISSUE> --resume`: preserve existing `.ai/<issue>/` artifacts and continue an existing workflow.
- `hrs-ai bug <ISSUE> --include-memory`: clean `.ai/<issue>/` and that issue's memory entry first, then rerun.
- `hrs-ai bug <ISSUE> --allow-mock`: explicitly allow mock/demo Jira fallback.
- `hrs-ai bug <ISSUE> --no-mock`: require real Jira data and stop if Jira fetch fails. This is the default.
- `hrs-ai jira-validate <ISSUE>`: validate Jira field mapping for a real issue (no code search, no Copilot task). Generates `jira_summary.md`, `jira_parsed.md`, and `jira_field_report.md`.

## Recommended Real Jira Workflow
```powershell
hrs-ai bug REAL-ISSUE
hrs-ai jira-validate REAL-ISSUE
```

`hrs-ai bug REAL-ISSUE` defaults to a fresh run, preserves memory, requires real Jira, and does not use mock fallback. Use `--resume` to preserve old `.ai/<issue>/` artifacts, and use `--allow-mock` only for demo/testing fallback.

## Safety Rules
- hrs-ai does not automatically modify product source code.
- hrs-ai does not automatically invoke Copilot CLI.
- hrs-ai does not update Jira.
- Jira integration is read-only; hrs-ai converts fetched Jira content to Markdown but does not comment, assign, close, or transition Jira issues.
- `jira-comment-draft` writes a local markdown draft only; it does not post comments to Jira.
- `jira-comment` previews by default; `jira-comment --execute` only adds a Jira comment and does not change status, fields, assignee, attachments, source code, git state, or PRs.
- hrs-ai does not create pull requests.
- hrs-ai does not merge.
- hrs-ai does not run `git add`, `git commit`, or `git push`.
- `commit-plan` and `push-plan` only generate markdown plans.
- Placeholder commit/push execute commands do not perform real delivery actions in this prototype.
- `hrs-ai commit <ISSUE> --execute` and `hrs-ai push <ISSUE> --execute` are disabled placeholders only.
- `clean` and `--fresh` remove only generated hrs-ai artifacts for the requested issue.
- Memory is preserved by default; `--include-memory` removes only `.ai_memory/bugs/<issue>.md`.

## Generated Artifacts
Primary issue package:
```text
.ai/<issue>/
```

Key search artifacts include:
```text
.ai/<issue>/code_search.md
.ai/<issue>/related_files.json
.ai/<issue>/search_quality.json
.ai/<issue>/copilot_team_instructions.md
.ai/<issue>/jira_comment_draft.md
```

Shared memory entry:
```text
.ai_memory/bugs/<issue>.md
```

These folders belong to the target repository where the command is run.

Reusable team instructions live at:
```text
docs/copilot_team_instructions.md
```

Each issue package gets a copy so Copilot CLI can read stable team rules together with the issue-specific task.

## Prototype Status
- Phase 1: prepare-only workflow skeleton.
- Phase 2: code search, memory search, git context, and enriched bug context.
- Phase 3: Copilot CLI task and handoff workflow.
- Phase 4: post-Copilot result summary, review package, and memory update.
- Phase 5: delivery readiness, commit plan, and push plan.
