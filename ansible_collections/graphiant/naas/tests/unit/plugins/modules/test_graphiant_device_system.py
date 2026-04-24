# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for graphiant_device_system module (mocked Ansible + connection)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ansible_collections.graphiant.naas.plugins.modules import graphiant_device_system


def test_ansible_diff_from_plan_builds_before_after_strings() -> None:
    """``--diff`` payload: one entry per device/branch with JSON before/after (manager ``diff_plan`` shape)."""
    diff_plan = [
        {
            "device": "edge-3-sdktest",
            "branch": "edge",
            "before": {"name": "edge-3-sdktest", "regionName": "us-east-1 (N. Virginia)", "site": {"name": "NY"}},
            "after": {"name": "edge-3-sdktest", "regionName": "us-east-2 (Atlanta)", "site": {"name": "NY"}},
        }
    ]
    d = graphiant_device_system._ansible_diff_from_plan(diff_plan)
    assert "before" in d and "after" in d
    assert "edge-3-sdktest" in d["before"] and "edge" in d["before"]
    assert "us-east-1" in d["before"] and "us-east-2" in d["after"]


def _base_params() -> dict:
    return {
        "host": "https://api.example.com",
        "username": "u",
        "password": "p",
        "access_token": None,
        "system_config_file": "sample_device_system.yaml",
        "device": None,
        "device_type": None,
        "name": None,
        "regionName": None,
        "site": None,
        "operation": "configure",
        "state": "present",
        "detailed_logs": False,
    }


def test_execute_with_logging_idempotent_includes_count_suffix() -> None:
    module = MagicMock()
    module.params = {"detailed_logs": False}

    def _impl():
        return {
            "changed": False,
            "configured_devices": [],
            "skipped_devices": ["edge-1", "edge-2"],
        }

    out = graphiant_device_system.execute_with_logging(
        module,
        _impl,
        success_msg="ok",
        no_change_msg="no delta",
    )
    assert out["changed"] is False
    assert "2 device(s) already match desired state" in out["result_msg"]


def test_execute_with_logging_dict_without_changed_key() -> None:
    module = MagicMock()
    module.params = {"detailed_logs": False}
    out = graphiant_device_system.execute_with_logging(module, lambda: {"foo": 1})
    assert out["changed"] is True


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_system.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_system.AnsibleModule")
def test_main_missing_file_and_device_fails(
    mock_ansible_module: MagicMock, _mock_get_connection: MagicMock
) -> None:
    mod = MagicMock()
    mod.check_mode = False
    p = _base_params()
    p["system_config_file"] = None
    p["device"] = "   "
    mod.params = p
    mock_ansible_module.return_value = mod
    graphiant_device_system.main()
    mod.fail_json.assert_called()
    err = mod.fail_json.call_args[1].get("msg", "")
    assert "system_config_file" in err or "device" in err


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_system.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_system.AnsibleModule")
def test_main_file_only_with_no_device_system_entries(
    mock_ansible_module: MagicMock, _mock_get_connection: MagicMock
) -> None:
    mod = MagicMock()
    mod.check_mode = False
    p = _base_params()
    mod.params = p
    mock_ansible_module.return_value = mod
    dsys = MagicMock()
    dsys.configure.return_value = {
        "no_input": True,
        "changed": False,
        "configured_devices": [],
        "skipped_devices": [],
    }
    gc = MagicMock()
    gc.device_system = dsys
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)
    graphiant_device_system.main()
    dsys.configure.assert_called_once()
    mod.exit_json.assert_called_once()
    assert "nothing to do" in (mod.exit_json.call_args[1].get("msg", "") or "").lower()


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_system.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_system.AnsibleModule")
def test_main_configure_call_args(
    mock_ansible_module: MagicMock, _mock_get_connection: MagicMock
) -> None:
    mod = MagicMock()
    mod.check_mode = False
    p = _base_params()
    mod.params = p
    mock_ansible_module.return_value = mod
    dsys = MagicMock()
    dsys.configure.return_value = {
        "changed": True,
        "configured_devices": ["edge-1"],
        "skipped_devices": [],
    }
    gc = MagicMock()
    gc.device_system = dsys
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)
    graphiant_device_system.main()
    cargs, _ckwargs = dsys.configure.call_args
    assert cargs[0] == "sample_device_system.yaml"
    mp = cargs[1]
    assert mp == {
        "device": None,
        "name": None,
        "regionName": None,
        "site": None,
    }
    mod.exit_json.assert_called_once()


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_system.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_system.AnsibleModule")
def test_main_configure_with_diff_mode_emits_ansible_diff(
    mock_ansible_module: MagicMock, _mock_get_connection: MagicMock
) -> None:
    """When the module runs in diff mode (``_diff``), ``exit_json`` includes Ansible ``diff`` from ``diff_plan``."""
    mod = MagicMock()
    mod.check_mode = False
    mod._diff = True
    p = _base_params()
    mod.params = p
    mock_ansible_module.return_value = mod
    dsys = MagicMock()
    dsys.configure.return_value = {
        "changed": True,
        "configured_devices": ["edge-3-sdktest"],
        "skipped_devices": ["edge-1-sdktest"],
        "diff_plan": [
            {
                "device": "edge-3-sdktest",
                "branch": "edge",
                "before": {"name": "edge-3-sdktest", "regionName": "us-east-1 (N. Virginia)"},
                "after": {"name": "edge-3-sdktest", "regionName": "us-east-2 (Atlanta)"},
            }
        ],
    }
    gc = MagicMock()
    gc.device_system = dsys
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)
    graphiant_device_system.main()
    mod.exit_json.assert_called_once()
    payload = mod.exit_json.call_args[1]
    assert "diff" in payload
    assert "before" in payload["diff"] and "after" in payload["diff"]
    assert "edge-3-sdktest" in payload["diff"]["before"]
    assert "us-east-2 (Atlanta)" in payload["diff"]["after"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_system.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_system.AnsibleModule")
def test_main_skipped_no_site_fails(
    mock_ansible_module: MagicMock, _mock_get_connection: MagicMock
) -> None:
    mod = MagicMock()
    mod.check_mode = False
    p = _base_params()
    mod.params = p
    mock_ansible_module.return_value = mod
    dsys = MagicMock()
    dsys.configure.return_value = {
        "changed": False,
        "configured_devices": [],
        "skipped_no_site": ["cpe-55"],
        "would_configure_devices": ["edge-1", "edge-2"],
        "aborted_pushes_due_to_no_site": True,
        "skipped_devices": [],
    }
    gc = MagicMock()
    gc.device_system = dsys
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)
    graphiant_device_system.main()
    mod.fail_json.assert_called_once()
    fk = mod.fail_json.call_args[1]
    assert fk.get("changed") is False
    assert fk.get("skipped_no_site") == ["cpe-55"]
    assert len(fk.get("would_configure_devices", [])) == 2
    assert "no site" in (fk.get("msg") or "").lower() or "Cannot apply" in (fk.get("msg") or "")
