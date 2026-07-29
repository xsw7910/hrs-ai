# bugpilot

## What It Is
bugpilot is a prototype CLI for an AI-assisted Jira bug workflow using GitHub Copilot CLI. It builds a deterministic development package from a Jira issue, local code search, shared memory, and git context so a developer can hand Copilot a clearer task.

## Why It Exists
AI-assisted bug work often starts with scattered context and ends with useful investigation notes disappearing into chat history. bugpilot is intended to make that work repeatable.

- AI usage is currently scattered across tools and conversations.
- Developers manually copy Jira context into AI tools.
- Useful AI investigation is lost after the fix is done.
- Similar bugs are repeatedly analyzed from scratch.
- Legacy C++/Qt repositories need better context before AI tools can help safely.

## How It Works
```text
Jira issue -> code search -> memory search -> bug_context.md -> Copilot CLI task -> result summary -> memory update -> delivery plan
```

bugpilot prepares files under `.ai/<issue>/` and shared memory under `.ai_memory/bugs/<issue>.md`. Jira Cloud ADF descriptions and comments are converted into readable Markdown for the issue package, and Jira attachment metadata is surfaced without downloading attachment content. Code search includes a confidence assessment so low-confidence false positives are visible before Copilot edits anything. Copilot CLI remains a manual handoff step, with reusable team instructions for legacy C++/Qt work.

## Installation

**Developers (working on bugpilot itself):** editable install, so source edits are live.
```powershell
python -m pip install -e .
```

**End users (recommended):** install Python 3.10+ (e.g. `winget install -e --id
Python.Python.3.12 --scope user`, no admin), then run the installer. The
distribution package is:

```text
BugPilot/
  install.cmd            <- double-click this
  installer/
    install.ps1
    bugpilot-<version>-py3-none-any.whl
```

`install.cmd` runs `installer\install.ps1`, which installs bugpilot via pipx (and
can install Python via winget if it's missing), then offers to run `bugpilot setup`.
**Alternative — no Python:** use the standalone `bugpilot.exe` (see **Building &
Distributing the Standalone Executable** below).

## Building & Distributing the Standalone Executable
Package the CLI into one self-contained `bugpilot.exe` (it embeds a Python runtime, so
the target machine needs no Python, pipx, or PATH setup). This is the recommended way to
hand bugpilot to teammates — especially when their only Python is a toolchain one
(e.g. vcpkg), which an editable/pipx install would fragilely depend on.

Build from the repo root, with any Python 3.10+ that has pip:
```powershell
python -m pip install --user pyinstaller
python -m PyInstaller --onefile --name bugpilot --collect-submodules bugpilot --paths . pyi_entry.py
```
Output: `dist\bugpilot.exe` (~9 MB). `pyi_entry.py` is the packaging entry point (a
top-level absolute-import shim, because `bugpilot/__main__.py` uses a package-relative
import that PyInstaller can't use directly). Build artifacts (`dist/`, `build/`, `*.spec`,
`*.whl`) are gitignored.

Distribute: give teammates the single `dist\bugpilot.exe`. They save it (e.g.
`C:\tools\bugpilot\`), optionally add that folder to PATH, then:
```powershell
bugpilot setup        # one-time: Jira email + API token -> %USERPROFILE%\.bugpilot\config.toml
bugpilot HR-12345     # prepare, then launch the agent
```
The first run may trip SmartScreen ("Windows protected your PC") because the exe is
unsigned — choose **More info -> Run anyway**.

Note: the packaged exe can't read `docs/copilot_team_instructions.md` from the repo, so it
uses the built-in fallback team instructions (same content).

## Jira Configuration
For real Jira fetches, set:

```powershell
$env:JIRA_BASE_URL="https://your-company.atlassian.net"
$env:JIRA_EMAIL="you@example.com"
$env:JIRA_TOKEN="your_jira_api_token"
```

The normal workflow uses real Jira only and does not fall back to mock data:

```powershell
bugpilot bug HR-12345
```

Equivalent explicit form:

```powershell
bugpilot bug HR-12345 --fresh --no-mock
```

Demo/testing fallback must be requested explicitly:

```powershell
bugpilot bug HR-12345 --allow-mock
```

When mock fallback is used, `jira_summary.md`, `jira.json`, and `execution.log` clearly mark the data as mock/demo fallback.

## Email Notification Configuration
At the commit gate (`bugpilot commit-plan <ISSUE>`), bugpilot can email you a summary of
the completed fix: the Jira item, the original problem, the root cause, and the changes
made. The email body is assembled from local `result_summary.md` and `jira_summary.md`;
run `bugpilot summarize-results <ISSUE>` first so those artifacts exist.

bugpilot supports two automatic transports plus a manual Outlook option. It picks
**Graph if configured, otherwise SMTP**. `bugpilot doctor` shows `email_configured`
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
$env:HRS_AI_EMAIL_FROM="bugpilot@your-company.com"
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
When no automatic transport is available, `bugpilot notify` still writes a portable
`.ai/<ISSUE>/notification.eml`. To open it as a pre-filled Outlook compose window
(Outlook sends over its own modern-auth channel, so no SMTP/port-25 needed):

```powershell
bugpilot notify HR-12345                       # writes email_draft.md + notification.eml
.\scripts\send-via-outlook.ps1 HR-12345      # opens Outlook; review and click Send
```

### Sending
Sending is opt-in and human-controlled, matching the rest of the workflow:

```powershell
bugpilot notify HR-12345             # preview only: writes email_draft.md + notification.eml, sends nothing
bugpilot notify HR-12345 --execute   # send automatically (Graph if configured, else SMTP)
bugpilot commit-plan HR-12345        # generate commit plan AND send the notification email
bugpilot commit-plan HR-12345 --no-email   # generate commit plan without sending email
```

If no transport is configured, `commit-plan` still succeeds and simply reports that no
email was sent (use Option 3 to send manually). The email body is sanitized to redact
secret-like values before sending, and no secret (SMTP password or Graph client secret)
is ever logged or included in error messages.

## Notify via Jira Comment (no email server needed)
If your tenant blocks SMTP and app registration for Graph is not available, the simplest
way to be notified when a fix is ready is a **Jira comment**: bugpilot posts the analysis
summary to the issue, and Jira emails the issue's watchers/assignee/reporter through its
own notification system. This reuses your existing Jira credentials
(`JIRA_BASE_URL` / `JIRA_EMAIL` / `JIRA_TOKEN`) — no mail server, no Graph, no IT ticket.

Opt in so the comment is posted automatically as soon as the fix results are summarized
(before you decide whether to commit):

```powershell
$env:HRS_AI_AUTO_JIRA_COMMENT="true"   # enable auto-post from summarize-results
bugpilot summarize-results HR-12345       # summarizes results AND posts one Jira comment
```

Per-run control overrides the environment variable:

```powershell
bugpilot summarize-results HR-12345 --jira-comment      # force post this run
bugpilot summarize-results HR-12345 --no-jira-comment   # never post this run
```

Notes:
- You must be **watching** the issue (or be its assignee/reporter) and have Jira email
  notifications enabled to receive the message; that is a Jira-side setting.
- Auto-post adds exactly one comment; it never edits fields, transitions, or assigns.
- If posting fails (e.g., no access to the issue), `summarize-results` still succeeds and
  prints a warning — post manually later with `bugpilot jira-comment <ISSUE> --execute`.
- The comment body is sanitized to redact secret-like values.

## Optional: Let an Agent Complete the Workflow
By default `bugpilot bug` is prepare-only and prints the manual handoff line. You can
instead have it launch a coding agent to read `copilot_task.md` and complete the
workflow (analyze, implement the smallest safe fix, write result files, post one Jira
status comment) — the agent still stops at the commit gate and asks before committing.

```powershell
bugpilot bug HR-12345 --claude     # launch Claude after preparation
bugpilot bug HR-12345 --copilot    # launch Copilot CLI instead
bugpilot bug HR-12345              # no flag: prepare only (default, unchanged)
```

To steer the agent straight to a known fix location (skips broad investigation — much
faster when you already know where the bug is), pass `--hint`:

```powershell
bugpilot bug HR-12345 --claude --hint "Fix in FooWidget.cxx: preserve selection on tab switch"
```

The hint is saved to `.ai/<ISSUE>/developer_hint.md`, injected as a "Developer Hint" section
at the top of `copilot_task.md`, and reused on `--resume`. copilot_task.md also tells the
agent to investigate inline (Read/Grep/Glob) and not spawn background sub-agents.

The agent runs interactively in the current (target) repo so you can watch it work.
Configuration:

```powershell
$env:HRS_AI_CLAUDE_COMMAND="claude"                        # binary to launch
$env:HRS_AI_CLAUDE_ARGS="--permission-mode acceptEdits"    # default: auto-accept file edits
# For a fully unattended run (also skips shell prompts for git / bugpilot):
$env:HRS_AI_CLAUDE_ARGS="--dangerously-skip-permissions"   # understand the risk first
```

With the default `acceptEdits`, the agent applies file edits without prompting but may
still ask before shell commands (e.g., running `bugpilot jira-comment --execute` or git).
`--dangerously-skip-permissions` removes those prompts too, at the cost of unattended
execution — use it only when you trust the task and repo.

Treat all agent-generated code as third-party: **review it before you commit**. bugpilot
never commits or pushes for you; the agent stops and asks at the commit gate.
`bugpilot doctor` reports `claude_available` / `copilot_available`.

## Important: Run From Target Repo Root
The bugpilot source repo can be anywhere. Run `bugpilot` from the target product repository root, because generated `.ai` and `.ai_memory` folders are written relative to the current working directory.

Copilot CLI should also be run from the target product repository root. Do not run the Copilot handoff from the bugpilot tool source directory unless that is the repository you intend to modify.

Example:
```powershell
cd C:\sandbox\target-repo
bugpilot bug HR-12345
```

## Quick Demo
```powershell
bugpilot doctor
bugpilot bug HR-12345
bugpilot status HR-12345
bugpilot clean HR-12345
bugpilot bug HR-12345 --resume
bugpilot copilot-task HR-12345
bugpilot check-results HR-12345
bugpilot summarize-results HR-12345
bugpilot memory update HR-12345
bugpilot review-package HR-12345
bugpilot jira-comment-draft HR-12345
bugpilot jira-comment HR-12345
bugpilot retry-prompt HR-12345
bugpilot manual-result HR-12345
bugpilot delivery-check HR-12345
bugpilot notify HR-12345
bugpilot commit-plan HR-12345
bugpilot push-plan HR-12345
```

## Main Commands
- `bugpilot doctor`: report environment, git, ripgrep, Jira env vars, and Copilot CLI availability.
- `bugpilot copilot-check`: check Copilot and GitHub CLI availability without invoking Copilot.
- `bugpilot fetch <ISSUE>`: fetch real Jira data and fail clearly if Jira is unavailable.
- `bugpilot fetch <ISSUE> --allow-mock`: allow clearly marked mock/demo fallback when Jira fetch fails.
- `bugpilot fetch <ISSUE> --no-mock`: require real Jira data. This is the default.
- `bugpilot parse <ISSUE>`: parse Jira data into a markdown summary.
- `bugpilot keywords <ISSUE>`: extract high-value, normal, and dropped keywords.
- `bugpilot search <ISSUE>`: run ripgrep-based code search and related file ranking.
- `bugpilot memory search <ISSUE or query>`: search shared markdown memory.
- `bugpilot memory add <ISSUE>`: create or refresh a shared memory entry.
- `bugpilot memory update <ISSUE>`: update memory with final result information.
- `bugpilot git-context <ISSUE>`: generate branch, status, and recent file history context.
- `bugpilot context <ISSUE>`: generate enriched `bug_context.md`.
- `bugpilot prompt <ISSUE>`: generate Copilot and review prompt files.
- `bugpilot copilot-task <ISSUE>`: regenerate Copilot task and handoff files from existing context.
- `bugpilot copilot-instructions <ISSUE>`: regenerate `.ai/<issue>/copilot_team_instructions.md` from the reusable team template.
- `bugpilot check-results <ISSUE>`: check whether Copilot result files exist.
- `bugpilot check-results <ISSUE> --strict`: return nonzero if required result files are missing.
- `bugpilot summarize-results <ISSUE>`: generate result summary and manual validation files.
- `bugpilot review-package <ISSUE>`: generate final review prompt.
- `bugpilot jira-comment-draft <ISSUE>`: generate a local, reviewable Jira comment draft from existing bugpilot artifacts.
- `bugpilot jira-comment-draft <ISSUE> --strict`: require Copilot result files before generating the local draft.
- `bugpilot jira-comment <ISSUE>`: preview the local Jira comment draft without posting to Jira.
- `bugpilot jira-comment <ISSUE> --execute`: post exactly one Jira comment from the local draft.
- `bugpilot retry-prompt <ISSUE>`: generate a second-attempt Copilot prompt from local artifacts and developer feedback.
- `bugpilot manual-result <ISSUE>`: create developer manual-fix result templates without overwriting existing result files.
- `bugpilot manual-result <ISSUE> --overwrite`: replace result files with fresh manual-fix templates.
- `bugpilot delivery-check <ISSUE>`: check readiness for manual delivery.
- `bugpilot notify <ISSUE>`: write the post-fix notification (`email_draft.md` + `notification.eml`); add `--execute` to send automatically (Graph if configured, else SMTP).
- `bugpilot commit-plan <ISSUE>`: generate a manual commit plan and email the fix summary at the commit gate (`--no-email` to skip).
- `bugpilot push-plan <ISSUE>`: generate a manual push plan.
- `bugpilot clean <ISSUE>`: remove generated `.ai/<issue>/` workflow artifacts while preserving memory.
- `bugpilot clean <ISSUE> --include-memory`: also remove `.ai_memory/bugs/<issue>.md` for that issue only.
- `bugpilot status <ISSUE>`: show workflow status and generated files.
- `bugpilot bug <ISSUE>`: run a fresh prepare-only workflow end to end with real Jira required and mock fallback disabled.
- `bugpilot bug <ISSUE> --fresh`: same as the default; kept for compatibility.
- `bugpilot bug <ISSUE> --resume`: preserve existing `.ai/<issue>/` artifacts and continue an existing workflow.
- `bugpilot bug <ISSUE> --include-memory`: clean `.ai/<issue>/` and that issue's memory entry first, then rerun.
- `bugpilot bug <ISSUE> --allow-mock`: explicitly allow mock/demo Jira fallback.
- `bugpilot bug <ISSUE> --no-mock`: require real Jira data and stop if Jira fetch fails. This is the default.
- `bugpilot jira-validate <ISSUE>`: validate Jira field mapping for a real issue (no code search, no Copilot task). Generates `jira_summary.md`, `jira_parsed.md`, and `jira_field_report.md`.

## Recommended Real Workflow
```powershell
bugpilot doctor
bugpilot jira-validate HR-26307
bugpilot bug HR-26307
bugpilot jira-comment-draft HR-26307
bugpilot jira-comment HR-26307
bugpilot jira-comment HR-26307 --execute
```

Run these from the target product repo root. Real Jira is the default, and mock fallback requires `--allow-mock`. `bugpilot bug <ISSUE>` is fresh by default; use `--resume` only when continuing existing artifacts. `bugpilot jira-comment <ISSUE>` previews without writing Jira, and `--execute` is required for Jira comment write-back.

## Safety Rules
- bugpilot does not automatically modify product source code.
- bugpilot does not automatically invoke Copilot CLI.
- bugpilot does not update Jira.
- Jira integration is read-only; bugpilot converts fetched Jira content to Markdown but does not comment, assign, close, or transition Jira issues.
- `jira-comment-draft` writes a local markdown draft only; it does not post comments to Jira.
- `jira-comment` previews by default; `jira-comment --execute` only adds a Jira comment and does not change status, fields, assignee, attachments, source code, git state, or PRs.
- `retry-prompt` and `manual-result` generate local artifacts only; they do not call Copilot or Jira.
- Generated Copilot instructions may ask whether you want Copilot to commit and push after completing the workflow, but commit/push is never automatic and requires explicit approval inside Copilot CLI.
- Copilot must not push main/master, force push, commit `.ai/` or `.ai_memory/`, or update Jira.
- bugpilot does not create pull requests.
- bugpilot does not merge.
- bugpilot does not run `git add`, `git commit`, or `git push`.
- `commit-plan` and `push-plan` only generate markdown plans.
- Placeholder commit/push execute commands do not perform real delivery actions in this prototype.
- `bugpilot commit <ISSUE> --execute` and `bugpilot push <ISSUE> --execute` are disabled placeholders only.
- `clean` and `--fresh` remove only generated bugpilot artifacts for the requested issue.
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
