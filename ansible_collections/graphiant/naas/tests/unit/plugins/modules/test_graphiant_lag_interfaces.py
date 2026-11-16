# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for graphiant_lag_interfaces module (mocked Ansible + connection).

Covers the module-layer wiring: operation dispatch (configure / deconfigure /
add_lag_members / remove_lag_members / update_lacp_configs /
delete_lag_subinterfaces), state->operation mapping, and the exit payload. The
manager's build/idempotency logic is tested separately in
test_lag_interface_manager.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ansible_collections.graphiant.naas.plugins.modules import graphiant_lag_interfaces

_CONN = (
    "ansible_collections.graphiant.naas.plugins.modules."
    "graphiant_lag_interfaces.graphiant_utils.get_graphiant_connection"
)
_AM = "ansible_collections.graphiant.naas.plugins.modules.graphiant_lag_interfaces.AnsibleModule"


def _base_params() -> dict:
    return {
        "host": "https://api.example.com",
        "username": "u",
        "password": "p",
        "access_token": None,
        "lag_config_file": "sample_lag_interface_config.yaml",
        "operation": "configure",
        "state": "present",
        "detailed_logs": False,
    }


def _connection_with(method_name: str, result: dict) -> MagicMock:
    lag = MagicMock()
    getattr(lag, method_name).return_value = result
    # MagicMock(lag_interfaces=lag) keeps the child stable across attribute access.
    gc = MagicMock(lag_interfaces=lag)
    return MagicMock(graphiant_config=gc)


# --- execute_with_logging ----------------------------------------------------


def test_execute_with_logging_passes_through_changed_and_details() -> None:
    module = MagicMock()
    out = graphiant_lag_interfaces.execute_with_logging(
        module,
        lambda: {"changed": False, "created_lags": [], "updated_lags": []},
        success_msg="done",
    )
    assert out["changed"] is False
    assert out["result_msg"] == "done"
    assert out["details"]["updated_lags"] == []


def test_execute_with_logging_falls_back_when_no_changed_key() -> None:
    module = MagicMock()
    out = graphiant_lag_interfaces.execute_with_logging(module, lambda: "not-a-dict", success_msg="done")
    assert out["changed"] is True
    assert out["result_msg"] == "done"


# --- main() dispatch + exit payload ------------------------------------------


@patch(_CONN)
@patch(_AM)
def test_main_configure_exit_payload(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod.params = _base_params()
    mock_ansible_module.return_value = mod

    mock_get_connection.return_value = _connection_with(
        "configure",
        {"changed": True, "configured_devices": [101], "created_lags": [{"device": "edge-1", "lag": "LAG1"}]},
    )

    graphiant_lag_interfaces.main()

    lag = mock_get_connection.return_value.graphiant_config.lag_interfaces
    lag.configure.assert_called_once_with("sample_lag_interface_config.yaml")
    mod.exit_json.assert_called_once()
    kwargs = mod.exit_json.call_args[1]
    assert kwargs["changed"] is True
    assert kwargs["operation"] == "configure"
    assert kwargs["lag_config_file"] == "sample_lag_interface_config.yaml"
    assert kwargs["msg"] == "Successfully configured LAG interfaces"


@pytest.mark.parametrize(
    "operation,method,success_msg",
    [
        ("deconfigure", "deconfigure", "Successfully deconfigured LAG"),
        ("add_lag_members", "add_lag_members", "Successfully added LAG members"),
        ("remove_lag_members", "remove_lag_members", "Successfully removed LAG members"),
        ("update_lacp_configs", "update_lacp_configs", "Successfully updated LACP configuration"),
        ("delete_lag_subinterfaces", "delete_lag_subinterfaces", "Successfully deleted LAG subinterfaces"),
    ],
)
@patch(_CONN)
@patch(_AM)
def test_main_dispatches_each_operation(
    mock_ansible_module, mock_get_connection, operation, method, success_msg
) -> None:
    mod = MagicMock()
    mod.check_mode = False
    p = _base_params()
    p["operation"] = operation
    mod.params = p
    mock_ansible_module.return_value = mod

    mock_get_connection.return_value = _connection_with(method, {"changed": True})

    graphiant_lag_interfaces.main()

    lag = mock_get_connection.return_value.graphiant_config.lag_interfaces
    getattr(lag, method).assert_called_once_with("sample_lag_interface_config.yaml")
    kwargs = mod.exit_json.call_args[1]
    assert kwargs["operation"] == operation
    assert kwargs["msg"] == success_msg
    assert kwargs["changed"] is True


@patch(_CONN)
@patch(_AM)
def test_main_configure_via_state_present(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    p = _base_params()
    p["operation"] = None
    p["state"] = "present"
    mod.params = p
    mock_ansible_module.return_value = mod

    mock_get_connection.return_value = _connection_with("configure", {"changed": False})

    graphiant_lag_interfaces.main()

    lag = mock_get_connection.return_value.graphiant_config.lag_interfaces
    lag.configure.assert_called_once_with("sample_lag_interface_config.yaml")
    assert mod.exit_json.call_args[1]["operation"] == "configure"


@patch(_CONN)
@patch(_AM)
def test_main_deconfigure_via_state_absent(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    p = _base_params()
    p["operation"] = None
    p["state"] = "absent"
    mod.params = p
    mock_ansible_module.return_value = mod

    mock_get_connection.return_value = _connection_with("deconfigure", {"changed": True})

    graphiant_lag_interfaces.main()

    lag = mock_get_connection.return_value.graphiant_config.lag_interfaces
    lag.deconfigure.assert_called_once_with("sample_lag_interface_config.yaml")
    assert mod.exit_json.call_args[1]["operation"] == "deconfigure"


@patch(_CONN)
@patch(_AM)
def test_main_operation_takes_precedence_over_state(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    p = _base_params()
    # Explicit operation wins even though state would map to deconfigure.
    p["operation"] = "add_lag_members"
    p["state"] = "absent"
    mod.params = p
    mock_ansible_module.return_value = mod

    mock_get_connection.return_value = _connection_with("add_lag_members", {"changed": True})

    graphiant_lag_interfaces.main()

    lag = mock_get_connection.return_value.graphiant_config.lag_interfaces
    lag.add_lag_members.assert_called_once_with("sample_lag_interface_config.yaml")
    lag.deconfigure.assert_not_called()
    assert mod.exit_json.call_args[1]["operation"] == "add_lag_members"


@patch(_CONN)
@patch(_AM)
def test_main_requires_operation_or_state(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod.fail_json.side_effect = SystemExit  # mirror real AnsibleModule.fail_json
    p = _base_params()
    p["operation"] = None
    p["state"] = None
    mod.params = p
    mock_ansible_module.return_value = mod

    with pytest.raises(SystemExit):
        graphiant_lag_interfaces.main()

    mod.fail_json.assert_called_once()
    assert "operation" in mod.fail_json.call_args[1]["msg"]
    mock_get_connection.assert_not_called()


@patch(_CONN)
@patch(_AM)
def test_main_exception_calls_fail_json(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod.params = _base_params()
    mock_ansible_module.return_value = mod

    mock_get_connection.side_effect = ValueError("boom")

    graphiant_lag_interfaces.main()

    mod.fail_json.assert_called_once()
    assert mod.fail_json.call_args[1]["operation"] == "configure"
    mod.exit_json.assert_not_called()


# --- exit payload details + diff mode ----------------------------------------


@patch(_CONN)
@patch(_AM)
def test_main_exit_payload_surfaces_devices_and_details(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod._diff = False
    mod.params = _base_params()
    mock_ansible_module.return_value = mod

    details = {
        "changed": True,
        "configured_devices": ["edge-1"],
        "skipped_devices": ["edge-2"],
        "diff_plan": [],
    }
    mock_get_connection.return_value = _connection_with("configure", details)

    graphiant_lag_interfaces.main()

    kwargs = mod.exit_json.call_args[1]
    assert kwargs["configured_devices"] == ["edge-1"]
    assert kwargs["skipped_devices"] == ["edge-2"]
    assert kwargs["details"] == details
    assert "diff" not in kwargs


@patch(_CONN)
@patch(_AM)
def test_main_diff_mode_sets_diff_key(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod._diff = True
    mod.params = _base_params()
    mock_ansible_module.return_value = mod

    mock_get_connection.return_value = _connection_with(
        "configure",
        {
            "changed": True,
            "configured_devices": [101],
            "skipped_devices": [],
            "diff_plan": [
                {
                    "device": "edge-1",
                    "branch": "edge",
                    "before": {"LAG1": {"mtu": 1500}},
                    "after": {"LAG1": {"mtu": 9000}},
                }
            ],
        },
    )

    graphiant_lag_interfaces.main()

    kwargs = mod.exit_json.call_args[1]
    assert "diff" in kwargs
    assert "edge-1" in kwargs["diff"]["before"]
    assert "edge-1" in kwargs["diff"]["after"]
