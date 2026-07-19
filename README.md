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

## Email Notification Configuration
At the commit gate (`hrs-ai commit-plan <ISSUE>`), hrs-ai can email you a summary of
the completed fix: the Jira item, the original problem, the root cause, and the changes
made. The email body is assembled from local `result_summary.md` and `jira_summary.md`;
run `hrs-ai summarize-results <ISSUE>` first so those artifacts exist.

hrs-ai supports two automatic transports plus a manual Outlook option. It picks
**Graph if configured, otherwise SMTP**. `hrs-ai doctor` shows `email_configured`
(SMTP) and `email_graph_configured` (Graph).

### Option 1 — Microsoft Graph (recommended for Microsoft 365)
Use this when your tenant disables SMTP client authentication (error `SmtpClientAuthentication
is disabled for the Tenant`) or blocks outbound port 25 — Graph sends over HTTPS/443.
It requires a one-time **app registration** by an admin (see below), then:

```powershell
$env:GRAPH_TENANT_ID="<tenant id / directory id>"
$env:GRAPH_CLIENT_ID="<application (client) id>"
$env:GRAPH_CLIENT_SECRET="..."        # store in a secrets manager, not in scripts
$env:HRS_AI_EMAIL_FROM="you@your-company.com"   # mailbox the app may send as
$env:HRS_AI_EMAIL_TO="you@your-company.com"     # comma/semicolon separated for multiple
```

**What to ask IT for (app registration):**
- An Entra ID (Azure AD) app registration; give you the **Directory (tenant) ID** and **Application (client) ID**.
- A **client secret** on that app.
- The **application** permission **`Mail.Send`** (Microsoft Graph), with **admin consent granted**.
- Ideally scope it with an *Application Access Policy* so the app can only send as your mailbox.

### Option 2 — SMTP
Configure SMTP through the environment (credentials are never hardcoded or persisted):

```powershell
$env:SMTP_HOST="smtp.your-company.com"
$env:SMTP_PORT="587"              # optional, default 587
$env:SMTP_USERNAME="relay-user"   # optional; omit for an open internal relay
$env:SMTP_PASSWORD="..."          # store in a secrets manager, not in scripts
$env:SMTP_USE_STARTTLS="true"     # optional, default true
$env:SMTP_USE_SSL="false"         # optional, default false (set true for SMTPS/465)
$env:HRS_AI_EMAIL_FROM="hrs-ai@your-company.com"
$env:HRS_AI_EMAIL_TO="you@your-company.com"   # comma/semicolon separated for multiple
```

For a guided setup that stores the password in the PowerShell SecretStore (never in
plain text) and loads every variable into your session, edit the values at the top of
`scripts/setup-email.ps1` once and run it:

```powershell
.\scripts\setup-email.ps1            # load config into the current session
.\scripts\setup-email.ps1 -Persist   # also apply to all future PowerShell sessions
.\scripts\setup-email.ps1 -ResetPassword   # re-enter the stored SMTP password
```

### Option 3 — Manual send via Outlook (no transport config)
When no automatic transport is available, `hrs-ai notify` still writes a portable
`.ai/<ISSUE>/notification.eml`. To open it as a pre-filled Outlook compose window
(Outlook sends over its own modern-auth channel, so no SMTP/port-25 needed):

```powershell
hrs-ai notify HR-12345                       # writes email_draft.md + notification.eml
.\scripts\send-via-outlook.ps1 HR-12345      # opens Outlook; review and click Send
```

### Sending
Sending is opt-in and human-controlled, matching the rest of the workflow:

```powershell
hrs-ai notify HR-12345             # preview only: writes email_draft.md + notification.eml, sends nothing
hrs-ai notify HR-12345 --execute   # send automatically (Graph if configured, else SMTP)
hrs-ai commit-plan HR-12345        # generate commit plan AND send the notification email
hrs-ai commit-plan HR-12345 --no-email   # generate commit plan without sending email
```

If no transport is configured, `commit-plan` still succeeds and simply reports that no
email was sent (use Option 3 to send manually). The email body is sanitized to redact
secret-like values before sending, and no secret (SMTP password or Graph client secret)
is ever logged or included in error messages.

## Notify via Jira Comment (no email server needed)
If your tenant blocks SMTP and app registration for Graph is not available, the simplest
way to be notified when a fix is ready is a **Jira comment**: hrs-ai posts the analysis
summary to the issue, and Jira emails the issue's watchers/assignee/reporter through its
own notification system. This reuses your existing Jira credentials
(`JIRA_BASE_URL` / `JIRA_EMAIL` / `JIRA_TOKEN`) — no mail server, no Graph, no IT ticket.

Opt in so the comment is posted automatically as soon as the fix results are summarized
(before you decide whether to commit):

```powershell
$env:HRS_AI_AUTO_JIRA_COMMENT="true"   # enable auto-post from summarize-results
hrs-ai summarize-results HR-12345       # summarizes results AND posts one Jira comment
```

Per-run control overrides the environment variable:

```powershell
hrs-ai summarize-results HR-12345 --jira-comment      # force post this run
hrs-ai summarize-results HR-12345 --no-jira-comment   # never post this run
```

Notes:
- You must be **watching** the issue (or be its assignee/reporter) and have Jira email
  notifications enabled to receive the message; that is a Jira-side setting.
- Auto-post adds exactly one comment; it never edits fields, transitions, or assigns.
- If posting fails (e.g., no access to the issue), `summarize-results` still succeeds and
  prints a warning — post manually later with `hrs-ai jira-comment <ISSUE> --execute`.
- The comment body is sanitized to redact secret-like values.

## Optional: Let an Agent Complete the Workflow
By default `hrs-ai bug` is prepare-only and prints the manual handoff line. You can
instead have it launch a coding agent to read `copilot_task.md` and complete the
workflow (analyze, implement the smallest safe fix, write result files, post one Jira
status comment) — the agent still stops at the commit gate and asks before committing.

```powershell
hrs-ai bug HR-12345 --claude     # launch Claude after preparation
hrs-ai bug HR-12345 --copilot    # launch Copilot CLI instead
hrs-ai bug HR-12345              # no flag: prepare only (default, unchanged)
```

The agent runs interactively in the current (target) repo so you can watch it work.
Configuration:

```powershell
$env:HRS_AI_CLAUDE_COMMAND="claude"                        # binary to launch
$env:HRS_AI_CLAUDE_ARGS="--permission-mode acceptEdits"    # default: auto-accept file edits
# For a fully unattended run (also skips shell prompts for git / hrs-ai):
$env:HRS_AI_CLAUDE_ARGS="--dangerously-skip-permissions"   # understand the risk first
```

With the default `acceptEdits`, the agent applies file edits without prompting but may
still ask before shell commands (e.g., running `hrs-ai jira-comment --execute` or git).
`--dangerously-skip-permissions` removes those prompts too, at the cost of unattended
execution — use it only when you trust the task and repo.

Treat all agent-generated code as third-party: **review it before you commit**. hrs-ai
never commits or pushes for you; the agent stops and asks at the commit gate.
`hrs-ai doctor` reports `claude_available` / `copilot_available`.

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
hrs-ai retry-prompt HR-12345
hrs-ai manual-result HR-12345
hrs-ai delivery-check HR-12345
hrs-ai notify HR-12345
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
- `hrs-ai retry-prompt <ISSUE>`: generate a second-attempt Copilot prompt from local artifacts and developer feedback.
- `hrs-ai manual-result <ISSUE>`: create developer manual-fix result templates without overwriting existing result files.
- `hrs-ai manual-result <ISSUE> --overwrite`: replace result files with fresh manual-fix templates.
- `hrs-ai delivery-check <ISSUE>`: check readiness for manual delivery.
- `hrs-ai notify <ISSUE>`: write the post-fix notification (`email_draft.md` + `notification.eml`); add `--execute` to send automatically (Graph if configured, else SMTP).
- `hrs-ai commit-plan <ISSUE>`: generate a manual commit plan and email the fix summary at the commit gate (`--no-email` to skip).
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

## Recommended Real Workflow
```powershell
hrs-ai doctor
hrs-ai jira-validate HR-26307
hrs-ai bug HR-26307
hrs-ai jira-comment-draft HR-26307
hrs-ai jira-comment HR-26307
hrs-ai jira-comment HR-26307 --execute
```

Run these from the target product repo root. Real Jira is the default, and mock fallback requires `--allow-mock`. `hrs-ai bug <ISSUE>` is fresh by default; use `--resume` only when continuing existing artifacts. `hrs-ai jira-comment <ISSUE>` previews without writing Jira, and `--execute` is required for Jira comment write-back.

## Safety Rules
- hrs-ai does not automatically modify product source code.
- hrs-ai does not automatically invoke Copilot CLI.
- hrs-ai does not update Jira.
- Jira integration is read-only; hrs-ai converts fetched Jira content to Markdown but does not comment, assign, close, or transition Jira issues.
- `jira-comment-draft` writes a local markdown draft only; it does not post comments to Jira.
- `jira-comment` previews by default; `jira-comment --execute` only adds a Jira comment and does not change status, fields, assignee, attachments, source code, git state, or PRs.
- `retry-prompt` and `manual-result` generate local artifacts only; they do not call Copilot or Jira.
- Generated Copilot instructions may ask whether you want Copilot to commit and push after completing the workflow, but commit/push is never automatic and requires explicit approval inside Copilot CLI.
- Copilot must not push main/master, force push, commit `.ai/` or `.ai_memory/`, or update Jira.
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
