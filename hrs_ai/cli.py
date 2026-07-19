"""Command line interface for hrs-ai."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from hrs_ai.core import agent_runner, copilot, doctor, workflow
from hrs_ai.core.cleanup import clean_issue_artifacts
from hrs_ai.core.context import build_context
from hrs_ai.core.email_notify import EmailSendError
from hrs_ai.core.jira import JiraCommentPostError, JiraFetchError, fetch_issue, parse_issue
from hrs_ai.core.keywords import extract_keywords
from hrs_ai.core.memory import add_memory_entry, search_memory
from hrs_ai.core.prompts import generate_prompts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hrs-ai")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="Check local environment readiness.")
    subparsers.add_parser("copilot-check", help="Check Copilot CLI readiness.")

    for name in ("parse", "keywords", "search", "git-context", "context", "prompt", "status", "copilot-task", "copilot-instructions", "review-package", "delivery-check", "push-plan", "retry-prompt"):
        command = subparsers.add_parser(name, help=f"Run the {name} step.")
        command.add_argument("issue_key")

    summarize_parser = subparsers.add_parser("summarize-results", help="Summarize Copilot results; optionally post a Jira comment so watchers are notified.")
    summarize_parser.add_argument("issue_key")
    summarize_jira = summarize_parser.add_mutually_exclusive_group()
    summarize_jira.add_argument("--jira-comment", action="store_true", help="Post the analysis summary as a Jira comment (Jira then notifies watchers by email).")
    summarize_jira.add_argument("--no-jira-comment", action="store_true", help="Do not post a Jira comment even if HRS_AI_AUTO_JIRA_COMMENT is set.")

    commit_plan_parser = subparsers.add_parser("commit-plan", help="Run the commit-plan step and notify by email at the commit gate.")
    commit_plan_parser.add_argument("issue_key")
    commit_plan_parser.add_argument("--no-email", action="store_true", help="Do not send the commit-gate notification email.")

    notify_parser = subparsers.add_parser("notify", help="Preview or send the post-fix notification email.")
    notify_parser.add_argument("issue_key")
    notify_parser.add_argument("--execute", action="store_true", help="Send the email over SMTP. Without this flag, only a local preview is written.")

    fetch_parser = subparsers.add_parser("fetch", help="Fetch Jira data.")
    fetch_parser.add_argument("issue_key")
    fetch_mock = fetch_parser.add_mutually_exclusive_group()
    fetch_mock.add_argument("--allow-mock", action="store_true", help="Allow mock/demo fallback when Jira fetch fails.")
    fetch_mock.add_argument("--no-mock", action="store_true", help="Require real Jira data. This is the default.")

    jira_validate_parser = subparsers.add_parser("jira-validate", help="Validate Jira issue fetch and field mapping (requires real Jira credentials).")
    jira_validate_parser.add_argument("issue_key")

    jira_comment_parser = subparsers.add_parser("jira-comment-draft", help="Generate a local Jira comment draft from existing hrs-ai artifacts.")
    jira_comment_parser.add_argument("issue_key")
    jira_comment_parser.add_argument("--strict", action="store_true", help="Fail if Copilot result artifacts are missing.")

    jira_post_parser = subparsers.add_parser("jira-comment", help="Preview or explicitly post a Jira comment draft.")
    jira_post_parser.add_argument("issue_key")
    jira_post_parser.add_argument("--execute", action="store_true", help="Post the local Jira comment draft to Jira.")

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

    manual_result_parser = subparsers.add_parser("manual-result", help="Generate developer manual-fix result templates.")
    manual_result_parser.add_argument("issue_key")
    manual_result_parser.add_argument("--overwrite", action="store_true", help="Overwrite existing result files with templates.")

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
    bug_run = bug_parser.add_mutually_exclusive_group()
    bug_run.add_argument(
        "--claude",
        action="store_true",
        help="After preparation, launch Claude in the target repo to complete the workflow.",
    )
    bug_run.add_argument(
        "--copilot",
        action="store_true",
        help="After preparation, launch Copilot CLI in the target repo to complete the workflow.",
    )
    bug_mode = bug_parser.add_mutually_exclusive_group()
    bug_mode.add_argument(
        "--fresh",
        action="store_true",
        help="Remove existing .ai/<issue>/ artifacts before running the workflow. This is the default.",
    )
    bug_mode.add_argument(
        "--resume",
        action="store_true",
        help="Preserve existing .ai/<issue>/ artifacts and continue an existing workflow.",
    )
    bug_parser.add_argument(
        "--include-memory",
        action="store_true",
        help="With fresh mode, also remove that issue's memory entry before rerunning.",
    )
    bug_mock = bug_parser.add_mutually_exclusive_group()
    bug_mock.add_argument("--allow-mock", action="store_true", help="Allow mock/demo fallback when Jira fetch fails.")
    bug_mock.add_argument("--no-mock", action="store_true", help="Require real Jira data. This is the default.")

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

    if args.command == "jira-comment-draft":
        try:
            path = workflow.jira_comment_draft_step(repo_root, args.issue_key, strict=args.strict)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(f"Generated Jira comment draft: {path}")
        return 0

    if args.command == "jira-comment":
        try:
            result = workflow.jira_comment_step(repo_root, args.issue_key, execute=args.execute)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        except JiraCommentPostError as exc:
            print(f"ERROR: {exc.message}", file=sys.stderr)
            return 1
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        if args.execute:
            print(f"Posted Jira comment for {args.issue_key}.")
            print(f"Comment ID: {result.get('comment_id') or '(not returned)'}")
            print(f"Generated: .ai/{args.issue_key}/jira_comment_post_result.json")
            print(f"Generated: .ai/{args.issue_key}/jira_comment_post_summary.md")
        else:
            print(f"Preview Jira comment for {args.issue_key}.")
            print(f"Draft: .ai/{args.issue_key}/jira_comment_draft.md")
            print(f"Length: {result.get('length', 0)} characters")
            print("No Jira comment was posted. Use --execute to post exactly one Jira comment.")
            print()
            print(str(result.get("preview", "")))
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

    if args.command == "retry-prompt":
        try:
            result = workflow.retry_prompt_step(repo_root, args.issue_key)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"Generated retry prompt: {result['prompt']}")
        if "user_feedback" in result:
            print(f"Generated user feedback template: {result['user_feedback']}")
        print(f"Next manual Copilot CLI instruction: Read .ai/{args.issue_key}/copilot_retry_prompt.md and continue the workflow.")
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

    if args.command == "manual-result":
        try:
            result = workflow.manual_result_step(repo_root, args.issue_key, overwrite=args.overwrite)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        if args.overwrite:
            print("WARN: overwrote result files with developer manual-fix templates.")
        print(f"Manual result templates for {args.issue_key}:")
        for file_name in result["created"]:
            print(f"  created: {file_name}")
        for file_name in result["preserved"]:
            print(f"  preserved: {file_name}")
        return 0

    if args.command == "summarize-results":
        workflow.summarize_results_step(repo_root, args.issue_key)
        print(f"Generated result summary and manual validation for {args.issue_key}.")
        if _auto_jira_comment_enabled(args):
            _post_jira_comment_auto(repo_root, args.issue_key)
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
        if not args.no_email:
            _notify_at_commit_gate(repo_root, args.issue_key)
        return 0

    if args.command == "notify":
        try:
            result = workflow.notify_step(repo_root, args.issue_key, execute=args.execute)
        except EmailSendError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            _print_email_env_hint()
            return 1
        _print_notify_result(result)
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
        fresh = not args.resume
        if args.include_memory and args.resume:
            print("ERROR: --include-memory requires fresh mode and cannot be used with --resume.", file=sys.stderr)
            return 1
        print(f"hrs-ai bug {args.issue_key}")
        progress = _bug_progress_printer(args.issue_key)
        try:
            result = workflow.run_bug_workflow(
                repo_root,
                args.issue_key,
                copilot_fix=args.copilot_fix,
                fresh=fresh,
                include_memory=args.include_memory,
                allow_mock=_allow_mock(args),
                progress=progress,
            )
        except JiraFetchError as exc:
            print(f"[ERROR] Fetching Jira issue failed: {exc.result.error_message}", file=sys.stderr)
            _print_log_hint(repo_root, args.issue_key)
            _print_jira_error(exc)
            return 1
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            _print_log_hint(repo_root, args.issue_key)
            return 1
        if result.jira_result and result.jira_result.source == "mock":
            print(f"WARN: {result.jira_result.error_message} Using mock/demo Jira data.")
        if not fresh:
            print(f"Resuming existing workflow package for {args.issue_key}.")
            print("Previous artifacts were preserved.")
        _print_key_generated_artifacts(repo_root, args.issue_key)
        print(f"Prepared hrs-ai workflow package for {args.issue_key}.")
        print(f"Artifacts: .ai/{args.issue_key}")
        print("Next manual Copilot CLI instruction:")
        print(f"  Read .ai/{args.issue_key}/copilot_task.md and complete the workflow.")
        if args.copilot_fix:
            copilot.print_copilot_check()
            copilot.print_auto_invocation_not_implemented(args.issue_key)
        if args.claude or args.copilot:
            agent = "claude" if args.claude else "copilot"
            return _run_agent_after_prepare(repo_root, args.issue_key, agent)
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
    return bool(getattr(args, "allow_mock", False))


def _run_agent_after_prepare(repo_root: Path, issue_key: str, agent: str) -> int:
    print()
    print(f"Launching {agent} to complete the workflow for {issue_key}.")
    print("The agent will analyze, implement the smallest safe fix, write result files,")
    print("and post ONE Jira status comment. It stops at the commit gate and asks before committing.")
    print("Review its changes as third-party code before you commit.")
    result = agent_runner.run_agent(repo_root, issue_key, agent)
    if not result.ran:
        print(f"WARN: could not launch {agent}: {result.skipped_reason}", file=sys.stderr)
        print(f"Open {agent} manually from the target repo root and run:", file=sys.stderr)
        print(f"  Read .ai/{issue_key}/copilot_task.md and complete the workflow.", file=sys.stderr)
        return 1
    if result.returncode not in (0, None):
        print(f"WARN: {agent} exited with code {result.returncode}.", file=sys.stderr)
        return result.returncode
    return 0


def _bug_progress_printer(issue_key: str):
    messages = {
        "doctor": "[1/9] Checking environment...",
        "fetch": f"[2/9] Fetching Jira issue {issue_key}...",
        "parse": "[3/9] Parsing Jira details...",
        "keywords": "[4/9] Extracting keywords...",
        "memory_search": "[5/9] Searching memory...",
        "code_search": "[6/9] Searching codebase...",
        "git_context": "[7/9] Collecting git context...",
        "context": "[8/9] Building bug context...",
        "prompt": "[9/9] Generating Copilot task package...",
    }

    def print_progress(event: str) -> None:
        if event == "clean_start":
            print(f"Cleaning previous workflow artifacts for {issue_key}...")
        elif event == "clean_done":
            print(f"Cleaned previous workflow artifacts for {issue_key}.")
        elif event == "clean_none":
            print(f"No previous workflow artifacts found for {issue_key}.")
        elif event in messages:
            print(messages[event])

    return print_progress


def _print_key_generated_artifacts(repo_root: Path, issue_key: str) -> None:
    key_files = [
        "jira_summary.md",
        "jira_parsed.md",
        "code_search.md",
        "bug_context.md",
        "copilot_task.md",
    ]
    existing = [f".ai/{issue_key}/{file_name}" for file_name in key_files if (repo_root / ".ai" / issue_key / file_name).exists()]
    if not existing:
        return
    print("Generated:")
    for file_name in existing:
        print(f"  {file_name}")


def _print_log_hint(repo_root: Path, issue_key: str) -> None:
    if (repo_root / ".ai" / issue_key / "execution.log").exists():
        print(f"See .ai/{issue_key}/execution.log for details.", file=sys.stderr)


def _auto_jira_comment_enabled(args) -> bool:
    if getattr(args, "no_jira_comment", False):
        return False
    if getattr(args, "jira_comment", False):
        return True
    return os.getenv("HRS_AI_AUTO_JIRA_COMMENT", "").strip().lower() in {"1", "true", "yes", "on"}


def _post_jira_comment_auto(repo_root: Path, issue_key: str) -> None:
    """Post the analysis summary as a Jira comment (best-effort, non-fatal).

    Runs right after the fix results are summarized so Jira notifies watchers by
    email before the developer decides whether to commit. A failure here never
    fails summarize-results.
    """
    try:
        workflow.jira_comment_draft_step(repo_root, issue_key, strict=False)
        result = workflow.jira_comment_step(repo_root, issue_key, execute=True)
    except (JiraCommentPostError, JiraFetchError) as exc:
        message = getattr(exc, "message", None) or getattr(getattr(exc, "result", None), "error_message", None) or str(exc)
        print(f"WARN: auto Jira comment not posted: {message}", file=sys.stderr)
        print("Post manually when ready:  hrs-ai jira-comment-draft "
              f"{issue_key}  then  hrs-ai jira-comment {issue_key} --execute", file=sys.stderr)
        return
    except (FileNotFoundError, ValueError) as exc:
        print(f"WARN: auto Jira comment not posted: {exc}", file=sys.stderr)
        return
    print(f"Posted Jira comment for {issue_key}. Jira will notify watchers by email.")
    print(f"  Comment ID: {result.get('comment_id') or '(not returned)'}")


def _notify_at_commit_gate(repo_root: Path, issue_key: str) -> None:
    """Send the notification email at the commit decision point (best-effort)."""
    try:
        result = workflow.notify_step(repo_root, issue_key, execute=True)
    except EmailSendError as exc:
        print(f"WARN: commit-gate email not sent: {exc}", file=sys.stderr)
        _print_email_env_hint()
        return
    _print_notify_result(result)


def _print_notify_result(result: dict) -> None:
    issue_key = result.get("issue_key")
    if result.get("draft_path"):
        print(f"Email draft: .ai/{issue_key}/email_draft.md")
    if result.get("eml_path"):
        print(f"Outlook-ready file: .ai/{issue_key}/notification.eml")
    if not result.get("execute"):
        print("Preview only. No email was sent.")
        print(f"  To send automatically:  hrs-ai notify {issue_key} --execute   (needs SMTP or Graph configured)")
        print(f"  To send via Outlook:    .\\scripts\\send-via-outlook.ps1 {issue_key}")
        return
    if result.get("sent"):
        recipients = result.get("recipients") or ()
        print(f"Sent notification email via {result.get('transport', 'smtp')} to: {', '.join(recipients)}")
    else:
        print(f"WARN: email not sent. {result.get('skipped_reason', '')}".rstrip())
        _print_email_env_hint()


def _print_email_env_hint() -> None:
    print("To enable automatic email, configure one transport:", file=sys.stderr)
    print(
        "  Graph (recommended for Microsoft 365): GRAPH_TENANT_ID, GRAPH_CLIENT_ID, "
        "GRAPH_CLIENT_SECRET, HRS_AI_EMAIL_FROM, HRS_AI_EMAIL_TO.",
        file=sys.stderr,
    )
    print(
        "  SMTP: SMTP_HOST, HRS_AI_EMAIL_FROM, HRS_AI_EMAIL_TO "
        "(and SMTP_USERNAME/SMTP_PASSWORD if the relay needs auth).",
        file=sys.stderr,
    )
    print("Store secrets in a secrets manager; do not hardcode them.", file=sys.stderr)
    print("No transport configured? Send via Outlook: .\\scripts\\send-via-outlook.ps1 <ISSUE>", file=sys.stderr)


def _print_jira_error(exc: JiraFetchError) -> None:
    print(f"ERROR: {exc.result.error_message}", file=sys.stderr)
    print("Mock fallback is disabled by default.", file=sys.stderr)
    print("Use --allow-mock only for demo/testing fallback.", file=sys.stderr)
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
