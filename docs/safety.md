# Safety

bugpilot is designed as a prepare-only and planning tool. The developer remains in control of source changes and delivery.

## Rules
- bugpilot does not modify product source code.
- bugpilot does not update Jira.
- bugpilot Jira access is read-only.
- bugpilot does not comment on, assign, close, or transition Jira issues.
- `jira-comment-draft` generates a local markdown draft only; it does not post to Jira.
- `jira-comment` previews by default and posts only when `--execute` is explicitly provided.
- `summarize-results` does not post to Jira by default. It posts one analysis comment only when opted in — either `--jira-comment` on the command, or the environment variable `HRS_AI_AUTO_JIRA_COMMENT` set to a truthy value. `--no-jira-comment` always wins. This is intended so Jira notifies watchers by email once the fix results are ready, before the developer decides whether to commit.
- Auto-posting from `summarize-results` adds exactly one Jira comment (same scope limits as `jira-comment --execute`); a Jira/network failure is non-fatal and never fails `summarize-results`.
- `jira-comment --execute` only adds one Jira comment; it does not update fields, transition status, assign issues, upload attachments, download attachments, call Copilot, or run git commands.
- `notify` previews by default (writes `.ai/<issue>/email_draft.md` and a portable `notification.eml`) and sends only when `--execute` is explicitly provided.
- Automatic sending uses Microsoft Graph when configured, otherwise SMTP; if neither is configured, `notify`/`commit-plan` still succeed and report that no email was sent, and the `.eml` can be sent manually via `scripts/send-via-outlook.ps1` (Outlook).
- `commit-plan` sends the notification email at the commit gate only when a transport is configured through the environment; `--no-email` suppresses it.
- The notification email contains only the fix summary (Jira item, original problem, root cause, changes made) assembled from local artifacts, is sanitized to redact secret-like values, and is sent only to `HRS_AI_EMAIL_TO`.
- SMTP passwords and Graph client secrets are read from environment variables only; bugpilot never hardcodes, logs, or persists them, and error messages never include the secret.
- Sending the notification email does not modify source code, Jira, or git state.
- `retry-prompt` and `manual-result` generate local markdown artifacts only.
- `retry-prompt` does not call Copilot; the developer runs Copilot manually.
- `manual-result` does not inspect or modify product source code.
- Generated Copilot instructions may offer optional assisted delivery, but Copilot must ask for explicit approval before any commit or push.
- The generated `copilot_task.md` instructs Copilot/Claude to post one Jira status comment (via `bugpilot jira-comment --execute`) after writing the result files and before commit, so watchers are notified while the developer still controls the commit. Pass `--no-jira-comment` to `bugpilot bug` (or `copilot-task` / `prompt`) to omit that instruction entirely; the choice is recorded per issue and survives `--resume`.
- Copilot must never push main/master, force push, commit `.ai/` or `.ai_memory/`, transition Jira, assign Jira, or change Jira fields. The single status comment above is the only permitted Jira write.
- bugpilot does not download Jira attachments; it records attachment metadata only.
- bugpilot does not create pull requests.
- bugpilot does not merge.
- bugpilot does not run `git add`.
- bugpilot does not run `git commit`.
- bugpilot does not run `git push`.
- Commit and push execute commands are placeholders only in this prototype.
- Generated artifacts live under `.ai` and `.ai_memory`.
- The developer reviews context, runs Copilot CLI manually, validates changes, and performs delivery actions manually.
- `bugpilot clean <ISSUE>` deletes only `.ai/<issue>/`.
- `bugpilot clean <ISSUE> --include-memory` also deletes only `.ai_memory/bugs/<issue>.md`.
- `bugpilot bug <ISSUE>` performs the same scoped cleanup before running the prepare-only workflow.
- `bugpilot bug <ISSUE> --resume` preserves existing `.ai/<issue>/` artifacts.
- `bugpilot bug <ISSUE>` is prepare-only unless `--claude` or `--copilot` is passed; those flags launch that agent interactively to complete the workflow, and the agent stops at the commit gate. Agent-generated code must be reviewed before commit.
- Mock/demo Jira fallback is disabled by default.
- `--allow-mock` explicitly enables mock/demo fallback for demos and testing.
- `--no-mock` is accepted for compatibility and matches the default real Jira-only behavior.

## Final Safety Summary

- Writing to Jira happens only via `bugpilot jira-comment <ISSUE> --execute`, or via `bugpilot summarize-results <ISSUE>` when explicitly opted in (`--jira-comment` or `HRS_AI_AUTO_JIRA_COMMENT`).
- Both add exactly one Jira comment from the local analysis draft; neither transitions, assigns, or edits fields.
- No other bugpilot command writes Jira, and the opt-in default is off.
- No command transitions Jira issues, assigns issues, updates fields, uploads attachments, or downloads attachments.
- `bugpilot bug` is prepare-only by default and invokes no agent. It launches a coding agent only when the developer explicitly passes `--claude` or `--copilot`; the agent runs interactively in the target repo, and bugpilot itself still never commits or pushes.
- bugpilot does not run `git add`, `git commit`, `git push`, merge, or PR creation.
- The only outbound network actions are the read-only Jira fetch, `jira-comment --execute` (one comment), and the notification email over SMTP or Microsoft Graph (`notify --execute` or a configured `commit-plan`). The email is sent only to the configured internal recipients and carries no credentials.

## Generated Artifact Scope
bugpilot writes generated workflow files to:

```text
.ai/<issue>/
.ai_memory/bugs/<issue>.md
```

These paths are relative to the current working directory, which should be the target product repository root.

Clean and fresh-run commands validate issue keys and are scoped to those generated artifact paths. They do not delete product source code.

## Manual Handoff
Copilot CLI should be run from the target product repository root. The generated `copilot_task.md` and `copilot_team_instructions.md` instruct Copilot to avoid destructive git commands, avoid unrelated refactoring, preserve legacy C++/Qt patterns, and generate result files before delivery planning.

## Jira Mock Fallback
When mock fallback is used, generated Jira artifacts are clearly marked as mock/demo fallback. For real Jira-only usage, run:

```powershell
bugpilot bug HR-12345
```

For demo/testing fallback, run:

```powershell
bugpilot bug HR-12345 --allow-mock
```
