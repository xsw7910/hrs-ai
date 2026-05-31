"""Jira fetch and parse helpers with controlled mock fallback."""

from __future__ import annotations

import base64
import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .config import load_config
from .jira_adf import adf_to_markdown


@dataclass
class JiraFetchResult:
    issue_key: str
    source: str
    success: bool
    error_type: str | None
    error_message: str | None
    data: dict


class JiraFetchError(Exception):
    def __init__(self, result: JiraFetchResult):
        super().__init__(result.error_message or "Unexpected Jira error.")
        self.result = result


ERROR_MESSAGES = {
    "missing_env": "Jira environment variables are missing. Set JIRA_BASE_URL, JIRA_EMAIL, and JIRA_TOKEN.",
    "auth_or_permission": "Jira authentication or permission failed. Check Jira credentials and project access.",
    "not_found": "Jira issue was not found or is not accessible. Check issue key and project permissions.",
    "rate_limited": "Jira rate limit reached. Retry later.",
    "timeout": "Jira request timed out. Check VPN, proxy, or network connection.",
    "network_error": "Jira network error. Check VPN, proxy, DNS, and Jira base URL.",
    "invalid_response": "Jira response could not be parsed. Check JIRA_BASE_URL and Jira API version.",
    "unknown_error": "Unexpected Jira error.",
}


COMMENT_RENDER_LIMIT = 10
COMMENT_SIGNAL_TERMS = ["crash", "error", "exception", "stack trace", "repro", "regression", "screenshot", "log"]


def fetch_issue(repo_root: Path, issue_key: str, allow_mock: bool = True) -> JiraFetchResult:
    config = load_config(repo_root)
    if not config.has_jira_credentials:
        failure = _failure(issue_key, "missing_env")
        return _fallback_or_raise(failure, allow_mock)

    url = f"{config.jira_base_url.rstrip('/')}/rest/api/3/issue/{issue_key}?expand=renderedFields"
    token = base64.b64encode(f"{config.jira_email}:{config.jira_token}".encode()).decode()
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Basic {token}",
            "Accept": "application/json",
            "User-Agent": "hrs-ai-prototype/0.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict) or "fields" not in payload:
            failure = _failure(issue_key, "invalid_response")
            return _fallback_or_raise(failure, allow_mock)
        payload["source"] = "jira"
        payload["mock"] = False
        payload["hrs_ai_fetch"] = {"mock": False, "source": "jira", "url": url}
        enrich_issue(payload)
        return JiraFetchResult(
            issue_key=issue_key,
            source="jira",
            success=True,
            error_type=None,
            error_message=None,
            data=payload,
        )
    except urllib.error.HTTPError as exc:
        failure = _failure(issue_key, _http_error_type(exc.code))
        return _fallback_or_raise(failure, allow_mock)
    except TimeoutError:
        failure = _failure(issue_key, "timeout")
        return _fallback_or_raise(failure, allow_mock)
    except socket.timeout:
        failure = _failure(issue_key, "timeout")
        return _fallback_or_raise(failure, allow_mock)
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            failure = _failure(issue_key, "timeout")
        else:
            failure = _failure(issue_key, "network_error")
        return _fallback_or_raise(failure, allow_mock)
    except json.JSONDecodeError:
        failure = _failure(issue_key, "invalid_response")
        return _fallback_or_raise(failure, allow_mock)
    except Exception:
        failure = _failure(issue_key, "unknown_error")
        return _fallback_or_raise(failure, allow_mock)


def parse_issue(issue: dict) -> dict[str, object]:
    # Defensive for standalone parse/backward compatibility with older jira.json files.
    enrich_issue(issue)
    fields = issue.get("fields", {})
    description_text = adf_to_markdown(fields.get("description"))

    normalized = issue.get("hrs_ai_normalized", {}) if isinstance(issue.get("hrs_ai_normalized"), dict) else {}
    comment_details = normalized.get("comments", []) if isinstance(normalized.get("comments"), list) else []
    comments = [str(comment.get("body_markdown", "")) for comment in comment_details if isinstance(comment, dict)]
    attachments = normalized.get("attachments", []) if isinstance(normalized.get("attachments"), list) else []

    text = "\n".join(
        [
            str(fields.get("summary", "")),
            description_text,
            "\n".join(comments),
        ]
    ).strip()

    return {
        "issue_key": issue.get("key"),
        "summary": fields.get("summary", ""),
        "issue_type": _field_name(fields.get("issuetype")),
        "status": _field_name(fields.get("status")),
        "priority": _field_name(fields.get("priority")),
        "labels": fields.get("labels", []) or [],
        "components": [component.get("name", "") for component in (fields.get("components", []) or []) if isinstance(component, dict)],
        "description": description_text,
        "comments": comments,
        "comment_details": comment_details,
        "comment_total": len(comment_details),
        "comment_signal_terms": _comment_signal_terms(comment_details),
        "latest_comment_timestamp": _latest_comment_timestamp(comment_details),
        "attachments": attachments,
        "attachment_kinds": _attachment_kinds(attachments),
        "combined_text": text,
        "is_mock": bool(issue.get("mock") or issue.get("hrs_ai_fetch", {}).get("mock")),
    }


def jira_summary_markdown(issue: dict, fetch_message: str) -> str:
    parsed = parse_issue(issue)
    is_mock = bool(parsed["is_mock"])
    data_source = "mock/demo fallback" if is_mock else "jira"
    reason = issue.get("fallback_reason") or fetch_message
    labels = ", ".join(map(str, parsed.get("labels", []))) or "_None_"
    components = ", ".join(map(str, parsed.get("components", []))) or "_None_"
    comments = parsed.get("comment_details", [])
    comments_text = _comments_markdown(comments if isinstance(comments, list) else [])
    attachments = parsed.get("attachments", [])
    attachments_text = _attachments_markdown(attachments if isinstance(attachments, list) else [])
    return (
        "# Jira Summary\n\n"
        "## Issue\n\n"
        f"{parsed['issue_key']}\n\n"
        "## Data Source\n\n"
        f"{data_source}\n\n"
        "## Fetch Note\n\n"
        f"{reason}\n\n"
        f"**Mock/demo Jira data:** {'yes' if is_mock else 'no'}\n\n"
        "## Summary\n\n"
        f"{parsed['summary'] or '_No summary available._'}\n\n"
        "## Status\n\n"
        f"{parsed['status'] or '_Unknown_'}\n\n"
        "## Priority\n\n"
        f"{parsed['priority'] or '_Unknown_'}\n\n"
        "## Type\n\n"
        f"{parsed['issue_type'] or '_Unknown_'}\n\n"
        "## Labels\n\n"
        f"{labels}\n\n"
        "## Components\n\n"
        f"{components}\n\n"
        "## Description\n\n"
        f"{parsed['description'] or '_No description available._'}\n\n"
        "## Comments\n\n"
        f"{comments_text}\n\n"
        "## Attachments\n\n"
        f"{attachments_text}\n"
    )


def parsed_markdown(parsed: dict[str, object]) -> str:
    comments = parsed.get("comments") or []
    comments_text = "\n\n".join(f"- {comment}" for comment in comments) or "_No comments available._"
    comment_signals = parsed.get("comment_signal_terms", [])
    attachment_kinds = parsed.get("attachment_kinds", [])
    return (
        f"# Parsed Jira: {parsed['issue_key']}\n\n"
        f"- Summary: {parsed['summary']}\n"
        f"- Issue type: {parsed['issue_type']}\n"
        f"- Status: {parsed['status']}\n"
        f"- Priority: {parsed['priority']}\n"
        f"- Mock/demo data: {parsed['is_mock']}\n\n"
        "## Reproduction And Signals\n\n"
        f"{parsed['description'] or '_No reproduction details available yet._'}\n\n"
        "## Comments\n\n"
        f"{comments_text}\n\n"
        "## Comment Signals\n\n"
        f"- Number of comments: {parsed.get('comment_total', 0)}\n"
        f"- Latest comment timestamp: {parsed.get('latest_comment_timestamp') or '_None_'}\n"
        f"- Signals found: {', '.join(map(str, comment_signals)) or '_None_'}\n\n"
        "## Attachment Signals\n\n"
        f"- Number of attachments: {len(parsed.get('attachments', [])) if isinstance(parsed.get('attachments'), list) else 0}\n"
        f"- Attachment kinds found: {', '.join(map(str, attachment_kinds)) or '_None_'}\n\n"
        "## Missing Information Checklist\n\n"
        f"- Description present: {'yes' if parsed.get('description') else 'no'}\n"
        f"- Comments present: {'yes' if comments else 'no'}\n"
        "- Reproduction steps identified: review description/comments above\n"
        "- Expected vs actual behavior identified: review description/comments above\n"
    )


def enrich_issue(issue: dict) -> dict:
    issue["hrs_ai_normalized"] = {
        "comments": normalize_comments(issue),
        "attachments": normalize_attachments(issue),
    }
    return issue


def normalize_comments(issue: dict) -> list[dict[str, str]]:
    fields = issue.get("fields", {}) if isinstance(issue.get("fields"), dict) else {}
    raw_comment = fields.get("comment")
    comment_field = raw_comment if isinstance(raw_comment, dict) else {}
    raw_comments = comment_field.get("comments", []) or []
    comments = []
    for comment in raw_comments:
        if not isinstance(comment, dict):
            continue
        author = comment.get("author", {}) if isinstance(comment.get("author"), dict) else {}
        body = adf_to_markdown(comment.get("body", "")) if comment.get("body") is not None else ""
        comments.append(
            {
                "author": str(author.get("displayName") or author.get("accountId") or ""),
                "created": str(comment.get("created", "") or ""),
                "updated": str(comment.get("updated", "") or ""),
                "body_markdown": body,
                "preview": _preview(body),
            }
        )
    return _ordered_comments(comments)


def normalize_attachments(issue: dict) -> list[dict[str, object]]:
    fields = issue.get("fields", {}) if isinstance(issue.get("fields"), dict) else {}
    raw_attachments = fields.get("attachment", []) or []
    attachments = []
    for attachment in raw_attachments:
        if not isinstance(attachment, dict):
            continue
        author = attachment.get("author", {}) if isinstance(attachment.get("author"), dict) else {}
        filename = str(attachment.get("filename", "") or "")
        mime_type = str(attachment.get("mimeType", "") or "")
        attachments.append(
            {
                "filename": filename,
                "mime_type": mime_type,
                "size": int(attachment.get("size") or 0),
                "created": str(attachment.get("created", "") or ""),
                "author": str(author.get("displayName") or author.get("accountId") or ""),
                "content_url": _safe_url(attachment.get("content")),
                "thumbnail_url": _safe_url(attachment.get("thumbnail")),
                "kind": classify_attachment(filename, mime_type),
            }
        )
    return attachments


def classify_attachment(filename: str, mime_type: str = "") -> str:
    name = filename.lower()
    mime = mime_type.lower()
    suffix = Path(name).suffix
    # Priority is intentional: direct screenshots first, then log/crash name hints,
    # then repro/archive/document extension fallbacks.
    if suffix in {".png", ".jpg", ".jpeg"} or mime.startswith("image/"):
        return "screenshot"
    if suffix in {".log", ".txt"} or "log" in name:
        return "log"
    if suffix in {".dmp", ".dump", ".mdmp"} or "crash" in name:
        return "crash_dump"
    if suffix in {".zip", ".7z", ".tar", ".gz"} or "repro" in name:
        return "repro_project"
    if suffix in {".pdf", ".docx"}:
        return "document"
    return "unknown"


def _comments_markdown(comments: list[object]) -> str:
    if not comments:
        return "No comments found."
    total = len(comments)
    visible = comments[-COMMENT_RENDER_LIMIT:]
    note = f"Showing latest {len(visible)} of {total} comments.\n\n" if total > COMMENT_RENDER_LIMIT else ""
    sections = []
    for index, comment in enumerate(visible, start=1):
        if not isinstance(comment, dict):
            body = str(comment).strip()
            author = ""
            created = ""
            updated = ""
        else:
            body = str(comment.get("body_markdown") or comment.get("body") or "").strip()
            author = str(comment.get("author", "")).strip()
            created = str(comment.get("created", "")).strip()
            updated = str(comment.get("updated", "")).strip()
        meta = []
        if author:
            meta.append(f"Author: {author}")
        if created:
            meta.append(f"Created: {created}")
        if updated:
            meta.append(f"Updated: {updated}")
        sections.append(
            f"### Comment {index}\n\n"
            + ("\n".join(meta) + "\n\n" if meta else "")
            + (body or "_No comment body available._")
        )
    return note + "\n\n".join(sections)


def _attachments_markdown(attachments: list[object]) -> str:
    if not attachments:
        return "No attachments found.\n\nAttachment content is not downloaded by hrs-ai."
    lines = [
        "Attachment content is not downloaded by hrs-ai.",
        "",
        "| Filename | Type | Size | Created | Author |",
        "|---|---|---:|---|---|",
    ]
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        lines.append(
            "| {filename} | {kind} | {size} | {created} | {author} |".format(
                filename=_table_cell(attachment.get("filename", "")),
                kind=_table_cell(attachment.get("kind", "unknown")),
                size=_table_cell(_format_size(attachment.get("size", 0))),
                created=_table_cell(attachment.get("created", "")),
                author=_table_cell(attachment.get("author", "")),
            )
        )
    return "\n".join(lines)


def _field_name(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("name", "") or "")
    return ""


def _ordered_comments(comments: list[dict[str, str]]) -> list[dict[str, str]]:
    created = [comment.get("created", "") for comment in comments]
    if all(created) and created != sorted(created):
        return sorted(comments, key=lambda comment: comment.get("created", ""))
    return comments


def _comment_signal_terms(comments: list[object]) -> list[str]:
    text = "\n".join(
        str(comment.get("body_markdown", "")) for comment in comments if isinstance(comment, dict)
    ).lower()
    return [term for term in COMMENT_SIGNAL_TERMS if term in text]


def _latest_comment_timestamp(comments: list[object]) -> str:
    timestamps = [
        str(comment.get("created", ""))
        for comment in comments
        if isinstance(comment, dict) and comment.get("created")
    ]
    return max(timestamps) if timestamps else ""


def _attachment_kinds(attachments: list[object]) -> list[str]:
    kinds = sorted(
        {
            str(attachment.get("kind", "unknown"))
            for attachment in attachments
            if isinstance(attachment, dict)
        }
    )
    return kinds


def _preview(text: str, limit: int = 160) -> str:
    compact = " ".join(text.split())
    return compact[: limit - 3].rstrip() + "..." if len(compact) > limit else compact


def _safe_url(value: object) -> str:
    if not value:
        return ""
    parts = urlsplit(str(value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _format_size(value: object) -> str:
    try:
        size = int(value)
    except (TypeError, ValueError):
        return ""
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{round(size / 1024)} KB"
    return f"{size} B"


def _table_cell(value: object) -> str:
    return str(value or "").replace("|", "\\|")


def _failure(issue_key: str, error_type: str) -> JiraFetchResult:
    return JiraFetchResult(
        issue_key=issue_key,
        source="jira",
        success=False,
        error_type=error_type,
        error_message=ERROR_MESSAGES.get(error_type, ERROR_MESSAGES["unknown_error"]),
        data={},
    )


def _fallback_or_raise(failure: JiraFetchResult, allow_mock: bool) -> JiraFetchResult:
    if not allow_mock:
        raise JiraFetchError(failure)
    mock = _mock_issue(failure.issue_key, failure.error_type or "unknown_error", failure.error_message or ERROR_MESSAGES["unknown_error"])
    return JiraFetchResult(
        issue_key=failure.issue_key,
        source="mock",
        success=True,
        error_type=failure.error_type,
        error_message=failure.error_message,
        data=mock,
    )


def _http_error_type(status_code: int) -> str:
    if status_code in {401, 403}:
        return "auth_or_permission"
    if status_code == 404:
        return "not_found"
    if status_code == 429:
        return "rate_limited"
    return "unknown_error"


def _mock_issue(issue_key: str, error_type: str, reason: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "key": issue_key,
        "source": "mock",
        "mock": True,
        "fallback_reason": reason,
        "fallback_error_type": error_type,
        "fields": {
            "summary": "Demo bug: employee search returns stale results after filter changes",
            "description": (
                "Mock/demo Jira content. Steps: open the HR employee search, "
                "apply a department filter, change the location filter, and observe stale "
                "results. Expected: results refresh for the new filter set. Actual: prior "
                "department results remain visible until page refresh."
            ),
            "issuetype": {"name": "Bug"},
            "status": {"name": "Open"},
            "priority": {"name": "Medium"},
            "comment": {
                "comments": [
                    {
                        "body": (
                            "Mock/demo note: suspected cache invalidation or query key issue "
                            "around employee search filters."
                        )
                    }
                ]
            },
        },
        "hrs_ai_fetch": {
            "source": "mock",
            "mock": True,
            "fallback_reason": reason,
            "fallback_error_type": error_type,
            "generated_at": now,
        },
    }
