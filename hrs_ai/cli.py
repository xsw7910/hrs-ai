"""Command line interface for hrs-ai."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from hrs_ai.core import copilot, doctor, workflow
from hrs_ai.core.cleanup import clean_issue_artifacts
from hrs_ai.core.context import build_context
from hrs_ai.core.jira import JiraFetchError, fetch_issue, parse_issue
from hrs_ai.core.keywords import extract_keywords
from hrs_ai.core.memory import add_memory_entry, search_memory
from hrs_ai.core.prompts import generate_prompts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hrs-ai")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="Check local environment readiness.")
    subparsers.add_parser("copilot-check", help="Check Copilot CLI readiness.")

    for name in ("parse", "keywords", "search", "git-context", "context", "prompt", "status", "copilot-task", "copilot-instructions", "summarize-results", "review-package", "delivery-check", "commit-plan", "push-plan"):
        command = subparsers.add_parser(name, help=f"Run the {name} step.")
        command.add_argument("issue_key")

    fetch_parser = subparsers.add_parser("fetch", help="Fetch Jira data.")
    fetch_parser.add_argument("issue_key")
    fetch_mock = fetch_parser.add_mutually_exclusive_group()
    fetch_mock.add_argument("--allow-mock", action="store_true", help="Allow mock/demo fallback when Jira fetch fails.")
    fetch_mock.add_argument("--no-mock", action="store_true", help="Fail instead of generating mock/demo Jira data.")

    jira_validate_parser = subparsers.add_parser("jira-validate", help="Validate Jira issue fetch and field mapping (requires real Jira credentials).")
    jira_validate_parser.add_argument("issue_key")

    clean_parser = subparsers.add_parser("clean", help="Remove generated workflow artifacts for an issue.")
    clean_parser.add_argument("issue_key")
    clean_parser.add_argument("--include-memory", action="store_true", help="Also remove that issue's memory entry.")

    commit_parser = subparsers.add_parser("commit", help="Commit placeholder.")
    commit_parser.add_argument("issue_key")
    commit_parser.add_argument("--execute", action="store_true", help="Placeholder only; execution is disabled.")

    push_parser = subparsers.add_parser("push", help="Push placeholder.")
    push_parser.add_argument("issue_key")
    push_parser.add_argument("--execute", action="store_true", help="Placeholder only; execution is disabled.")

    check_parser = subparsers.add_parser("check-results", help="Check Copilot result files.")
    check_parser.add_argument("issue_key")
    check_parser.add_argument("--strict", action="store_true", help="Exit non-zero when result files are missing.")

    memory_parser = subparsers.add_parser("memory", help="Manage shared AI memory.")
    memory_subparsers = memory_parser.add_subparsers(dest="memory_command", required=True)
    memory_add = memory_subparsers.add_parser("add", help="Add bug memory entry.")
    memory_add.add_argument("issue_key")
    memory_update = memory_subparsers.add_parser("update", help="Update bug memory from result summary.")
    memory_update.add_argument("issue_key")
    memory_search = memory_subparsers.add_parser("search", help="Search shared AI memory.")
    memory_search.add_argument("query")

    bug_parser = subparsers.add_parser("bug", help="Run prepare-only bug workflow.")
    bug_parser.add_argument("issue_key")
    bug_parser.add_argument(
        "--copilot-fix",
        action="store_true",
        help="Print experimental Copilot invocation guidance after preparation.",
    )
    bug_parser.add_argument(
        "--fresh",
        action="store_true",
        help="Remove existing .ai/<issue>/ artifacts before running the workflow.",
    )
    bug_parser.add_argument(
        "--include-memory",
        action="store_true",
        help="With --fresh, also remove that issue's memory entry before rerunning.",
    )
    bug_mock = bug_parser.add_mutually_exclusive_group()
    bug_mock.add_argument("--allow-mock", action="store_true", help="Allow mock/demo fallback when Jira fetch fails.")
    bug_mock.add_argument("--no-mock", action="store_true", help="Fail instead of generating mock/demo Jira data.")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd()

    if args.command == "doctor":
        doctor.print_doctor_report(repo_root)
        return 0

    if args.command == "copilot-check":
        copilot.print_copilot_check()
        return 0

    if args.command == "clean":
        try:
            result = clean_issue_artifacts(repo_root, args.issue_key, include_memory=args.include_memory)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        _print_clean_result(result, include_memory=args.include_memory)
        return 0

    if args.command == "jira-validate":
        try:
            summary = workflow.jira_validate_step(repo_root, args.issue_key)
        except JiraFetchError as exc:
            _print_jira_validate_error(exc)
            return 1
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        _print_jira_validate_summary(args.issue_key, summary)
        return 0

    if args.command == "fetch":
        try:
            result = workflow.fetch_step(repo_root, args.issue_key, allow_mock=_allow_mock(args))
        except JiraFetchError as exc:
            _print_jira_error(exc)
            return 1
        if result.source == "mock":
            print(f"WARN: {result.error_message} Using mock/demo Jira data.")
        print(f"Fetched Jira data for {args.issue_key} into .ai/{args.issue_key}/")
        return 0

    if args.command == "parse":
        workflow.parse_step(repo_root, args.issue_key)
        print(f"Parsed Jira data for {args.issue_key}.")
        return 0

    if args.command == "keywords":
        workflow.keywords_step(repo_root, args.issue_key)
        print(f"Extracted keywords for {args.issue_key}.")
        return 0

    if args.command == "search":
        workflow.code_search_step(repo_root, args.issue_key)
        print(f"Generated code search for {args.issue_key}.")
        return 0

    if args.command == "git-context":
        workflow.git_context_step(repo_root, args.issue_key)
        print(f"Generated git context for {args.issue_key}.")
        return 0

    if args.command == "context":
        workflow.context_step(repo_root, args.issue_key)
        print(f"Generated bug context for {args.issue_key}.")
        return 0

    if args.command == "prompt":
        workflow.prompt_step(repo_root, args.issue_key)
        print(f"Generated prompts for {args.issue_key}.")
        return 0

    if args.command == "copilot-task":
        try:
            workflow.copilot_task_step(repo_root, args.issue_key)
        except FileNotFoundError:
            print(f"Missing .ai/{args.issue_key}/bug_context.md.", file=sys.stderr)
            print(f"Run: hrs-ai bug {args.issue_key}", file=sys.stderr)
            return 1
        print(f"Regenerated Copilot task files for {args.issue_key}.")
        return 0

    if args.command == "copilot-instructions":
        path = workflow.copilot_instructions_step(repo_root, args.issue_key)
        print(f"Generated Copilot team instructions: {path}")
        return 0

    if args.command == "check-results":
        missing = workflow.check_results_step(repo_root, args.issue_key, strict=args.strict)
        if missing:
            print(f"WARN: missing {len(missing)} Copilot result file(s).")
            for file_name in missing:
                print(f"  {file_name}")
            return 1 if args.strict else 0
        else:
            print("PASS: all Copilot result files exist.")
        return 0

    if args.command == "summarize-results":
        workflow.summarize_results_step(repo_root, args.issue_key)
        print(f"Generated result summary and manual validation for {args.issue_key}.")
        return 0

    if args.command == "review-package":
        workflow.review_package_step(repo_root, args.issue_key)
        print(f"Generated final review prompt for {args.issue_key}.")
        return 0

    if args.command == "delivery-check":
        warnings = workflow.delivery_check_step(repo_root, args.issue_key)
        if warnings:
            print("WARN: delivery is not ready.")
            for warning in warnings:
                print(f"  {warning}")
        else:
            print("PASS: ready for manual commit/push.")
        return 0

    if args.command == "commit-plan":
        workflow.commit_plan_step(repo_root, args.issue_key)
        print(f"Generated commit plan for {args.issue_key}.")
        return 0

    if args.command == "push-plan":
        workflow.push_plan_step(repo_root, args.issue_key)
        print(f"Generated push plan for {args.issue_key}.")
        return 0

    if args.command in {"commit", "push"}:
        print("Automatic commit/push execution is not enabled in this prototype.")
        print("Use commit-plan or push-plan and run the commands manually.")
        return 0

    if args.command == "memory":
        if args.memory_command == "add":
            workflow.memory_add_step(repo_root, args.issue_key)
            print(f"Added shared memory entry for {args.issue_key}.")
        elif args.memory_command == "update":
            updated = workflow.memory_update_step(repo_root, args.issue_key)
            if updated:
                print(f"Updated shared memory entry for {args.issue_key}.")
            else:
                print(f"WARN: missing .ai/{args.issue_key}/result_summary.md. Run: hrs-ai summarize-results {args.issue_key}")
        elif args.memory_command == "search":
            issue_key = args.query if workflow.looks_like_issue_key(args.query) else None
            if issue_key:
                workflow.memory_search_step(repo_root, issue_key)
                print(f"Generated memory search for {issue_key}.")
            else:
                _issue_key, markdown, _results = search_memory(repo_root, args.query)
                print(markdown, end="")
        else:
            return 1
        return 0

    if args.command == "status":
        return _print_status(repo_root, args.issue_key)

    if args.command == "bug":
        if args.include_memory and not args.fresh:
            print("ERROR: --include-memory can only be used with --fresh.", file=sys.stderr)
            return 1
        try:
            result = workflow.run_bug_workflow(
                repo_root,
                args.issue_key,
                copilot_fix=args.copilot_fix,
                fresh=args.fresh,
                include_memory=args.include_memory,
                allow_mock=_allow_mock(args),
            )
        except JiraFetchError as exc:
            _print_jira_error(exc)
            return 1
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        if result.jira_result and result.jira_result.source == "mock":
            print(f"WARN: {result.jira_result.error_message} Using mock/demo Jira data.")
        print(f"Prepared hrs-ai workflow package for {args.issue_key}.")
        print(f"Artifacts: {result.issue_dir}")
        print("Next manual Copilot CLI instruction:")
        print(f"  Read .ai/{args.issue_key}/copilot_task.md and complete the workflow.")
        if args.copilot_fix:
            copilot.print_copilot_check()
            copilot.print_auto_invocation_not_implemented(args.issue_key)
        return 0

    return 1


def _print_status(repo_root: Path, issue_key: str) -> int:
    status_path = repo_root / ".ai" / issue_key / "workflow_status.json"
    if not status_path.exists():
        print(f"No workflow status found for {issue_key}.", file=sys.stderr)
        print("Run:", file=sys.stderr)
        print(f"  hrs-ai bug {issue_key}", file=sys.stderr)
        return 1

    status = json.loads(status_path.read_text(encoding="utf-8"))
    print(f"Issue: {status.get('issue_key', issue_key)}")
    print(f"Mode: {status.get('mode', 'unknown')}")
    print("Steps:")
    steps = status.get("steps", {})
    if isinstance(steps, dict):
        for name, step_status in steps.items():
            print(f"  {name}: {step_status}")
    else:
        for step in steps:
            print(f"  {step.get('name')}: {step.get('status')}")
    print("Generated files:")
    for file_name in status.get("generated_files", []):
        print(f"  {file_name}")
    return 0


def _allow_mock(args) -> bool:
    return not getattr(args, "no_mock", False)


def _print_jira_error(exc: JiraFetchError) -> None:
    print(f"ERROR: {exc.result.error_message}", file=sys.stderr)
    print("Mock fallback is disabled by --no-mock.", file=sys.stderr)
    print("No mock Jira artifacts were generated.", file=sys.stderr)


def _print_jira_validate_error(exc: JiraFetchError) -> None:
    print(f"ERROR: {exc.result.error_message}", file=sys.stderr)
    print("jira-validate requires real Jira credentials (JIRA_BASE_URL, JIRA_EMAIL, JIRA_TOKEN).", file=sys.stderr)
    print("No Jira artifacts were generated.", file=sys.stderr)


def _print_jira_validate_summary(issue_key: str, summary: dict) -> None:
    print(f"Jira validation: {issue_key}")
    print(f"  source: {summary.get('source', '')}")
    print(f"  issue type: {summary.get('issue_type', '') or '(not specified)'}")
    print(f"  status: {summary.get('status', '') or '(not specified)'}")
    print(f"  priority: {summary.get('priority', '') or '(not specified)'}")
    print(f"  comments: {summary.get('comment_count', 0)}")
    print(f"  attachments: {summary.get('attachment_count', 0)}")
    print(f"  description: {'yes' if summary.get('has_description') else 'no'}")
    print(f"  reproduction steps found: {'yes' if summary.get('has_reproduction_steps') else 'no'}")
    count = summary.get("missing_information_count", 0)
    print(f"  missing information: {count} item(s)")
    print(f"Generated: .ai/{issue_key}/jira.json")
    print(f"Generated: .ai/{issue_key}/jira_summary.md")
    print(f"Generated: .ai/{issue_key}/jira_parsed.md")
    print(f"Generated: .ai/{issue_key}/jira_field_report.md")


def _print_clean_result(result, include_memory: bool) -> None:
    if f".ai/{result.issue_key}/" in result.deleted_paths:
        print(f"Cleaned workflow artifacts for {result.issue_key}:")
        print(f"  deleted: .ai/{result.issue_key}/")
    else:
        print(f"No workflow artifacts found for {result.issue_key}.")

    memory_path = f".ai_memory/bugs/{result.issue_key}.md"
    if include_memory:
        if memory_path in result.deleted_paths:
            print(f"  deleted memory: {memory_path}")
        else:
            print(f"  memory not found: {memory_path}")
    else:
        print(f"Preserved memory entry: {memory_path}")


__all__ = [
    "build_context",
    "extract_keywords",
    "fetch_issue",
    "generate_prompts",
    "main",
    "parse_issue",
    "add_memory_entry",
    "search_memory",
]
