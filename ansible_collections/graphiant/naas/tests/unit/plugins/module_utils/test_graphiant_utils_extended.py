# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""More graphiant_utils coverage: GraphiantConnection, lazy imports, handle_graphiant with missing libs."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ansible_collections.graphiant.naas.plugins.module_utils import graphiant_utils


def test_resolved_access_token_strips() -> None:
    assert (
        graphiant_utils._resolved_access_token({"access_token": "  tok  "})  # pylint: disable=protected-access
        == "tok"
    )


def test_resolved_access_token_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRAPHIANT_ACCESS_TOKEN", "e")
    assert (
        graphiant_utils._resolved_access_token({})  # pylint: disable=protected-access
        == "e"
    )


def test_graphiant_connection_test_connection_true() -> None:
    conn = graphiant_utils.GraphiantConnection("https://h", "u", "p")
    mock_cfg = MagicMock()
    mock_cfg.get_manager_status.return_value = {"a": True, "b": True}
    with patch.object(
        type(conn),
        "graphiant_config",
        new=property(lambda self: mock_cfg),
    ):
        assert conn.test_connection() is True


def test_graphiant_connection_test_connection_exception() -> None:
    conn = graphiant_utils.GraphiantConnection("https://h", "u", "p")
    mock_cfg = MagicMock()
    mock_cfg.get_manager_status.side_effect = RuntimeError("nope")
    with patch.object(
        type(conn),
        "graphiant_config",
        new=property(lambda self: mock_cfg),
    ):
        assert conn.test_connection() is False


def test_handle_graphiant_when_types_unavailable() -> None:
    with patch.object(
        graphiant_utils,
        "_get_graphiant_libs",
        return_value=(None, None, None, None, None),
    ):
        msg = graphiant_utils.handle_graphiant_exception(ValueError("e"), "op")
        assert "Error during" in msg and "e" in msg


def test_graphiant_config_property_import_error() -> None:
    with patch.object(
        graphiant_utils,
        "_get_graphiant_libs",
        return_value=(None, None, None, None, None),
    ):
        conn = graphiant_utils.GraphiantConnection("https://h", "u", "p")
        with pytest.raises(ImportError, match="Failed to import Graphiant"):
            def access_config():
                return conn.graphiant_config

            access_config()


def test_graphiant_config_property_wraps_init_failure() -> None:
    class BadGC:
        def __init__(self, **kwargs):
            raise ValueError("init failed")

    gpe = graphiant_utils.GraphiantPlaybookError
    if gpe is None:
        pytest.skip("GraphiantPlaybookError not available (validate-modules stub)")
    with patch.object(
        graphiant_utils,
        "_get_graphiant_libs",
        return_value=(BadGC, gpe, None, None, None),
    ):
        conn = graphiant_utils.GraphiantConnection("https://h", "u", "p")
        with pytest.raises(gpe, match="Failed to initialize"):
            def access_config():
                return conn.graphiant_config

            access_config()


def test_ansible_module_log_ignores_none_module() -> None:
    # Early return: line 19-20
    graphiant_utils.ansible_module_log(None, "x")


def test_ansible_module_log_calls_log_and_ignores_errors() -> None:
    m = MagicMock()
    m.log = MagicMock()
    graphiant_utils.ansible_module_log(m, "m")
    m.log.assert_called_once()
    m.log = MagicMock(side_effect=RuntimeError("bad"))
    graphiant_utils.ansible_module_log(m, "m2")


def test_ansible_module_log_no_log_attr() -> None:
    class NoLog:
        pass

    graphiant_utils.ansible_module_log(NoLog(), "x")


def test_graphiant_connection_test_connection_partial() -> None:
    conn = graphiant_utils.GraphiantConnection("https://h", "u", "p")
    mock_cfg = MagicMock()
    mock_cfg.get_manager_status.return_value = {"a": True, "b": False}
    with patch.object(
        type(conn),
        "graphiant_config",
        new=property(lambda self: mock_cfg),
    ):
        assert conn.test_connection() is False


def _typed_exc() -> tuple:
    gpe = graphiant_utils.GraphiantPlaybookError
    ce = graphiant_utils.ConfigurationError
    ae = graphiant_utils.APIError
    dnf = graphiant_utils.DeviceNotFoundError
    if gpe is None or ce is None or ae is None or dnf is None:
        return None
    return (gpe, ce, ae, dnf)


def test_handle_graphiant_typed_and_builtin_exceptions() -> None:
    types = _typed_exc()
    if not types:
        pytest.skip("Graphiant lib exception types not loaded")
    gpe, ce, ae, dnf = types
    assert "Configuration error" in graphiant_utils.handle_graphiant_exception(
        ce("c"), "op"
    )
    assert "API error" in graphiant_utils.handle_graphiant_exception(ae("a"), "op")
    assert "not found" in graphiant_utils.handle_graphiant_exception(dnf("d"), "op")
    assert "playbook error" in graphiant_utils.handle_graphiant_exception(
        gpe("g"), "op"
    )
    assert "Invalid parameters" in graphiant_utils.handle_graphiant_exception(
        ValueError("v"), "op"
    )
    assert "File or I/O error" in graphiant_utils.handle_graphiant_exception(
        OSError("io"), "op"
    )
    assert "Import error" in graphiant_utils.handle_graphiant_exception(
        ImportError("i"), "op"
    )
    assert "KeyError" in graphiant_utils.handle_graphiant_exception(
        KeyError("k"), "op"
    )
    assert "TypeError" in graphiant_utils.handle_graphiant_exception(
        TypeError("t"), "op"
    )
    assert "AttributeError" in graphiant_utils.handle_graphiant_exception(
        AttributeError("a"), "op"
    )
    msg = graphiant_utils.handle_graphiant_exception(RuntimeError("boom"), "op")
    assert "Unexpected error" in msg and "RuntimeError" in msg
