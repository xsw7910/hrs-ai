from __future__ import annotations

import json

from hrs_ai.cli import main
from hrs_ai.core.git_ops import branch_name
from hrs_ai.core.workflow import run_bug_workflow


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
        "context": "pass",
        "prompt": "pass",
        "memory_add": "pass",
        "copilot_fix": "skipped",
    }
    assert ".ai/HR-12345/copilot_task.md" in status["generated_files"]
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
    assert "[START] context" in log_text
    assert "[END] context: pass" in log_text
    assert "[START] prompt" in log_text
    assert "[END] prompt: pass" in log_text
    assert "[START] memory_add" in log_text
    assert "[END] memory_add: pass" in log_text
    assert "[SKIP] copilot_fix: prepare-only mode" in log_text
    assert "[GENERATED] .ai/HR-12345/copilot_task.md" in log_text
    assert "[GENERATED] .ai_memory/bugs/HR-12345.md" in log_text
    assert "[END] workflow: pass" in log_text


def test_copilot_task_references_code_search(tmp_path):
    run_bug_workflow(tmp_path, "HR-12345")
    task = (tmp_path / ".ai" / "HR-12345" / "copilot_task.md").read_text()

    assert "Run Copilot CLI from the target repo root" in task
    assert "feature/HR-12345-ai-assisted-jira-bug-workflow" in task
    assert ".ai/HR-12345/code_search.md" in task
    assert "matched line numbers" in task
    assert ".ai/HR-12345/bug_analysis.md" in task
