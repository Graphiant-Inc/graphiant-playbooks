# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for graphiant_ospfv2 module (mocked Ansible + connection)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ansible_collections.graphiant.naas.plugins.modules import graphiant_ospfv2


def _base_params() -> dict:
    return {
        "host": "https://api.example.com",
        "username": "u",
        "password": "p",
        "access_token": None,
        "ospfv2_config_file": "sample_ospfv2.yaml",
        "operation": "configure",
        "state": "present",
        "detailed_logs": False,
    }


def test_execute_with_logging_no_change_adds_skipped_count_to_message() -> None:
    module = MagicMock()
    module.params = {"detailed_logs": False}
    out = graphiant_ospfv2.execute_with_logging(
        module,
        lambda: {
            "changed": False,
            "configured_devices": [],
            "skipped_devices": ["d1", "d2"],
        },
    )
    assert out["changed"] is False
    assert "skipped" in out["result_msg"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_ospfv2.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_ospfv2.AnsibleModule")
def test_main_configure(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod.params = _base_params()
    mod.params["operation"] = "configure"
    mock_ansible_module.return_value = mod

    ospfv2 = MagicMock()
    ospfv2.configure.return_value = {
        "changed": False,
        "configured_devices": [],
        "skipped_devices": ["x"],
    }
    gc = MagicMock()
    gc.ospfv2 = ospfv2
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_ospfv2.main()
    ospfv2.configure.assert_called_once_with("sample_ospfv2.yaml", {})


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_ospfv2.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_ospfv2.AnsibleModule")
def test_main_configure_passes_vault_ospf_md5_passwords(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod.params = _base_params()
    mod.params["operation"] = "configure"
    vault = {"edge-1-sdktest": {"GigabitEthernet3": "vaultsecret"}}
    mod.params["vault_ospf_md5_passwords"] = vault
    mock_ansible_module.return_value = mod

    ospfv2 = MagicMock()
    ospfv2.configure.return_value = {
        "changed": True,
        "configured_devices": ["edge-1-sdktest"],
        "skipped_devices": [],
    }
    gc = MagicMock()
    gc.ospfv2 = ospfv2
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_ospfv2.main()
    ospfv2.configure.assert_called_once_with("sample_ospfv2.yaml", vault)


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_ospfv2.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_ospfv2.AnsibleModule")
def test_main_deconfigure(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod.params = _base_params()
    mod.params["operation"] = "deconfigure"
    mod.params["state"] = "absent"
    mock_ansible_module.return_value = mod

    ospfv2 = MagicMock()
    ospfv2.deconfigure.return_value = {
        "changed": True,
        "configured_devices": ["edge-1-sdktest"],
        "skipped_devices": [],
    }
    gc = MagicMock()
    gc.ospfv2 = ospfv2
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_ospfv2.main()
    ospfv2.deconfigure.assert_called_once_with("sample_ospfv2.yaml")
