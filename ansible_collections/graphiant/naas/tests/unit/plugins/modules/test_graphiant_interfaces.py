# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for graphiant_interfaces module (mocked Ansible + connection).

Covers the module-layer wiring for check mode and diff support: no-change
messaging, exit payload device lists, operation dispatch, and the ``--diff`` key.
The manager's build/diff logic is tested separately in test_interfaces_manager.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ansible_collections.graphiant.naas.plugins.modules import graphiant_interfaces


def _base_params() -> dict:
    return {
        "host": "https://api.example.com",
        "username": "u",
        "password": "p",
        "access_token": None,
        "interface_config_file": "sample_interface_config.yaml",
        "circuit_config_file": "sample_circuit_config.yaml",
        "operation": "configure_interfaces",
        "circuits_only": False,
        "state": "present",
        "detailed_logs": False,
    }


def _connection_with(method_name: str, result: dict) -> MagicMock:
    interfaces = MagicMock()
    getattr(interfaces, method_name).return_value = result
    gc = MagicMock()
    gc.interfaces = interfaces
    return MagicMock(graphiant_config=gc)


# --- execute_with_logging ----------------------------------------------------


def test_execute_with_logging_no_change_adds_skipped_count_to_message() -> None:
    module = MagicMock()
    out = graphiant_interfaces.execute_with_logging(
        module,
        lambda: {"changed": False, "configured_devices": [], "skipped_devices": ["d1", "d2"]},
    )
    assert out["changed"] is False
    assert "skipped" in out["result_msg"]
    assert out["skipped_devices"] == ["d1", "d2"]


def test_execute_with_logging_changed_uses_success_msg() -> None:
    module = MagicMock()
    out = graphiant_interfaces.execute_with_logging(
        module,
        lambda: {"changed": True, "configured_devices": ["edge-1"], "skipped_devices": []},
        success_msg="done",
    )
    assert out["changed"] is True
    assert out["result_msg"] == "done"
    assert out["configured_devices"] == ["edge-1"]


# --- main() dispatch + exit payload ------------------------------------------


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_interfaces.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_interfaces.AnsibleModule")
def test_main_configure_interfaces_exit_payload(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod._diff = False
    mod.params = _base_params()
    mock_ansible_module.return_value = mod

    mock_get_connection.return_value = _connection_with(
        "configure_interfaces",
        {
            "changed": True,
            "configured_devices": ["edge-1-sdktest"],
            "skipped_devices": ["edge-2-sdktest"],
            "diff_plan": [],
        },
    )

    graphiant_interfaces.main()

    interfaces = mock_get_connection.return_value.graphiant_config.interfaces
    interfaces.configure_interfaces.assert_called_once_with(
        "sample_interface_config.yaml", "sample_circuit_config.yaml"
    )
    mod.exit_json.assert_called_once()
    kwargs = mod.exit_json.call_args[1]
    assert kwargs["changed"] is True
    assert kwargs["operation"] == "configure_interfaces"
    assert kwargs["configured_devices"] == ["edge-1-sdktest"]
    assert kwargs["skipped_devices"] == ["edge-2-sdktest"]
    assert "details" in kwargs


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_interfaces.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_interfaces.AnsibleModule")
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
        "deconfigure_interfaces",
        {"changed": True, "configured_devices": ["edge-1-sdktest"], "skipped_devices": [], "diff_plan": []},
    )

    graphiant_interfaces.main()

    interfaces = mock_get_connection.return_value.graphiant_config.interfaces
    interfaces.deconfigure_interfaces.assert_called_once_with(
        "sample_interface_config.yaml", "sample_circuit_config.yaml", False
    )
    kwargs = mod.exit_json.call_args[1]
    assert kwargs["operation"] == "deconfigure_interfaces"


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_interfaces.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_interfaces.AnsibleModule")
def test_main_configure_circuits_call_args(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod._diff = False
    p = _base_params()
    p["operation"] = "configure_circuits"
    mod.params = p
    mock_ansible_module.return_value = mod

    mock_get_connection.return_value = _connection_with(
        "configure_circuits",
        {"changed": True, "configured_devices": ["edge-1-sdktest"], "skipped_devices": [], "diff_plan": []},
    )

    graphiant_interfaces.main()

    interfaces = mock_get_connection.return_value.graphiant_config.interfaces
    # configure_circuits receives (circuit_config_file, interface_config_file).
    interfaces.configure_circuits.assert_called_once_with(
        "sample_circuit_config.yaml", "sample_interface_config.yaml"
    )
    assert mod.exit_json.call_args[1]["operation"] == "configure_circuits"


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_interfaces.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_interfaces.AnsibleModule")
def test_main_circuit_operation_requires_circuit_config_file(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod._diff = False
    mod.fail_json.side_effect = SystemExit  # mirror real AnsibleModule.fail_json
    p = _base_params()
    p["operation"] = "configure_circuits"
    p["circuit_config_file"] = None
    mod.params = p
    mock_ansible_module.return_value = mod

    with pytest.raises(SystemExit):
        graphiant_interfaces.main()

    mod.fail_json.assert_called_once()
    assert "circuit_config_file" in mod.fail_json.call_args[1]["msg"]
    mock_get_connection.assert_not_called()


# --- diff mode ---------------------------------------------------------------


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_interfaces.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_interfaces.AnsibleModule")
def test_main_diff_mode_sets_diff_key(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod._diff = True
    mod.params = _base_params()
    mock_ansible_module.return_value = mod

    mock_get_connection.return_value = _connection_with(
        "configure_interfaces",
        {
            "changed": True,
            "configured_devices": ["edge-1-sdktest"],
            "skipped_devices": [],
            "diff_plan": [
                {
                    "device": "edge-1-sdktest",
                    "branch": "edge",
                    "before": {"interfaces": {"gig1": {}}},
                    "after": {"interfaces": {"gig1": {"interface": {"lan": "seg-a"}}}},
                }
            ],
        },
    )

    graphiant_interfaces.main()

    kwargs = mod.exit_json.call_args[1]
    assert "diff" in kwargs
    assert "edge-1-sdktest" in kwargs["diff"]["before"]
    assert "edge-1-sdktest" in kwargs["diff"]["after"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_interfaces.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_interfaces.AnsibleModule")
def test_main_no_diff_key_when_diff_mode_off(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod._diff = False
    mod.params = _base_params()
    mock_ansible_module.return_value = mod

    mock_get_connection.return_value = _connection_with(
        "configure_interfaces",
        {
            "changed": True,
            "configured_devices": ["edge-1-sdktest"],
            "skipped_devices": [],
            "diff_plan": [{"device": "edge-1-sdktest", "branch": "edge", "before": {}, "after": {"x": 1}}],
        },
    )

    graphiant_interfaces.main()

    kwargs = mod.exit_json.call_args[1]
    assert "diff" not in kwargs
