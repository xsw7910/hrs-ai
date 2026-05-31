from __future__ import annotations

import json
from subprocess import CompletedProcess

from hrs_ai.cli import main
from hrs_ai.core.context import _code_search_summary
from hrs_ai.core.git_ops import branch_name
from hrs_ai.core.keywords import extract_keywords
from hrs_ai.core.memory import build_memory_entry, search_memory
from hrs_ai.core.search import INCLUDE_GLOBS, run_code_search
from hrs_ai.core.workflow import git_context_step, run_bug_workflow


def test_output_directory_creation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_bug_workflow(tmp_path, "HR-12345")

    assert (tmp_path / ".ai" / "HR-12345").is_dir()
    assert (tmp_path / ".ai_memory" / "bugs" / "HR-12345.md").is_file()


def test_branch_name_generation():
    assert branch_name("HR-12345") == "feature/HR-12345-ai-assisted-jira-bug-workflow"
    assert branch_name("HR-1", "Fix stale search!") == "feature/HR-1-fix-stale-search"


def test_workflow_status_json_generation(tmp_path):
    run_bug_workflow(tmp_path, "HR-12345")
    status = json.loads((tmp_path / ".ai" / "HR-12345" / "workflow_status.json").read_text())

    assert status["issue_key"] == "HR-12345"
    assert status["mode"] == "prepare-only"
    assert status["steps"] == {
        "doctor": "pass",
        "fetch": "pass",
        "parse": "pass",
        "keywords": "pass",
        "memory_search": "pass",
        "code_search": "pass",
        "git_context": "pass",
        "context": "pass",
        "prompt": "pass",
        "memory_add": "pass",
        "copilot_fix": "skipped",
        "result_summary": "skipped",
        "manual_validation": "skipped",
        "final_review_prompt": "skipped",
        "memory_update": "skipped",
        "delivery_check": "skipped",
        "commit_plan": "skipped",
        "push_plan": "skipped",
    }
    assert ".ai/HR-12345/copilot_task.md" in status["generated_files"]
    assert ".ai/HR-12345/copilot_handoff.md" in status["generated_files"]
    assert ".ai/HR-12345/code_search.md" in status["generated_files"]
    assert ".ai/HR-12345/related_files.json" in status["generated_files"]
    assert ".ai/HR-12345/memory_search.md" in status["generated_files"]
    assert ".ai/HR-12345/git_context.md" in status["generated_files"]
    assert ".ai_memory/bugs/HR-12345.md" in status["generated_files"]


def test_bug_command_runs_in_temporary_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    exit_code = main(["bug", "HR-12345"])

    assert exit_code == 0
    assert (tmp_path / ".ai" / "HR-12345" / "jira_summary.md").is_file()
    assert (tmp_path / ".ai" / "HR-12345" / "workflow_status.json").is_file()


def test_execution_log_contains_prepare_only_lifecycle(tmp_path, monkeypatch):
    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_TOKEN", raising=False)

    run_bug_workflow(tmp_path, "HR-12345")
    log_text = (tmp_path / ".ai" / "HR-12345" / "execution.log").read_text()

    assert "[START] command: hrs-ai bug HR-12345" in log_text
    assert "[START] doctor" in log_text
    assert "[END] doctor: pass" in log_text
    assert "[START] fetch" in log_text
    assert "[WARN] Using mock/demo Jira data because Jira environment variables are missing." in log_text
    assert "[END] fetch: pass" in log_text
    assert "[START] parse" in log_text
    assert "[END] parse: pass" in log_text
    assert "[START] keywords" in log_text
    assert "[END] keywords: pass" in log_text
    assert "[START] memory_search" in log_text
    assert "[END] memory_search: pass" in log_text
    assert "[START] code_search" in log_text
    assert "[END] code_search: pass" in log_text
    assert "[START] git_context" in log_text
    assert "[END] git_context: pass" in log_text
    assert "[START] context" in log_text
    assert "[END] context: pass" in log_text
    assert "[START] prompt" in log_text
    assert "[END] prompt: pass" in log_text
    assert "[START] memory_add" in log_text
    assert "[END] memory_add: pass" in log_text
    assert "[SKIP] copilot_fix: prepare-only mode" in log_text
    assert "[GENERATED] .ai/HR-12345/code_search.md" in log_text
    assert "[GENERATED] .ai/HR-12345/related_files.json" in log_text
    assert "[GENERATED] .ai/HR-12345/memory_search.md" in log_text
    assert "[GENERATED] .ai/HR-12345/git_context.md" in log_text
    assert "[GENERATED] .ai/HR-12345/copilot_task.md" in log_text
    assert "[GENERATED] .ai/HR-12345/copilot_handoff.md" in log_text
    assert "[GENERATED] .ai_memory/bugs/HR-12345.md" in log_text
    assert "[END] workflow: pass" in log_text


def test_copilot_task_references_code_search(tmp_path):
    run_bug_workflow(tmp_path, "HR-12345")
    task = (tmp_path / ".ai" / "HR-12345" / "copilot_task.md").read_text()

    assert "Run Copilot CLI from the target repo root" in task
    assert "Do not run Copilot CLI from the hrs-ai tool source directory" in task
    assert ".ai/HR-12345/` files are relative to the target repo root" in task
    assert "feature/HR-12345-ai-assisted-jira-bug-workflow" in task
    assert "Check the current branch before editing" in task
    assert "Create or switch to the feature branch before editing files" in task
    assert ".ai/HR-12345/bug_context.md" in task
    assert ".ai/HR-12345/code_search.md" in task
    assert ".ai/HR-12345/related_files.json" in task
    assert ".ai/HR-12345/memory_search.md" in task
    assert ".ai/HR-12345/git_context.md" in task
    assert "Do not edit code until after reviewing context and related files" in task
    assert "matched line numbers" in task
    assert ".ai/HR-12345/bug_analysis.md" in task
    assert ".ai/HR-12345/fix_summary.md" in task
    assert ".ai/HR-12345/test_result.md" in task
    assert ".ai/HR-12345/diff_summary.md" in task
    assert ".ai/HR-12345/review_notes.md" in task
    assert "git reset --hard" in task
    assert "git clean -fd" in task
    assert "Do not push unless explicitly instructed" in task
    assert "Do not update Jira" in task


def test_keyword_schema_matches_phase_2_plan():
    keywords = extract_keywords("EmployeeSearch stale filter query cache actual expected cache")

    assert set(keywords) == {"high_value_keywords", "normal_keywords", "dropped_keywords"}
    assert isinstance(keywords["high_value_keywords"], list)
    assert isinstance(keywords["normal_keywords"], list)
    assert isinstance(keywords["dropped_keywords"], list)


def test_search_command_generates_code_search_and_related_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "employee_search.py"
    source.write_text("class EmployeeSearch:\n    def refresh_filter_cache(self):\n        return 'filter cache'\n")
    issue_dir = tmp_path / ".ai" / "HR-12345"
    issue_dir.mkdir(parents=True)
    (issue_dir / "extracted_keywords.json").write_text(
        json.dumps(
            {
                "high_value_keywords": ["EmployeeSearch", "filter"],
                "normal_keywords": ["cache"],
                "dropped_keywords": [],
            }
        )
    )

    assert main(["search", "HR-12345"]) == 0
    related = json.loads((issue_dir / "related_files.json").read_text())

    assert (issue_dir / "code_search.md").is_file()
    assert related[0]["file"] == "employee_search.py"
    assert related[0]["score"] >= 3


def test_rg_unavailable_fallback_generates_empty_results(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "")
    markdown, related = run_code_search(
        tmp_path,
        "HR-12345",
        {"high_value_keywords": ["EmployeeSearch"], "normal_keywords": [], "dropped_keywords": []},
    )

    assert related == []
    assert "rg is unavailable" in markdown


def test_memory_search_with_no_memory_entries_writes_no_results(tmp_path):
    issue_dir = tmp_path / ".ai" / "HR-12345"
    issue_dir.mkdir(parents=True)
    (issue_dir / "extracted_keywords.json").write_text(
        json.dumps({"high_value_keywords": ["EmployeeSearch"], "normal_keywords": [], "dropped_keywords": []})
    )

    issue_key, markdown, results = search_memory(tmp_path, "HR-12345")

    assert issue_key == "HR-12345"
    assert results == []
    assert "No similar memory entries found." in markdown
    assert "No similar memory entries found." in (issue_dir / "memory_search.md").read_text()


def test_git_context_outside_git_repo_does_not_crash(tmp_path):
    git_context_step(tmp_path, "HR-12345")

    text = (tmp_path / ".ai" / "HR-12345" / "git_context.md").read_text()
    assert "Current directory is not inside a git repository" in text


def test_bug_workflow_generates_phase_2_files_and_enriched_context(tmp_path):
    run_bug_workflow(tmp_path, "HR-12345")
    issue_dir = tmp_path / ".ai" / "HR-12345"
    context = (issue_dir / "bug_context.md").read_text()

    assert (issue_dir / "code_search.md").is_file()
    assert (issue_dir / "related_files.json").is_file()
    assert (issue_dir / "memory_search.md").is_file()
    assert (issue_dir / "git_context.md").is_file()
    assert "## Code Search Summary" in context
    assert "## Similar Historical Issues" in context
    assert "## Git Context" in context
    assert (issue_dir / "copilot_handoff.md").is_file()


def test_rg_subprocess_uses_utf8_replace_and_include_globs(tmp_path, monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return CompletedProcess(args, 0, stdout="employee_search.py:1:EmployeeSearch cache\n", stderr="")

    monkeypatch.setattr("hrs_ai.core.search.command_available", lambda command: command == "rg")
    monkeypatch.setattr("hrs_ai.core.search.subprocess.run", fake_run)

    markdown, related = run_code_search(
        tmp_path,
        "HR-12345",
        {"high_value_keywords": ["EmployeeSearch"], "normal_keywords": [], "dropped_keywords": []},
    )

    args, kwargs = calls[0]
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["errors"] == "replace"
    assert "text" not in kwargs
    for glob in INCLUDE_GLOBS:
        assert ["-g", glob] in [args[index : index + 2] for index in range(len(args) - 1)]
    assert related[0]["file"] == "employee_search.py"
    assert "EmployeeSearch cache" in markdown


def test_git_run_command_uses_utf8_replace(monkeypatch, tmp_path):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(kwargs)
        return CompletedProcess(args, 0, stdout="clean\n")

    monkeypatch.setattr("hrs_ai.core.git_ops.subprocess.run", fake_run)

    from hrs_ai.core.git_ops import run_command

    code, output = run_command(["git", "status", "--short"], tmp_path)

    assert code == 0
    assert output == "clean"
    assert calls[0]["encoding"] == "utf-8"
    assert calls[0]["errors"] == "replace"
    assert "text" not in calls[0]


def test_free_text_memory_search_prints_markdown(tmp_path, monkeypatch, capsys):
    memory_dir = tmp_path / ".ai_memory" / "bugs"
    memory_dir.mkdir(parents=True)
    (memory_dir / "HR-1.md").write_text("# HR-1\n\nEmployeeSearch cache bug\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["memory", "search", "EmployeeSearch cache"]) == 0
    output = capsys.readouterr().out

    assert "# Memory Search: EmployeeSearch cache" in output
    assert ".ai_memory/bugs/HR-1.md" in output


def test_memory_entry_uses_prepare_only_phase_2_wording():
    entry = build_memory_entry("HR-12345", {"summary": "Demo", "is_mock": True}, ".ai/HR-12345/bug_context.md")

    assert "Phase 1" not in entry
    assert "Prototype prepare-only workflow" in entry
    assert "## Code Search Summary" in entry
    assert "## Related Files" in entry


def test_context_code_search_summary_prefers_related_files_over_warnings():
    markdown = """# Code Search: HR-12345

## Warnings

- warning first

## Top Related Files

- `src/EmployeeSearch.cpp` score=10 matches=2 keywords=EmployeeSearch
"""

    summary = _code_search_summary(markdown)

    assert summary.startswith("- `src/EmployeeSearch.cpp`")
    assert "Warnings:" in summary


def test_copilot_handoff_is_generated(tmp_path):
    run_bug_workflow(tmp_path, "HR-12345")
    handoff = (tmp_path / ".ai" / "HR-12345" / "copilot_handoff.md").read_text()

    assert "Read `.ai/HR-12345/copilot_task.md` and complete the workflow." in handoff
    assert "Run Copilot CLI from the target repo root" in handoff
    assert "Do not work directly on main/master" in handoff
    assert "Do not push or merge" in handoff


def test_copilot_task_command_regenerates_task_files(tmp_path, monkeypatch):
    issue_dir = tmp_path / ".ai" / "HR-12345"
    issue_dir.mkdir(parents=True)
    (issue_dir / "bug_context.md").write_text("# Bug Context\n", encoding="utf-8")
    (issue_dir / "copilot_task.md").write_text("old", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["copilot-task", "HR-12345"]) == 0

    assert "Copilot CLI Task" in (issue_dir / "copilot_task.md").read_text()
    assert (issue_dir / "copilot_handoff.md").is_file()
    assert (issue_dir / "copilot_fix_prompt.md").is_file()
    assert (issue_dir / "review_prompt.md").is_file()


def test_copilot_task_command_reports_missing_bug_context(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    assert main(["copilot-task", "HR-12345"]) == 1
    error = capsys.readouterr().err

    assert "Missing .ai/HR-12345/bug_context.md." in error
    assert "Run: hrs-ai bug HR-12345" in error


def test_check_results_reports_missing_files(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    assert main(["check-results", "HR-12345"]) == 0
    output = capsys.readouterr().out

    assert "WARN: missing 5 Copilot result file(s)." in output
    assert ".ai/HR-12345/bug_analysis.md" in output
    assert ".ai/HR-12345/review_notes.md" in output


def test_check_results_strict_missing_files_exits_nonzero(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    assert main(["check-results", "HR-12345", "--strict"]) == 1
    output = capsys.readouterr().out

    assert "WARN: missing 5 Copilot result file(s)." in output


def test_check_results_passes_when_all_files_exist(tmp_path, monkeypatch, capsys):
    issue_dir = tmp_path / ".ai" / "HR-12345"
    issue_dir.mkdir(parents=True)
    for file_name in ["bug_analysis.md", "fix_summary.md", "test_result.md", "diff_summary.md", "review_notes.md"]:
        (issue_dir / file_name).write_text("done", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["check-results", "HR-12345"]) == 0

    assert "PASS: all Copilot result files exist." in capsys.readouterr().out


def test_check_results_strict_passes_when_all_files_exist(tmp_path, monkeypatch, capsys):
    issue_dir = tmp_path / ".ai" / "HR-12345"
    issue_dir.mkdir(parents=True)
    for file_name in ["bug_analysis.md", "fix_summary.md", "test_result.md", "diff_summary.md", "review_notes.md"]:
        (issue_dir / file_name).write_text("done", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["check-results", "HR-12345", "--strict"]) == 0

    assert "PASS: all Copilot result files exist." in capsys.readouterr().out


def test_bug_copilot_fix_remains_manual_and_safe(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    assert main(["bug", "HR-12345", "--copilot-fix"]) == 0
    output = capsys.readouterr().out
    log_text = (tmp_path / ".ai" / "HR-12345" / "execution.log").read_text()
    status = json.loads((tmp_path / ".ai" / "HR-12345" / "workflow_status.json").read_text())

    assert "Copilot automatic invocation is not enabled." in output
    assert "Read .ai/HR-12345/copilot_task.md and complete the workflow." in output
    assert "[INFO] Copilot automatic invocation is not enabled, using manual handoff" in log_text
    assert "[INFO] Next Copilot CLI instruction: Read .ai/HR-12345/copilot_task.md and complete the workflow." in log_text
    assert status["steps"]["copilot_fix"] == "skipped"


def test_summarize_results_generates_summary_and_manual_validation(tmp_path, monkeypatch):
    issue_dir = tmp_path / ".ai" / "HR-12345"
    issue_dir.mkdir(parents=True)
    (issue_dir / "bug_analysis.md").write_text("Root cause: stale cache", encoding="utf-8")
    (issue_dir / "fix_summary.md").write_text("Cleared cache on filter change", encoding="utf-8")
    (issue_dir / "related_files.json").write_text(json.dumps([{"file": "src/EmployeeSearch.cpp"}]), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["summarize-results", "HR-12345"]) == 0
    summary = (issue_dir / "result_summary.md").read_text()
    manual = (issue_dir / "manual_validation.md").read_text()
    status = json.loads((issue_dir / "workflow_status.json").read_text())

    assert "- bug_analysis.md: present" in summary
    assert "- test_result.md: missing" in summary
    assert "Root cause: stale cache" in summary
    assert "Cleared cache on filter change" in summary
    assert "## Suggested Validation Steps" in manual
    assert "- src/EmployeeSearch.cpp" in manual
    assert status["steps"]["result_summary"] == "pass"
    assert status["steps"]["manual_validation"] == "pass"


def test_memory_update_replaces_final_result_section(tmp_path, monkeypatch):
    issue_dir = tmp_path / ".ai" / "HR-12345"
    memory_dir = tmp_path / ".ai_memory" / "bugs"
    issue_dir.mkdir(parents=True)
    memory_dir.mkdir(parents=True)
    (issue_dir / "result_summary.md").write_text(
        "# Result Summary\n\n"
        "## Root Cause Summary\nOld cache key\n\n"
        "## Fix Summary\nNew query key\n\n"
        "## Test Summary\nFocused tests passed\n\n"
        "## Review Notes\nLooks safe\n",
        encoding="utf-8",
    )
    (memory_dir / "HR-12345.md").write_text(
        "# HR-12345 AI Bug Workflow Memory\n\n"
        "## Jira Summary\n\nPreserve me.\n\n"
        "## Code Search Summary\n\nPreserve code search.\n\n"
        "## Related Files\n\nPreserve related files.\n\n"
        "## Final Result\n\nold final\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    assert main(["memory", "update", "HR-12345"]) == 0
    memory = (memory_dir / "HR-12345.md").read_text()
    status = json.loads((issue_dir / "workflow_status.json").read_text())

    assert "Preserve me." in memory
    assert "Preserve code search." in memory
    assert "Preserve related files." in memory
    assert "old final" not in memory
    assert "### Root Cause\nOld cache key" in memory
    assert "### Fix\nNew query key" in memory
    assert "### Tests\nFocused tests passed" in memory
    assert "### Review Notes\nLooks safe" in memory
    assert "Result files incomplete. Manual update required." in memory
    assert status["steps"]["memory_update"] == "pass"


def test_memory_update_missing_result_summary_is_graceful(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    assert main(["memory", "update", "HR-12345"]) == 0
    output = capsys.readouterr().out
    status = json.loads((tmp_path / ".ai" / "HR-12345" / "workflow_status.json").read_text())

    assert "WARN: missing .ai/HR-12345/result_summary.md" in output
    assert status["steps"]["memory_update"] == "skipped"


def test_review_package_generates_final_review_prompt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert main(["review-package", "HR-12345"]) == 0
    prompt = (tmp_path / ".ai" / "HR-12345" / "final_review_prompt.md").read_text()
    status = json.loads((tmp_path / ".ai" / "HR-12345" / "workflow_status.json").read_text())

    assert "# Final Review Request" in prompt
    assert "Please review the completed fix for Jira issue HR-12345." in prompt
    assert ".ai/HR-12345/result_summary.md if present" in prompt
    assert "Verdict:" in prompt
    assert "PASS / PASS WITH MINOR COMMENTS / NEEDS CHANGES" in prompt
    assert status["steps"]["final_review_prompt"] == "pass"


def test_phase_4_commands_log_generated_and_updated_files(tmp_path, monkeypatch):
    issue_dir = tmp_path / ".ai" / "HR-12345"
    memory_dir = tmp_path / ".ai_memory" / "bugs"
    issue_dir.mkdir(parents=True)
    memory_dir.mkdir(parents=True)
    (issue_dir / "bug_analysis.md").write_text("Root cause", encoding="utf-8")
    (issue_dir / "fix_summary.md").write_text("Fix", encoding="utf-8")
    (memory_dir / "HR-12345.md").write_text("# HR-12345\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    main(["summarize-results", "HR-12345"])
    main(["memory", "update", "HR-12345"])
    main(["review-package", "HR-12345"])
    log_text = (issue_dir / "execution.log").read_text()

    assert "[GENERATED] .ai/HR-12345/result_summary.md" in log_text
    assert "[GENERATED] .ai/HR-12345/manual_validation.md" in log_text
    assert "[UPDATED] .ai_memory/bugs/HR-12345.md" in log_text
    assert "[GENERATED] .ai/HR-12345/final_review_prompt.md" in log_text


def _write_delivery_artifacts(tmp_path):
    issue_dir = tmp_path / ".ai" / "HR-12345"
    memory_dir = tmp_path / ".ai_memory" / "bugs"
    issue_dir.mkdir(parents=True, exist_ok=True)
    memory_dir.mkdir(parents=True, exist_ok=True)
    for file_name in ["bug_analysis.md", "fix_summary.md", "test_result.md", "diff_summary.md", "review_notes.md"]:
        (issue_dir / file_name).write_text("done", encoding="utf-8")
    (issue_dir / "result_summary.md").write_text("## Fix Summary\nshort summary\n", encoding="utf-8")
    (issue_dir / "final_review_prompt.md").write_text("review", encoding="utf-8")
    (memory_dir / "HR-12345.md").write_text("memory", encoding="utf-8")
    return issue_dir


def test_delivery_check_warns_when_required_files_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    assert main(["delivery-check", "HR-12345"]) == 0
    output = capsys.readouterr().out
    status = json.loads((tmp_path / ".ai" / "HR-12345" / "workflow_status.json").read_text())

    assert "WARN: delivery is not ready." in output
    assert "Missing required result file: .ai/HR-12345/bug_analysis.md" in output
    assert status["steps"]["delivery_check"] == "fail"


def test_delivery_check_passes_when_ready(tmp_path, monkeypatch, capsys):
    _write_delivery_artifacts(tmp_path)

    monkeypatch.setattr("hrs_ai.core.workflow.inside_git_repo", lambda repo_root: True)
    monkeypatch.setattr("hrs_ai.core.workflow.current_branch", lambda repo_root: "feature/HR-12345-demo")
    monkeypatch.setattr("hrs_ai.core.workflow.working_tree_status", lambda repo_root: " M src/file.cpp")
    monkeypatch.chdir(tmp_path)

    assert main(["delivery-check", "HR-12345"]) == 0
    output = capsys.readouterr().out
    status = json.loads((tmp_path / ".ai" / "HR-12345" / "workflow_status.json").read_text())

    assert "PASS: ready for manual commit/push." in output
    assert status["steps"]["delivery_check"] == "pass"


def test_commit_plan_generates_file_without_git_mutation(tmp_path, monkeypatch):
    calls = []

    def fake_run_command(args, repo_root):
        calls.append(args)
        if args[:3] == ["git", "branch", "--show-current"]:
            return 0, "feature/HR-12345-demo"
        if args[:3] == ["git", "diff", "--name-only"]:
            return 0, "src/file.cpp"
        if args[:3] == ["git", "diff", "--stat"]:
            return 0, " src/file.cpp | 2 +-\n 1 file changed"
        return 0, ""

    monkeypatch.setattr("hrs_ai.core.workflow.run_command", fake_run_command)
    monkeypatch.chdir(tmp_path)

    assert main(["commit-plan", "HR-12345"]) == 0
    plan = (tmp_path / ".ai" / "HR-12345" / "commit_plan.md").read_text()

    assert "# Commit Plan" in plan
    assert "feature/HR-12345-demo" in plan
    assert "src/file.cpp" in plan
    assert 'git commit -m "Fix HR-12345:' in plan
    assert not any(call[:2] == ["git", "add"] for call in calls)
    assert not any(call[:2] == ["git", "commit"] for call in calls)


def test_push_plan_generates_file_without_git_push(tmp_path, monkeypatch):
    calls = []

    def fake_run_command(args, repo_root):
        calls.append(args)
        if args[:3] == ["git", "branch", "--show-current"]:
            return 0, "feature/HR-12345-demo"
        if args[:2] == ["git", "remote"]:
            return 0, "origin https://example/repo.git (fetch)\norigin https://example/repo.git (push)"
        if args[:2] == ["git", "log"]:
            return 0, "abc123 Fix HR-12345"
        if args[:3] == ["git", "status", "--porcelain"]:
            return 0, " M src/file.cpp"
        return 0, ""

    monkeypatch.setattr("hrs_ai.core.workflow.run_command", fake_run_command)
    monkeypatch.chdir(tmp_path)

    assert main(["push-plan", "HR-12345"]) == 0
    plan = (tmp_path / ".ai" / "HR-12345" / "push_plan.md").read_text()

    assert "# Push Plan" in plan
    assert "feature/HR-12345-demo" in plan
    assert "git push -u origin feature/HR-12345-demo" in plan
    assert not any(call[:2] == ["git", "push"] for call in calls)


def test_delivery_commands_are_safe_outside_git_repo(tmp_path, monkeypatch, capsys):
    _write_delivery_artifacts(tmp_path)
    monkeypatch.setattr("hrs_ai.core.workflow.inside_git_repo", lambda repo_root: False)
    monkeypatch.setattr("hrs_ai.core.workflow.current_branch", lambda repo_root: None)
    monkeypatch.setattr("hrs_ai.core.workflow.working_tree_status", lambda repo_root: None)
    monkeypatch.chdir(tmp_path)

    assert main(["delivery-check", "HR-12345"]) == 0
    output = capsys.readouterr().out

    assert "Current directory is not inside a git repository." in output
    assert "Current branch is unavailable." in output


def test_delivery_plan_status_and_log_entries(tmp_path, monkeypatch):
    monkeypatch.setattr("hrs_ai.core.workflow.run_command", lambda args, repo_root: (0, "feature/HR-12345-demo"))
    monkeypatch.chdir(tmp_path)

    main(["commit-plan", "HR-12345"])
    main(["push-plan", "HR-12345"])
    status = json.loads((tmp_path / ".ai" / "HR-12345" / "workflow_status.json").read_text())
    log_text = (tmp_path / ".ai" / "HR-12345" / "execution.log").read_text()

    assert status["steps"]["commit_plan"] == "pass"
    assert status["steps"]["push_plan"] == "pass"
    assert ".ai/HR-12345/commit_plan.md" in status["generated_files"]
    assert ".ai/HR-12345/push_plan.md" in status["generated_files"]
    assert "[GENERATED] .ai/HR-12345/commit_plan.md" in log_text
    assert "[GENERATED] .ai/HR-12345/push_plan.md" in log_text


def test_commit_and_push_execute_placeholders_do_not_mutate_git(tmp_path, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr("hrs_ai.core.workflow.run_command", lambda args, repo_root: calls.append(args) or (0, ""))
    monkeypatch.chdir(tmp_path)

    assert main(["commit", "HR-12345", "--execute"]) == 0
    assert main(["push", "HR-12345", "--execute"]) == 0
    output = capsys.readouterr().out

    assert "Automatic commit/push execution is not enabled in this prototype." in output
    assert calls == []


def test_clean_removes_issue_artifact_directory(tmp_path, monkeypatch, capsys):
    issue_dir = tmp_path / ".ai" / "HR-12345"
    issue_dir.mkdir(parents=True)
    (issue_dir / "some_old_file.md").write_text("old", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["clean", "HR-12345"]) == 0
    output = capsys.readouterr().out

    assert not issue_dir.exists()
    assert "deleted: .ai/HR-12345/" in output


def test_clean_preserves_memory_by_default(tmp_path, monkeypatch):
    issue_dir = tmp_path / ".ai" / "HR-12345"
    memory_file = tmp_path / ".ai_memory" / "bugs" / "HR-12345.md"
    issue_dir.mkdir(parents=True)
    memory_file.parent.mkdir(parents=True)
    memory_file.write_text("keep me", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["clean", "HR-12345"]) == 0

    assert not issue_dir.exists()
    assert memory_file.read_text(encoding="utf-8") == "keep me"


def test_clean_include_memory_removes_only_that_issue_memory(tmp_path, monkeypatch):
    issue_dir = tmp_path / ".ai" / "HR-12345"
    memory_dir = tmp_path / ".ai_memory" / "bugs"
    issue_dir.mkdir(parents=True)
    memory_dir.mkdir(parents=True)
    (memory_dir / "HR-12345.md").write_text("delete", encoding="utf-8")
    (memory_dir / "HR-99999.md").write_text("keep", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["clean", "HR-12345", "--include-memory"]) == 0

    assert not issue_dir.exists()
    assert not (memory_dir / "HR-12345.md").exists()
    assert (memory_dir / "HR-99999.md").read_text(encoding="utf-8") == "keep"


def test_clean_handles_missing_artifacts_gracefully(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    assert main(["clean", "HR-12345"]) == 0
    output = capsys.readouterr().out

    assert "No workflow artifacts found for HR-12345." in output
    assert "Preserved memory entry: .ai_memory/bugs/HR-12345.md" in output


def test_clean_rejects_invalid_issue_keys_without_deleting(tmp_path, monkeypatch, capsys):
    product_file = tmp_path / "src" / "example.cpp"
    product_file.parent.mkdir()
    product_file.write_text("int main() { return 0; }\n", encoding="utf-8")
    protected_dir = tmp_path / ".ai" / "HR-12345"
    protected_dir.mkdir(parents=True)
    (protected_dir / "keep.md").write_text("keep", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    for invalid in ["../HR-12345", "..\\HR-12345", "HR-12345/../../x", "HR", "12345", " HR-12345", "HR-12345 "]:
        assert main(["clean", invalid]) == 1

    assert protected_dir.exists()
    assert product_file.exists()
    assert "Invalid issue key" in capsys.readouterr().err


def test_clean_accepts_unpadded_valid_issue_key(tmp_path, monkeypatch):
    issue_dir = tmp_path / ".ai" / "HR-12345"
    issue_dir.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    assert main(["clean", "HR-12345"]) == 0

    assert not issue_dir.exists()


def test_bug_fresh_removes_old_later_phase_artifacts(tmp_path, monkeypatch):
    issue_dir = tmp_path / ".ai" / "HR-12345"
    issue_dir.mkdir(parents=True)
    (issue_dir / "result_summary.md").write_text("old result", encoding="utf-8")
    (issue_dir / "commit_plan.md").write_text("old commit", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["bug", "HR-12345", "--fresh"]) == 0

    assert not (issue_dir / "result_summary.md").exists()
    assert not (issue_dir / "commit_plan.md").exists()
    assert (issue_dir / "workflow_status.json").is_file()
    assert (issue_dir / "bug_context.md").is_file()
    log_text = (issue_dir / "execution.log").read_text(encoding="utf-8")
    assert "[INFO] fresh run requested" in log_text
    assert "[INFO] memory entry preserved" in log_text


def test_bug_fresh_preserves_memory_by_default(tmp_path, monkeypatch):
    memory_file = tmp_path / ".ai_memory" / "bugs" / "HR-12345.md"
    memory_file.parent.mkdir(parents=True)
    memory_file.write_text("old memory", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["bug", "HR-12345", "--fresh"]) == 0

    assert memory_file.exists()


def test_bug_fresh_include_memory_removes_old_memory_then_recreates(tmp_path, monkeypatch):
    memory_file = tmp_path / ".ai_memory" / "bugs" / "HR-12345.md"
    memory_file.parent.mkdir(parents=True)
    memory_file.write_text("UNIQUE OLD MEMORY", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["bug", "HR-12345", "--fresh", "--include-memory"]) == 0

    memory = memory_file.read_text(encoding="utf-8")
    assert "UNIQUE OLD MEMORY" not in memory
    assert "Prototype prepare-only workflow" in memory


def test_clean_does_not_affect_product_files(tmp_path, monkeypatch):
    issue_dir = tmp_path / ".ai" / "HR-12345"
    product_file = tmp_path / "src" / "example.cpp"
    issue_dir.mkdir(parents=True)
    product_file.parent.mkdir()
    product_file.write_text("source", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["clean", "HR-12345"]) == 0

    assert product_file.read_text(encoding="utf-8") == "source"


def test_bug_include_memory_requires_fresh(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    assert main(["bug", "HR-12345", "--include-memory"]) == 1

    assert "--include-memory can only be used with --fresh" in capsys.readouterr().err
