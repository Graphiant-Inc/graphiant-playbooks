# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for graphiant_macsec_info module (mocked Ansible + connection)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ansible_collections.graphiant.naas.plugins.modules import graphiant_macsec_info


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_macsec_info.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_macsec_info.AnsibleModule")
def test_main_requires_device(mock_module_cls, mock_conn) -> None:
    module = MagicMock()
    module.params = {
        "host": "https://api.example.com",
        "username": "u",
        "password": "p",
        "access_token": None,
        "device": "",
        "interface": None,
        "detailed_logs": False,
    }
    module.check_mode = False
    mock_module_cls.return_value = module

    graphiant_macsec_info.main()
    module.fail_json.assert_called_once()
    assert "device is required" in module.fail_json.call_args.kwargs["msg"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_macsec_info.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_macsec_info.AnsibleModule")
def test_main_returns_statuses(mock_module_cls, mock_conn) -> None:
    module = MagicMock()
    module.params = {
        "host": "https://api.example.com",
        "username": "u",
        "password": "p",
        "access_token": None,
        "device": "edge-1-sdktest",
        "interface": None,
        "detailed_logs": False,
    }
    module.check_mode = False
    mock_module_cls.return_value = module

    mock_macsec = MagicMock()
    mock_macsec.get_macsec_status.return_value = {
        "device": "edge-1-sdktest",
        "device_id": 30000056248,
        "macsec_statuses": [
            {"interfaceName": "LAG1", "status": "MACSEC_STATUS_UNSECURE"},
        ],
    }
    mock_conn.return_value.graphiant_config.macsec = mock_macsec

    graphiant_macsec_info.main()
    module.exit_json.assert_called_once()
    payload = module.exit_json.call_args.kwargs
    assert payload["changed"] is False
    assert payload["macsec_statuses"][0]["status"] == "MACSEC_STATUS_UNSECURE"
