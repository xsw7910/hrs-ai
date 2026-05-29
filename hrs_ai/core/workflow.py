"""Deterministic prepare-only workflow orchestration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import WORKFLOW_STEPS, issue_dir
from .context import build_context
from .doctor import collect_doctor_report
from .jira import fetch_issue, jira_summary_markdown, parse_issue, parsed_markdown
from .keywords import extract_keywords, keywords_json
from .logging_utils import log
from .memory import add_memory_entry, build_memory_entry
from .prompts import generate_prompts


@dataclass
class WorkflowResult:
    issue_key: str
    issue_dir: Path
    generated_files: list[str]


def run_bug_workflow(repo_root: Path, issue_key: str) -> WorkflowResult:
    target = _prepare_issue_dir(repo_root, issue_key)
    log(target, f"[START] command: hrs-ai bug {issue_key}")

    try:
        log(target, "[START] doctor")
        doctor_report = collect_doctor_report(repo_root)
        log(target, f"doctor report: {doctor_report}")
        _mark_step(repo_root, issue_key, "doctor", "pass")
        log(target, "[END] doctor: pass")

        fetch_step(repo_root, issue_key)
        parse_step(repo_root, issue_key)
        keywords_step(repo_root, issue_key)
        context_step(repo_root, issue_key)
        prompt_step(repo_root, issue_key)
        memory_add_step(repo_root, issue_key)
    except Exception as exc:
        log(target, f"[ERROR] workflow: {exc}")
        _write_status(repo_root, issue_key, _read_step_status(repo_root, issue_key), _generated_files(repo_root, issue_key))
        raise

    _mark_step(repo_root, issue_key, "copilot_fix", "skipped")
    log(target, "[SKIP] copilot_fix: prepare-only mode")
    generated = _generated_files(repo_root, issue_key)
    for file_name in generated:
        log(target, f"[GENERATED] {file_name}")
    log(target, "[END] workflow: pass")
    _write_status(
        repo_root,
        issue_key,
        {
            "doctor": "pass",
            "fetch": "pass",
            "parse": "pass",
            "keywords": "pass",
            "context": "pass",
            "prompt": "pass",
            "memory_add": "pass",
            "copilot_fix": "skipped",
        },
        generated,
    )
    return WorkflowResult(issue_key=issue_key, issue_dir=target, generated_files=generated)


def fetch_step(repo_root: Path, issue_key: str) -> None:
    target = _prepare_issue_dir(repo_root, issue_key)
    log(target, "[START] fetch")
    try:
        issue, is_mock, message = fetch_issue(repo_root, issue_key)
        (target / "jira.json").write_text(json.dumps(issue, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (target / "jira_summary.md").write_text(jira_summary_markdown(issue, message), encoding="utf-8")
        if is_mock:
            log(target, f"[WARN] {message}")
            log(target, "[WARN] MOCK/DEMO Jira data was generated for this run.")
        else:
            log(target, message)
        _mark_step(repo_root, issue_key, "fetch", "pass")
        log(target, "[END] fetch: pass")
    except Exception as exc:
        _mark_step(repo_root, issue_key, "fetch", "fail")
        log(target, f"[ERROR] fetch: {exc}")
        raise


def parse_step(repo_root: Path, issue_key: str) -> None:
    target = _prepare_issue_dir(repo_root, issue_key)
    log(target, "[START] parse")
    try:
        issue = _read_json(target / "jira.json")
        parsed = parse_issue(issue)
        (target / "jira_parsed.md").write_text(parsed_markdown(parsed), encoding="utf-8")
        _mark_step(repo_root, issue_key, "parse", "pass")
        log(target, "[END] parse: pass")
    except Exception as exc:
        _mark_step(repo_root, issue_key, "parse", "fail")
        log(target, f"[ERROR] parse: {exc}")
        raise


def keywords_step(repo_root: Path, issue_key: str) -> None:
    target = _prepare_issue_dir(repo_root, issue_key)
    log(target, "[START] keywords")
    try:
        parsed = parse_issue(_read_json(target / "jira.json"))
        keywords = extract_keywords(str(parsed.get("combined_text", "")))
        (target / "extracted_keywords.json").write_text(keywords_json(keywords), encoding="utf-8")
        _mark_step(repo_root, issue_key, "keywords", "pass")
        log(target, "[END] keywords: pass")
    except Exception as exc:
        _mark_step(repo_root, issue_key, "keywords", "fail")
        log(target, f"[ERROR] keywords: {exc}")
        raise


def context_step(repo_root: Path, issue_key: str) -> None:
    target = _prepare_issue_dir(repo_root, issue_key)
    log(target, "[START] context")
    try:
        parsed = parse_issue(_read_json(target / "jira.json"))
        keywords = _read_json(target / "extracted_keywords.json")
        context = build_context(repo_root, issue_key, parsed, keywords)
        (target / "bug_context.md").write_text(context, encoding="utf-8")
        _mark_step(repo_root, issue_key, "context", "pass")
        log(target, "[END] context: pass")
    except Exception as exc:
        _mark_step(repo_root, issue_key, "context", "fail")
        log(target, f"[ERROR] context: {exc}")
        raise


def prompt_step(repo_root: Path, issue_key: str) -> None:
    target = _prepare_issue_dir(repo_root, issue_key)
    log(target, "[START] prompt")
    try:
        for file_name, content in generate_prompts(issue_key).items():
            (target / file_name).write_text(content, encoding="utf-8")
        _mark_step(repo_root, issue_key, "prompt", "pass")
        log(target, "[END] prompt: pass")
    except Exception as exc:
        _mark_step(repo_root, issue_key, "prompt", "fail")
        log(target, f"[ERROR] prompt: {exc}")
        raise


def memory_add_step(repo_root: Path, issue_key: str) -> None:
    target = _prepare_issue_dir(repo_root, issue_key)
    log(target, "[START] memory_add")
    try:
        parsed = parse_issue(_read_json(target / "jira.json"))
        entry = build_memory_entry(issue_key, parsed, f".ai/{issue_key}/bug_context.md")
        (target / "memory_entry.md").write_text(entry, encoding="utf-8")
        add_memory_entry(repo_root, issue_key, entry)
        _mark_step(repo_root, issue_key, "memory_add", "pass")
        log(target, "[END] memory_add: pass")
    except Exception as exc:
        _mark_step(repo_root, issue_key, "memory_add", "fail")
        log(target, f"[ERROR] memory_add: {exc}")
        raise


def _prepare_issue_dir(repo_root: Path, issue_key: str) -> Path:
    target = issue_dir(repo_root, issue_key)
    target.mkdir(parents=True, exist_ok=True)
    return target


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _generated_files(repo_root: Path, issue_key: str) -> list[str]:
    target = issue_dir(repo_root, issue_key)
    generated = [
        f".ai/{issue_key}/{path.name}"
        for path in target.iterdir()
        if path.is_file()
    ]
    memory_path = repo_root / ".ai_memory" / "bugs" / f"{issue_key}.md"
    if memory_path.exists():
        generated.append(f".ai_memory/bugs/{issue_key}.md")
    return sorted(generated)


def _write_status(repo_root: Path, issue_key: str, step_status: dict[str, str], generated: list[str]) -> None:
    target = _prepare_issue_dir(repo_root, issue_key)
    status = {
        "issue_key": issue_key,
        "mode": "prepare-only",
        "steps": {step: step_status.get(step, "skipped") for step in WORKFLOW_STEPS},
        "generated_files": sorted(generated),
    }
    (target / "workflow_status.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")


def _mark_step(repo_root: Path, issue_key: str, step: str, status: str) -> None:
    status = _normalize_status(status)
    step_status = _read_step_status(repo_root, issue_key)
    step_status[step] = status
    generated = _generated_files(repo_root, issue_key)
    _write_status(repo_root, issue_key, step_status, generated)


def _read_step_status(repo_root: Path, issue_key: str) -> dict[str, str]:
    target = _prepare_issue_dir(repo_root, issue_key)
    status_path = target / "workflow_status.json"
    if not status_path.exists():
        return {}
    current = json.loads(status_path.read_text(encoding="utf-8"))
    steps = current.get("steps", {})
    if isinstance(steps, dict):
        return {name: _normalize_status(status) for name, status in steps.items()}
    return {item["name"]: _normalize_status(item["status"]) for item in steps}


def _normalize_status(status: str) -> str:
    if status in {"pass", "fail", "skipped"}:
        return status
    if status == "completed":
        return "pass"
    if status in {"manual-only", "not-run", "pending", "running"}:
        return "skipped"
    if status in {"exception", "error"}:
        return "fail"
    return "skipped"
