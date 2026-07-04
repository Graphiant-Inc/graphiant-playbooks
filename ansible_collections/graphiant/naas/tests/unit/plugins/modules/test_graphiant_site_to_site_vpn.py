# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for graphiant_site_to_site_vpn module (mocked Ansible + connection)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ansible_collections.graphiant.naas.plugins.modules import graphiant_site_to_site_vpn


def _base_params() -> dict:
    return {
        "host": "https://api.example.com",
        "username": "u",
        "password": "p",
        "access_token": None,
        "site_to_site_vpn_config_file": "sample_site_to_site_vpn.yaml",
        "operation": "create",
        "state": "present",
        "detailed_logs": False,
        "vault_site_to_site_vpn_keys": {},
        "vault_bgp_md5_passwords": {},
    }


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_site_to_site_vpn.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_site_to_site_vpn.AnsibleModule")
def test_main_create_calls_create_site_to_site_vpn(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod._diff = False
    mod.params = _base_params()
    mock_ansible_module.return_value = mod

    s2s = MagicMock()
    s2s.create_site_to_site_vpn.return_value = {"changed": True}
    gc = MagicMock()
    gc.site_to_site_vpn = s2s
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_site_to_site_vpn.main()

    s2s.create_site_to_site_vpn.assert_called_once()
    mod.exit_json.assert_called_once()
    kwargs = mod.exit_json.call_args[1]
    assert kwargs["operation"] == "create"
    assert kwargs["changed"] is True


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_site_to_site_vpn.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_site_to_site_vpn.AnsibleModule")
def test_main_delete_calls_delete_site_to_site_vpn(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod._diff = False
    p = _base_params()
    p["operation"] = "delete"
    p["state"] = "absent"
    mod.params = p
    mock_ansible_module.return_value = mod

    s2s = MagicMock()
    s2s.delete_site_to_site_vpn.return_value = {"changed": True}
    gc = MagicMock()
    gc.site_to_site_vpn = s2s
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_site_to_site_vpn.main()

    s2s.delete_site_to_site_vpn.assert_called_once()
    mod.exit_json.assert_called_once()
    kwargs = mod.exit_json.call_args[1]
    assert kwargs["operation"] == "delete"


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_site_to_site_vpn.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_site_to_site_vpn.AnsibleModule")
def test_main_diff_mode_create_sets_diff_key(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod._diff = True
    mod.params = _base_params()
    mock_ansible_module.return_value = mod

    s2s = MagicMock()
    s2s.create_site_to_site_vpn.return_value = {
        "changed": True,
        "diff_plan": [
            {
                "device": "edge-1-sdktest",
                "branch": "edge.siteToSiteVpn",
                "before": {"siteToSiteVpn": {}},
                "after": {"siteToSiteVpn": {"vpn-test": {"port": 500, "localIp": "192.168.1.1"}}},
            }
        ],
    }
    gc = MagicMock()
    gc.site_to_site_vpn = s2s
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_site_to_site_vpn.main()

    kwargs = mod.exit_json.call_args[1]
    assert "diff" in kwargs
    assert "edge-1-sdktest" in kwargs["diff"]["before"]
    assert "edge-1-sdktest" in kwargs["diff"]["after"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_site_to_site_vpn.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_site_to_site_vpn.AnsibleModule")
def test_main_diff_mode_delete_sets_diff_key_without_secrets(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod._diff = True
    p = _base_params()
    p["operation"] = "delete"
    mod.params = p
    mock_ansible_module.return_value = mod

    s2s = MagicMock()
    # Simulate the manager returning redacted before-snapshot (presharedKey already dropped by _drop_secrets)
    s2s.delete_site_to_site_vpn.return_value = {
        "changed": True,
        "diff_plan": [
            {
                "device": "edge-1-sdktest",
                "branch": "edge.siteToSiteVpn",
                "before": {"siteToSiteVpn": {"vpn-test": {"port": 500}}},
                "after": {"siteToSiteVpn": {"vpn-test": None}},
            }
        ],
    }
    gc = MagicMock()
    gc.site_to_site_vpn = s2s
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_site_to_site_vpn.main()

    kwargs = mod.exit_json.call_args[1]
    assert "diff" in kwargs
    assert "presharedKey" not in kwargs["diff"]["before"]
    assert "md5Password" not in kwargs["diff"]["before"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_site_to_site_vpn.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_site_to_site_vpn.AnsibleModule")
def test_main_create_idempotent_no_diff(mock_ansible_module, mock_get_connection) -> None:
    """When VPNs already match desired state the module exits changed=False with no diff key."""
    mod = MagicMock()
    mod.check_mode = False
    mod._diff = True
    mod.params = _base_params()
    mock_ansible_module.return_value = mod

    s2s = MagicMock()
    s2s.create_site_to_site_vpn.return_value = {"changed": False, "diff_plan": []}
    gc = MagicMock()
    gc.site_to_site_vpn = s2s
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_site_to_site_vpn.main()

    kwargs = mod.exit_json.call_args[1]
    assert kwargs["changed"] is False
    assert "diff" not in kwargs


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_site_to_site_vpn.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_site_to_site_vpn.AnsibleModule")
def test_main_delete_idempotent_no_diff(mock_ansible_module, mock_get_connection) -> None:
    """When VPNs to delete are already absent the module exits changed=False with no diff key."""
    mod = MagicMock()
    mod.check_mode = False
    mod._diff = True
    p = _base_params()
    p["operation"] = "delete"
    p["state"] = "absent"
    mod.params = p
    mock_ansible_module.return_value = mod

    s2s = MagicMock()
    s2s.delete_site_to_site_vpn.return_value = {"changed": False, "diff_plan": []}
    gc = MagicMock()
    gc.site_to_site_vpn = s2s
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_site_to_site_vpn.main()

    kwargs = mod.exit_json.call_args[1]
    assert kwargs["changed"] is False
    assert "diff" not in kwargs


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_site_to_site_vpn.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_site_to_site_vpn.AnsibleModule")
def test_main_no_diff_key_when_diff_mode_off(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod._diff = False
    mod.params = _base_params()
    mock_ansible_module.return_value = mod

    s2s = MagicMock()
    s2s.create_site_to_site_vpn.return_value = {
        "changed": True,
        "diff_plan": [
            {"device": "edge-1-sdktest", "branch": "edge.siteToSiteVpn", "before": {}, "after": {"x": 1}}
        ],
    }
    gc = MagicMock()
    gc.site_to_site_vpn = s2s
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_site_to_site_vpn.main()

    kwargs = mod.exit_json.call_args[1]
    assert "diff" not in kwargs
