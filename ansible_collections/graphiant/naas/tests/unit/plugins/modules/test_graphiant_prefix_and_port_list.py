# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for graphiant_prefix_port_list module (mocked Ansible + connection)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ansible_collections.graphiant.naas.plugins.module_utils.libs.device_config_common import (
    ansible_diff_from_plan,
)
from ansible_collections.graphiant.naas.plugins.modules import graphiant_prefix_port_list


def _base_params() -> dict:
    return {
        "host": "https://api.example.com",
        "username": "u",
        "password": "p",
        "access_token": None,
        "prefix_port_list_config_file": "sample_prefix_and_port_list.yaml",
        "operation": "create_prefix_port_lists",
        "state": "present",
        "detailed_logs": False,
    }


def _manager_result(*, changed: bool = False, configured=None, skipped=None, diff_plan=None) -> dict:
    return {
        "changed": changed,
        "configured_devices": configured or [],
        "skipped_devices": skipped or [],
        "diff_plan": diff_plan or [],
    }


def test_ansible_diff_from_plan_prefix_port_lists() -> None:
    diff_plan = [
        {
            "device": "edge-1-sdktest",
            "branch": "edge.trafficPolicy",
            "before": {"networkLists": {"demo": None}},
            "after": {"networkLists": {"demo": {"name": "demo", "networks": ["1.1.1.1/32"]}}},
        }
    ]
    d = ansible_diff_from_plan(diff_plan)
    assert "edge-1-sdktest" in d["before"]
    assert "1.1.1.1/32" in d["after"]


def test_execute_with_logging_no_change_adds_skipped_count_to_message() -> None:
    module = MagicMock()
    module.params = {"detailed_logs": False}
    out = graphiant_prefix_port_list.execute_with_logging(
        module,
        lambda: _manager_result(skipped=["d1", "d2"]),
    )
    assert out["changed"] is False
    assert "skipped" in out["result_msg"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_prefix_port_list.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_prefix_port_list.AnsibleModule")
def test_main_create_prefix_port_lists_diff_mode(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod._diff = True
    mod.params = _base_params()
    mod.params["operation"] = "create_prefix_port_lists"
    mock_ansible_module.return_value = mod

    diff_plan = [
        {
            "device": "edge-1-sdktest",
            "branch": "edge.trafficPolicy",
            "before": {"networkLists": {"graphiant_dia_prefix": None}},
            "after": {
                "networkLists": {
                    "graphiant_dia_prefix": {"name": "graphiant_dia_prefix", "networks": ["1.1.1.1/32"]}
                }
            },
        }
    ]
    ppl = MagicMock()
    ppl.create_prefix_port_lists.return_value = _manager_result(
        changed=True, configured=["edge-1-sdktest"], diff_plan=diff_plan
    )
    gc = MagicMock()
    gc.prefix_port_list = ppl
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_prefix_port_list.main()

    kwargs = mod.exit_json.call_args[1]
    assert "diff" in kwargs
    assert "graphiant_dia_prefix" in kwargs["diff"]["after"]
    assert kwargs["details"]["diff_plan"] == diff_plan


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_prefix_port_list.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_prefix_port_list.AnsibleModule")
def test_main_create_prefix_port_lists(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod.params = _base_params()
    mod.params["operation"] = "create_prefix_port_lists"
    mock_ansible_module.return_value = mod

    ppl = MagicMock()
    ppl.create_prefix_port_lists.return_value = _manager_result(skipped=["x"])
    gc = MagicMock()
    gc.prefix_port_list = ppl
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_prefix_port_list.main()

    ppl.create_prefix_port_lists.assert_called_once_with("sample_prefix_and_port_list.yaml")
    mod.exit_json.assert_called_once()
    kwargs = mod.exit_json.call_args[1]
    assert kwargs["operation"] == "create_prefix_port_lists"
    assert kwargs["changed"] is False
    assert kwargs["skipped_devices"] == ["x"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_prefix_port_list.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_prefix_port_list.AnsibleModule")
def test_main_delete_prefix_port_lists(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod.params = _base_params()
    mod.params["operation"] = "delete_prefix_port_lists"
    mock_ansible_module.return_value = mod

    ppl = MagicMock()
    ppl.delete_prefix_port_lists.return_value = _manager_result(changed=True, configured=["edge-1"])
    gc = MagicMock()
    gc.prefix_port_list = ppl
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_prefix_port_list.main()

    ppl.delete_prefix_port_lists.assert_called_once_with("sample_prefix_and_port_list.yaml")
    kwargs = mod.exit_json.call_args[1]
    assert kwargs["operation"] == "delete_prefix_port_lists"
    assert kwargs["changed"] is True
    assert kwargs["configured_devices"] == ["edge-1"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_prefix_port_list.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_prefix_port_list.AnsibleModule")
def test_main_create_prefix_lists(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod.params = _base_params()
    mod.params["operation"] = "create_prefix_lists"
    mock_ansible_module.return_value = mod

    ppl = MagicMock()
    ppl.create_prefix_lists.return_value = _manager_result(changed=True, configured=["edge-1"])
    gc = MagicMock()
    gc.prefix_port_list = ppl
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_prefix_port_list.main()

    ppl.create_prefix_lists.assert_called_once_with("sample_prefix_and_port_list.yaml")
    assert mod.exit_json.call_args[1]["operation"] == "create_prefix_lists"


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_prefix_port_list.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_prefix_port_list.AnsibleModule")
def test_main_delete_prefix_lists(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod.params = _base_params()
    mod.params["operation"] = "delete_prefix_lists"
    mock_ansible_module.return_value = mod

    ppl = MagicMock()
    ppl.delete_prefix_lists.return_value = _manager_result()
    gc = MagicMock()
    gc.prefix_port_list = ppl
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_prefix_port_list.main()

    ppl.delete_prefix_lists.assert_called_once_with("sample_prefix_and_port_list.yaml")
    assert mod.exit_json.call_args[1]["operation"] == "delete_prefix_lists"


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_prefix_port_list.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_prefix_port_list.AnsibleModule")
def test_main_create_port_lists(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod.params = _base_params()
    mod.params["operation"] = "create_port_lists"
    mock_ansible_module.return_value = mod

    ppl = MagicMock()
    ppl.create_port_lists.return_value = _manager_result(changed=True, configured=["edge-1"])
    gc = MagicMock()
    gc.prefix_port_list = ppl
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_prefix_port_list.main()

    ppl.create_port_lists.assert_called_once_with("sample_prefix_and_port_list.yaml")
    assert mod.exit_json.call_args[1]["operation"] == "create_port_lists"


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_prefix_port_list.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_prefix_port_list.AnsibleModule")
def test_main_delete_port_lists(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod.params = _base_params()
    mod.params["operation"] = "delete_port_lists"
    mock_ansible_module.return_value = mod

    ppl = MagicMock()
    ppl.delete_port_lists.return_value = _manager_result()
    gc = MagicMock()
    gc.prefix_port_list = ppl
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_prefix_port_list.main()

    ppl.delete_port_lists.assert_called_once_with("sample_prefix_and_port_list.yaml")
    assert mod.exit_json.call_args[1]["operation"] == "delete_port_lists"


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_prefix_port_list.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_prefix_port_list.AnsibleModule")
def test_main_state_present_defaults_to_create_prefix_port_lists(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    p = _base_params()
    p["operation"] = None
    p["state"] = "present"
    mod.params = p
    mock_ansible_module.return_value = mod

    ppl = MagicMock()
    ppl.create_prefix_port_lists.return_value = _manager_result()
    gc = MagicMock()
    gc.prefix_port_list = ppl
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_prefix_port_list.main()

    ppl.create_prefix_port_lists.assert_called_once_with("sample_prefix_and_port_list.yaml")
    assert mod.exit_json.call_args[1]["operation"] == "create_prefix_port_lists"


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_prefix_port_list.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_prefix_port_list.AnsibleModule")
def test_main_state_absent_defaults_to_delete_prefix_port_lists(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    p = _base_params()
    p["operation"] = None
    p["state"] = "absent"
    mod.params = p
    mock_ansible_module.return_value = mod

    ppl = MagicMock()
    ppl.delete_prefix_port_lists.return_value = _manager_result()
    gc = MagicMock()
    gc.prefix_port_list = ppl
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_prefix_port_list.main()

    ppl.delete_prefix_port_lists.assert_called_once_with("sample_prefix_and_port_list.yaml")
    assert mod.exit_json.call_args[1]["operation"] == "delete_prefix_port_lists"


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_prefix_port_list.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_prefix_port_list.AnsibleModule")
def test_main_unsupported_operation_fails_json(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    p = _base_params()
    p["operation"] = "not-a-valid-op"
    mod.params = p
    mock_ansible_module.return_value = mod

    mock_get_connection.return_value = MagicMock()

    graphiant_prefix_port_list.main()
    mod.fail_json.assert_called_once()
    err = mod.fail_json.call_args[1]
    assert "Unsupported" in err["msg"]
    assert err["operation"] == "not-a-valid-op"
    mod.exit_json.assert_not_called()
