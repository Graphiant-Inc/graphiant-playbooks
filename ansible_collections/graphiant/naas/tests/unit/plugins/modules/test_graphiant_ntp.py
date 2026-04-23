# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for graphiant_ntp module (mocked Ansible + connection)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ansible_collections.graphiant.naas.plugins.modules import graphiant_ntp


def _base_params() -> dict:
    return {
        "host": "https://api.example.com",
        "username": "u",
        "password": "p",
        "access_token": None,
        "ntp_config_file": "sample_device_ntp.yaml",
        "operation": "configure",
        "state": "present",
        "detailed_logs": False,
    }


def test_execute_with_logging_changed_with_skipped() -> None:
    module = MagicMock()
    module.params = {"detailed_logs": False}

    def _impl():
        return {
            "changed": False,
            "configured_devices": [],
            "skipped_devices": ["edge-1"],
        }

    out = graphiant_ntp.execute_with_logging(module, _impl)
    assert out["changed"] is False
    assert "skipped" in out["result_msg"]


def test_execute_with_logging_non_dict_result_uses_default_success() -> None:
    module = MagicMock()
    module.params = {"detailed_logs": False}
    out = graphiant_ntp.execute_with_logging(module, lambda: None)
    assert out["changed"] is True
    assert "success" in out["result_msg"].lower() or "completed" in out["result_msg"].lower()


def test_execute_with_logging_dict_without_changed_key() -> None:
    module = MagicMock()
    module.params = {"detailed_logs": False}
    out = graphiant_ntp.execute_with_logging(module, lambda: {"foo": 1})
    assert out["changed"] is True
    assert out["details"] == {"foo": 1}


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_ntp.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_ntp.AnsibleModule")
def test_main_configure_calls_ntp_manager(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod.params = _base_params()
    mod.params["operation"] = "configure"
    mock_ansible_module.return_value = mod

    ntp = MagicMock()
    ntp.configure.return_value = {
        "changed": True,
        "configured_devices": ["a"],
        "skipped_devices": [],
    }
    gc = MagicMock()
    gc.ntp = ntp
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_ntp.main()

    ntp.configure.assert_called_once_with("sample_device_ntp.yaml")
    mod.exit_json.assert_called_once()
    kwargs = mod.exit_json.call_args[1]
    assert kwargs["operation"] == "configure"
    assert kwargs["changed"] is True


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_ntp.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_ntp.AnsibleModule")
def test_main_state_absent_defaults_to_deconfigure(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    p = _base_params()
    p["operation"] = None
    p["state"] = "absent"
    mod.params = p
    mock_ansible_module.return_value = mod

    ntp = MagicMock()
    ntp.deconfigure.return_value = {
        "changed": False,
        "configured_devices": [],
        "skipped_devices": [],
    }
    gc = MagicMock()
    gc.ntp = ntp
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_ntp.main()

    ntp.deconfigure.assert_called_once()
    mod.exit_json.assert_called_once()
    assert mod.exit_json.call_args[1]["operation"] == "deconfigure"
