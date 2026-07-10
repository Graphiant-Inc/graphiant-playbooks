# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for graphiant_dhcp_relay module (mocked Ansible + connection)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ansible_collections.graphiant.naas.plugins.modules import graphiant_dhcp_relay


def _base_params() -> dict:
    return {
        "host": "https://api.example.com",
        "username": "u",
        "password": "p",
        "access_token": None,
        "dhcp_relay_config_file": "sample_dhcp_relay_config.yaml",
        "operation": "configure",
        "state": "present",
        "detailed_logs": False,
    }


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_dhcp_relay.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_dhcp_relay.AnsibleModule")
def test_main_configure_no_change_message(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod._diff = False
    mod.params = _base_params()
    mock_ansible_module.return_value = mod

    mgr = MagicMock()
    mgr.configure_dhcp_relay_interfaces.return_value = {
        "changed": False,
        "configured_devices": [],
        "skipped_devices": ["edge-1-sdktest"],
        "diff_plan": [],
    }
    gc = MagicMock()
    gc.dhcp_relay_interfaces = mgr
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_dhcp_relay.main()

    kwargs = mod.exit_json.call_args[1]
    assert kwargs["changed"] is False
    assert "already matches" in kwargs["msg"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_dhcp_relay.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_dhcp_relay.AnsibleModule")
def test_main_diff_mode_sets_diff_key(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod._diff = True
    mod.params = _base_params()
    mock_ansible_module.return_value = mod

    mgr = MagicMock()
    mgr.configure_dhcp_relay_interfaces.return_value = {
        "changed": True,
        "configured_devices": ["edge-1-sdktest"],
        "skipped_devices": [],
        "diff_plan": [
            {
                "device": "edge-1-sdktest",
                "branch": "edge.interfaces",
                "before": {"GigabitEthernet4/0/0.1": {"ipv4": []}},
                "after": {"GigabitEthernet4/0/0.1": {"ipv4": ["10.1.1.1"]}},
            }
        ],
    }
    gc = MagicMock()
    gc.dhcp_relay_interfaces = mgr
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_dhcp_relay.main()

    kwargs = mod.exit_json.call_args[1]
    assert "diff" in kwargs
    assert "edge-1-sdktest" in kwargs["diff"]["before"]
    assert "GigabitEthernet4/0/0.1" in kwargs["diff"]["after"]
