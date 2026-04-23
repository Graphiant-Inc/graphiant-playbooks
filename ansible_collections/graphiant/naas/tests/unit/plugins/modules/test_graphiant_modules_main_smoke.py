# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""
Smoke: call main() for each collection module with AnsibleModule and connection mocked.

Raises overall coverage; full branch coverage of large managers would need separate tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

BASE = {
    "host": "https://api.example.com",
    "username": "u",
    "password": "p",
    "access_token": None,
    "detailed_logs": False,
}


def _mod(**params) -> MagicMock:
    p = {**BASE, **params}
    m = MagicMock()
    m.check_mode = False
    m.params = p
    return m


def _result():
    return {"changed": False, "skipped_devices": []}


def _conn_with(**attrs: MagicMock) -> MagicMock:
    # Use MagicMock(k=v) for children so global_config and managers are stable (not
    # auto children that return new MagicMocks per call; see graphiant_global_config
    # execute_with_logging, which needs a real dict from deconfigure, not a mock object).
    gc = MagicMock(**attrs)
    c = MagicMock()
    c.graphiant_config = gc
    return c


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_bgp.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_bgp.AnsibleModule")
def test_graphiant_bgp_detach_policies(m_am, m_gc) -> None:
    from ansible_collections.graphiant.naas.plugins.modules import graphiant_bgp

    m = _mod(
        bgp_config_file="x.yaml",
        operation="detach_policies",
        state="present",
    )
    m_am.return_value = m
    mgr = MagicMock()
    mgr.detach_policies.return_value = _result()
    m_gc.return_value = _conn_with(bgp=mgr)
    graphiant_bgp.main()
    m.exit_json.assert_called_once()
    mgr.detach_policies.assert_called_once_with("x.yaml")


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_bgp.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_bgp.AnsibleModule")
def test_graphiant_bgp_deconfigure(m_am, m_gc) -> None:
    from ansible_collections.graphiant.naas.plugins.modules import graphiant_bgp

    m = _mod(
        bgp_config_file="x.yaml",
        operation="deconfigure",
        state="present",
    )
    m_am.return_value = m
    mgr = MagicMock()
    mgr.deconfigure.return_value = _result()
    m_gc.return_value = _conn_with(bgp=mgr)
    graphiant_bgp.main()
    m.exit_json.assert_called_once()
    mgr.deconfigure.assert_called_once_with("x.yaml")


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_bgp.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_bgp.AnsibleModule")
def test_graphiant_bgp_configure(m_am, m_gc) -> None:
    from ansible_collections.graphiant.naas.plugins.modules import graphiant_bgp

    m = _mod(
        bgp_config_file="x.yaml",
        operation="configure",
        state="present",
    )
    m_am.return_value = m
    mgr = MagicMock()
    mgr.configure.return_value = _result()
    m_gc.return_value = _conn_with(bgp=mgr)
    graphiant_bgp.main()
    m.exit_json.assert_called_once()
    mgr.configure.assert_called_once_with("x.yaml")


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_sites.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_sites.AnsibleModule")
def test_graphiant_sites_deconfigure(m_am, m_gc) -> None:
    from ansible_collections.graphiant.naas.plugins.modules import graphiant_sites

    m = _mod(
        site_config_file="s.yaml",
        operation="deconfigure",
        state="present",
    )
    m_am.return_value = m
    mgr = MagicMock()
    mgr.deconfigure.return_value = _result()
    m_gc.return_value = _conn_with(sites=mgr)
    graphiant_sites.main()
    m.exit_json.assert_called_once()
    mgr.deconfigure.assert_called_once_with("s.yaml")


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_sites.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_sites.AnsibleModule")
def test_graphiant_sites_attach_objects(m_am, m_gc) -> None:
    from ansible_collections.graphiant.naas.plugins.modules import graphiant_sites

    m = _mod(
        site_config_file="s.yaml",
        operation="attach_objects",
        state="present",
    )
    m_am.return_value = m
    mgr = MagicMock()
    mgr.attach_objects.return_value = _result()
    m_gc.return_value = _conn_with(sites=mgr)
    graphiant_sites.main()
    m.exit_json.assert_called_once()
    mgr.attach_objects.assert_called_once_with("s.yaml")


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_sites.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_sites.AnsibleModule")
def test_graphiant_sites_configure(m_am, m_gc) -> None:
    from ansible_collections.graphiant.naas.plugins.modules import graphiant_sites

    m = _mod(
        site_config_file="s.yaml",
        operation="configure",
        state="present",
    )
    m_am.return_value = m
    mgr = MagicMock()
    mgr.configure.return_value = _result()
    m_gc.return_value = _conn_with(sites=mgr)
    graphiant_sites.main()
    m.exit_json.assert_called_once()


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_vrrp.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_vrrp.AnsibleModule")
def test_graphiant_vrrp_deconfigure(m_am, m_gc) -> None:
    from ansible_collections.graphiant.naas.plugins.modules import graphiant_vrrp

    m = _mod(
        vrrp_config_file="v.yaml",
        operation="deconfigure",
        state="present",
    )
    m_am.return_value = m
    mgr = MagicMock()
    mgr.deconfigure_vrrp_interfaces.return_value = _result()
    m_gc.return_value = _conn_with(vrrp_interfaces=mgr)
    graphiant_vrrp.main()
    m.exit_json.assert_called_once()
    mgr.deconfigure_vrrp_interfaces.assert_called_once_with("v.yaml")


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_vrrp.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_vrrp.AnsibleModule")
def test_graphiant_vrrp_configure(m_am, m_gc) -> None:
    from ansible_collections.graphiant.naas.plugins.modules import graphiant_vrrp

    m = _mod(
        vrrp_config_file="v.yaml",
        operation="configure",
        state="present",
    )
    m_am.return_value = m
    mgr = MagicMock()
    mgr.configure_vrrp_interfaces.return_value = _result()
    m_gc.return_value = _conn_with(vrrp_interfaces=mgr)
    graphiant_vrrp.main()
    m.exit_json.assert_called_once()


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_interfaces.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_interfaces.AnsibleModule")
def test_graphiant_interfaces_configure_circuits(m_am, m_gc) -> None:
    from ansible_collections.graphiant.naas.plugins.modules import graphiant_interfaces

    m = _mod(
        interface_config_file="i.yaml",
        circuit_config_file="c.yaml",
        operation="configure_circuits",
        state="present",
    )
    m_am.return_value = m
    mgr = MagicMock()
    mgr.configure_circuits.return_value = _result()
    m_gc.return_value = _conn_with(interfaces=mgr)
    graphiant_interfaces.main()
    m.exit_json.assert_called_once()
    mgr.configure_circuits.assert_called_once_with("c.yaml", "i.yaml")


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_interfaces.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_interfaces.AnsibleModule")
def test_graphiant_interfaces_configure_lan(m_am, m_gc) -> None:
    from ansible_collections.graphiant.naas.plugins.modules import graphiant_interfaces

    m = _mod(
        interface_config_file="i.yaml",
        operation="configure_lan_interfaces",
        state="present",
    )
    m_am.return_value = m
    mgr = MagicMock()
    mgr.configure_lan_interfaces.return_value = _result()
    m_gc.return_value = _conn_with(interfaces=mgr)
    graphiant_interfaces.main()
    m.exit_json.assert_called_once()


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_lag_interfaces.graphiant_utils.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_lag_interfaces.AnsibleModule")
def test_graphiant_lag_configure(m_am, m_gc) -> None:
    from ansible_collections.graphiant.naas.plugins.modules import graphiant_lag_interfaces

    m = _mod(
        lag_config_file="l.yaml",
        operation="configure",
        state="present",
    )
    m_am.return_value = m
    mgr = MagicMock()
    mgr.configure.return_value = _result()
    m_gc.return_value = _conn_with(lag_interfaces=mgr)
    graphiant_lag_interfaces.main()
    m.exit_json.assert_called_once()


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_config.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_config.AnsibleModule")
def test_graphiant_device_config_show_validated_payload(m_am, m_gc) -> None:
    from ansible_collections.graphiant.naas.plugins.modules import graphiant_device_config

    m = _mod(
        config_file="c.yaml",
        template_file=None,
        operation="show_validated_payload",
        state="present",
    )
    m_am.return_value = m
    mgr = MagicMock()
    mgr.show_validated_payload.return_value = {"changed": False, "payload": {}}
    m_gc.return_value = _conn_with(device_config=mgr)
    graphiant_device_config.main()
    m.exit_json.assert_called_once()
    mgr.show_validated_payload.assert_called_once_with("c.yaml", None)


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_config.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_config.AnsibleModule")
def test_graphiant_device_config_configure(m_am, m_gc) -> None:
    from ansible_collections.graphiant.naas.plugins.modules import graphiant_device_config

    m = _mod(
        config_file="c.yaml",
        template_file=None,
        operation="configure",
        state="present",
    )
    m_am.return_value = m
    mgr = MagicMock()
    mgr.configure.return_value = _result()
    m_gc.return_value = _conn_with(device_config=mgr)
    graphiant_device_config.main()
    m.exit_json.assert_called_once()


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_global_config.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_global_config.AnsibleModule")
def test_graphiant_global_config_deconfigure_fail_in_use(m_am, m_gc) -> None:
    from ansible_collections.graphiant.naas.plugins.modules import graphiant_global_config

    m = _mod(
        config_file="g.yaml",
        operation="deconfigure",
        state="present",
    )
    m_am.return_value = m

    class FailingDeconfigure:
        @staticmethod
        def deconfigure(_path: str) -> dict:
            return {"changed": True, "failed_objects": ["obj1"]}

    m_gc.return_value = _conn_with(global_config=FailingDeconfigure())
    m.fail_json.side_effect = SystemExit(0)  # real fail_json does not return
    with pytest.raises(SystemExit):
        graphiant_global_config.main()
    m.fail_json.assert_called_once()
    m.exit_json.assert_not_called()


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_global_config.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_global_config.AnsibleModule")
def test_graphiant_global_config_deconfigure_prefix_sets(m_am, m_gc) -> None:
    from ansible_collections.graphiant.naas.plugins.modules import graphiant_global_config

    m = _mod(
        config_file="g.yaml",
        operation="deconfigure_prefix_sets",
        state="present",
    )
    m_am.return_value = m
    mgr = MagicMock()
    mgr.deconfigure_prefix_sets.return_value = {"changed": True, "deleted": [], "skipped": []}
    m_gc.return_value = _conn_with(global_config=mgr)
    graphiant_global_config.main()
    m.exit_json.assert_called_once()
    mgr.deconfigure_prefix_sets.assert_called_once_with("g.yaml")


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_global_config.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_global_config.AnsibleModule")
def test_graphiant_global_config_configure(m_am, m_gc) -> None:
    from ansible_collections.graphiant.naas.plugins.modules import graphiant_global_config

    m = _mod(
        config_file="g.yaml",
        operation="configure",
        state="present",
    )
    m_am.return_value = m
    mgr = MagicMock()
    mgr.configure.return_value = _result()
    m_gc.return_value = _conn_with(global_config=mgr)
    graphiant_global_config.main()
    m.exit_json.assert_called_once()


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_site_to_site_vpn.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_site_to_site_vpn.AnsibleModule")
def test_graphiant_site_to_site_vpn_create(m_am, m_gc) -> None:
    from ansible_collections.graphiant.naas.plugins.modules import graphiant_site_to_site_vpn

    m = _mod(
        site_to_site_vpn_config_file="v.yaml",
        operation="create",
        state="present",
        vault_site_to_site_vpn_keys={},
        vault_bgp_md5_passwords={},
    )
    m_am.return_value = m
    mgr = MagicMock()
    mgr.create_site_to_site_vpn.return_value = _result()
    m_gc.return_value = _conn_with(site_to_site_vpn=mgr)
    graphiant_site_to_site_vpn.main()
    m.exit_json.assert_called_once()


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_data_exchange.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_data_exchange.AnsibleModule")
def test_graphiant_data_exchange_delete_services(m_am, m_gc) -> None:
    from ansible_collections.graphiant.naas.plugins.modules import graphiant_data_exchange

    m = _mod(
        operation="delete_services",
        state=None,
        config_file="d.yaml",
        matches_file=None,
    )
    m.params["state"] = None
    m_am.return_value = m
    mgr = MagicMock()
    mgr.delete_services.return_value = _result()
    m_gc.return_value = _conn_with(data_exchange=mgr)
    graphiant_data_exchange.main()
    m.exit_json.assert_called_once()
    mgr.delete_services.assert_called_once_with("d.yaml")


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_data_exchange.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_data_exchange.AnsibleModule")
def test_graphiant_data_exchange_create_services(m_am, m_gc) -> None:
    from ansible_collections.graphiant.naas.plugins.modules import graphiant_data_exchange

    m = _mod(
        operation="create_services",
        state=None,
        config_file="d.yaml",
        matches_file=None,
    )
    m.params["state"] = None
    m_am.return_value = m
    mgr = MagicMock()
    mgr.create_services.return_value = _result()
    m_gc.return_value = _conn_with(data_exchange=mgr)
    graphiant_data_exchange.main()
    m.exit_json.assert_called_once()


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_data_exchange_info.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_data_exchange_info.AnsibleModule")
def test_graphiant_data_exchange_info_summary(m_am, m_gc) -> None:
    from ansible_collections.graphiant.naas.plugins.modules import graphiant_data_exchange_info

    m = _mod(
        query="services_summary",
        service_name=None,
        is_provider=False,
    )
    m_am.return_value = m
    dx = MagicMock()
    dx.get_services_summary.return_value = {"result_msg": "m", "result_data": []}
    m_gc.return_value = _conn_with(data_exchange=dx)
    graphiant_data_exchange_info.main()
    m.exit_json.assert_called_once()
