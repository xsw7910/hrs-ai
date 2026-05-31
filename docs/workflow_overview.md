# Workflow Overview

```text
Jira Issue
  |
  v
hrs-ai fetch / parse / keywords
  |
  v
Code Search + Memory Search + Git Context
  |
  v
bug_context.md
  |
  v
copilot_task.md + copilot_handoff.md + copilot_team_instructions.md
  |
  v
Copilot CLI manual handoff
  |
  v
bug_analysis.md / fix_summary.md / test_result.md / diff_summary.md / review_notes.md
  |
  v
summarize-results
  |
  v
memory update
  |
  v
review-package
  |
  v
delivery-check / commit-plan / push-plan
```

## Stages

### Jira Issue
The workflow starts from a Jira issue key such as `HR-12345`. If Jira is not configured or fetch fails, the prototype can continue with clearly marked mock/demo data.

### Fetch, Parse, Keywords
hrs-ai collects Jira content, converts Jira Cloud ADF descriptions/comments into readable Markdown, writes summary files, and extracts high-value and normal keywords for search. Jira integration remains read-only. The recommended real Jira path is `hrs-ai bug REAL-ISSUE --fresh --no-mock`. Use `hrs-ai jira-validate REAL-ISSUE` to validate Jira field mapping before running the full workflow — it writes `jira_summary.md`, `jira_parsed.md`, and `jira_field_report.md` without running code search or generating Copilot tasks.

### Code Search, Memory Search, Git Context
The tool searches source files with ripgrep, ranks related files, assesses search confidence, searches prior issue memory under `.ai_memory`, and captures branch/status/history information with read-only git commands.

### Bug Context
`bug_context.md` combines Jira details, keywords, related files, search quality, snippets, historical issues, and git context into one file for AI-assisted investigation.

### Copilot Task And Handoff
`copilot_task.md` gives Copilot CLI strict instructions, required inputs, search-confidence cautions, safety rules, and expected output files. `copilot_team_instructions.md` gives stable team rules for legacy C++/Qt work. `copilot_handoff.md` is the short instruction a developer can paste into Copilot CLI.

### Copilot CLI Manual Handoff
The developer runs Copilot CLI manually from the target repo root. hrs-ai does not invoke Copilot automatically.

### Result Files
After Copilot completes the work, it should write `bug_analysis.md`, `fix_summary.md`, `test_result.md`, `diff_summary.md`, and `review_notes.md` under `.ai/<issue>/`.

### Summarize Results
`summarize-results` creates `result_summary.md` and `manual_validation.md` from the Copilot result files.

### Memory Update
`memory update` records the final result in `.ai_memory/bugs/<issue>.md` so future similar issues can reuse the investigation.

### Review Package
`review-package` creates a final review prompt for an AI or human reviewer to inspect the current git diff and result package.

### Delivery Planning
`delivery-check`, `commit-plan`, and `push-plan` help prepare manual delivery. They do not commit, push, merge, or create PRs.
