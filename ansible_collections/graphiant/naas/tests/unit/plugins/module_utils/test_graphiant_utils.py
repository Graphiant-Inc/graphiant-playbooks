# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for graphiant_utils (no live API)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ansible_collections.graphiant.naas.plugins.module_utils import graphiant_utils
from ansible_collections.graphiant.naas.plugins.module_utils.libs.exceptions import (
    APIError,
    ConfigurationError,
    DeviceNotFoundError,
    GraphiantPlaybookError,
)


def test_graphiant_portal_auth_argument_spec_keys() -> None:
    spec = graphiant_utils.graphiant_portal_auth_argument_spec()
    assert "host" in spec and "username" in spec and "password" in spec and "access_token" in spec
    assert spec["host"]["type"] == "str" and spec["host"].get("required") is True


def test_get_graphiant_connection_requires_host() -> None:
    with pytest.raises(ValueError, match="Missing required parameter: host"):
        graphiant_utils.get_graphiant_connection({})
    with pytest.raises(ValueError, match="Missing required parameter: host"):
        graphiant_utils.get_graphiant_connection({"host": ""})


def test_get_graphiant_connection_with_token() -> None:
    conn = graphiant_utils.get_graphiant_connection(
        {"host": "https://api.example.com", "access_token": "tok"}
    )
    assert conn.host == "https://api.example.com"
    assert conn.access_token == "tok"


def test_get_graphiant_connection_username_password() -> None:
    conn = graphiant_utils.get_graphiant_connection(
        {
            "host": "https://api.example.com",
            "username": "u",
            "password": "p",
        }
    )
    assert conn.username == "u"
    assert conn.password == "p"
    assert conn.access_token is None


def test_get_graphiant_connection_env_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRAPHIANT_ACCESS_TOKEN", "envtok")
    conn = graphiant_utils.get_graphiant_connection(
        {
            "host": "https://api.example.com",
        }
    )
    assert conn.access_token == "envtok"


def test_get_graphiant_connection_rejects_no_auth() -> None:
    with pytest.raises(ValueError, match="Authentication requires"):
        graphiant_utils.get_graphiant_connection(
            {
                "host": "https://api.example.com",
                "username": "",
                "password": "",
            }
        )


@pytest.mark.parametrize(
    "params,ok",
    [
        ({"username": "u", "password": "p"}, True),
        ({"username": "u", "password": ""}, False),
        ({"username": None, "password": "p"}, False),
    ],
)
def test_password_auth_usable(params: dict, ok: bool) -> None:
    assert (
        graphiant_utils._password_auth_usable(  # pylint: disable=protected-access
            params.get("username"), params.get("password")
        )
        is ok
    )


def test_handle_graphiant_exception_configuration() -> None:
    msg = graphiant_utils.handle_graphiant_exception(
        ConfigurationError("bad config"), "operation"
    )
    assert "Configuration error" in msg
    assert "operation" in msg


def test_handle_graphiant_exception_api() -> None:
    msg = graphiant_utils.handle_graphiant_exception(
        APIError("timeout"), "sync"
    )
    assert "API error" in msg


def test_handle_graphiant_exception_device() -> None:
    msg = graphiant_utils.handle_graphiant_exception(
        DeviceNotFoundError("missing"), "push"
    )
    assert "Device not found" in msg


def test_handle_graphiant_exception_value_error() -> None:
    msg = graphiant_utils.handle_graphiant_exception(
        ValueError("oops"), "x"
    )
    assert "Invalid parameters" in msg
    assert "oops" in msg


def test_handle_graphiant_exception_unexpected_type() -> None:
    msg = graphiant_utils.handle_graphiant_exception(
        RuntimeError("boom"), "x"
    )
    assert "Unexpected error" in msg
    assert "RuntimeError" in msg
    assert "boom" in msg


def test_ansible_module_log_silent_on_broken_module() -> None:
    m = MagicMock()
    m.log = MagicMock(side_effect=RuntimeError("log failed"))
    graphiant_utils.ansible_module_log(m, "hi")  # does not raise


def test_ansible_module_log_calls_log() -> None:
    m = type("M", (), {})()
    called = []

    def _capture(s):
        called.append(s)

    m.log = _capture
    graphiant_utils.ansible_module_log(m, "ping")
    assert any("ping" in c and "graphiant" in c for c in called)


def test_handle_graphiant_exception_playbook_base() -> None:
    msg = graphiant_utils.handle_graphiant_exception(
        GraphiantPlaybookError("base err"), "op"
    )
    assert "Graphiant playbook error" in msg
