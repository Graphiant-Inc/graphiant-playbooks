# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for graphiant_static_routes module (mocked Ansible + connection)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ansible_collections.graphiant.naas.plugins.modules import graphiant_static_routes


def _base_params() -> dict:
    return {
        "host": "https://api.example.com",
        "username": "u",
        "password": "p",
        "access_token": None,
        "static_routes_config_file": "sample_static_route.yaml",
        "operation": "configure",
        "state": "present",
        "detailed_logs": False,
    }


def test_execute_with_logging_no_change_adds_skipped_count_to_message() -> None:
    module = MagicMock()
    module.params = {"detailed_logs": False}
    out = graphiant_static_routes.execute_with_logging(
        module,
        lambda: {
            "changed": False,
            "configured_devices": [],
            "skipped_devices": ["d1", "d2"],
        },
    )
    assert out["changed"] is False
    assert "skipped" in out["result_msg"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_static_routes.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_static_routes.AnsibleModule")
def test_main_configure(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod.params = _base_params()
    mod.params["operation"] = "configure"
    mock_ansible_module.return_value = mod

    sr = MagicMock()
    sr.configure.return_value = {
        "changed": False,
        "configured_devices": [],
        "skipped_devices": ["x"],
    }
    gc = MagicMock()
    gc.static_routes = sr
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_static_routes.main()
    sr.configure.assert_called_once_with("sample_static_route.yaml")
    mod.exit_json.assert_called_once()


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_static_routes.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_static_routes.AnsibleModule")
def test_main_unsupported_operation_fails_json(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    p = _base_params()
    p["operation"] = "not-a-valid-op"
    mod.params = p
    mock_ansible_module.return_value = mod

    mock_get_connection.return_value = MagicMock()

    graphiant_static_routes.main()
    mod.fail_json.assert_called_once()
    err = mod.fail_json.call_args[1]
    assert "Unsupported" in err["msg"]
    assert err["operation"] == "not-a-valid-op"
    mod.exit_json.assert_not_called()
