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
    }
    assert ".ai/HR-12345/copilot_task.md" in status["generated_files"]
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
    assert "[GENERATED] .ai_memory/bugs/HR-12345.md" in log_text
    assert "[END] workflow: pass" in log_text


def test_copilot_task_references_code_search(tmp_path):
    run_bug_workflow(tmp_path, "HR-12345")
    task = (tmp_path / ".ai" / "HR-12345" / "copilot_task.md").read_text()

    assert "Run Copilot CLI from the target repo root" in task
    assert "feature/HR-12345-ai-assisted-jira-bug-workflow" in task
    assert ".ai/HR-12345/code_search.md" in task
    assert ".ai/HR-12345/related_files.json" in task
    assert "Do not edit code until after reviewing context and related files" in task
    assert "matched line numbers" in task
    assert ".ai/HR-12345/bug_analysis.md" in task


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
