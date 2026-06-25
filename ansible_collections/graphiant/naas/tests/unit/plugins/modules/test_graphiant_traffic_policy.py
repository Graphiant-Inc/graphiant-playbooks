# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for graphiant_traffic_policy module (mocked Ansible + connection)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ansible_collections.graphiant.naas.plugins.modules import graphiant_traffic_policy


def _base_params() -> dict:
    return {
        "host": "https://api.example.com",
        "username": "u",
        "password": "p",
        "access_token": None,
        "traffic_policy_config_file": "sample_device_traffic_policies.yaml",
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

    out = graphiant_traffic_policy.execute_with_logging(module, _impl)
    assert out["changed"] is False
    assert "skipped" in out["result_msg"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_traffic_policy.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_traffic_policy.AnsibleModule")
def test_main_configure_calls_traffic_policy_manager(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod.params = _base_params()
    mod.params["operation"] = "configure"
    mock_ansible_module.return_value = mod

    tpm = MagicMock()
    tpm.configure.return_value = {
        "changed": True,
        "configured_devices": ["a"],
        "skipped_devices": [],
    }
    gc = MagicMock()
    gc.traffic_policy = tpm
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_traffic_policy.main()

    tpm.configure.assert_called_once_with("sample_device_traffic_policies.yaml")
    mod.exit_json.assert_called_once()
    kwargs = mod.exit_json.call_args[1]
    assert kwargs["operation"] == "configure"
    assert kwargs["changed"] is True


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_traffic_policy.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_traffic_policy.AnsibleModule")
def test_main_state_absent_defaults_to_deconfigure(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    p = _base_params()
    p["operation"] = None
    p["state"] = "absent"
    mod.params = p
    mock_ansible_module.return_value = mod

    tpm = MagicMock()
    tpm.deconfigure.return_value = {
        "changed": False,
        "configured_devices": [],
        "skipped_devices": [],
    }
    gc = MagicMock()
    gc.traffic_policy = tpm
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_traffic_policy.main()

    tpm.deconfigure.assert_called_once()
    mod.exit_json.assert_called_once()
    assert mod.exit_json.call_args[1]["operation"] == "deconfigure"


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_traffic_policy.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_traffic_policy.AnsibleModule")
def test_main_attach_to_lan_segments(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    p = _base_params()
    p["operation"] = "attach_to_lan_segments"
    mod.params = p
    mock_ansible_module.return_value = mod

    tpm = MagicMock()
    tpm.attach_to_lan_segments.return_value = {
        "changed": True,
        "configured_devices": ["edge-1"],
        "skipped_devices": [],
    }
    gc = MagicMock()
    gc.traffic_policy = tpm
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_traffic_policy.main()

    tpm.attach_to_lan_segments.assert_called_once_with("sample_device_traffic_policies.yaml")
    assert mod.exit_json.call_args[1]["operation"] == "attach_to_lan_segments"


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_traffic_policy.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_traffic_policy.AnsibleModule")
def test_main_configure_diff_mode(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod._diff = True
    p = _base_params()
    p["operation"] = "configure"
    mod.params = p
    mock_ansible_module.return_value = mod

    diff_plan = [
        {
            "device": "edge-1",
            "branch": "edge.trafficPolicy.trafficRulesets",
            "before": {"trafficRulesets": {"rs1": {"rules": {"10": {"seq": 10, "action": "old"}}}}},
            "after": {"trafficRulesets": {"rs1": {"rules": {"10": {"seq": 10, "action": "new"}}}}},
        }
    ]
    tpm = MagicMock()
    tpm.configure.return_value = {
        "changed": True,
        "configured_devices": ["edge-1"],
        "skipped_devices": [],
        "diff_plan": diff_plan,
    }
    gc = MagicMock()
    gc.traffic_policy = tpm
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_traffic_policy.main()

    kwargs = mod.exit_json.call_args[1]
    assert "diff" in kwargs
    assert '"10"' in kwargs["diff"]["after"]
    assert kwargs["details"]["diff_plan"] == diff_plan
