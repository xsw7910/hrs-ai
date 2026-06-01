# Safety

hrs-ai is designed as a prepare-only and planning tool. The developer remains in control of source changes and delivery.

## Rules
- hrs-ai does not modify product source code.
- hrs-ai does not update Jira.
- hrs-ai Jira access is read-only.
- hrs-ai does not comment on, assign, close, or transition Jira issues.
- hrs-ai does not download Jira attachments; it records attachment metadata only.
- hrs-ai does not create pull requests.
- hrs-ai does not merge.
- hrs-ai does not run `git add`.
- hrs-ai does not run `git commit`.
- hrs-ai does not run `git push`.
- Commit and push execute commands are placeholders only in this prototype.
- Generated artifacts live under `.ai` and `.ai_memory`.
- The developer reviews context, runs Copilot CLI manually, validates changes, and performs delivery actions manually.
- `hrs-ai clean <ISSUE>` deletes only `.ai/<issue>/`.
- `hrs-ai clean <ISSUE> --include-memory` also deletes only `.ai_memory/bugs/<issue>.md`.
- `hrs-ai bug <ISSUE>` performs the same scoped cleanup before running the prepare-only workflow.
- `hrs-ai bug <ISSUE> --resume` preserves existing `.ai/<issue>/` artifacts.
- Mock/demo Jira fallback is disabled by default.
- `--allow-mock` explicitly enables mock/demo fallback for demos and testing.
- `--no-mock` is accepted for compatibility and matches the default real Jira-only behavior.

## Generated Artifact Scope
hrs-ai writes generated workflow files to:

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
hrs-ai bug HR-12345
```

For demo/testing fallback, run:

```powershell
hrs-ai bug HR-12345 --allow-mock
```
