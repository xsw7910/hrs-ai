# Real End-to-End Workflow

This workflow is for a real Jira-backed trial from the target product repository root. It keeps hrs-ai as the deterministic context and workflow tool, while Copilot CLI remains the manually launched coding agent.

## Step 1: Run From Target Product Repo Root

```powershell
cd C:\path\to\your\product\repo
```

Generated `.ai` and `.ai_memory` files are written relative to this directory.

## Step 2: Check Environment

```powershell
hrs-ai doctor
```

Confirm Python, git, ripgrep, Jira environment variables, and Copilot CLI availability.

## Step 3: Validate Jira

```powershell
hrs-ai jira-validate HR-26307
```

This validates real Jira field mapping and generates Jira summary/parsing diagnostics without running code search or Copilot task generation.

## Step 4: Prepare Workflow Package

```powershell
hrs-ai bug HR-26307
```

Real Jira is the default. Mock fallback requires `--allow-mock`. The `bug` command is fresh by default; use `--resume` only when continuing existing artifacts.

## Step 5: Inspect Generated Context

Review the generated files:

```text
.ai/HR-26307/jira_summary.md
.ai/HR-26307/jira_parsed.md
.ai/HR-26307/code_search.md
.ai/HR-26307/search_quality.json
.ai/HR-26307/bug_context.md
.ai/HR-26307/copilot_task.md
```

Confirm the data source is Jira, the parsed details are useful, and search confidence makes sense before handing work to Copilot.

## Step 6: Optional Copilot CLI Handoff

Open Copilot CLI from the same target repo root:

```powershell
copilot
```

Paste:

```text
Read .ai/HR-26307/copilot_task.md and complete the workflow.
```

Copilot should generate:

```text
.ai/HR-26307/bug_analysis.md
.ai/HR-26307/fix_summary.md
.ai/HR-26307/test_result.md
.ai/HR-26307/diff_summary.md
.ai/HR-26307/review_notes.md
```

## Step 7: Result Processing

If Copilot needs another attempt, add feedback and generate a retry prompt:

```powershell
hrs-ai retry-prompt HR-26307
```

Edit:

```text
.ai/HR-26307/user_feedback.md
```

Then run Copilot manually from the target repo root and paste:

```text
Read .ai/HR-26307/copilot_retry_prompt.md and continue the workflow.
```

If the developer fixed the issue manually, generate result templates instead:

```powershell
hrs-ai manual-result HR-26307
```

Existing result files are preserved unless `--overwrite` is explicitly used.

```powershell
hrs-ai check-results HR-26307
hrs-ai summarize-results HR-26307
hrs-ai memory update HR-26307
hrs-ai review-package HR-26307
```

Review generated result and validation files before preparing any Jira comment.

## Step 8: Jira Comment Draft

```powershell
hrs-ai jira-comment-draft HR-26307
```

This creates a local draft only:

```text
.ai/HR-26307/jira_comment_draft.md
```

## Step 9: Preview Jira Comment

```powershell
hrs-ai jira-comment HR-26307
```

Preview mode does not call Jira and does not write a comment.

## Step 10: Execute Jira Comment Write-Back

Only after reviewing the draft:

```powershell
hrs-ai jira-comment HR-26307 --execute
```

This posts exactly one Jira comment from the local draft. It does not update status, assignee, priority, fields, or attachments.

## Step 11: Confirm Jira Safety

Confirm manually:

- Exactly one comment was added.
- Status is unchanged.
- Assignee is unchanged.
- Priority is unchanged.
- Fields are unchanged.
- No attachments were uploaded or downloaded.
