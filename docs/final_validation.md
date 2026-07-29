# Final Validation

Run from the target repository root after installing bugpilot:

```powershell
python -m pip install -e .
python -m pytest
python -m bugpilot bug HR-12345
python -m bugpilot status HR-12345
python -m bugpilot summarize-results HR-12345
python -m bugpilot memory update HR-12345
python -m bugpilot review-package HR-12345
python -m bugpilot delivery-check HR-12345
python -m bugpilot commit-plan HR-12345
python -m bugpilot push-plan HR-12345
python -m bugpilot clean HR-12345
python -m bugpilot status HR-12345
python -m bugpilot bug HR-12345
python -m bugpilot status HR-12345
python -m bugpilot bug HR-12345 --resume
python -m bugpilot clean HR-12345 --include-memory
python -m bugpilot bug HR-12345 --include-memory
python -m bugpilot bug HR-12345 --allow-mock
python -m bugpilot clean HR-12345
python -m bugpilot bug HR-12345 --fresh --no-mock
python -m bugpilot fetch HR-12345 --allow-mock
python -m bugpilot fetch HR-12345
```

Expected outcomes:

- Tests pass.
- `.ai/HR-12345/` is generated.
- `.ai_memory/bugs/HR-12345.md` is generated or updated.
- `result_summary.md`, `manual_validation.md`, and `final_review_prompt.md` can be generated.
- `commit_plan.md` and `push_plan.md` can be generated.
- `clean` removes only `.ai/HR-12345/`.
- The default `bug` command creates a clean `.ai/HR-12345/` run output.
- `--resume` preserves existing `.ai/HR-12345/` artifacts.
- Memory is preserved unless `--include-memory` is provided.
- Default real Jira mode fails clearly when Jira fetch fails.
- `--allow-mock` works without Jira env vars by using clearly marked mock fallback.
- No automatic agent invocation occurs.
- No automatic Jira write, commit, push, merge, or PR creation occurs.
