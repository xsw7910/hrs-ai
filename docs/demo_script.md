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
The default workflow requires real Jira, disables mock fallback, and starts fresh by cleaning old `.ai/HR-12345/` artifacts while preserving memory.

For demo/testing without Jira credentials, request mock fallback explicitly:

```powershell
hrs-ai bug HR-12345 --allow-mock
```

When fallback is used, Jira artifacts are clearly marked as mock/demo data.

To continue an existing workflow package without cleaning old artifacts, run:

```powershell
hrs-ai bug HR-12345 --resume
```

To have an agent complete the workflow right after preparation (analyze, fix, write
result files, post one Jira status comment, then stop at the commit gate), add
`--claude` or `--copilot`:

```powershell
hrs-ai bug HR-12345 --claude
```

Without a flag, `hrs-ai bug` stays prepare-only. Review agent-generated code before committing.

For a faster, more predictable run when the fix location is known, add `--hint` so the agent
goes straight there instead of investigating:

```powershell
hrs-ai bug HR-12345 --claude --hint "Fix in FooWidget.cxx: <root cause / approach>"
```

`--fresh` and `--no-mock` are still accepted for compatibility, but they are no longer required for the normal real Jira workflow.

3. Show generated files:

```text
.ai/HR-12345/bug_context.md
.ai/HR-12345/search_quality.json
.ai/HR-12345/copilot_task.md
.ai/HR-12345/copilot_team_instructions.md
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

As soon as results are summarized, `summarize-results` can post the analysis as a Jira
comment so Jira notifies watchers by email — before the developer decides whether to commit.
Opt in with `HRS_AI_AUTO_JIRA_COMMENT=true` or `summarize-results --jira-comment`; suppress
with `--no-jira-comment`. This reuses the existing Jira credentials (no mail server needed)
and is the simplest notification path when SMTP/Graph are unavailable.

At the commit gate, `commit-plan` also emails a fix summary (Jira item, original problem,
root cause, and changes made) when an email transport is configured. hrs-ai uses
**Microsoft Graph** (recommended for Microsoft 365, sends over HTTPS) when
`GRAPH_TENANT_ID`/`GRAPH_CLIENT_ID`/`GRAPH_CLIENT_SECRET` are set, otherwise **SMTP**.
Preview without sending using `hrs-ai notify HR-12345`; add `--execute` to send, or run
`commit-plan --no-email` to skip. With no transport configured, `commit-plan` still
succeeds and reports that no email was sent — the generated `notification.eml` can be sent
manually via `scripts/send-via-outlook.ps1`. See the README "Email Notification Configuration" section.

6. Explain generated memory:

```text
.ai_memory/bugs/HR-12345.md
```

Show how the memory entry preserves Jira context, code search context, related files, and final result notes for future similar issues.

## Demo Talking Points
- hrs-ai is a deterministic context builder.
- Search confidence makes noisy matches and false positives explicit.
- Team instructions give Copilot stable legacy C++/Qt engineering rules.
- Copilot does the AI coding work through a manual handoff.
- Safety gates keep the developer in control.
- Shared AI memory keeps investigation history reusable.
- There is no automatic commit, push, merge, PR creation, or Jira write-back.
