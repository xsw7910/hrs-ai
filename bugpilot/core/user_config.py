"""User-level BugPilot configuration stored under the home directory.

This is distinct from :mod:`bugpilot.core.config`, which reads process environment
variables. ``bugpilot setup`` writes a small ``config.toml`` here so a first-time
user does not have to export ``JIRA_*`` variables by hand. Environment variables
still win over this file (see :func:`bugpilot.core.config.load_config`).

The company Jira URL is fixed and is NOT persisted. Only ``jira_email`` and (for
now) ``jira_token`` are stored. Token persistence goes through :class:`TokenStore`
so it can later be swapped for the Windows Credential Manager without touching the
rest of the code.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

# The company Jira site is fixed. It is never edited by the user and never saved
# to disk; it is the default base URL everywhere JIRA_BASE_URL is not set.
DEFAULT_JIRA_BASE_URL = "https://geosoftwaretech.atlassian.net"

CONFIG_DIR_ENV = "BUGPILOT_CONFIG_DIR"
_CONFIG_FILE_NAME = "config.toml"


@dataclass(frozen=True)
class UserConfig:
    jira_email: str | None = None
    jira_token: str | None = None


def user_config_dir() -> Path:
    """Directory holding the user's BugPilot config (``~/.bugpilot`` by default).

    Overridable via the ``BUGPILOT_CONFIG_DIR`` environment variable, which keeps
    tests hermetic and lets advanced users relocate the file.
    """
    override = os.getenv(CONFIG_DIR_ENV)
    if override and override.strip():
        return Path(override.strip())
    return Path.home() / ".bugpilot"


def user_config_path() -> Path:
    return user_config_dir() / _CONFIG_FILE_NAME


# --- token storage seam -----------------------------------------------------


class TokenStore(ABC):
    """Where the Jira API token lives.

    The default keeps the token inline in ``config.toml``. A future
    ``CredentialManagerTokenStore`` can implement the same two methods to move
    the token into the Windows Credential Manager without changing callers.
    """

    @abstractmethod
    def load(self, config_data: dict[str, str]) -> str | None:
        """Return the token, given the already-parsed config table."""

    @abstractmethod
    def save(self, config_data: dict[str, str], token: str | None) -> None:
        """Persist the token. May mutate ``config_data`` (the file table)."""


class FileTokenStore(TokenStore):
    """Stores the token inline in ``config.toml`` (current default)."""

    def load(self, config_data: dict[str, str]) -> str | None:
        token = config_data.get("jira_token")
        return token or None

    def save(self, config_data: dict[str, str], token: str | None) -> None:
        if token:
            config_data["jira_token"] = token
        else:
            config_data.pop("jira_token", None)


def _token_store() -> TokenStore:
    # Future: return a Windows Credential Manager store on win32 once implemented.
    return FileTokenStore()


# --- load / save ------------------------------------------------------------


def load_user_config() -> UserConfig:
    path = user_config_path()
    if not path.exists():
        return UserConfig()
    data = _parse_toml(path.read_text(encoding="utf-8"))
    email = data.get("jira_email") or None
    token = _token_store().load(data)
    return UserConfig(jira_email=email, jira_token=token)


def save_user_config(jira_email: str, jira_token: str | None) -> Path:
    """Write ``jira_email`` (and, via the token store, the token) to config.toml.

    The fixed company Jira URL is intentionally not written. Returns the path.
    """
    path = user_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, str] = {"jira_email": jira_email}
    _token_store().save(data, jira_token)
    path.write_text(_dump_toml(data), encoding="utf-8")
    _restrict_permissions(path)
    return path


def _restrict_permissions(path: Path) -> None:
    """Best-effort tighten of file permissions (the file may hold a token)."""
    try:
        os.chmod(path, 0o600)
    except OSError:
        # No-op where chmod is unsupported (e.g. some Windows filesystems).
        pass


# --- minimal flat-TOML reader/writer ----------------------------------------
# BugPilot has no third-party dependencies and targets Python 3.10 (no stdlib
# tomllib), and this file is always a flat table of string keys that we alone
# write. A small, well-scoped reader/writer keeps that contract without adding a
# dependency. It is not a general TOML implementation.

_ESCAPES = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t"}
_UNESCAPES = {"\\\\": "\\", '\\"': '"', "\\n": "\n", "\\r": "\r", "\\t": "\t"}


def _dump_toml(data: dict[str, str]) -> str:
    lines = []
    for key, value in data.items():
        lines.append(f'{key} = "{_escape(value)}"')
    return "\n".join(lines) + "\n"


def _parse_toml(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            value = _unescape(value[1:-1])
        if key:
            result[key] = value
    return result


def _escape(value: str) -> str:
    out = []
    for ch in value:
        out.append(_ESCAPES.get(ch, ch))
    return "".join(out)


def _unescape(value: str) -> str:
    out = []
    i = 0
    while i < len(value):
        pair = value[i:i + 2]
        if pair in _UNESCAPES:
            out.append(_UNESCAPES[pair])
            i += 2
        else:
            out.append(value[i])
            i += 1
    return "".join(out)
