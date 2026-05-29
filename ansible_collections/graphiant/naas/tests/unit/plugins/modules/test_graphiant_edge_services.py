# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for graphiant_edge_services module (mocked Ansible + connection)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ansible_collections.graphiant.naas.plugins.module_utils.libs.device_config_common import (
    ansible_diff_from_plan,
)
from ansible_collections.graphiant.naas.plugins.modules import graphiant_edge_services


def test_ansible_diff_from_plan() -> None:
    diff_plan = [
        {
            "device": "edge-10-joule-sj-dr",
            "branch": "edge",
            "before": {"dns": {"mode": "DNSModeDynamic"}},
            "after": {"dns": {"mode": "DNSModeCloudflare"}},
        }
    ]
    d = ansible_diff_from_plan(diff_plan)
    assert "DNSModeCloudflare" in d["after"]


def test_module_params_from_ansible_camel_case() -> None:
    mp = graphiant_edge_services._module_params_from_ansible(
        {
            "device": " edge-1 ",
            "localWebServerPassword": "Secret1Pass",
            "localWebServerPasswordForce": True,
            "dns": {"mode": "DNSModeDynamic"},
            "lldp": {"GigabitEthernet4/0/0": True},
            "dhcpSubnets": [{"segment": "lan-1-test", "interface": "GigabitEthernet7/0/0", "ipPrefix": "10.1.11.0/24"}],
        }
    )
    assert mp["device"] == "edge-1"
    assert mp["localWebServerPassword"] == "Secret1Pass"
    assert mp["localWebServerPasswordForce"] is True
    assert mp["dhcpSubnets"][0]["segment"] == "lan-1-test"


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_edge_services.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_edge_services.AnsibleModule")
def test_main_requires_device_or_file(mock_module_cls, mock_conn) -> None:
    module = MagicMock()
    module.params = {
        "host": "https://api.example.com",
        "username": "u",
        "password": "p",
        "access_token": None,
        "edge_services_config_file": None,
        "device": "",
        "localWebServerPassword": None,
        "localWebServerPasswordForce": False,
        "dns": None,
        "lldp": None,
        "dhcpSubnets": None,
        "vault_devices_lws_password": {},
        "operation": "configure",
        "state": "present",
        "detailed_logs": False,
    }
    module.check_mode = False
    mock_module_cls.return_value = module

    graphiant_edge_services.main()
    module.fail_json.assert_called_once()
    assert "edge_services_config_file" in module.fail_json.call_args.kwargs["msg"]
