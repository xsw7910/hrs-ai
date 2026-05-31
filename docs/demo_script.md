# Demo Script

Estimated time: 8 minutes

## Demo Goal
Show how a Jira issue becomes an AI-ready development package.

## Setup
Open a terminal in the target repository root:

```powershell
cd C:\sandbox\target-repo
```

The hrs-ai source repo can live elsewhere. The demo should be run from the product repository where `.ai` and `.ai_memory` should be created.

## Demo Steps
1. Check the environment:

```powershell
hrs-ai doctor
```

Point out Python, git, current directory, git repo status, ripgrep, Jira env vars, and Copilot CLI availability.

2. Build the AI-ready package:

```powershell
hrs-ai bug HR-12345
```

Explain that this is prepare-only. It builds context, prompts, memory, git context, and handoff files without modifying source code.
The default demo mode allows clearly marked mock/demo Jira fallback when Jira credentials are not configured.

For a fresh demo reset, run:

```powershell
hrs-ai bug HR-12345 --fresh
```

This removes old `.ai/HR-12345/` workflow artifacts first while preserving memory by default.

For a real Jira demo with credentials configured, run:

```powershell
hrs-ai bug HR-12345 --no-mock
```

This prevents accidental mock/demo fallback.

3. Show generated files:

```text
.ai/HR-12345/bug_context.md
.ai/HR-12345/search_quality.json
.ai/HR-12345/copilot_task.md
.ai/HR-12345/copilot_handoff.md
```

4. Open Copilot CLI from the target repo root and paste:

```text
Read .ai/HR-12345/copilot_task.md and complete the workflow.
```

5. After Copilot generates result files, run:

```powershell
hrs-ai check-results HR-12345
hrs-ai summarize-results HR-12345
hrs-ai memory update HR-12345
hrs-ai review-package HR-12345
hrs-ai delivery-check HR-12345
hrs-ai commit-plan HR-12345
hrs-ai push-plan HR-12345
```

6. Explain generated memory:

```text
.ai_memory/bugs/HR-12345.md
```

Show how the memory entry preserves Jira context, code search context, related files, and final result notes for future similar issues.

## Demo Talking Points
- hrs-ai is a deterministic context builder.
- Search confidence makes noisy matches and false positives explicit.
- Copilot does the AI coding work through a manual handoff.
- Safety gates keep the developer in control.
- Shared AI memory keeps investigation history reusable.
- There is no automatic commit, push, merge, PR creation, or Jira write-back.
