"""Command line interface for hrs-ai."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from hrs_ai.core import copilot, doctor, workflow
from hrs_ai.core.context import build_context
from hrs_ai.core.jira import fetch_issue, parse_issue
from hrs_ai.core.keywords import extract_keywords
from hrs_ai.core.memory import add_memory_entry
from hrs_ai.core.prompts import generate_prompts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hrs-ai")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="Check local environment readiness.")
    subparsers.add_parser("copilot-check", help="Check Copilot CLI readiness.")

    for name in ("fetch", "parse", "keywords", "context", "prompt", "status"):
        command = subparsers.add_parser(name, help=f"Run the {name} step.")
        command.add_argument("issue_key")

    memory_parser = subparsers.add_parser("memory", help="Manage shared AI memory.")
    memory_subparsers = memory_parser.add_subparsers(dest="memory_command", required=True)
    memory_add = memory_subparsers.add_parser("add", help="Add bug memory entry.")
    memory_add.add_argument("issue_key")

    bug_parser = subparsers.add_parser("bug", help="Run prepare-only bug workflow.")
    bug_parser.add_argument("issue_key")
    bug_parser.add_argument(
        "--copilot-fix",
        action="store_true",
        help="Print experimental Copilot invocation guidance after preparation.",
    )

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

    if args.command == "fetch":
        workflow.fetch_step(repo_root, args.issue_key)
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

    if args.command == "context":
        workflow.context_step(repo_root, args.issue_key)
        print(f"Generated bug context for {args.issue_key}.")
        return 0

    if args.command == "prompt":
        workflow.prompt_step(repo_root, args.issue_key)
        print(f"Generated prompts for {args.issue_key}.")
        return 0

    if args.command == "memory":
        workflow.memory_add_step(repo_root, args.issue_key)
        print(f"Added shared memory entry for {args.issue_key}.")
        return 0

    if args.command == "status":
        return _print_status(repo_root, args.issue_key)

    if args.command == "bug":
        result = workflow.run_bug_workflow(repo_root, args.issue_key)
        print(f"Prepared hrs-ai workflow package for {args.issue_key}.")
        print(f"Artifacts: {result.issue_dir}")
        print("Next manual Copilot CLI instruction:")
        print(f"  Read .ai/{args.issue_key}/copilot_task.md and complete the workflow.")
        if args.copilot_fix:
            copilot.print_auto_invocation_not_implemented(args.issue_key)
        return 0

    return 1


def _print_status(repo_root: Path, issue_key: str) -> int:
    status_path = repo_root / ".ai" / issue_key / "workflow_status.json"
    if not status_path.exists():
        print(f"No workflow status found at {status_path}", file=sys.stderr)
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


__all__ = [
    "build_context",
    "extract_keywords",
    "fetch_issue",
    "generate_prompts",
    "main",
    "parse_issue",
    "add_memory_entry",
]
