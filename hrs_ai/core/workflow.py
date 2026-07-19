"""Deterministic prepare-only workflow orchestration."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .cleanup import clean_issue_artifacts, validate_issue_key
from .config import WORKFLOW_STEPS, EmailConfig, GraphConfig, issue_dir, load_email_config, load_graph_config
from .email_notify import EmailSendError, EmailSendResult, build_email_draft, render_eml, send_notification, send_via_graph
from .context import build_context
from .delivery_instructions import delivery_instructions_block
from .doctor import collect_doctor_report
from .git_ops import current_branch, generate_git_context, inside_git_repo, run_command, working_tree_status
from .jira import JiraCommentPostError, JiraCommentPostResult, JiraFetchError, JiraFetchResult, enrich_issue, fetch_issue, jira_field_report_markdown, jira_summary_markdown, parse_issue, parsed_markdown, post_jira_comment, prepare_jira_comment_text, sanitize_comment_text
from .keywords import extract_keywords, keywords_json
from .logging_utils import log
from .memory import ISSUE_KEY_RE, add_memory_entry, build_memory_entry, search_memory
from .prompts import copilot_team_instructions, generate_copilot_task_files, generate_prompts
from .search import related_files_json, run_code_search, search_quality_json


@dataclass
class WorkflowResult:
    issue_key: str
    issue_dir: Path
    generated_files: list[str]
    jira_result: JiraFetchResult | None = None
    clean_result: object | None = None
    fresh: bool = False
    allow_mock: bool = False


REQUIRED_COPILOT_RESULT_FILES = [
    "bug_analysis.md",
    "fix_summary.md",
    "test_result.md",
    "diff_summary.md",
    "review_notes.md",
]


def looks_like_issue_key(value: str) -> bool:
    return bool(ISSUE_KEY_RE.match(value.strip()))


def run_bug_workflow(
    repo_root: Path,
    issue_key: str,
    copilot_fix: bool = False,
    fresh: bool = True,
    include_memory: bool = False,
    allow_mock: bool = False,
    progress: Callable[[str], None] | None = None,
) -> WorkflowResult:
    clean_result = None
    if fresh:
        validate_issue_key(issue_key)
        _progress(progress, "clean_start")
        clean_result = clean_issue_artifacts(repo_root, issue_key, include_memory=include_memory)
        _progress(progress, "clean_done" if f".ai/{issue_key}/" in clean_result.deleted_paths else "clean_none")

    target = _prepare_issue_dir(repo_root, issue_key)
    command = f"hrs-ai bug {issue_key}"
    if not fresh:
        command += " --resume"
    if include_memory:
        command += " --include-memory"
    if allow_mock:
        command += " --allow-mock"
    log(target, f"[START] command: {command}")
    log(target, f"[INFO] effective mode: fresh={str(fresh).lower()}, allow_mock={str(allow_mock).lower()}")
    if allow_mock:
        log(target, "[INFO] mock/demo Jira fallback enabled by --allow-mock")
    else:
        log(target, "[INFO] real Jira required")
        log(target, "[INFO] mock fallback disabled")
    if fresh:
        log(target, "[INFO] fresh run requested/defaulted")
        log(target, "[INFO] previous workflow artifacts were removed before this run")
        if include_memory:
            log(target, "[INFO] memory entry removed due to --include-memory")
        else:
            log(target, "[INFO] memory entry preserved")
        if clean_result:
            for path in clean_result.deleted_paths:
                log(target, f"[INFO] fresh deleted: {path}")
            for path in clean_result.preserved_paths:
                log(target, f"[INFO] fresh preserved: {path}")
            for path in clean_result.missing_paths:
                log(target, f"[INFO] fresh missing: {path}")
    else:
        log(target, "[INFO] resume requested")
        log(target, "[INFO] previous workflow artifacts were preserved")

    try:
        _progress(progress, "doctor")
        log(target, "[START] doctor")
        doctor_report = collect_doctor_report(repo_root)
        log(target, f"doctor report: {doctor_report}")
        _mark_step(repo_root, issue_key, "doctor", "pass")
        log(target, "[END] doctor: pass")

        _progress(progress, "fetch")
        jira_result = fetch_step(repo_root, issue_key, allow_mock=allow_mock)
        _progress(progress, "parse")
        parse_step(repo_root, issue_key)
        _progress(progress, "keywords")
        keywords_step(repo_root, issue_key)
        _progress(progress, "memory_search")
        memory_search_step(repo_root, issue_key)
        _progress(progress, "code_search")
        code_search_step(repo_root, issue_key)
        _progress(progress, "git_context")
        git_context_step(repo_root, issue_key)
        _progress(progress, "context")
        context_step(repo_root, issue_key)
        _progress(progress, "prompt")
        prompt_step(repo_root, issue_key)
        memory_add_step(repo_root, issue_key)
    except Exception as exc:
        log(target, f"[ERROR] workflow: {exc}")
        _write_status(
            repo_root,
            issue_key,
            _read_step_status(repo_root, issue_key),
            _generated_files(repo_root, issue_key),
            fresh=fresh,
            allow_mock=allow_mock,
        )
        raise

    _mark_step(repo_root, issue_key, "copilot_fix", "skipped")
    log(target, "[SKIP] copilot_fix: prepare-only mode")
    if copilot_fix:
        log(target, "[INFO] Copilot automatic invocation is not enabled, using manual handoff")
        log(target, f"[INFO] Next Copilot CLI instruction: Read .ai/{issue_key}/copilot_task.md and complete the workflow.")
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
            "memory_search": "pass",
            "code_search": "pass",
            "git_context": "pass",
            "context": "pass",
            "prompt": "pass",
            "memory_add": "pass",
            "copilot_fix": "skipped",
        },
        generated,
        fresh=fresh,
        allow_mock=allow_mock,
    )
    return WorkflowResult(
        issue_key=issue_key,
        issue_dir=target,
        generated_files=generated,
        jira_result=jira_result,
        clean_result=clean_result,
        fresh=fresh,
        allow_mock=allow_mock,
    )


def _progress(progress: Callable[[str], None] | None, event: str) -> None:
    if progress:
        progress(event)


def fetch_step(repo_root: Path, issue_key: str, allow_mock: bool = False) -> JiraFetchResult:
    target = _prepare_issue_dir(repo_root, issue_key)
    log(target, "[START] fetch")
    if allow_mock:
        log(target, "[INFO] mock/demo Jira fallback enabled by --allow-mock")
    else:
        log(target, "[INFO] real Jira required")
        log(target, "[INFO] mock fallback disabled")
    try:
        result = fetch_issue(repo_root, issue_key, allow_mock=allow_mock)
        issue = result.data
        enrich_issue(issue)
        message = _fetch_message(result)
        (target / "jira.json").write_text(json.dumps(issue, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (target / "jira_summary.md").write_text(jira_summary_markdown(issue, message), encoding="utf-8")
        if result.source == "mock":
            log(target, f"[WARN] Jira fetch failed: {result.error_type} - {result.error_message}")
            log(target, "[WARN] Using mock/demo Jira data")
        else:
            log(target, message)
        _mark_step(repo_root, issue_key, "fetch", "pass")
        log(target, "[END] fetch: pass")
        return result
    except JiraFetchError as exc:
        _mark_step(repo_root, issue_key, "fetch", "fail")
        log(target, f"[ERROR] Jira fetch failed: {exc.result.error_type} - {exc.result.error_message}")
        log(target, "[ERROR] Mock fallback disabled")
        log(target, "[END] fetch: fail")
        raise
    except Exception as exc:
        _mark_step(repo_root, issue_key, "fetch", "fail")
        log(target, f"[ERROR] fetch: {exc}")
        raise


def jira_validate_step(repo_root: Path, issue_key: str) -> dict:
    """Fetch and validate a real Jira issue. No mock fallback.

    Writes jira.json, jira_summary.md, jira_parsed.md, jira_field_report.md.
    Returns a validation summary dict.
    """
    target = _prepare_issue_dir(repo_root, issue_key)
    log(target, "[START] jira_validate")
    try:
        result = fetch_issue(repo_root, issue_key, allow_mock=False)
        issue = result.data
        enrich_issue(issue)
        message = "Fetched Jira data from configured Jira instance."
        (target / "jira.json").write_text(json.dumps(issue, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (target / "jira_summary.md").write_text(jira_summary_markdown(issue, message), encoding="utf-8")
        parsed = parse_issue(issue)
        (target / "jira_parsed.md").write_text(parsed_markdown(parsed), encoding="utf-8")
        (target / "jira_field_report.md").write_text(jira_field_report_markdown(issue), encoding="utf-8")
        log(target, "[END] jira_validate: pass")
        return {
            "source": "jira",
            "issue_type": str(parsed.get("issue_type", "") or ""),
            "status": str(parsed.get("status", "") or ""),
            "priority": str(parsed.get("priority", "") or ""),
            "comment_count": int(parsed.get("comment_total", 0)),
            "attachment_count": len(parsed.get("attachments", []) or []),
            "has_description": bool(parsed.get("description")),
            "has_reproduction_steps": bool(parsed.get("reproduction_steps")),
            "missing_information_count": len(parsed.get("missing_information", []) or []),
        }
    except JiraFetchError as exc:
        log(target, f"[ERROR] jira_validate Jira fetch failed: {exc.result.error_type} - {exc.result.error_message}")
        log(target, "[END] jira_validate: fail")
        raise
    except Exception as exc:
        log(target, f"[ERROR] jira_validate: {exc}")
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


def memory_search_step(repo_root: Path, issue_key: str) -> None:
    target = _prepare_issue_dir(repo_root, issue_key)
    log(target, "[START] memory_search")
    try:
        search_memory(repo_root, issue_key)
        _mark_step(repo_root, issue_key, "memory_search", "pass")
        log(target, "[END] memory_search: pass")
    except Exception as exc:
        _mark_step(repo_root, issue_key, "memory_search", "fail")
        log(target, f"[ERROR] memory_search: {exc}")
        raise


def code_search_step(repo_root: Path, issue_key: str) -> None:
    target = _prepare_issue_dir(repo_root, issue_key)
    log(target, "[START] code_search")
    try:
        keywords = _read_json(target / "extracted_keywords.json")
        markdown, related_files, search_quality = run_code_search(repo_root, issue_key, keywords)
        (target / "code_search.md").write_text(markdown, encoding="utf-8")
        (target / "related_files.json").write_text(related_files_json(related_files), encoding="utf-8")
        (target / "search_quality.json").write_text(search_quality_json(search_quality), encoding="utf-8")
        _mark_step(repo_root, issue_key, "code_search", "pass")
        log(target, "[END] code_search: pass")
    except Exception as exc:
        _mark_step(repo_root, issue_key, "code_search", "fail")
        log(target, f"[ERROR] code_search: {exc}")
        raise


def git_context_step(repo_root: Path, issue_key: str) -> None:
    target = _prepare_issue_dir(repo_root, issue_key)
    log(target, "[START] git_context")
    try:
        context = generate_git_context(repo_root, issue_key)
        (target / "git_context.md").write_text(context, encoding="utf-8")
        _mark_step(repo_root, issue_key, "git_context", "pass")
        log(target, "[END] git_context: pass")
    except Exception as exc:
        _mark_step(repo_root, issue_key, "git_context", "fail")
        log(target, f"[ERROR] git_context: {exc}")
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
        summary = _issue_summary(target)
        for file_name, content in generate_prompts(issue_key, summary).items():
            (target / file_name).write_text(content, encoding="utf-8")
        _mark_step(repo_root, issue_key, "prompt", "pass")
        log(target, "[END] prompt: pass")
    except Exception as exc:
        _mark_step(repo_root, issue_key, "prompt", "fail")
        log(target, f"[ERROR] prompt: {exc}")
        raise


def copilot_task_step(repo_root: Path, issue_key: str) -> None:
    target = _prepare_issue_dir(repo_root, issue_key)
    bug_context = target / "bug_context.md"
    if not bug_context.exists():
        raise FileNotFoundError(f"Missing {bug_context}. Run: hrs-ai bug {issue_key}")
    log(target, "[START] copilot_task")
    try:
        summary = _issue_summary(target)
        for file_name, content in generate_copilot_task_files(issue_key, summary).items():
            (target / file_name).write_text(content, encoding="utf-8")
        log(target, "[END] copilot_task: pass")
    except Exception as exc:
        log(target, f"[ERROR] copilot_task: {exc}")
        raise


def copilot_instructions_step(repo_root: Path, issue_key: str) -> Path:
    target = _prepare_issue_dir(repo_root, issue_key)
    log(target, "[START] copilot_instructions")
    try:
        path = target / "copilot_team_instructions.md"
        path.write_text(copilot_team_instructions(), encoding="utf-8")
        _mark_step(repo_root, issue_key, "copilot_instructions", "pass")
        log(target, f"[GENERATED] .ai/{issue_key}/copilot_team_instructions.md")
        log(target, "[END] copilot_instructions: pass")
        return path
    except Exception as exc:
        _mark_step(repo_root, issue_key, "copilot_instructions", "fail")
        log(target, f"[ERROR] copilot_instructions: {exc}")
        raise


def check_result_files(repo_root: Path, issue_key: str) -> list[str]:
    target = issue_dir(repo_root, issue_key)
    return [
        f".ai/{issue_key}/{file_name}"
        for file_name in REQUIRED_COPILOT_RESULT_FILES
        if not (target / file_name).exists()
    ]


def check_results_step(repo_root: Path, issue_key: str, strict: bool = False) -> list[str]:
    target = _prepare_issue_dir(repo_root, issue_key)
    log(target, f"[START] check_results{' --strict' if strict else ''}")
    missing = check_result_files(repo_root, issue_key)
    if missing:
        log(target, f"[WARN] check_results: missing {len(missing)} Copilot result file(s).")
        for file_name in missing:
            log(target, f"[WARN] missing result file: {file_name}")
    else:
        log(target, "[END] check_results: pass")
    if missing:
        log(target, "[END] check_results: warn")
    return missing


def summarize_results_step(repo_root: Path, issue_key: str) -> None:
    target = _prepare_issue_dir(repo_root, issue_key)
    log(target, "[START] summarize_results")
    try:
        result_summary = _build_result_summary(repo_root, issue_key)
        manual_validation = _build_manual_validation(repo_root, issue_key)
        (target / "result_summary.md").write_text(result_summary, encoding="utf-8")
        (target / "manual_validation.md").write_text(manual_validation, encoding="utf-8")
        _mark_step(repo_root, issue_key, "result_summary", "pass")
        _mark_step(repo_root, issue_key, "manual_validation", "pass")
        log(target, f"[GENERATED] .ai/{issue_key}/result_summary.md")
        log(target, f"[GENERATED] .ai/{issue_key}/manual_validation.md")
        log(target, "[END] summarize_results: pass")
    except Exception as exc:
        _mark_step(repo_root, issue_key, "result_summary", "fail")
        _mark_step(repo_root, issue_key, "manual_validation", "fail")
        log(target, f"[ERROR] summarize_results: {exc}")
        raise


def review_package_step(repo_root: Path, issue_key: str) -> None:
    target = _prepare_issue_dir(repo_root, issue_key)
    log(target, "[START] review_package")
    try:
        (target / "final_review_prompt.md").write_text(_build_final_review_prompt(issue_key), encoding="utf-8")
        _mark_step(repo_root, issue_key, "final_review_prompt", "pass")
        log(target, f"[GENERATED] .ai/{issue_key}/final_review_prompt.md")
        log(target, "[END] review_package: pass")
    except Exception as exc:
        _mark_step(repo_root, issue_key, "final_review_prompt", "fail")
        log(target, f"[ERROR] review_package: {exc}")
        raise


def delivery_check_step(repo_root: Path, issue_key: str) -> list[str]:
    target = _prepare_issue_dir(repo_root, issue_key)
    log(target, "[START] delivery_check")
    warnings = _delivery_warnings(repo_root, issue_key)
    if warnings:
        for warning in warnings:
            log(target, f"[WARN] delivery_check: {warning}")
        _mark_step(repo_root, issue_key, "delivery_check", "fail")
        log(target, "[END] delivery_check: warn")
    else:
        _mark_step(repo_root, issue_key, "delivery_check", "pass")
        log(target, "[END] delivery_check: pass")
    return warnings


def commit_plan_step(repo_root: Path, issue_key: str) -> Path:
    target = _prepare_issue_dir(repo_root, issue_key)
    log(target, "[START] commit_plan")
    try:
        plan = _build_commit_plan(repo_root, issue_key)
        path = target / "commit_plan.md"
        path.write_text(plan, encoding="utf-8")
        _mark_step(repo_root, issue_key, "commit_plan", "pass")
        log(target, f"[GENERATED] .ai/{issue_key}/commit_plan.md")
        log(target, "[END] commit_plan: pass")
        return path
    except Exception as exc:
        _mark_step(repo_root, issue_key, "commit_plan", "fail")
        log(target, f"[ERROR] commit_plan: {exc}")
        raise


def push_plan_step(repo_root: Path, issue_key: str) -> Path:
    target = _prepare_issue_dir(repo_root, issue_key)
    log(target, "[START] push_plan")
    try:
        plan = _build_push_plan(repo_root, issue_key)
        path = target / "push_plan.md"
        path.write_text(plan, encoding="utf-8")
        _mark_step(repo_root, issue_key, "push_plan", "pass")
        log(target, f"[GENERATED] .ai/{issue_key}/push_plan.md")
        log(target, "[END] push_plan: pass")
        return path
    except Exception as exc:
        _mark_step(repo_root, issue_key, "push_plan", "fail")
        log(target, f"[ERROR] push_plan: {exc}")
        raise


def notify_step(
    repo_root: Path,
    issue_key: str,
    execute: bool = False,
    config: EmailConfig | None = None,
    graph_config: GraphConfig | None = None,
) -> dict[str, object]:
    """Build the post-fix notification email and, when execute is set, send it.

    A local preview (email_draft.md) and a portable notification.eml are always
    written. Sending is an explicit, opt-in outward action (mirrors jira-comment):
    it happens only when execute is True and a transport is configured. Microsoft
    Graph is preferred when configured (works when SMTP client auth / port 25 are
    blocked); otherwise SMTP is used.
    """
    target = _prepare_issue_dir(repo_root, issue_key)
    log(target, f"[START] notify {'execute' if execute else 'preview'}")
    try:
        email_config = config if config is not None else load_email_config()
        graph_config = graph_config if graph_config is not None else load_graph_config()
        draft = build_email_draft(repo_root, issue_key)
        draft_path = target / "email_draft.md"
        draft_path.write_text(f"Subject: {draft.subject}\n\n{draft.body}", encoding="utf-8")
        log(target, f"[GENERATED] .ai/{issue_key}/email_draft.md")

        eml_path = target / "notification.eml"
        eml_path.write_bytes(render_eml(draft, email_config.sender, email_config.recipients))
        log(target, f"[GENERATED] .ai/{issue_key}/notification.eml")

        if not execute:
            _mark_step(repo_root, issue_key, "notify", "skipped")
            log(target, "[INFO] notify preview only; no email was sent")
            log(target, "[END] notify: skipped")
            return {
                "issue_key": issue_key,
                "execute": False,
                "sent": False,
                "draft_path": draft_path,
                "eml_path": eml_path,
                "subject": draft.subject,
            }

        if graph_config.is_configured:
            transport = "graph"
            result = send_via_graph(graph_config, draft, email_config.sender, email_config.recipients)
        else:
            transport = "smtp"
            result = send_notification(email_config, draft)
        if result.sent:
            _mark_step(repo_root, issue_key, "notify", "pass")
            log(target, f"[INFO] notification email sent via {transport} to {len(result.recipients)} recipient(s)")
            log(target, "[END] notify: pass")
        else:
            _mark_step(repo_root, issue_key, "notify", "skipped")
            log(target, f"[WARN] notify skipped ({transport}): {result.skipped_reason}")
            log(target, "[END] notify: skipped")
        return {
            "issue_key": issue_key,
            "execute": True,
            "sent": result.sent,
            "transport": transport,
            "draft_path": draft_path,
            "eml_path": eml_path,
            "subject": draft.subject,
            "recipients": result.recipients,
            "skipped_reason": result.skipped_reason,
        }
    except EmailSendError as exc:
        _mark_step(repo_root, issue_key, "notify", "fail")
        log(target, f"[ERROR] notify: {exc}")
        log(target, "[END] notify: fail")
        raise
    except Exception as exc:
        _mark_step(repo_root, issue_key, "notify", "fail")
        log(target, f"[ERROR] notify: {exc}")
        log(target, "[END] notify: fail")
        raise


def memory_update_step(repo_root: Path, issue_key: str) -> bool:
    target = _prepare_issue_dir(repo_root, issue_key)
    log(target, "[START] memory_update")
    summary_path = target / "result_summary.md"
    memory_path = repo_root / ".ai_memory" / "bugs" / f"{issue_key}.md"
    if not summary_path.exists():
        log(target, f"[WARN] memory_update: missing .ai/{issue_key}/result_summary.md; run hrs-ai summarize-results {issue_key}")
        _mark_step(repo_root, issue_key, "memory_update", "skipped")
        return False

    memory_path.parent.mkdir(parents=True, exist_ok=True)
    existing = memory_path.read_text(encoding="utf-8") if memory_path.exists() else f"# {issue_key} AI Bug Workflow Memory\n"
    final_result = _build_final_result_section(summary_path.read_text(encoding="utf-8"), bool(check_result_files(repo_root, issue_key)))
    updated = _replace_section(existing, "## Final Result", final_result)
    memory_path.write_text(updated, encoding="utf-8")
    _mark_step(repo_root, issue_key, "memory_update", "pass")
    log(target, f"[UPDATED] .ai_memory/bugs/{issue_key}.md")
    log(target, "[END] memory_update: pass")
    return True


def memory_add_step(repo_root: Path, issue_key: str) -> None:
    target = _prepare_issue_dir(repo_root, issue_key)
    log(target, "[START] memory_add")
    try:
        parsed = parse_issue(_read_json(target / "jira.json"))
        entry = build_memory_entry(issue_key, parsed, f".ai/{issue_key}/bug_context.md")
        # The shared memory file under .ai_memory/ is the source of truth; no local
        # per-issue copy is written to keep the .ai/<issue>/ output lean.
        add_memory_entry(repo_root, issue_key, entry)
        _mark_step(repo_root, issue_key, "memory_add", "pass")
        log(target, "[END] memory_add: pass")
    except Exception as exc:
        _mark_step(repo_root, issue_key, "memory_add", "fail")
        log(target, f"[ERROR] memory_add: {exc}")
        raise


def jira_comment_draft_step(repo_root: Path, issue_key: str, strict: bool = False) -> Path:
    target = issue_dir(repo_root, issue_key)
    if not target.exists():
        raise FileNotFoundError(f"No workflow package found for {issue_key}. Run: hrs-ai bug {issue_key}")
    if not (target / "bug_context.md").exists() and not (target / "jira_parsed.md").exists():
        raise FileNotFoundError(f"No core context found for {issue_key}. Run: hrs-ai bug {issue_key}")

    log(target, "[START] jira_comment_draft")
    missing = check_result_files(repo_root, issue_key)
    if strict and missing:
        for file_name in missing:
            log(target, f"[ERROR] jira_comment_draft missing required result file: {file_name}")
        _mark_step(repo_root, issue_key, "jira_comment_draft", "fail")
        log(target, "[END] jira_comment_draft: fail")
        raise ValueError("Missing required Copilot result files: " + ", ".join(missing))

    draft = _build_jira_comment_draft(repo_root, issue_key, missing)
    path = target / "jira_comment_draft.md"
    path.write_text(draft, encoding="utf-8")
    _mark_step(repo_root, issue_key, "jira_comment_draft", "pass")
    log(target, f"[GENERATED] .ai/{issue_key}/jira_comment_draft.md")
    log(target, "[END] jira_comment_draft: pass")
    return path


def jira_comment_step(repo_root: Path, issue_key: str, execute: bool = False) -> dict[str, object]:
    target = issue_dir(repo_root, issue_key)
    if not target.exists():
        raise FileNotFoundError(f"No workflow package found for {issue_key}. Run: hrs-ai bug {issue_key}")
    draft_path = target / "jira_comment_draft.md"
    if not draft_path.exists():
        raise FileNotFoundError(f"Missing .ai/{issue_key}/jira_comment_draft.md. Run: hrs-ai jira-comment-draft {issue_key}")

    mode = "execute" if execute else "preview"
    log(target, f"[START] jira_comment {mode}")
    try:
        comment_text = _prepared_jira_comment_text(draft_path, issue_key)
        if not execute:
            _mark_step(repo_root, issue_key, "jira_comment", "skipped")
            log(target, "[INFO] jira_comment preview only; no Jira POST was made")
            log(target, "[END] jira_comment: skipped")
            return {
                "issue_key": issue_key,
                "execute": False,
                "posted": False,
                "path": draft_path,
                "preview": _comment_preview(comment_text),
                "length": len(comment_text),
            }

        result = post_jira_comment(repo_root, issue_key, comment_text)
        result_json = _jira_comment_result_json(result)
        (target / "jira_comment_post_result.json").write_text(json.dumps(result_json, indent=2) + "\n", encoding="utf-8")
        (target / "jira_comment_post_summary.md").write_text(_jira_comment_post_summary(result), encoding="utf-8")
        _mark_step(repo_root, issue_key, "jira_comment", "pass")
        log(target, f"[GENERATED] .ai/{issue_key}/jira_comment_post_result.json")
        log(target, f"[GENERATED] .ai/{issue_key}/jira_comment_post_summary.md")
        log(target, "[END] jira_comment: pass")
        return {
            "issue_key": issue_key,
            "execute": True,
            "posted": True,
            "comment_id": result.comment_id,
            "timestamp": result.timestamp,
        }
    except Exception as exc:
        _mark_step(repo_root, issue_key, "jira_comment", "fail")
        log(target, f"[ERROR] jira_comment: {exc}")
        log(target, "[END] jira_comment: fail")
        raise


def retry_prompt_step(repo_root: Path, issue_key: str) -> dict[str, Path]:
    target = issue_dir(repo_root, issue_key)
    if not target.exists():
        raise FileNotFoundError(f"No workflow package found for {issue_key}. Run: hrs-ai bug {issue_key}")
    log(target, "[START] retry_prompt")
    try:
        feedback_path = target / "user_feedback.md"
        created_feedback = False
        if not feedback_path.exists():
            feedback_path.write_text(_user_feedback_template(issue_key), encoding="utf-8")
            created_feedback = True
            log(target, f"[GENERATED] .ai/{issue_key}/user_feedback.md")
        prompt_path = target / "copilot_retry_prompt.md"
        prompt_path.write_text(_build_retry_prompt(repo_root, issue_key), encoding="utf-8")
        _mark_step(repo_root, issue_key, "retry_prompt", "pass")
        log(target, f"[GENERATED] .ai/{issue_key}/copilot_retry_prompt.md")
        log(target, "[END] retry_prompt: pass")
        result = {"prompt": prompt_path}
        if created_feedback:
            result["user_feedback"] = feedback_path
        return result
    except Exception as exc:
        _mark_step(repo_root, issue_key, "retry_prompt", "fail")
        log(target, f"[ERROR] retry_prompt: {exc}")
        log(target, "[END] retry_prompt: fail")
        raise


def manual_result_step(repo_root: Path, issue_key: str, overwrite: bool = False) -> dict[str, list[str]]:
    target = issue_dir(repo_root, issue_key)
    if not target.exists():
        raise FileNotFoundError(f"No workflow package found for {issue_key}. Run: hrs-ai bug {issue_key}")
    log(target, "[START] manual_result")
    created: list[str] = []
    preserved: list[str] = []
    try:
        for file_name, content in _manual_result_templates(issue_key).items():
            path = target / file_name
            rel = f".ai/{issue_key}/{file_name}"
            if path.exists() and not overwrite:
                preserved.append(rel)
                log(target, f"[INFO] manual_result preserved existing file: {rel}")
                continue
            if path.exists() and overwrite:
                log(target, f"[WARN] manual_result overwriting existing file: {rel}")
            path.write_text(content, encoding="utf-8")
            created.append(rel)
            log(target, f"[GENERATED] {rel}")
        _mark_step(repo_root, issue_key, "manual_result", "pass")
        log(target, "[END] manual_result: pass")
        return {"created": created, "preserved": preserved}
    except Exception as exc:
        _mark_step(repo_root, issue_key, "manual_result", "fail")
        log(target, f"[ERROR] manual_result: {exc}")
        log(target, "[END] manual_result: fail")
        raise


def _prepare_issue_dir(repo_root: Path, issue_key: str) -> Path:
    target = issue_dir(repo_root, issue_key)
    target.mkdir(parents=True, exist_ok=True)
    return target


def _build_jira_comment_draft(repo_root: Path, issue_key: str, missing_results: list[str]) -> str:
    target = issue_dir(repo_root, issue_key)
    status = _draft_status(target, missing_results)
    summary = _draft_summary(target)
    root_cause = _artifact_or_missing(target, "bug_analysis.md", "No root cause analysis artifact found.")
    fix = _artifact_or_missing(target, "fix_summary.md", "No fix summary artifact found.")
    validation = _artifact_or_missing(target, "test_result.md", "No test result artifact found. Validation is pending.")
    diff = _artifact_or_missing(target, "diff_summary.md", "No diff summary artifact found.")
    search_quality = _search_quality_draft(target / "search_quality.json")
    missing_info = _missing_information_draft(target / "jira_parsed.md")
    missing_results_text = _missing_results_markdown(missing_results)
    draft = (
        "# hrs-ai Analysis Summary\n\n"
        f"Issue: {issue_key}\n\n"
        "## Status\n\n"
        f"{status}\n\n"
        "## Summary\n\n"
        f"{summary}\n\n"
        "## Root Cause / Investigation\n\n"
        f"{root_cause}\n\n"
        "## Fix Summary\n\n"
        f"{fix}\n\n"
        "## Validation\n\n"
        f"{validation}\n\n"
        "## Changed Files / Diff Summary\n\n"
        f"{diff}\n\n"
        "## Search Confidence\n\n"
        f"{search_quality}\n\n"
        "## Missing Information\n\n"
        f"{missing_info}\n\n"
        "## Missing Local Artifacts\n\n"
        f"{missing_results_text}\n\n"
        "## Attachment Note\n\n"
        "hrs-ai did not download or inspect Jira attachment contents. Attachment metadata may have been included if available.\n\n"
        "## Safety Note\n\n"
        "This comment was generated from local hrs-ai artifacts and should be reviewed by a developer before posting to Jira.\n"
    )
    return _cap_text(sanitize_comment_text(draft), 12000)


def _user_feedback_template(issue_key: str) -> str:
    return (
        f"# User Feedback: {issue_key}\n\n"
        "## Review of Previous Attempt\n\n"
        "Describe what did not work.\n\n"
        "## My Observations\n\n"
        "- ...\n\n"
        "## Required Next Attempt\n\n"
        "- ...\n\n"
        "## Do Not Do\n\n"
        "- Do not commit or push unless the developer explicitly approves after a delivery summary.\n"
        "- Do not update Jira.\n"
        "- Do not make broad unrelated refactors.\n"
        "- Do not claim tests passed unless they were run.\n"
    )


def _build_retry_prompt(repo_root: Path, issue_key: str) -> str:
    target = issue_dir(repo_root, issue_key)
    reading_files = [
        "bug_context.md",
        "code_search.md",
        "search_quality.json",
        "related_files.json",
        "git_context.md",
        "review_notes.md",
        "test_result.md",
        "diff_summary.md",
        "user_feedback.md",
    ]
    reading = [f"- .ai/{issue_key}/{name}" for name in reading_files if (target / name).exists()]
    if f"- .ai/{issue_key}/user_feedback.md" not in reading:
        reading.append(f"- .ai/{issue_key}/user_feedback.md")
    reading.append("- current git diff")
    feedback = _cap_text(_read_artifact(target, "user_feedback.md") or "No user feedback file found.", 3000)
    previous = _previous_attempt_summary(target)
    return (
        f"# Copilot Retry Prompt: {issue_key}\n\n"
        "## Purpose\n\n"
        "The previous attempt did not fully resolve the issue, or the developer wants a second focused attempt.\n\n"
        "## Required Reading\n\n"
        f"{chr(10).join(reading)}\n\n"
        "## Developer Feedback\n\n"
        f"{feedback}\n\n"
        "## Previous Attempt Summary\n\n"
        f"{previous}\n\n"
        "## Retry Instructions\n\n"
        "- First explain why the previous attempt did not fully resolve the issue.\n"
        "- Re-check the implementation location.\n"
        "- Use user_feedback.md as the main correction for this retry.\n"
        "- If current git diff exists, review it before editing.\n"
        "- If the previous change is wrong, explain whether to revert or adjust it.\n"
        "- Do not make broad refactors.\n"
        "- Do not modify unrelated files.\n"
        "- Do not commit or push automatically.\n"
        "- Do not update Jira.\n"
        "- Do not claim tests passed unless they were run.\n"
        "- Update the required result files.\n\n"
        f"{delivery_instructions_block(issue_key, intro='After completing the retry and updating required result files')}"
        "## Required Output Files\n\n"
        f"- .ai/{issue_key}/bug_analysis.md\n"
        f"- .ai/{issue_key}/fix_summary.md\n"
        f"- .ai/{issue_key}/test_result.md\n"
        f"- .ai/{issue_key}/diff_summary.md\n"
        f"- .ai/{issue_key}/review_notes.md\n\n"
        "## How to Run\n\n"
        "Run Copilot manually from the target repo root and paste:\n\n"
        f"Read .ai/{issue_key}/copilot_retry_prompt.md and continue the workflow.\n"
    )


def _previous_attempt_summary(target: Path) -> str:
    lines = []
    for file_name in REQUIRED_COPILOT_RESULT_FILES:
        text = _read_artifact(target, file_name)
        if text:
            lines.append(f"### {file_name}\n\npresent\n\n{_cap_text(text, 800)}")
        else:
            lines.append(f"### {file_name}\n\nmissing")
    return "\n\n".join(lines)


def _manual_result_templates(issue_key: str) -> dict[str, str]:
    return {
        "bug_analysis.md": (
            f"# Bug Analysis: {issue_key}\n\n"
            "## Fix Source\n\n"
            "Developer manual fix.\n\n"
            "## Root Cause\n\n"
            "TODO: Describe the root cause.\n\n"
            "## Relevant Files\n\n"
            "- TODO\n\n"
            "## Notes\n\n"
            "TODO\n"
        ),
        "fix_summary.md": (
            f"# Fix Summary: {issue_key}\n\n"
            "## Fix Source\n\n"
            "Developer manual fix.\n\n"
            "## Changes Made\n\n"
            "- TODO\n\n"
            "## Scope\n\n"
            "Small targeted fix. No unrelated refactor.\n"
        ),
        "test_result.md": (
            f"# Test Result: {issue_key}\n\n"
            "## Fix Source\n\n"
            "Developer manual fix.\n\n"
            "## Commands Run\n\n"
            "```text\n"
            "TODO\n"
            "```\n\n"
            "## Result\n\n"
            "TODO: PASS / FAIL / PARTIAL / NOT RUN\n\n"
            "## Notes\n\n"
            "TODO\n\n"
            "Important: Do not claim tests passed unless they were run.\n"
        ),
        "diff_summary.md": (
            f"# Diff Summary: {issue_key}\n\n"
            "## Fix Source\n\n"
            "Developer manual fix.\n\n"
            "## Changed Files\n\n"
            "- TODO\n\n"
            "## Summary\n\n"
            "- TODO\n\n"
            "## Risk\n\n"
            "- TODO\n"
        ),
        "review_notes.md": (
            f"# Review Notes: {issue_key}\n\n"
            "## Fix Source\n\n"
            "Developer manual fix.\n\n"
            "## Review Focus\n\n"
            "- TODO\n\n"
            "## Known Limitations\n\n"
            "- TODO\n"
        ),
    }


def _prepared_jira_comment_text(draft_path: Path, issue_key: str) -> str:
    raw = draft_path.read_text(encoding="utf-8", errors="replace")
    _validate_comment_issue_key(raw, issue_key)
    prepared = prepare_jira_comment_text(raw)
    if not prepared:
        raise ValueError("Jira comment draft is empty.")
    return prepared


def _validate_comment_issue_key(comment_text: str, issue_key: str) -> None:
    match = re.search(r"(?im)^Issue:\s*(\S+)\s*$", comment_text)
    if match and match.group(1) != issue_key:
        raise ValueError(f"Jira comment draft issue key mismatch: found {match.group(1)}, expected {issue_key}.")


def _comment_preview(comment_text: str, limit: int = 800) -> str:
    compact = comment_text.strip()
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "\n\n[preview truncated by hrs-ai]"


def _jira_comment_result_json(result: JiraCommentPostResult) -> dict[str, object]:
    return {
        "issue_key": result.issue_key,
        "posted": result.posted,
        "comment_id": result.comment_id,
        "created": result.created,
        "updated": result.updated,
        "self": result.self_url,
        "timestamp": result.timestamp,
    }


def _jira_comment_post_summary(result: JiraCommentPostResult) -> str:
    return (
        "# Jira Comment Post Summary\n\n"
        "## Issue\n\n"
        f"{result.issue_key}\n\n"
        "## Posted\n\n"
        f"{'yes' if result.posted else 'no'}\n\n"
        "## Comment ID\n\n"
        f"{result.comment_id or 'Not returned.'}\n\n"
        "## Timestamp\n\n"
        f"{result.timestamp}\n\n"
        "## Safety Note\n\n"
        "Only a Jira comment was added. hrs-ai did not update Jira fields, transition status, assign the issue, upload attachments, download attachments, modify source code, commit, push, merge, create a PR, or invoke Copilot.\n"
    )


def _draft_status(target: Path, missing_results: list[str]) -> str:
    bug_analysis = _read_artifact(target, "bug_analysis.md")
    fix_summary = _read_artifact(target, "fix_summary.md")
    diff_summary = _read_artifact(target, "diff_summary.md")
    review_notes = _read_artifact(target, "review_notes.md")
    jira_parsed = _read_artifact(target, "jira_parsed.md")
    combined = "\n".join([bug_analysis, review_notes]).lower()
    if "no-op" in combined or "no code change" in combined or "no source change" in combined:
        return "No code change applied"
    if fix_summary and _diff_indicates_changes(diff_summary):
        return "Fix prepared"
    if "missing information" in jira_parsed.lower() and not fix_summary:
        return "Needs more information"
    if bug_analysis:
        return "Analysis completed"
    if any(path.endswith("test_result.md") for path in missing_results):
        return "Validation pending"
    return "Analysis completed"


def _draft_summary(target: Path) -> str:
    for file_name in ["result_summary.md", "fix_summary.md", "bug_analysis.md", "jira_parsed.md"]:
        text = _read_artifact(target, file_name)
        if text:
            return _cap_artifact(text)
    return "No summary artifact found."


def _artifact_or_missing(target: Path, file_name: str, missing_message: str) -> str:
    text = _read_artifact(target, file_name)
    return _cap_artifact(text) if text else missing_message


def _read_artifact(target: Path, file_name: str) -> str:
    path = target / file_name
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _cap_artifact(text: str) -> str:
    return _cap_text(text.strip(), 2000)


def _cap_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n\n[truncated by hrs-ai]"


def _diff_indicates_changes(diff_summary: str) -> bool:
    if not diff_summary:
        return False
    lowered = diff_summary.lower()
    no_change_markers = ["no diff", "no changes", "no code change", "no source change"]
    return not any(marker in lowered for marker in no_change_markers)


def _search_quality_draft(path: Path) -> str:
    quality = _read_json_default(path, {})
    if not isinstance(quality, dict) or not quality:
        return "No search quality artifact found."
    confidence = str(quality.get("confidence", "unknown"))
    reasons = quality.get("reasons", [])
    lines = [f"Confidence: {confidence}"]
    if isinstance(reasons, list) and reasons:
        lines.append("Reasons:")
        lines.extend(f"- {reason}" for reason in reasons[:5])
    if confidence.lower() == "low":
        lines.append("Implementation location may need manual verification because search confidence is Low.")
    return "\n".join(lines)


def _missing_information_draft(path: Path) -> str:
    text = _read_artifact(path.parent, path.name)
    if not text:
        return "No missing information checklist found."
    section = _section(text, "## Missing Information Checklist")
    return _cap_artifact(section) if section and section != "TBD" else "No missing information checklist found."


def _missing_results_markdown(missing_results: list[str]) -> str:
    if not missing_results:
        return "All expected Copilot result artifacts are present."
    return "\n".join(f"- Missing: {path}" for path in missing_results)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _fetch_message(result: JiraFetchResult) -> str:
    if result.source == "mock":
        return f"{result.error_message} Using mock/demo Jira data."
    return "Fetched Jira data from configured Jira instance."


def _issue_summary(target: Path) -> str | None:
    jira_path = target / "jira.json"
    if not jira_path.exists():
        return None
    try:
        issue = _read_json(jira_path)
    except Exception:
        return None
    fields = issue.get("fields", {}) if isinstance(issue.get("fields"), dict) else {}
    summary = fields.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary
    normalized = issue.get("hrs_ai_normalized", {}) if isinstance(issue.get("hrs_ai_normalized"), dict) else {}
    normalized_summary = normalized.get("summary")
    if isinstance(normalized_summary, str) and normalized_summary.strip():
        return normalized_summary
    return None


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


def _write_status(
    repo_root: Path,
    issue_key: str,
    step_status: dict[str, str],
    generated: list[str],
    fresh: bool | None = None,
    allow_mock: bool | None = None,
) -> None:
    target = _prepare_issue_dir(repo_root, issue_key)
    status = {
        "issue_key": issue_key,
        "mode": "prepare-only",
        "steps": {step: step_status.get(step, "skipped") for step in WORKFLOW_STEPS},
        "generated_files": sorted(generated),
    }
    if fresh is not None:
        status["fresh"] = fresh
    if allow_mock is not None:
        status["allow_mock"] = allow_mock
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


def _build_result_summary(repo_root: Path, issue_key: str) -> str:
    target = issue_dir(repo_root, issue_key)
    status_lines = []
    sections = {}
    for file_name in REQUIRED_COPILOT_RESULT_FILES:
        path = target / file_name
        present = path.exists()
        status_lines.append(f"- {file_name}: {'present' if present else 'missing'}")
        sections[file_name] = path.read_text(encoding="utf-8", errors="replace").strip() if present else "TBD"
    all_present = all((target / file_name).exists() for file_name in REQUIRED_COPILOT_RESULT_FILES)
    next_step = (
        "All result files exist. Recommended next step: run final review."
        if all_present
        else "Some result files are missing. Recommended next step: complete the missing files."
    )
    return (
        "# Result Summary\n\n"
        "## Issue\n"
        f"{issue_key}\n\n"
        "## Result File Status\n"
        + "\n".join(status_lines)
        + "\n\n"
        "## Root Cause Summary\n"
        f"{sections['bug_analysis.md']}\n\n"
        "## Fix Summary\n"
        f"{sections['fix_summary.md']}\n\n"
        "## Test Summary\n"
        f"{sections['test_result.md']}\n\n"
        "## Diff Summary\n"
        f"{sections['diff_summary.md']}\n\n"
        "## Review Notes\n"
        f"{sections['review_notes.md']}\n\n"
        "## Next Step\n"
        f"{next_step}\n"
    )


def _build_manual_validation(repo_root: Path, issue_key: str) -> str:
    target = issue_dir(repo_root, issue_key)
    related = _read_json_default(target / "related_files.json", [])
    review_notes = (target / "review_notes.md").read_text(encoding="utf-8", errors="replace").strip() if (target / "review_notes.md").exists() else ""
    related_lines = []
    if isinstance(related, list) and related:
        for item in related[:10]:
            if isinstance(item, dict) and item.get("file"):
                related_lines.append(f"- {item['file']}")
    if review_notes:
        related_lines.append("- Risks from review_notes.md:")
        related_lines.extend(f"  {line}" for line in review_notes.splitlines() if line.strip())
    return (
        "# Manual Validation\n\n"
        "## Issue\n"
        f"{issue_key}\n\n"
        "## Original Context\n"
        "Reference:\n"
        f".ai/{issue_key}/bug_context.md\n\n"
        "## Suggested Validation Steps\n"
        "1. Reproduce the original issue if possible.\n"
        "2. Confirm the failure no longer occurs.\n"
        "3. Confirm the fix does not change unrelated behavior.\n"
        "4. Run focused tests listed in test_result.md if present.\n"
        "5. Check regression areas mentioned in bug_context.md and code_search.md.\n\n"
        "## Regression Areas\n"
        f"{chr(10).join(related_lines) if related_lines else '- No related files or review risks available yet.'}\n"
    )


def _build_final_review_prompt(issue_key: str) -> str:
    return (
        "# Final Review Request\n\n"
        f"Please review the completed fix for Jira issue {issue_key}.\n\n"
        "Use:\n"
        f"- .ai/{issue_key}/bug_context.md\n"
        f"- .ai/{issue_key}/code_search.md if present\n"
        f"- .ai/{issue_key}/result_summary.md if present\n"
        "- current git diff\n\n"
        "Review focus:\n"
        "1. Correctness\n"
        "2. Regression risk\n"
        "3. Whether the fix matches the Jira issue\n"
        "4. Whether the fix is minimal and safe\n"
        "5. Whether tests are sufficient\n"
        "6. Whether memory entry should be updated\n"
        "7. Any follow-up work\n\n"
        "Expected output:\n"
        "Verdict:\n"
        "PASS / PASS WITH MINOR COMMENTS / NEEDS CHANGES\n\n"
        "Blocking issues:\n"
        "Non-blocking suggestions:\n"
        "Test concerns:\n"
        "Memory update suggestions:\n"
        "Recommended next step:\n"
    )


def _build_final_result_section(result_summary: str, incomplete: bool) -> str:
    marker = "\n\nResult files incomplete. Manual update required." if incomplete else ""
    return (
        "## Final Result\n\n"
        "### Root Cause\n"
        f"{_section(result_summary, '## Root Cause Summary')}\n\n"
        "### Fix\n"
        f"{_section(result_summary, '## Fix Summary')}\n\n"
        "### Tests\n"
        f"{_section(result_summary, '## Test Summary')}\n\n"
        "### Review Notes\n"
        f"{_section(result_summary, '## Review Notes')}{marker}\n\n"
        "### Updated At\n"
        f"{datetime.now(timezone.utc).isoformat()}\n"
    )


def _section(markdown: str, heading: str) -> str:
    lines = markdown.splitlines()
    try:
        start = lines.index(heading) + 1
    except ValueError:
        return "TBD"
    collected = []
    for line in lines[start:]:
        if line.startswith("## ") and collected:
            break
        collected.append(line)
    text = "\n".join(collected).strip()
    return text or "TBD"


def _replace_section(markdown: str, heading: str, replacement: str) -> str:
    start = markdown.find(heading)
    if start == -1:
        return markdown.rstrip() + "\n\n" + replacement
    next_start = markdown.find("\n## ", start + len(heading))
    if next_start == -1:
        return markdown[:start].rstrip() + "\n\n" + replacement
    return markdown[:start].rstrip() + "\n\n" + replacement.rstrip() + "\n" + markdown[next_start:]


def _read_json_default(path: Path, default: object) -> object:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _delivery_warnings(repo_root: Path, issue_key: str) -> list[str]:
    warnings = []
    if not inside_git_repo(repo_root):
        warnings.append("Current directory is not inside a git repository.")
    branch = current_branch(repo_root)
    if not branch:
        warnings.append("Current branch is unavailable.")
    elif branch in {"main", "master"}:
        warnings.append(f"Current branch is {branch}; do not deliver directly from main/master.")
    status = working_tree_status(repo_root)
    if status in {None, "clean"}:
        warnings.append("Working tree has no uncommitted changes visible for delivery.")

    warnings.extend(f"Missing required result file: {file_name}" for file_name in check_result_files(repo_root, issue_key))
    for file_name in [
        f".ai/{issue_key}/result_summary.md",
        f".ai/{issue_key}/final_review_prompt.md",
        f".ai_memory/bugs/{issue_key}.md",
    ]:
        if not (repo_root / file_name).exists():
            warnings.append(f"Missing delivery artifact: {file_name}")
    return warnings


def _build_commit_plan(repo_root: Path, issue_key: str) -> str:
    branch = _git_output(repo_root, ["git", "branch", "--show-current"], "unknown")
    status = _git_output(repo_root, ["git", "status", "--porcelain"], "_No status available._")
    changed_files = _git_output(repo_root, ["git", "diff", "--name-only"], "_No git diff files found._")
    diff_stat = _git_output(repo_root, ["git", "diff", "--stat"], "_No diff stat available._")
    short_summary = _result_summary_line(repo_root, issue_key)
    return (
        "# Commit Plan\n\n"
        "## Issue\n"
        f"{issue_key}\n\n"
        "## Current Branch\n"
        f"{branch}\n\n"
        "## Working Tree Status\n"
        "```text\n"
        f"{status or 'clean'}\n"
        "```\n\n"
        "## Changed Files\n"
        "```text\n"
        f"{changed_files}\n"
        "```\n\n"
        "## Diff Stat\n"
        "```text\n"
        f"{diff_stat}\n"
        "```\n\n"
        "## Suggested Commit Message\n"
        f"Fix {issue_key}: {short_summary}\n\n"
        "## Suggested Commit Body\n"
        "- Root cause:\n"
        "- Fix:\n"
        "- Tests:\n"
        "- Risk:\n\n"
        "## Safety Notes\n"
        "- Confirm branch is not main/master.\n"
        "- Confirm result files are complete.\n"
        "- Confirm tests are complete.\n\n"
        "## Manual Commands\n"
        "```bash\n"
        "git status\n"
        "git add <files>\n"
        f"git commit -m \"Fix {issue_key}: {short_summary}\"\n"
        "```\n"
    )


def _build_push_plan(repo_root: Path, issue_key: str) -> str:
    branch = _git_output(repo_root, ["git", "branch", "--show-current"], "unknown")
    remote = _git_output(repo_root, ["git", "remote", "-v"], "_No remotes configured._")
    recent = _git_output(repo_root, ["git", "log", "--oneline", "-n", "5"], "_No recent commits available._")
    status = _git_output(repo_root, ["git", "status", "--porcelain"], "_No status available._")
    return (
        "# Push Plan\n\n"
        "## Issue\n"
        f"{issue_key}\n\n"
        "## Current Branch\n"
        f"{branch}\n\n"
        "## Remote\n"
        "```text\n"
        f"{remote}\n"
        "```\n\n"
        "## Working Tree Status\n"
        "```text\n"
        f"{status or 'clean'}\n"
        "```\n\n"
        "## Recent Commits\n"
        "```text\n"
        f"{recent}\n"
        "```\n\n"
        "## Safety Checklist\n"
        "- Not on main/master\n"
        "- Result files complete\n"
        "- Review package generated\n"
        "- Memory updated\n\n"
        "## Manual Push Command\n"
        "```bash\n"
        f"git push -u origin {branch or '<current-branch>'}\n"
        "```\n"
    )


def _git_output(repo_root: Path, args: list[str], fallback: str) -> str:
    code, output = run_command(args, repo_root)
    if code != 0:
        return fallback
    cleaned = "\n".join(
        line for line in output.splitlines()
        if not line.startswith("warning:")
    ).strip()
    return cleaned or fallback


def _result_summary_line(repo_root: Path, issue_key: str) -> str:
    path = issue_dir(repo_root, issue_key) / "result_summary.md"
    if not path.exists():
        return "complete AI-assisted bug fix"
    fix = _section(path.read_text(encoding="utf-8", errors="replace"), "## Fix Summary")
    first_line = next((line.strip("- ").strip() for line in fix.splitlines() if line.strip() and line.strip() != "TBD"), "")
    return first_line[:72] or "complete AI-assisted bug fix"
