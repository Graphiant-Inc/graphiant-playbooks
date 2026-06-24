# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for graphiant_security_policy module (mocked Ansible + connection)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ansible_collections.graphiant.naas.plugins.modules import graphiant_security_policy


def _base_params() -> dict:
    return {
        "host": "https://api.example.com",
        "username": "u",
        "password": "p",
        "access_token": None,
        "security_policy_config_file": "sample_device_security_policies.yaml",
        "operation": "configure",
        "state": "present",
        "detailed_logs": False,
    }


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_security_policy.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_security_policy.AnsibleModule")
def test_main_configure_calls_security_policy_manager(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod.params = _base_params()
    mod.params["operation"] = "configure"
    mock_ansible_module.return_value = mod

    spm = MagicMock()
    spm.configure.return_value = {
        "changed": True,
        "configured_devices": ["edge-1-sdktest"],
        "skipped_devices": [],
    }
    gc = MagicMock()
    gc.security_policy = spm
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_security_policy.main()

    spm.configure.assert_called_once_with("sample_device_security_policies.yaml")
    mod.exit_json.assert_called_once()
    kwargs = mod.exit_json.call_args[1]
    assert kwargs["operation"] == "configure"
    assert kwargs["changed"] is True


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_security_policy.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_security_policy.AnsibleModule")
def test_main_state_absent_defaults_to_deconfigure(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    p = _base_params()
    p["operation"] = None
    p["state"] = "absent"
    mod.params = p
    mock_ansible_module.return_value = mod

    spm = MagicMock()
    spm.deconfigure.return_value = {
        "changed": False,
        "configured_devices": [],
        "skipped_devices": ["edge-1-sdktest"],
    }
    gc = MagicMock()
    gc.security_policy = spm
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_security_policy.main()

    spm.deconfigure.assert_called_once_with("sample_device_security_policies.yaml")
    mod.exit_json.assert_called_once()
    assert mod.exit_json.call_args[1]["operation"] == "deconfigure"
