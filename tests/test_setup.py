from __future__ import annotations

import json
import urllib.error

import pytest

from hrs_ai.cli import main
from hrs_ai.core.config import load_config
from hrs_ai.core.jira import JiraValidationResult, validate_credentials
from hrs_ai.core.setup import run_setup
from hrs_ai.core.user_config import (
    DEFAULT_JIRA_BASE_URL,
    UserConfig,
    load_user_config,
    save_user_config,
    user_config_path,
)


@pytest.fixture(autouse=True)
def clear_jira_env(monkeypatch):
    for name in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_TOKEN"):
        monkeypatch.delenv(name, raising=False)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# --- user_config ------------------------------------------------------------


def test_save_and_load_round_trip():
    path = save_user_config("shiwei.xing@geosoftware.com", "tok-123")
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert 'jira_email = "shiwei.xing@geosoftware.com"' in text
    assert 'jira_token = "tok-123"' in text
    # The fixed company URL is never written to disk.
    assert "atlassian.net" not in text
    assert "jira_url" not in text and "jira_base_url" not in text

    cfg = load_user_config()
    assert cfg.jira_email == "shiwei.xing@geosoftware.com"
    assert cfg.jira_token == "tok-123"


def test_load_missing_config_returns_empty():
    assert load_user_config() == UserConfig()


def test_toml_round_trips_special_characters():
    save_user_config('a"b', "c\\d")
    cfg = load_user_config()
    assert cfg.jira_email == 'a"b'
    assert cfg.jira_token == "c\\d"


# --- validate_credentials ---------------------------------------------------


def test_validate_credentials_ok(monkeypatch):
    monkeypatch.setattr(
        "hrs_ai.core.jira.urllib.request.urlopen",
        lambda request, timeout: _FakeResponse({"emailAddress": "e@x.com", "displayName": "Dev"}),
    )
    result = validate_credentials("https://x.atlassian.net", "e@x.com", "tok")
    assert result.ok
    assert result.account_email == "e@x.com"
    assert result.display_name == "Dev"


def test_validate_credentials_auth_failure(monkeypatch):
    def raise_http(request, timeout):
        raise urllib.error.HTTPError("url", 401, "Unauthorized", None, None)

    monkeypatch.setattr("hrs_ai.core.jira.urllib.request.urlopen", raise_http)
    result = validate_credentials("https://x", "e", "bad")
    assert not result.ok
    assert result.error_type == "auth_or_permission"
    assert result.error_message


def test_validate_credentials_network_error(monkeypatch):
    def raise_url(request, timeout):
        raise urllib.error.URLError("host down")

    monkeypatch.setattr("hrs_ai.core.jira.urllib.request.urlopen", raise_url)
    result = validate_credentials("https://x", "e", "t")
    assert not result.ok
    assert result.error_type == "network_error"


# --- load_config integration ------------------------------------------------


def test_load_config_uses_user_config_and_fixed_url(tmp_path):
    save_user_config("e@x.com", "tok")
    cfg = load_config(tmp_path)
    assert cfg.jira_base_url == DEFAULT_JIRA_BASE_URL
    assert cfg.jira_email == "e@x.com"
    assert cfg.jira_token == "tok"
    assert cfg.has_jira_credentials


def test_env_overrides_user_config(monkeypatch, tmp_path):
    save_user_config("file@x.com", "filetok")
    monkeypatch.setenv("JIRA_EMAIL", "env@x.com")
    monkeypatch.setenv("JIRA_TOKEN", "envtok")
    monkeypatch.setenv("JIRA_BASE_URL", "https://custom.example.com")
    cfg = load_config(tmp_path)
    assert cfg.jira_email == "env@x.com"
    assert cfg.jira_token == "envtok"
    assert cfg.jira_base_url == "https://custom.example.com"


# --- run_setup flow ---------------------------------------------------------


def _all_tools_present(monkeypatch):
    monkeypatch.setattr("hrs_ai.core.git_ops.command_available", lambda command: True)


def test_run_setup_success_saves_config(monkeypatch):
    _all_tools_present(monkeypatch)
    monkeypatch.setattr(
        "hrs_ai.core.jira.validate_credentials",
        lambda base_url, email, token, timeout=30: JiraValidationResult(ok=True, account_email=email),
    )
    emails = iter(["shiwei.xing@geosoftware.com"])
    tokens = iter(["tok-123"])
    out = []

    rc = run_setup(prompt=lambda p: next(emails), prompt_secret=lambda p: next(tokens), out=out.append)

    text = "\n".join(out)
    assert rc == 0
    assert "BugPilot Setup" in text
    assert DEFAULT_JIRA_BASE_URL in text
    assert "Login successful" in text
    assert "Setup completed!" in text
    assert "bugpilot HR-26609" in text

    cfg = load_user_config()
    assert cfg.jira_email == "shiwei.xing@geosoftware.com"
    assert cfg.jira_token == "tok-123"


def test_run_setup_auth_failure_does_not_save(monkeypatch):
    _all_tools_present(monkeypatch)
    monkeypatch.setattr(
        "hrs_ai.core.jira.validate_credentials",
        lambda *a, **k: JiraValidationResult(ok=False, error_type="auth_or_permission", error_message="x"),
    )
    out = []

    rc = run_setup(prompt=lambda p: "e@x.com", prompt_secret=lambda p: "bad", out=out.append)

    text = "\n".join(out)
    assert rc == 1
    assert "Authentication failed." in text
    assert "bugpilot setup" in text
    # Bad credentials are never persisted.
    assert not user_config_path().exists()
    assert load_user_config() == UserConfig()


def test_run_setup_warns_when_copilot_missing(monkeypatch):
    availability = {"git": True, "rg": True, "copilot": False}
    monkeypatch.setattr("hrs_ai.core.git_ops.command_available", lambda command: availability.get(command, False))
    monkeypatch.setattr(
        "hrs_ai.core.jira.validate_credentials",
        lambda *a, **k: JiraValidationResult(ok=True),
    )
    out = []

    rc = run_setup(prompt=lambda p: "e@x.com", prompt_secret=lambda p: "t", out=out.append)

    text = "\n".join(out)
    assert rc == 0
    assert "GitHub Copilot CLI not found" in text
    assert "✓ Git" in text
    assert "✓ ripgrep" in text


def test_run_setup_aborts_when_email_abandoned(monkeypatch):
    _all_tools_present(monkeypatch)

    def eof(_prompt):
        raise EOFError

    out = []
    rc = run_setup(prompt=eof, prompt_secret=lambda p: "t", out=out.append)
    assert rc == 1
    assert not user_config_path().exists()


# --- CLI wiring -------------------------------------------------------------


def test_setup_subcommand_dispatches(monkeypatch):
    called = {}

    def spy():
        called["ran"] = True
        return 0

    monkeypatch.setattr("hrs_ai.core.setup.run_setup", spy)
    assert main(["setup"]) == 0
    assert called.get("ran") is True
