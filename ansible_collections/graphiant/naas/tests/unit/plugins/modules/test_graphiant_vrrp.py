# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for graphiant_vrrp module (mocked Ansible + connection).

Covers the module-layer wiring: operation dispatch (configure / deconfigure /
enable), state->operation mapping, the exit payload device lists, and the
``--diff`` key. The manager's build/idempotency/diff logic is tested separately
in test_vrrp_interface_manager.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ansible_collections.graphiant.naas.plugins.modules import graphiant_vrrp


def _base_params() -> dict:
    return {
        "host": "https://api.example.com",
        "username": "u",
        "password": "p",
        "access_token": None,
        "vrrp_config_file": "sample_vrrp_config.yaml",
        "operation": "configure",
        "state": "present",
        "detailed_logs": False,
    }


def _connection_with(method_name: str, result: dict) -> MagicMock:
    vrrp = MagicMock()
    getattr(vrrp, method_name).return_value = result
    gc = MagicMock()
    gc.vrrp_interfaces = vrrp
    return MagicMock(graphiant_config=gc)


# --- execute_with_logging ----------------------------------------------------


def test_execute_with_logging_passes_through_changed_and_details() -> None:
    module = MagicMock()
    out = graphiant_vrrp.execute_with_logging(
        module,
        lambda: {"changed": False, "configured_devices": [], "skipped_devices": ["d1"], "diff_plan": []},
        success_msg="done",
    )
    assert out["changed"] is False
    assert out["result_msg"] == "done"
    assert out["details"]["skipped_devices"] == ["d1"]


def test_execute_with_logging_falls_back_when_no_changed_key() -> None:
    module = MagicMock()
    out = graphiant_vrrp.execute_with_logging(module, lambda: "not-a-dict", success_msg="done")
    assert out["changed"] is True
    assert out["result_msg"] == "done"


# --- main() dispatch + exit payload ------------------------------------------


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_vrrp.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_vrrp.AnsibleModule")
def test_main_configure_exit_payload(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod._diff = False
    mod.params = _base_params()
    mock_ansible_module.return_value = mod

    mock_get_connection.return_value = _connection_with(
        "configure_vrrp_interfaces",
        {
            "changed": True,
            "configured_devices": ["edge-1-sdktest"],
            "skipped_devices": ["edge-2-sdktest"],
            "diff_plan": [],
        },
    )

    graphiant_vrrp.main()

    vrrp = mock_get_connection.return_value.graphiant_config.vrrp_interfaces
    vrrp.configure_vrrp_interfaces.assert_called_once_with("sample_vrrp_config.yaml")
    mod.exit_json.assert_called_once()
    kwargs = mod.exit_json.call_args[1]
    assert kwargs["changed"] is True
    assert kwargs["operation"] == "configure"
    assert kwargs["vrrp_config_file"] == "sample_vrrp_config.yaml"
    assert kwargs["configured_devices"] == ["edge-1-sdktest"]
    assert kwargs["skipped_devices"] == ["edge-2-sdktest"]
    assert "details" in kwargs


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_vrrp.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_vrrp.AnsibleModule")
def test_main_deconfigure_via_state_absent(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod._diff = False
    p = _base_params()
    p["operation"] = None
    p["state"] = "absent"
    mod.params = p
    mock_ansible_module.return_value = mod

    mock_get_connection.return_value = _connection_with(
        "deconfigure_vrrp_interfaces",
        {"changed": True, "deconfigured_devices": ["edge-1-sdktest"], "skipped_interfaces": [], "diff_plan": []},
    )

    graphiant_vrrp.main()

    vrrp = mock_get_connection.return_value.graphiant_config.vrrp_interfaces
    vrrp.deconfigure_vrrp_interfaces.assert_called_once_with("sample_vrrp_config.yaml")
    assert mod.exit_json.call_args[1]["operation"] == "deconfigure"


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_vrrp.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_vrrp.AnsibleModule")
def test_main_enable_dispatch(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod._diff = False
    p = _base_params()
    p["operation"] = "enable"
    mod.params = p
    mock_ansible_module.return_value = mod

    mock_get_connection.return_value = _connection_with(
        "enable_vrrp_interfaces",
        {"changed": False, "enabled_devices": [], "skipped_interfaces": [], "diff_plan": []},
    )

    graphiant_vrrp.main()

    vrrp = mock_get_connection.return_value.graphiant_config.vrrp_interfaces
    vrrp.enable_vrrp_interfaces.assert_called_once_with("sample_vrrp_config.yaml")
    kwargs = mod.exit_json.call_args[1]
    assert kwargs["operation"] == "enable"
    assert kwargs["changed"] is False


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_vrrp.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_vrrp.AnsibleModule")
def test_main_requires_operation_or_state(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod._diff = False
    mod.fail_json.side_effect = SystemExit  # mirror real AnsibleModule.fail_json
    p = _base_params()
    p["operation"] = None
    p["state"] = None
    mod.params = p
    mock_ansible_module.return_value = mod

    with pytest.raises(SystemExit):
        graphiant_vrrp.main()

    mod.fail_json.assert_called_once()
    assert "operation" in mod.fail_json.call_args[1]["msg"]
    mock_get_connection.assert_not_called()


# --- diff mode ---------------------------------------------------------------


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_vrrp.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_vrrp.AnsibleModule")
def test_main_diff_mode_sets_diff_key(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod._diff = True
    mod.params = _base_params()
    mock_ansible_module.return_value = mod

    mock_get_connection.return_value = _connection_with(
        "configure_vrrp_interfaces",
        {
            "changed": True,
            "configured_devices": ["edge-1-sdktest"],
            "skipped_devices": [],
            "diff_plan": [
                {
                    "device": "edge-1-sdktest",
                    "branch": "edge",
                    "before": {"GigabitEthernet7/0/0": {"ipv4": {"priority": 100}}},
                    "after": {"GigabitEthernet7/0/0": {"ipv4": {"priority": 120}}},
                }
            ],
        },
    )

    graphiant_vrrp.main()

    kwargs = mod.exit_json.call_args[1]
    assert "diff" in kwargs
    assert "edge-1-sdktest" in kwargs["diff"]["before"]
    assert "edge-1-sdktest" in kwargs["diff"]["after"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_vrrp.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_vrrp.AnsibleModule")
def test_main_no_diff_key_when_diff_mode_off(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod._diff = False
    mod.params = _base_params()
    mock_ansible_module.return_value = mod

    mock_get_connection.return_value = _connection_with(
        "configure_vrrp_interfaces",
        {
            "changed": True,
            "configured_devices": ["edge-1-sdktest"],
            "skipped_devices": [],
            "diff_plan": [{"device": "edge-1-sdktest", "branch": "edge", "before": {}, "after": {"x": 1}}],
        },
    )

    graphiant_vrrp.main()

    kwargs = mod.exit_json.call_args[1]
    assert "diff" not in kwargs
