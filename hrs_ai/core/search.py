"""Ripgrep-based code search and related file ranking."""

from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .git_ops import command_available


INCLUDE_GLOBS = [
    "*.cpp",
    "*.cxx",
    "*.cc",
    "*.h",
    "*.hpp",
    "*.ui",
    "*.qrc",
    "*.py",
    "*.cmake",
    "CMakeLists.txt",
    "*.md",
]
EXCLUDE_DIRS = [
    ".git",
    "build",
    "out",
    "node_modules",
    "vcpkg",
    "third_party",
    "external",
    ".ai",
    ".ai_memory",
    ".venv",
    "__pycache__",
]
MAX_MATCHES_PER_KEYWORD = 20
MAX_SNIPPETS_PER_FILE = 5
MAX_TOTAL_RELATED_FILES = 10
MAX_TOTAL_CODE_SEARCH_LINES = 300


@dataclass
class Match:
    keyword: str
    tier: str
    file: str
    line_number: int
    line: str


@dataclass
class FileScore:
    file: str
    score: int = 0
    matched_keywords: set[str] = field(default_factory=set)
    match_count: int = 0
    snippets: list[Match] = field(default_factory=list)


def run_code_search(repo_root: Path, issue_key: str, keywords: dict[str, object]) -> tuple[str, list[dict[str, object]]]:
    high_value = _keyword_list(keywords.get("high_value_keywords", []))
    normal = _keyword_list(keywords.get("normal_keywords", []))

    if not command_available("rg"):
        markdown = _render_markdown(
            issue_key,
            high_value,
            normal,
            [],
            ["rg is unavailable; code search was skipped."],
        )
        return markdown, []

    all_matches: list[Match] = []
    warnings: list[str] = []
    for keyword in high_value:
        all_matches.extend(_rg_keyword(repo_root, keyword, "high_value", warnings))
    for keyword in normal:
        all_matches.extend(_rg_keyword(repo_root, keyword, "normal", warnings))

    ranked = _rank_related_files(all_matches, high_value, normal)
    if not ranked:
        warnings.append("No code search results found for extracted keywords.")

    markdown = _render_markdown(issue_key, high_value, normal, ranked, warnings)
    related = [
        {
            "file": item.file,
            "score": item.score,
            "matched_keywords": sorted(item.matched_keywords),
            "match_count": item.match_count,
        }
        for item in ranked[:MAX_TOTAL_RELATED_FILES]
    ]
    return markdown, related


def related_files_json(related_files: list[dict[str, object]]) -> str:
    return json.dumps(related_files, indent=2, sort_keys=True) + "\n"


def _keyword_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _rg_keyword(repo_root: Path, keyword: str, tier: str, warnings: list[str]) -> list[Match]:
    args = ["rg", "--line-number", "--no-heading", "--ignore-case", "--fixed-strings"]
    for glob in INCLUDE_GLOBS:
        args.extend(["-g", glob])
    for directory in EXCLUDE_DIRS:
        args.extend(["-g", f"!{directory}/**"])
    args.append(keyword)
    args.append(".")

    try:
        completed = subprocess.run(
            args,
            cwd=repo_root,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=20,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        warnings.append(f"Search failed for keyword `{keyword}`: {exc}")
        return []

    if completed.returncode not in {0, 1}:
        warnings.append(f"Search failed for keyword `{keyword}`: {completed.stderr.strip()}")
        return []

    matches = []
    for line in completed.stdout.splitlines():
        parsed = _parse_rg_line(line)
        if parsed is None:
            continue
        path, line_number, text = parsed
        if not _is_included_path(path):
            continue
        matches.append(Match(keyword=keyword, tier=tier, file=path, line_number=line_number, line=text.strip()))
        if len(matches) >= MAX_MATCHES_PER_KEYWORD:
            break
    return matches


def _parse_rg_line(line: str) -> tuple[str, int, str] | None:
    parts = line.split(":", 2)
    if len(parts) != 3:
        return None
    path, line_number, text = parts
    try:
        normalized = path.replace("\\", "/")
        if normalized.startswith("./"):
            normalized = normalized[2:]
        return normalized, int(line_number), text
    except ValueError:
        return None


def _is_included_path(path: str) -> bool:
    name = Path(path).name
    suffix = Path(path).suffix.lower()
    return name == "CMakeLists.txt" or suffix in {".cpp", ".cxx", ".cc", ".h", ".hpp", ".ui", ".qrc", ".py", ".cmake", ".md"}


def _rank_related_files(matches: list[Match], high_value: list[str], normal: list[str]) -> list[FileScore]:
    scores: dict[str, FileScore] = {}
    high_set = {keyword.lower() for keyword in high_value}
    normal_set = {keyword.lower() for keyword in normal}

    for match in matches:
        item = scores.setdefault(match.file, FileScore(file=match.file))
        keyword = match.keyword.lower()
        if keyword in high_set:
            item.score += 5
        elif keyword in normal_set:
            item.score += 2
        if keyword in match.file.lower():
            item.score += 3
        item.matched_keywords.add(match.keyword)
        item.match_count += 1
        if len(item.snippets) < MAX_SNIPPETS_PER_FILE:
            item.snippets.append(match)

    _apply_header_implementation_bonus(scores)
    return sorted(
        [item for item in scores.values() if item.score >= 3],
        key=lambda item: (-item.score, item.file),
    )[:MAX_TOTAL_RELATED_FILES]


def _apply_header_implementation_bonus(scores: dict[str, FileScore]) -> None:
    by_stem: defaultdict[str, list[FileScore]] = defaultdict(list)
    for item in scores.values():
        path = Path(item.file)
        if path.suffix.lower() in {".h", ".hpp", ".cpp", ".cxx", ".cc"}:
            by_stem[str(path.with_suffix(""))].append(item)
    for items in by_stem.values():
        suffixes = {Path(item.file).suffix.lower() for item in items}
        if suffixes & {".h", ".hpp"} and suffixes & {".cpp", ".cxx", ".cc"}:
            for item in items:
                item.score += 2


def _render_markdown(
    issue_key: str,
    high_value: list[str],
    normal: list[str],
    ranked: list[FileScore],
    warnings: list[str],
) -> str:
    lines = [
        f"# Code Search: {issue_key}",
        "",
        "## Search Keywords",
        "",
        f"- High value: {', '.join(high_value) or '_None_'}",
        f"- Normal: {', '.join(normal) or '_None_'}",
        "",
    ]
    if warnings:
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")

    lines.extend(["## Top Related Files", ""])
    if ranked:
        for item in ranked[:MAX_TOTAL_RELATED_FILES]:
            keywords = ", ".join(sorted(item.matched_keywords))
            lines.append(f"- `{item.file}` score={item.score} matches={item.match_count} keywords={keywords}")
    else:
        lines.append("_No related files found._")
    lines.extend(["", "## Matched Lines", ""])

    line_budget = MAX_TOTAL_CODE_SEARCH_LINES
    for item in ranked:
        if line_budget <= 0:
            break
        lines.append(f"### {item.file}")
        lines.append("")
        line_budget -= 2
        for match in item.snippets:
            if line_budget <= 0:
                break
            lines.append(f"- Line {match.line_number}: `{match.line}`")
            line_budget -= 1
        lines.append("")
        line_budget -= 1
    return "\n".join(lines).rstrip() + "\n"
