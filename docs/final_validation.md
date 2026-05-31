# Final Validation

Run from the target repository root after installing hrs-ai:

```powershell
python -m pip install -e .
python -m pytest
python -m hrs_ai bug HR-12345
python -m hrs_ai status HR-12345
python -m hrs_ai summarize-results HR-12345
python -m hrs_ai memory update HR-12345
python -m hrs_ai review-package HR-12345
python -m hrs_ai delivery-check HR-12345
python -m hrs_ai commit-plan HR-12345
python -m hrs_ai push-plan HR-12345
python -m hrs_ai clean HR-12345
python -m hrs_ai status HR-12345
python -m hrs_ai bug HR-12345 --fresh
python -m hrs_ai status HR-12345
python -m hrs_ai clean HR-12345 --include-memory
python -m hrs_ai bug HR-12345 --fresh --include-memory
python -m hrs_ai bug HR-12345 --fresh --allow-mock
python -m hrs_ai clean HR-12345
python -m hrs_ai bug HR-12345 --no-mock
python -m hrs_ai fetch HR-12345 --allow-mock
python -m hrs_ai fetch HR-12345 --no-mock
```

Expected outcomes:

- Tests pass.
- `.ai/HR-12345/` is generated.
- `.ai_memory/bugs/HR-12345.md` is generated or updated.
- `result_summary.md`, `manual_validation.md`, and `final_review_prompt.md` can be generated.
- `commit_plan.md` and `push_plan.md` can be generated.
- `clean` removes only `.ai/HR-12345/`.
- `--fresh` creates a clean `.ai/HR-12345/` run output.
- Memory is preserved unless `--include-memory` is provided.
- Default/demo Jira mode still works without Jira env vars by using clearly marked mock fallback.
- `--no-mock` fails clearly when Jira fetch fails.
- No automatic Copilot invocation occurs.
- No automatic Jira write, commit, push, merge, or PR creation occurs.
