"""Deterministic prepare-only workflow orchestration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .cleanup import clean_issue_artifacts, validate_issue_key
from .config import WORKFLOW_STEPS, issue_dir
from .context import build_context
from .doctor import collect_doctor_report
from .git_ops import current_branch, generate_git_context, inside_git_repo, run_command, working_tree_status
from .jira import JiraFetchError, JiraFetchResult, fetch_issue, jira_summary_markdown, parse_issue, parsed_markdown
from .keywords import extract_keywords, keywords_json
from .logging_utils import log
from .memory import ISSUE_KEY_RE, add_memory_entry, build_memory_entry, search_memory
from .prompts import generate_copilot_task_files, generate_prompts
from .search import related_files_json, run_code_search


@dataclass
class WorkflowResult:
    issue_key: str
    issue_dir: Path
    generated_files: list[str]
    jira_result: JiraFetchResult | None = None


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
    fresh: bool = False,
    include_memory: bool = False,
    allow_mock: bool = True,
) -> WorkflowResult:
    clean_result = None
    if fresh:
        validate_issue_key(issue_key)
        clean_result = clean_issue_artifacts(repo_root, issue_key, include_memory=include_memory)

    target = _prepare_issue_dir(repo_root, issue_key)
    command = f"hrs-ai bug {issue_key}"
    if fresh:
        command += " --fresh"
    if include_memory:
        command += " --include-memory"
    if not allow_mock:
        command += " --no-mock"
    log(target, f"[START] command: {command}")
    if fresh:
        log(target, "[INFO] fresh run requested")
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

    try:
        log(target, "[START] doctor")
        doctor_report = collect_doctor_report(repo_root)
        log(target, f"doctor report: {doctor_report}")
        _mark_step(repo_root, issue_key, "doctor", "pass")
        log(target, "[END] doctor: pass")

        jira_result = fetch_step(repo_root, issue_key, allow_mock=allow_mock)
        parse_step(repo_root, issue_key)
        keywords_step(repo_root, issue_key)
        memory_search_step(repo_root, issue_key)
        code_search_step(repo_root, issue_key)
        git_context_step(repo_root, issue_key)
        context_step(repo_root, issue_key)
        prompt_step(repo_root, issue_key)
        memory_add_step(repo_root, issue_key)
    except Exception as exc:
        log(target, f"[ERROR] workflow: {exc}")
        _write_status(repo_root, issue_key, _read_step_status(repo_root, issue_key), _generated_files(repo_root, issue_key))
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
    )
    return WorkflowResult(issue_key=issue_key, issue_dir=target, generated_files=generated, jira_result=jira_result)


def fetch_step(repo_root: Path, issue_key: str, allow_mock: bool = True) -> JiraFetchResult:
    target = _prepare_issue_dir(repo_root, issue_key)
    log(target, "[START] fetch")
    try:
        result = fetch_issue(repo_root, issue_key, allow_mock=allow_mock)
        issue = result.data
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
        log(target, "[ERROR] Mock fallback disabled by --no-mock")
        log(target, "[END] fetch: fail")
        raise
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
        markdown, related_files = run_code_search(repo_root, issue_key, keywords)
        (target / "code_search.md").write_text(markdown, encoding="utf-8")
        (target / "related_files.json").write_text(related_files_json(related_files), encoding="utf-8")
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
        for file_name, content in generate_prompts(issue_key).items():
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
        for file_name, content in generate_copilot_task_files(issue_key).items():
            (target / file_name).write_text(content, encoding="utf-8")
        log(target, "[END] copilot_task: pass")
    except Exception as exc:
        log(target, f"[ERROR] copilot_task: {exc}")
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


def _fetch_message(result: JiraFetchResult) -> str:
    if result.source == "mock":
        return f"{result.error_message} Using mock/demo Jira data."
    return "Fetched Jira data from configured Jira instance."


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
