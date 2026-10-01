# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for graphiant_device_lifecycle_info module (mocked Ansible + connection)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ansible_collections.graphiant.naas.plugins.modules import graphiant_device_lifecycle_info


def _base_params(**overrides) -> dict:
    params = {
        "host": "https://api.example.com",
        "username": "u",
        "password": "p",
        "access_token": None,
        "config_file": None,
        "device": None,
        "role": None,
        "detailed_logs": False,
    }
    params.update(overrides)
    return params


def _mock_module(params: dict) -> MagicMock:
    mod = MagicMock()
    mod.check_mode = False
    mod.params = params
    return mod


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle_info.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle_info.AnsibleModule")
def test_main_lists_all_devices_by_role(mock_ansible_module: MagicMock, _mock_get_connection: MagicMock) -> None:
    mod = _mock_module(_base_params(role="cpe"))
    mock_ansible_module.return_value = mod
    manager = MagicMock()
    manager.get_status.return_value = {
        "changed": False,
        "devices": {"edge-1-sdktest": {"status": "active"}},
        "failed_devices": [],
    }
    gc = MagicMock()
    gc.device_lifecycle = manager
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle_info.main()

    ckwargs = manager.get_status.call_args.kwargs
    assert ckwargs["role"] == "cpe"
    mod.exit_json.assert_called_once()
    payload = mod.exit_json.call_args[1]
    assert payload["changed"] is False
    assert payload["devices"] == {"edge-1-sdktest": {"status": "active"}}


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle_info.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle_info.AnsibleModule")
def test_main_single_device_call_args(mock_ansible_module: MagicMock, _mock_get_connection: MagicMock) -> None:
    mod = _mock_module(_base_params(device="edge-1-sdktest"))
    mock_ansible_module.return_value = mod
    manager = MagicMock()
    manager.get_status.return_value = {
        "changed": False,
        "devices": {"edge-1-sdktest": {"status": "active"}},
        "failed_devices": [],
    }
    gc = MagicMock()
    gc.device_lifecycle = manager
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle_info.main()

    ckwargs = manager.get_status.call_args.kwargs
    assert ckwargs["module_params"] == {"device": "edge-1-sdktest"}
    mod.exit_json.assert_called_once()


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle_info.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle_info.AnsibleModule")
def test_main_fails_when_requested_device_not_found(
    mock_ansible_module: MagicMock, _mock_get_connection: MagicMock
) -> None:
    # failed_devices is only ever non-empty when specific devices were requested (by device or
    # config_file) — that's a real failure, not just informational.
    mod = _mock_module(_base_params(device="ghost-device"))
    mock_ansible_module.return_value = mod
    manager = MagicMock()
    manager.get_status.return_value = {
        "changed": False,
        "devices": {},
        "failed_devices": [{"device_name": "ghost-device", "error": "Device 'ghost-device' not found"}],
    }
    gc = MagicMock()
    gc.device_lifecycle = manager
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle_info.main()

    mod.exit_json.assert_not_called()
    mod.fail_json.assert_called_once()
    payload = mod.fail_json.call_args[1]
    assert payload["failed_devices"] == [{"device_name": "ghost-device", "error": "Device 'ghost-device' not found"}]
    assert "not found" in payload["msg"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle_info.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle_info.AnsibleModule")
def test_main_preserves_detailed_logs_suffix(mock_ansible_module: MagicMock, _mock_get_connection: MagicMock) -> None:
    """The module recomputes its summary msg from details, but must not drop the
    "Detailed logs:" suffix capture_library_logs appends when detailed_logs=true."""
    from ansible_collections.graphiant.naas.plugins.module_utils.libs.logger import setup_logger

    mod = _mock_module(_base_params(role="cpe", detailed_logs=True))
    mock_ansible_module.return_value = mod

    def _fake_get_status(**_kwargs):
        setup_logger().info("fetched status for edge-1-sdktest")
        return {"changed": False, "devices": {"edge-1-sdktest": {"status": "active"}}, "failed_devices": []}

    manager = MagicMock()
    manager.get_status.side_effect = _fake_get_status
    gc = MagicMock()
    gc.device_lifecycle = manager
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle_info.main()

    payload = mod.exit_json.call_args[1]
    assert payload["msg"].startswith("Retrieved status for 1 device(s)")
    assert "Detailed logs:" in payload["msg"]
    assert "fetched status for edge-1-sdktest" in payload["msg"]
