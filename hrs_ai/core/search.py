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
LOW_VALUE_KEYWORDS = {
    "crash",
    "error",
    "failed",
    "issue",
    "problem",
    "stale",
    "result",
    "results",
    "change",
    "changes",
    "update",
}
MEDIUM_VALUE_KEYWORDS = {
    "import",
    "filter",
    "search",
    "export",
    "volume",
    "project",
}
NOISE_PATH_INDICATORS = {
    ".github": "build_or_ci_path",
    ".gitlab": "build_or_ci_path",
    "ci": "build_or_ci_path",
    "build": "build_or_ci_path",
    "out": "build_or_ci_path",
    "cmake": "build_or_ci_path",
    "scripts/build": "build_or_ci_path",
    "license": "license_or_sdk_path",
    "licensing": "license_or_sdk_path",
    "sdk": "license_or_sdk_path",
    "third_party": "vendor_or_external_path",
    "external": "vendor_or_external_path",
    "vendor": "vendor_or_external_path",
    "generated": "generated_path",
    "auto_generated": "generated_path",
    "testdata": "testdata_path",
    "docs": "docs_or_examples_path",
    "documentation": "docs_or_examples_path",
    "examples": "docs_or_examples_path",
    "sample": "docs_or_examples_path",
}
APPLICATION_PATH_INDICATORS = {
    "src",
    "source",
    "lib",
    "app",
    "modules",
    "plugins",
}


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
    confidence: str = "low"
    reasons: list[str] = field(default_factory=list)
    noise_flags: list[str] = field(default_factory=list)
    keyword_quality_counts: dict[str, int] = field(default_factory=lambda: {"high": 0, "medium": 0, "low": 0})


def run_code_search(repo_root: Path, issue_key: str, keywords: dict[str, object]) -> tuple[str, list[dict[str, object]], dict[str, object]]:
    high_value = _keyword_list(keywords.get("high_value_keywords", []))
    normal = _keyword_list(keywords.get("normal_keywords", []))
    phrases = _keyword_list(keywords.get("phrase_keywords", []))

    if not command_available("rg"):
        quality = _overall_quality([], ["rg is unavailable; code search was skipped."])
        markdown = _render_markdown(
            issue_key,
            high_value,
            normal,
            phrases,
            [],
            ["rg is unavailable; code search was skipped."],
            quality,
        )
        return markdown, [], quality

    all_matches: list[Match] = []
    warnings: list[str] = []
    # Exact quoted phrases first — an exact UI/error-string hit is the strongest
    # signal (rg --fixed-strings matches the literal string, spaces included).
    for phrase in phrases:
        all_matches.extend(_rg_keyword(repo_root, phrase, "phrase", warnings))
    for keyword in high_value:
        all_matches.extend(_rg_keyword(repo_root, keyword, "high_value", warnings))
    for keyword in normal:
        all_matches.extend(_rg_keyword(repo_root, keyword, "normal", warnings))

    ranked = _rank_related_files(all_matches, high_value, normal)
    if not ranked:
        warnings.append("No code search results found for extracted keywords.")

    related = _related_files(ranked)
    quality = _overall_quality(related, warnings)
    markdown = _render_markdown(issue_key, high_value, normal, phrases, ranked, warnings, quality)
    return markdown, related, quality


def _related_files(ranked: list[FileScore]) -> list[dict[str, object]]:
    related = [
        {
            "file": item.file,
            "score": item.score,
            "confidence": item.confidence,
            "matched_keywords": sorted(item.matched_keywords),
            "match_count": item.match_count,
            "reasons": item.reasons,
            "noise_flags": item.noise_flags,
        }
        for item in ranked[:MAX_TOTAL_RELATED_FILES]
    ]
    return related


def related_files_json(related_files: list[dict[str, object]]) -> str:
    return json.dumps(related_files, indent=2, sort_keys=True) + "\n"


def search_quality_json(search_quality: dict[str, object]) -> str:
    return json.dumps(search_quality, indent=2, sort_keys=True) + "\n"


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
        if match.tier == "phrase":
            # Exact quoted-string hit — the strongest, most specific signal.
            item.score += 10
            item.keyword_quality_counts["high"] += 1
            if "exact phrase match" not in item.reasons:
                item.reasons.append("exact phrase match")
        else:
            keyword = match.keyword.lower()
            quality = _keyword_quality(match.keyword, keyword in high_set, keyword in normal_set)
            if quality == "high":
                item.score += 8 if match.keyword.lower() in match.line.lower() else 5
                item.keyword_quality_counts["high"] += 1
            elif quality == "medium":
                item.score += 2
                item.keyword_quality_counts["medium"] += 1
            else:
                item.score += 1
                item.keyword_quality_counts["low"] += 1
            if keyword in match.file.lower():
                item.score += 3 if quality == "high" else 1
        item.matched_keywords.add(match.keyword)
        item.match_count += 1
        if len(item.snippets) < MAX_SNIPPETS_PER_FILE:
            item.snippets.append(match)

    _apply_header_implementation_bonus(scores)
    for item in scores.values():
        _apply_path_adjustments(item)
        _assign_confidence(item)
    return sorted(
        list(scores.values()),
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
                item.reasons.append("header/source pair bonus")


def _keyword_quality(keyword: str, in_high_value: bool, in_normal: bool) -> str:
    lower = keyword.lower()
    if lower in LOW_VALUE_KEYWORDS:
        return "low"
    if _looks_like_specific_identifier(keyword):
        return "high"
    if in_high_value and lower not in MEDIUM_VALUE_KEYWORDS:
        return "high"
    if lower in MEDIUM_VALUE_KEYWORDS or in_normal:
        return "medium"
    return "low"


def _looks_like_specific_identifier(keyword: str) -> bool:
    return (
        any(char.islower() for char in keyword) and any(char.isupper() for char in keyword)
    ) or "." in keyword or "/" in keyword or "\\" in keyword or "::" in keyword or '"' in keyword


def _apply_path_adjustments(item: FileScore) -> None:
    flags = _noise_flags(item.file)
    if flags:
        item.noise_flags = flags
        item.score -= 4
        item.reasons.append("path looks like CI/build/license/vendor/docs/generated content")
    if _is_application_path(item.file):
        item.score += 3
        item.reasons.append("matched keyword in application source path")


def _noise_flags(path: str) -> list[str]:
    normalized = path.replace("\\", "/").lower()
    parts = [part for part in normalized.split("/") if part]
    flags: set[str] = set()
    for indicator, flag in NOISE_PATH_INDICATORS.items():
        if "/" in indicator:
            if indicator in normalized:
                flags.add(flag)
        elif indicator in parts:
            flags.add(flag)
    return sorted(flags)


def _is_application_path(path: str) -> bool:
    parts = [part.lower() for part in path.replace("\\", "/").split("/") if part]
    return any(part in APPLICATION_PATH_INDICATORS for part in parts)


def _assign_confidence(item: FileScore) -> None:
    high = item.keyword_quality_counts["high"]
    medium = item.keyword_quality_counts["medium"]
    low = item.keyword_quality_counts["low"]
    has_app_path = _is_application_path(item.file)
    has_noise = bool(item.noise_flags)
    if high and has_app_path and not has_noise:
        item.confidence = "high"
        item.reasons.append("matched high-value keyword in application source path")
    elif (high or medium) and (has_app_path or not has_noise):
        item.confidence = "medium"
        item.reasons.append("matched plausible implementation keyword")
    else:
        item.confidence = "low"
        if low and not high and not medium:
            item.reasons.append("matched only generic keyword")
        if has_noise:
            item.reasons.append("match appears in noisy path")
    if not item.reasons:
        item.reasons.append("keyword match candidate")


def _overall_quality(related: list[dict[str, object]], warnings: list[str]) -> dict[str, object]:
    high_files = [str(item["file"]) for item in related if item.get("confidence") == "high"]
    medium_files = [str(item["file"]) for item in related if item.get("confidence") == "medium"]
    low_files = [str(item["file"]) for item in related if item.get("confidence") == "low"]
    noise_indicators = sorted(
        {
            str(flag)
            for item in related
            for flag in item.get("noise_flags", [])
        }
    )
    reasons: list[str] = []
    if high_files:
        confidence = "high"
        reasons.append("At least one high-confidence application source file was found.")
    elif medium_files:
        confidence = "medium"
        reasons.append("Some plausible application or implementation files were matched.")
    else:
        confidence = "low"
        reasons.append("No high-confidence application source file was found.")

    if related and len(low_files) >= max(1, len(related) // 2) and not high_files:
        reasons.append("Matches are mostly from low-value keywords or weak candidates.")
        confidence = "low" if not medium_files else confidence
    if noise_indicators:
        reasons.append("Several matches appear in build/CI/license/vendor/docs/generated paths.")
        if not high_files:
            confidence = "low"
    if not related:
        confidence = "low"
        reasons.append("No related files were found.")
    reasons.extend(warnings)
    return {
        "confidence": confidence,
        "reasons": reasons,
        "high_confidence_files": high_files,
        "medium_confidence_files": medium_files,
        "low_confidence_files": low_files,
        "noise_indicators": noise_indicators,
    }


def _render_markdown(
    issue_key: str,
    high_value: list[str],
    normal: list[str],
    phrases: list[str],
    ranked: list[FileScore],
    warnings: list[str],
    quality: dict[str, object],
) -> str:
    lines = [
        f"# Code Search: {issue_key}",
        "",
        "## Search Quality",
        "",
        f"Confidence: {str(quality.get('confidence', 'low')).title()}",
        "",
        "Reasons:",
    ]
    reasons = quality.get("reasons", [])
    if isinstance(reasons, list) and reasons:
        lines.extend(f"- {reason}" for reason in reasons)
    else:
        lines.append("- No search quality reasons available.")
    phrase_str = ", ".join('"' + phrase + '"' for phrase in phrases) or "_None_"
    lines.extend(
        [
            "",
            "## Search Keywords",
            "",
            f"- High value: {', '.join(high_value) or '_None_'}",
            f"- Normal: {', '.join(normal) or '_None_'}",
            f"- Phrases: {phrase_str}",
            "",
        ]
    )
    if warnings:
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")

    lines.extend(["## High-Confidence Matches", ""])
    high_ranked = [item for item in ranked if item.confidence == "high"]
    if high_ranked:
        for item in high_ranked:
            lines.append(f"- `{item.file}` score={item.score} matches={item.match_count}")
    else:
        lines.append("_No high-confidence matches found._")
    lines.extend(["", "## Low-Confidence / Possible False Positives", ""])
    low_ranked = [item for item in ranked if item.confidence == "low"]
    if low_ranked:
        for item in low_ranked:
            flags = ", ".join(item.noise_flags) or "none"
            lines.append(f"- `{item.file}` score={item.score} noise={flags}")
    else:
        lines.append("_No low-confidence matches found._")
    lines.append("")

    lines.extend(["## Top Related Files", ""])
    if ranked:
        for item in ranked[:MAX_TOTAL_RELATED_FILES]:
            keywords = ", ".join(sorted(item.matched_keywords))
            lines.append(f"- `{item.file}` confidence={item.confidence} score={item.score} matches={item.match_count} keywords={keywords}")
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
