# Final Workflow Checklist

Use this checklist before and after a real end-to-end hrs-ai workflow.

## A. Before Running

- [ ] You are in the target product repo root.
- [ ] `hrs-ai doctor` passes or any warnings are understood.
- [ ] Jira environment variables are present.
- [ ] Working tree state is understood.
- [ ] Issue key is confirmed.

## B. After `hrs-ai bug`

- [ ] `jira_summary.md` shows `Data Source` as `jira`.
- [ ] `Mock/demo Jira data` is `no`.
- [ ] `jira_summary.md` is readable.
- [ ] `jira_parsed.md` is useful.
- [ ] `code_search.md` references product code.
- [ ] `search_quality.json` has been reviewed.

## C. Before Copilot

- [ ] Current branch is not `main` or `master`.
- [ ] `copilot_task.md` has been reviewed.
- [ ] `copilot_team_instructions.md` has been reviewed.
- [ ] Search confidence is understood.

## C2. Retry Or Manual Fix

- [ ] If retrying Copilot, `user_feedback.md` describes what failed or needs correction.
- [ ] If retrying Copilot, `copilot_retry_prompt.md` has been generated and reviewed.
- [ ] If the developer fixed the issue manually, `manual-result` templates have been filled in.
- [ ] Existing result files were not overwritten unless `--overwrite` was intentional.

## D. Before `jira-comment --execute`

- [ ] `jira_comment_draft.md` has been reviewed.
- [ ] Draft contains no secrets or tokens.
- [ ] Draft contains no false test claims.
- [ ] Draft contains no attachment-content claims.
- [ ] Draft contains no private local paths if those should not be shared.
- [ ] Preview command has been run:

```powershell
hrs-ai jira-comment HR-26307
```

## E. After `jira-comment --execute`

- [ ] Only one comment was added.
- [ ] Jira status did not change.
- [ ] Jira fields did not change.
- [ ] Jira assignee did not change.
- [ ] Result artifacts were saved:

```text
.ai/HR-26307/jira_comment_post_result.json
.ai/HR-26307/jira_comment_post_summary.md
```
