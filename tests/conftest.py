"""Shared pytest fixtures.

Isolates the user-level BugPilot config so tests never read or write the real
``~/.bugpilot/config.toml`` (which would make results depend on whether the
developer has run ``bugpilot setup``).
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_bugpilot_config(tmp_path_factory, monkeypatch):
    config_dir = tmp_path_factory.mktemp("bugpilot-home")
    monkeypatch.setenv("BUGPILOT_CONFIG_DIR", str(config_dir))
    return config_dir
