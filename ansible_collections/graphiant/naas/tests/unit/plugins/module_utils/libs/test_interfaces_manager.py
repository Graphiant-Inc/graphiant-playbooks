# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""
Unit tests for InterfaceManager.

Two areas are covered:

1. Payload builders -- the pure-Python ``_build_interface`` / ``_build_circuit``
   that replaced the Jinja2 templates. Representative cases assert the exact
   payload dict for LAN/WAN/subinterface/delete/default_lan and circuits.

2. Check-mode / diff-plan reporting -- each operation returns the standard
   apply-result (``changed``, ``configured_devices``, ``skipped_devices``,
   ``diff_plan``). Pushes no-op under check mode (gsdk.put_device_config).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from ansible_collections.graphiant.naas.plugins.module_utils.libs.exceptions import ConfigurationError
from ansible_collections.graphiant.naas.plugins.module_utils.libs.interface_manager import InterfaceManager

# ===========================================================================
# Payload builder tests
# ===========================================================================


def test_build_interface_lan_static_addresses() -> None:
    result = InterfaceManager._build_interface(
        "GigabitEthernet7/0/0",
        action="add",
        lan="lan-1",
        ipv4="10.1.11.1/24",
        ipv6="2001:db8::1/64",
        maxTransmissionUnit=1500,
        v4TcpMss=1392,
    )
    assert result == {
        "interfaces": {
            "GigabitEthernet7/0/0": {
                "interface": {
                    "adminStatus": True,
                    "loopback": None,
                    "maxTransmissionUnit": 1500,
                    "lan": "lan-1",
                    "description": "lan-1",
                    "v4TcpMss": {"tcpMssV4": 1392},
                    "ipv4": {"address": {"address": "10.1.11.1/24"}},
                    "ipv6": {"address": {"address": "2001:db8::1/64"}},
                }
            }
        }
    }


def test_build_interface_wan_circuit_defaults_to_dhcp() -> None:
    result = InterfaceManager._build_interface("GigabitEthernet5/0/0", action="add", circuit="c-wan")
    interface = result["interfaces"]["GigabitEthernet5/0/0"]["interface"]
    assert interface["circuit"] == "c-wan"
    assert interface["description"] == "c-wan"  # defaults to circuit name
    assert interface["alias"] == "c-wan"  # circuit interfaces keep a synthesized (unique) alias
    assert interface["ipv4"] == {"dhcp": {"dhcpClient": True}}
    assert interface["ipv6"] == {"dhcp": {"dhcpClient": True}}


def test_build_interface_subinterface_keys_are_strings_values_int() -> None:
    result = InterfaceManager._build_interface(
        "GigabitEthernet7/0/0",
        action="add",
        subinterfaces=[{"vlan": 18, "lan": "lan-7", "ipv4": "10.1.17.1/24", "v4TcpMss": 1392}],
    )
    subs = result["interfaces"]["GigabitEthernet7/0/0"]["interface"]["subinterfaces"]
    # Key is the quoted vlan (string); inner "vlan" stays an int.
    assert set(subs) == {"18"}
    sub = subs["18"]["interface"]
    assert sub["vlan"] == 18
    assert sub["lan"] == "lan-7"
    assert sub["description"] == "18_lan-7"  # default(vlan_lan)
    assert "alias" not in sub  # alias is never synthesized — only sent when set
    assert sub["v4TcpMss"] == {"tcpMssV4": 1392}
    assert sub["ipv4"] == {"address": {"address": "10.1.17.1/24"}}
    assert sub["ipv6"] == {"dhcp": {"dhcpClient": True}}


def test_build_interface_explicit_alias_passes_through() -> None:
    # When alias is explicitly set on the main interface and a subinterface, it is sent as-is.
    result = InterfaceManager._build_interface(
        "GigabitEthernet7/0/0",
        action="add",
        lan="lan-1",
        alias="uplink-A",
        subinterfaces=[{"vlan": 18, "lan": "lan-7", "alias": "sub-18"}],
    )
    interface = result["interfaces"]["GigabitEthernet7/0/0"]["interface"]
    assert interface["alias"] == "uplink-A"
    assert interface["subinterfaces"]["18"]["interface"]["alias"] == "sub-18"


def test_build_interface_circuit_sub_alias_synthesized_lan_sub_omitted() -> None:
    # WAN/circuit sub with no alias → synthesized from the (unique) circuit name.
    # LAN sub with no alias → alias omitted (collision-prone default is not sent).
    result = InterfaceManager._build_interface(
        "GigabitEthernet5/0/0",
        action="add",
        circuit="c-wan",
        subinterfaces=[
            {"vlan": 1001, "circuit": "c-wan.1001"},
            {"vlan": 20, "lan": "lan-7"},
        ],
    )
    subs = result["interfaces"]["GigabitEthernet5/0/0"]["interface"]["subinterfaces"]
    assert subs["1001"]["interface"]["alias"] == "c-wan.1001"  # circuit sub keeps a synthesized alias
    assert "alias" not in subs["20"]["interface"]  # LAN sub alias is omitted


def test_build_interface_delete_resets_to_default_lan() -> None:
    result = InterfaceManager._build_interface("gig1", action="delete", default_lan="default-ent1", lan="lan-1")
    assert result == {
        "interfaces": {
            "gig1": {"interface": {"lan": "default-ent1", "circuit": None, "description": "", "alias": "gig1"}}
        }
    }


def test_build_interface_default_lan_with_subinterface() -> None:
    result = InterfaceManager._build_interface(
        "gig1",
        action="default_lan",
        default_lan="default-ent1",
        lan="lan-1",
        subinterfaces=[{"vlan": 10, "lan": "lan-x"}],
    )
    interface = result["interfaces"]["gig1"]["interface"]
    assert interface["lan"] == "default-ent1"
    assert interface["circuit"] is None
    assert interface["subinterfaces"]["10"]["interface"] == {
        "lan": "default-ent1",
        "vlan": 10,
        "circuit": None,
        "description": "",
        "alias": "gig1.10",
    }


def test_build_interface_delete_subinterface_is_null() -> None:
    result = InterfaceManager._build_interface(
        "gig1", action="delete", default_lan="default-ent1", subinterfaces=[{"vlan": 10, "lan": "lan-x"}]
    )
    subs = result["interfaces"]["gig1"]["interface"]["subinterfaces"]
    assert subs == {"10": {"interface": None}}


def test_build_interface_legacy_aliases_resolve() -> None:
    # mtu/enabled/v4_tcp_mss/sub_interfaces are accepted as legacy names.
    result = InterfaceManager._build_interface(
        "gig1",
        action="add",
        lan="lan-1",
        mtu=1400,
        enabled=False,
        sub_interfaces=[{"vlan": 5, "lan": "lan-y", "v4_tcp_mss": 1300}],
    )
    interface = result["interfaces"]["gig1"]["interface"]
    assert interface["adminStatus"] is False
    assert interface["maxTransmissionUnit"] == 1400
    assert interface["subinterfaces"]["5"]["interface"]["v4TcpMss"] == {"tcpMssV4": 1300}


def test_build_circuit_add_with_static_routes() -> None:
    result = InterfaceManager._build_circuit(
        "c1",
        action="add",
        upload_bandwidth=500,
        download_bandwidth=1000,
        dia=True,
        static_routes={
            "10.10.0.0/16": {
                "destination_prefix": "10.10.0.0/16",
                "administrative_distance": 2,
                "next_hops": [{"next_hop_address": "10.10.0.1"}],
            }
        },
    )
    assert result == {
        "circuits": {
            "c1": {
                "name": "c1",
                "description": "c1",
                "linkUpSpeedMbps": 500,
                "linkDownSpeedMbps": 1000,
                "circuitType": "circuitType_internet",
                "label": "internet_dia_4",
                "diaEnabled": True,
                "lastResort": False,
                "loopback": None,
                "qosProfile": "gold10",
                "qosProfileType": "balanced",
                "staticRoutes": {
                    "10.10.0.0/16": {
                        "route": {
                            "destinationPrefix": "10.10.0.0/16",
                            "description": "10.10.0.0/16",
                            "administrativeDistance": {"distance": 2},
                            "nextHops": [{"nextHopAddress": "10.10.0.1"}],
                        }
                    }
                },
            }
        }
    }


def test_build_circuit_add_defaults() -> None:
    body = InterfaceManager._build_circuit("c1", action="add")["circuits"]["c1"]
    assert body["linkUpSpeedMbps"] == 100
    assert body["linkDownSpeedMbps"] == 1000
    assert body["label"] == "internet_dia_4"
    assert body["diaEnabled"] is False
    assert body["qosProfile"] == "gold10"
    assert body["staticRoutes"] == {}


def test_build_circuit_delete_nulls_routes() -> None:
    result = InterfaceManager._build_circuit("c1", action="delete", static_routes={"10.10.0.0/16": {}})
    assert result == {"circuits": {"c1": {"staticRoutes": {"10.10.0.0/16": {"route": None}}}}}


def test_build_circuit_camelcase_and_snake_alias_equivalent() -> None:
    # API-aligned camelCase (primary) and legacy snake_case must render identically.
    camel = InterfaceManager._build_circuit(
        "c1",
        action="add",
        linkUpSpeedMbps=500,
        linkDownSpeedMbps=1000,
        circuitType="circuitType_internet",
        diaEnabled=True,
        lastResort=False,
        qosProfile="gold25",
        qosProfileType="balanced",
        staticRoutes={
            "10.10.0.0/16": {
                "destinationPrefix": "10.10.0.0/16",
                "administrativeDistance": 2,
                "nextHops": [{"nextHopAddress": "10.10.0.1"}],
            }
        },
    )
    snake = InterfaceManager._build_circuit(
        "c1",
        action="add",
        upload_bandwidth=500,
        download_bandwidth=1000,
        circuit_type="circuitType_internet",
        dia=True,
        last_resort=False,
        qos_profile="gold25",
        qos_profile_type="balanced",
        static_routes={
            "10.10.0.0/16": {
                "destination_prefix": "10.10.0.0/16",
                "administrative_distance": 2,
                "next_hops": [{"next_hop_address": "10.10.0.1"}],
            }
        },
    )
    assert camel == snake
    body = camel["circuits"]["c1"]
    assert body["linkUpSpeedMbps"] == 500
    assert body["diaEnabled"] is True
    assert body["staticRoutes"]["10.10.0.0/16"]["route"]["nextHops"] == [{"nextHopAddress": "10.10.0.1"}]


def test_build_circuit_camelcase_wins_over_snake_alias() -> None:
    # When both are given, camelCase takes precedence.
    body = InterfaceManager._build_circuit("c1", action="add", linkUpSpeedMbps=999, upload_bandwidth=100)["circuits"][
        "c1"
    ]
    assert body["linkUpSpeedMbps"] == 999


# ===========================================================================
# Check-mode / diff-plan reporting tests
# ===========================================================================


class _AllSegmentsPresent(dict):
    """LAN-segment lookup stub that reports every referenced segment as existing."""

    def __contains__(self, item: object) -> bool:
        return True

    def __bool__(self) -> bool:
        return True


def _make_manager() -> InterfaceManager:
    config_utils = MagicMock()
    config_utils.gsdk = MagicMock()
    config_utils.template = MagicMock()
    mgr = InterfaceManager(config_utils)
    mgr.gsdk.get_device_id = MagicMock(return_value=101)
    mgr.gsdk.get_enterprise_id = MagicMock(return_value="ent1")
    mgr.gsdk.enterprise_info = {"company_name": "acme"}
    mgr.gsdk.check_mode = False
    # By default every referenced LAN segment exists (override per-test to simulate a missing one).
    mgr.gsdk.get_lan_segments_dict = MagicMock(return_value=_AllSegmentsPresent())
    # Never hit the real concurrent executor / API in unit tests.
    mgr.execute_concurrent_tasks = MagicMock()
    return mgr


def _addr(address: Optional[str] = None, dhcp: bool = False) -> Dict[str, Any]:
    """Mimic a GET ipv4/ipv6 block (static address or DHCP client), to_dict-style."""
    block: Dict[str, Any] = {}
    if address is not None:
        block["address"] = address
    if dhcp:
        block["dhcpClient"] = True
    return block


def _iface(
    name: str,
    lan: Optional[str] = None,
    circuit: Optional[str] = None,
    subinterfaces=None,
    *,
    enabled: bool = True,
    loopback: Optional[bool] = None,
    ipv4: Optional[Dict[str, Any]] = None,
    ipv6: Optional[Dict[str, Any]] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """Mimic a ManaV2Interface GET dict (to_dict by_alias; admin flag is ``enabled``)."""
    iface: Dict[str, Any] = {"name": name, "enabled": enabled, "subinterfaces": subinterfaces or []}
    if lan is not None:
        iface["lan"] = lan
    if circuit is not None:
        iface["circuit"] = circuit
    if loopback is not None:
        iface["loopback"] = loopback
    if ipv4 is not None:
        iface["ipv4"] = ipv4
    if ipv6 is not None:
        iface["ipv6"] = ipv6
    if description is not None:
        iface["description"] = description
    return iface


def _circuit(name: str, **attrs: Any) -> Dict[str, Any]:
    """Mimic a ManaV2Circuit GET dict; only the given params are present."""
    circuit: Dict[str, Any] = {"name": name}
    circuit.update(attrs)
    return circuit


def _device_info(interfaces: Optional[List[Any]] = None, circuits: Optional[List[Any]] = None) -> SimpleNamespace:
    """A stand-in for the SDK device-info object: exposes ``to_dict`` like the real model."""
    device = {"interfaces": interfaces or [], "circuits": circuits or []}
    return SimpleNamespace(to_dict=lambda: device)


def _set_config(mgr: InterfaceManager, mapping: Dict[str, Dict[str, Any]]) -> None:
    """Route render_config_file(path) -> the mapped config dict."""
    mgr.render_config_file = MagicMock(side_effect=lambda path: mapping[path])


def test_configure_interfaces_records_diff_and_changed() -> None:
    mgr = _make_manager()
    _set_config(
        mgr,
        {
            "ifaces.yaml": {
                "interfaces": [{"edge-1": [{"name": "GigabitEthernet4/0/0", "lan": "seg-a", "ipv4": "10.0.0.1/24"}]}]
            }
        },
    )
    # Current device has no interface config yet.
    mgr.gsdk.get_device_info = MagicMock(return_value=_device_info(interfaces=[_iface("GigabitEthernet4/0/0")]))

    result = mgr.configure_interfaces("ifaces.yaml")

    assert result["changed"] is True
    assert result["configured_devices"] == ["edge-1"]
    assert result["skipped_devices"] == []
    assert len(result["diff_plan"]) == 1
    entry = result["diff_plan"][0]
    assert entry["device"] == "edge-1"
    assert entry["branch"] == "edge"
    assert "GigabitEthernet4/0/0" in entry["after"]["interfaces"]
    mgr.execute_concurrent_tasks.assert_called_once()


def test_configure_check_mode_still_reports_changed() -> None:
    mgr = _make_manager()
    mgr.gsdk.check_mode = True  # push self-no-ops; manager should still report intent
    _set_config(
        mgr,
        {"ifaces.yaml": {"interfaces": [{"edge-1": [{"name": "GigabitEthernet4/0/0", "lan": "seg-a"}]}]}},
    )
    mgr.gsdk.get_device_info = MagicMock(return_value=_device_info(interfaces=[_iface("GigabitEthernet4/0/0")]))

    result = mgr.configure_interfaces("ifaces.yaml")

    assert result["changed"] is True
    assert result["configured_devices"] == ["edge-1"]
    # The push is still invoked (put_device_config itself no-ops under check mode).
    mgr.execute_concurrent_tasks.assert_called_once()


def test_deconfigure_lan_interfaces_noop_marks_skipped() -> None:
    mgr = _make_manager()
    _set_config(
        mgr,
        {"ifaces.yaml": {"interfaces": [{"edge-1": [{"name": "gig1", "lan": "seg-a"}]}]}},
    )
    # Interface already sits on the enterprise default LAN -> nothing to reset.
    mgr.gsdk.get_device_info = MagicMock(return_value=_device_info(interfaces=[_iface("gig1", lan="default-ent1")]))

    result = mgr.deconfigure_lan_interfaces("ifaces.yaml")

    assert result["changed"] is False
    assert result["configured_devices"] == []
    assert result["skipped_devices"] == ["edge-1"]
    assert result["diff_plan"] == []
    mgr.execute_concurrent_tasks.assert_not_called()


def test_deconfigure_lan_interfaces_resets_when_on_other_lan() -> None:
    mgr = _make_manager()
    _set_config(
        mgr,
        {"ifaces.yaml": {"interfaces": [{"edge-1": [{"name": "gig1", "lan": "seg-a"}]}]}},
    )
    # Interface is on a non-default LAN -> should be reset (changed).
    mgr.gsdk.get_device_info = MagicMock(return_value=_device_info(interfaces=[_iface("gig1", lan="seg-a")]))

    result = mgr.deconfigure_lan_interfaces("ifaces.yaml")

    assert result["changed"] is True
    assert result["configured_devices"] == ["edge-1"]
    assert result["skipped_devices"] == []
    assert len(result["diff_plan"]) == 1
    mgr.execute_concurrent_tasks.assert_called_once()


def test_configure_circuits_records_diff() -> None:
    mgr = _make_manager()
    _set_config(
        mgr,
        {
            "cir.yaml": {"circuits": [{"edge-1": [{"circuit": "c1", "upload_bandwidth": 100}]}]},
            "if.yaml": {"interfaces": [{"edge-1": [{"name": "gig5", "circuit": "c1"}]}]},
        },
    )
    mgr.gsdk.get_device_info = MagicMock(return_value=_device_info(interfaces=[_iface("gig5")], circuits=[]))

    result = mgr.configure_circuits("cir.yaml", "if.yaml")

    assert result["changed"] is True
    assert result["configured_devices"] == ["edge-1"]
    assert len(result["diff_plan"]) == 1
    assert "c1" in result["diff_plan"][0]["after"]["circuits"]
    mgr.execute_concurrent_tasks.assert_called_once()


# ===========================================================================
# Field-level idempotency (configure skips unchanged devices)
# ===========================================================================


def test_configure_skips_when_state_matches() -> None:
    mgr = _make_manager()
    _set_config(
        mgr,
        {"ifaces.yaml": {"interfaces": [{"edge-1": [{"name": "gig1", "lan": "seg-a", "ipv4": "10.0.0.1/24"}]}]}},
    )
    # Live state already matches: lan seg-a, static ipv4, ipv6 dhcp (config omits ipv6),
    # adminStatus true (default), loopback false (default).
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info(
            interfaces=[_iface("gig1", lan="seg-a", ipv4=_addr(address="10.0.0.1/24"), ipv6=_addr(dhcp=True))]
        )
    )

    result = mgr.configure_interfaces("ifaces.yaml")

    assert result["changed"] is False
    assert result["configured_devices"] == []
    assert result["skipped_devices"] == ["edge-1"]
    assert result["diff_plan"] == []
    mgr.execute_concurrent_tasks.assert_not_called()


def test_configure_changed_on_ipv4_drift() -> None:
    mgr = _make_manager()
    _set_config(
        mgr,
        {"ifaces.yaml": {"interfaces": [{"edge-1": [{"name": "gig1", "lan": "seg-a", "ipv4": "10.0.0.1/24"}]}]}},
    )
    # Same everything except the static IPv4 address differs.
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info(
            interfaces=[_iface("gig1", lan="seg-a", ipv4=_addr(address="10.0.0.9/24"), ipv6=_addr(dhcp=True))]
        )
    )

    result = mgr.configure_interfaces("ifaces.yaml")

    assert result["changed"] is True
    assert result["configured_devices"] == ["edge-1"]
    mgr.execute_concurrent_tasks.assert_called_once()


def test_configure_changed_when_admin_status_differs() -> None:
    mgr = _make_manager()
    _set_config(
        mgr,
        {"ifaces.yaml": {"interfaces": [{"edge-1": [{"name": "gig1", "lan": "seg-a", "ipv4": "10.0.0.1/24"}]}]}},
    )
    # Device is administratively down; desired defaults adminStatus to true.
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info(
            interfaces=[
                _iface("gig1", lan="seg-a", enabled=False, ipv4=_addr(address="10.0.0.1/24"), ipv6=_addr(dhcp=True))
            ]
        )
    )

    result = mgr.configure_interfaces("ifaces.yaml")

    assert result["changed"] is True
    assert result["configured_devices"] == ["edge-1"]


def test_configure_skips_wan_interface_when_up_matches_admin_status() -> None:
    # WAN/circuit interfaces from the API omit "enabled" and report admin status via "up".
    # A device with "up": false and config "adminStatus": false must be seen as unchanged.
    mgr = _make_manager()
    _set_config(
        mgr,
        {
            "ifaces.yaml": {
                "interfaces": [
                    {"edge-1": [{"name": "gig5", "circuit": "ckt-5", "adminStatus": False, "ipv4": "100.0.0.1/24"}]}
                ]
            }
        },
    )
    wan_iface: Dict[str, Any] = {
        "name": "gig5",
        "circuit": "ckt-5",
        "up": False,  # no "enabled" key — WAN API behaviour
        "subinterfaces": [],
        "ipv4": {"address": "100.0.0.1/24", "dhcpClient": False},
        "ipv6": {"dhcpClient": True},  # config omits ipv6, so desired defaults to DHCP
    }
    mgr.gsdk.get_device_info = MagicMock(return_value=_device_info(interfaces=[wan_iface]))

    result = mgr.configure_interfaces("ifaces.yaml")

    assert result["changed"] is False
    assert result["skipped_devices"] == ["edge-1"]
    mgr.execute_concurrent_tasks.assert_not_called()


def test_configure_skips_wan_subinterface_admin_up_when_link_down() -> None:
    # WAN subinterfaces omit "enabled" and "up" reflects link status, not admin status.
    # A subinterface can be admin-enabled ("adminStatus": true in config) while the parent
    # circuit is link-down ("up": false in GET). Must NOT be seen as a change.
    mgr = _make_manager()
    _set_config(
        mgr,
        {
            "ifaces.yaml": {
                "interfaces": [
                    {
                        "edge-1": [
                            {
                                "name": "gig5",
                                "circuit": "ckt-5",
                                "adminStatus": False,
                                "ipv4": "100.210.1.1/24",
                                "subinterfaces": [
                                    {
                                        "vlan": 1001,
                                        "circuit": "ckt-5.1001",
                                        "adminStatus": True,  # admin-up desired
                                        "ipv4": "100.200.30.1/24",
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        },
    )
    wan_subif: Dict[str, Any] = {
        "vlan": 1001,
        "circuit": "ckt-5.1001",
        "up": False,  # link-down because parent circuit is down — NOT admin-disabled
        # no "enabled" key — WAN subinterface API behaviour
        "ipv4": {"address": "100.200.30.1/24", "dhcpClient": False},
        "ipv6": {"dhcpClient": True},
    }
    wan_iface: Dict[str, Any] = {
        "name": "gig5",
        "circuit": "ckt-5",
        "up": False,
        "subinterfaces": [wan_subif],
        "ipv4": {"address": "100.210.1.1/24", "dhcpClient": False},
        "ipv6": {"dhcpClient": True},
    }
    mgr.gsdk.get_device_info = MagicMock(return_value=_device_info(interfaces=[wan_iface]))

    result = mgr.configure_interfaces("ifaces.yaml")

    assert result["changed"] is False
    assert result["skipped_devices"] == ["edge-1"]
    mgr.execute_concurrent_tasks.assert_not_called()


def test_configure_changed_on_new_subinterface() -> None:
    mgr = _make_manager()
    _set_config(
        mgr,
        {
            "ifaces.yaml": {
                "interfaces": [
                    {
                        "edge-1": [
                            {"name": "gig1", "subinterfaces": [{"vlan": 10, "lan": "seg-b", "ipv4": "10.0.10.1/24"}]}
                        ]
                    }
                ]
            }
        },
    )
    # Parent exists but has no subinterfaces -> desired vlan 10 is new -> changed.
    mgr.gsdk.get_device_info = MagicMock(return_value=_device_info(interfaces=[_iface("gig1")]))

    result = mgr.configure_interfaces("ifaces.yaml")

    assert result["changed"] is True
    assert result["configured_devices"] == ["edge-1"]


def test_configure_description_only_default_is_skipped() -> None:
    mgr = _make_manager()
    _set_config(
        mgr,
        {"ifaces.yaml": {"interfaces": [{"edge-1": [{"name": "gig1", "lan": "seg-a", "ipv4": "10.0.0.1/24"}]}]}},
    )
    # Device has a custom description; config did NOT set one (builder would default
    # it to the lan name). Description is cosmetic + not user-set -> not compared -> skip.
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info(
            interfaces=[
                _iface(
                    "gig1",
                    lan="seg-a",
                    ipv4=_addr(address="10.0.0.1/24"),
                    ipv6=_addr(dhcp=True),
                    description="operator note",
                )
            ]
        )
    )

    result = mgr.configure_interfaces("ifaces.yaml")

    assert result["changed"] is False
    assert result["skipped_devices"] == ["edge-1"]


def test_configure_description_user_set_triggers_change() -> None:
    mgr = _make_manager()
    _set_config(
        mgr,
        {
            "ifaces.yaml": {
                "interfaces": [
                    {"edge-1": [{"name": "gig1", "lan": "seg-a", "ipv4": "10.0.0.1/24", "description": "new"}]}
                ]
            }
        },
    )
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info(
            interfaces=[
                _iface("gig1", lan="seg-a", ipv4=_addr(address="10.0.0.1/24"), ipv6=_addr(dhcp=True), description="old")
            ]
        )
    )

    result = mgr.configure_interfaces("ifaces.yaml")

    assert result["changed"] is True
    assert result["configured_devices"] == ["edge-1"]


def test_configure_circuits_skips_when_matches() -> None:
    mgr = _make_manager()
    _set_config(
        mgr,
        {
            "cir.yaml": {
                "circuits": [
                    {
                        "edge-1": [
                            {
                                "circuit": "c1",
                                "upload_bandwidth": 100,
                                "download_bandwidth": 1000,
                                "circuit_type": "circuitType_internet",
                                "label": "internet_dia_4",
                                "qos_profile": "gold10",
                                "qos_profile_type": "balanced",
                            }
                        ]
                    }
                ]
            },
            "if.yaml": {"interfaces": [{"edge-1": [{"name": "gig5", "circuit": "c1"}]}]},
        },
    )
    # WAN interface gig5 already attached to c1; circuit params already match defaults.
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info(
            interfaces=[_iface("gig5", circuit="c1", ipv4=_addr(dhcp=True), ipv6=_addr(dhcp=True))],
            circuits=[
                _circuit(
                    "c1",
                    linkUpSpeedMbps=100,
                    linkDownSpeedMbps=1000,
                    circuitType="circuitType_internet",
                    label="internet_dia_4",
                    diaEnabled=False,
                    lastResort=False,
                    qosProfile="gold10",
                    qosProfileType="balanced",
                )
            ],
        )
    )

    result = mgr.configure_circuits("cir.yaml", "if.yaml")

    assert result["changed"] is False
    assert result["skipped_devices"] == ["edge-1"]
    mgr.execute_concurrent_tasks.assert_not_called()


def test_configure_fails_when_lan_segment_missing() -> None:
    mgr = _make_manager()
    # Only 'seg-a' exists in the enterprise; the config references 'seg-missing'.
    mgr.gsdk.get_lan_segments_dict = MagicMock(return_value={"seg-a": 1})
    _set_config(
        mgr,
        {"ifaces.yaml": {"interfaces": [{"edge-1": [{"name": "gig1", "lan": "seg-missing", "ipv4": "10.0.0.1/24"}]}]}},
    )

    with pytest.raises(ConfigurationError) as exc:
        mgr.configure_interfaces("ifaces.yaml")

    assert "seg-missing" in str(exc.value)
    assert "Available LAN segments" in str(exc.value)
    # Fails before any device is fetched or pushed.
    mgr.gsdk.get_device_info.assert_not_called()
    mgr.execute_concurrent_tasks.assert_not_called()


def test_configure_dhcp_leased_interface_not_falsely_changed() -> None:
    # A DHCP interface reports BOTH a leased address and dhcpClient=true (real GET).
    # A config that leaves ipv4 as DHCP must not be seen as a static->change.
    mgr = _make_manager()
    _set_config(
        mgr,
        {
            "cir.yaml": {"circuits": [{"edge-1": [{"circuit": "c1"}]}]},
            "if.yaml": {"interfaces": [{"edge-1": [{"name": "gig2", "circuit": "c1"}]}]},
        },
    )
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info(
            interfaces=[
                _iface(
                    "gig2",
                    circuit="c1",
                    # leased DHCP: has an address AND dhcpClient true, plus origin.
                    ipv4={"address": "100.64.162.30/20", "origin": "dhcp", "dhcpClient": True},
                    ipv6={"dhcpClient": True},
                )
            ],
            circuits=[
                _circuit(
                    "c1",
                    linkUpSpeedMbps=100,
                    linkDownSpeedMbps=1000,
                    circuitType="circuitType_internet",
                    label="internet_dia_4",
                    diaEnabled=False,
                    lastResort=False,
                    qosProfile="gold10",
                    qosProfileType="balanced",
                )
            ],
        )
    )

    result = mgr.configure_circuits("cir.yaml", "if.yaml")

    # ipv4/ipv6 are DHCP on both sides -> the leased address must not trigger a change.
    assert result["changed"] is False
    assert result["skipped_devices"] == ["edge-1"]
    mgr.execute_concurrent_tasks.assert_not_called()


def test_configure_static_with_dhcp_relay_is_static_and_skipped() -> None:
    # A static interface with a DHCP relay reports ipv4 with an address + origin but
    # NO dhcpClient key. It must read as static (dhcpClient absent -> False) and match
    # a static config; the dhcpRelay block (a separate module's concern) is ignored.
    mgr = _make_manager()
    _set_config(
        mgr,
        {"ifaces.yaml": {"interfaces": [{"edge-1": [{"name": "gig7", "lan": "lan-4", "ipv4": "10.1.5.1/25"}]}]}},
    )
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info(
            interfaces=[
                _iface(
                    "gig7",
                    lan="lan-4",
                    ipv4={
                        "address": "10.1.5.1/25",
                        "origin": "configured",
                        "dhcpRelay": {"dhcpv4Relays": ["10.2.5.2"]},
                    },
                    ipv6={"dhcpClient": True},
                )
            ]
        )
    )

    result = mgr.configure_interfaces("ifaces.yaml")

    assert result["changed"] is False
    assert result["skipped_devices"] == ["edge-1"]
    mgr.execute_concurrent_tasks.assert_not_called()


def test_configure_subinterfaces_all_match_skipped() -> None:
    # Main LAN interface plus two static subinterfaces, all already matching -> skip.
    mgr = _make_manager()
    _set_config(
        mgr,
        {
            "ifaces.yaml": {
                "interfaces": [
                    {
                        "edge-1": [
                            {
                                "name": "gig6",
                                "lan": "lan-1",
                                "ipv4": "10.1.1.1/24",
                                "ipv6": "2001:10:1:1::1/64",
                                "subinterfaces": [
                                    {"vlan": 12, "lan": "lan-2", "ipv4": "10.1.2.1/24", "ipv6": "2001:10:1:2::1/64"},
                                    {"vlan": 13, "lan": "lan-3", "ipv4": "10.1.3.1/24", "ipv6": "2001:10:1:3::1/64"},
                                ],
                            }
                        ]
                    }
                ]
            }
        },
    )
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info(
            interfaces=[
                _iface(
                    "gig6",
                    lan="lan-1",
                    ipv4=_addr(address="10.1.1.1/24"),
                    ipv6=_addr(address="2001:10:1:1::1/64"),
                    subinterfaces=[
                        {
                            "vlan": 12,
                            "lan": "lan-2",
                            "enabled": True,
                            "ipv4": {"address": "10.1.2.1/24", "origin": "configured", "dhcpClient": False},
                            "ipv6": {"address": "2001:10:1:2::1/64", "origin": "configured", "dhcpClient": False},
                        },
                        {
                            "vlan": 13,
                            "lan": "lan-3",
                            "enabled": True,
                            "ipv4": {"address": "10.1.3.1/24", "origin": "configured", "dhcpClient": False},
                            "ipv6": {"address": "2001:10:1:3::1/64", "origin": "configured", "dhcpClient": False},
                        },
                    ],
                )
            ]
        )
    )

    result = mgr.configure_interfaces("ifaces.yaml")

    assert result["changed"] is False
    assert result["skipped_devices"] == ["edge-1"]
    mgr.execute_concurrent_tasks.assert_not_called()


def test_configure_subinterface_ipv4_drift_changes() -> None:
    # One subinterface's IPv4 differs -> device is changed.
    mgr = _make_manager()
    _set_config(
        mgr,
        {
            "ifaces.yaml": {
                "interfaces": [
                    {
                        "edge-1": [
                            {
                                "name": "gig6",
                                "lan": "lan-1",
                                "ipv4": "10.1.1.1/24",
                                "ipv6": "2001:10:1:1::1/64",
                                "subinterfaces": [
                                    {"vlan": 12, "lan": "lan-2", "ipv4": "10.1.2.1/24", "ipv6": "2001:10:1:2::1/64"},
                                ],
                            }
                        ]
                    }
                ]
            }
        },
    )
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info(
            interfaces=[
                _iface(
                    "gig6",
                    lan="lan-1",
                    ipv4=_addr(address="10.1.1.1/24"),
                    ipv6=_addr(address="2001:10:1:1::1/64"),
                    subinterfaces=[
                        {
                            "vlan": 12,
                            "lan": "lan-2",
                            "enabled": True,
                            "ipv4": {"address": "10.9.9.9/24", "origin": "configured", "dhcpClient": False},
                            "ipv6": {"address": "2001:10:1:2::1/64", "origin": "configured", "dhcpClient": False},
                        },
                    ],
                )
            ]
        )
    )

    result = mgr.configure_interfaces("ifaces.yaml")

    assert result["changed"] is True
    assert result["configured_devices"] == ["edge-1"]


def test_configure_diff_before_is_projected_to_desired_keys() -> None:
    # Subinterface-only config on an interface that currently has a main circuit/IP.
    # The merge PUT only adds the subinterface, so the diff `before` must NOT show
    # the main-interface circuit/ipv4 (which would imply a removal that never happens).
    mgr = _make_manager()
    _set_config(
        mgr,
        {
            "ifaces.yaml": {
                "interfaces": [{"edge-1": [{"name": "gig4", "subinterfaces": [{"vlan": 1, "lan": "seg-a"}]}]}]
            }
        },
    )
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info(
            interfaces=[_iface("gig4", circuit="c-old", ipv4=_addr(address="100.64.0.1/20"), ipv6=_addr(dhcp=True))]
        )
    )

    result = mgr.configure_interfaces("ifaces.yaml")

    assert result["changed"] is True
    before_iface = result["diff_plan"][0]["before"]["interfaces"]["gig4"]
    after_iface = result["diff_plan"][0]["after"]["interfaces"]["gig4"]
    # `after` (and therefore `before`) is limited to the subinterfaces key only.
    assert set(after_iface) == {"subinterfaces"}
    assert set(before_iface) <= {"subinterfaces"}
    assert "circuit" not in before_iface
    assert "ipv4" not in before_iface


def test_configure_mixed_devices_split_skip_and_change() -> None:
    mgr = _make_manager()
    _set_config(
        mgr,
        {
            "ifaces.yaml": {
                "interfaces": [
                    {"edge-match": [{"name": "gig1", "lan": "seg-a", "ipv4": "10.0.0.1/24"}]},
                    {"edge-diff": [{"name": "gig1", "lan": "seg-a", "ipv4": "10.0.0.1/24"}]},
                ]
            }
        },
    )
    ids = {"edge-match": 1, "edge-diff": 2}
    mgr.gsdk.get_device_id = MagicMock(side_effect=lambda name: ids[name])
    states = {
        1: _device_info(
            interfaces=[_iface("gig1", lan="seg-a", ipv4=_addr(address="10.0.0.1/24"), ipv6=_addr(dhcp=True))]
        ),
        2: _device_info(
            interfaces=[_iface("gig1", lan="seg-a", ipv4=_addr(address="10.9.9.9/24"), ipv6=_addr(dhcp=True))]
        ),
    }
    mgr.gsdk.get_device_info = MagicMock(side_effect=lambda device_id: states[device_id])

    result = mgr.configure_interfaces("ifaces.yaml")

    assert result["changed"] is True
    assert result["configured_devices"] == ["edge-diff"]
    assert result["skipped_devices"] == ["edge-match"]
    # Only the changed device is pushed.
    pushed = mgr.execute_concurrent_tasks.call_args[0][1]
    assert list(pushed.keys()) == [2]


# ===========================================================================
# state: absent support tests
# ===========================================================================


def test_build_interface_absent_sub_generates_null_payload() -> None:
    # A subinterface with state:absent must produce {"interface": null} in the payload.
    result = InterfaceManager._build_interface(
        "gig7",
        action="add",
        lan="lan-1",
        ipv4="10.1.1.1/24",
        subinterfaces=[
            {"vlan": 18, "lan": "lan-7", "ipv4": "10.1.17.1/24"},  # kept
            {"vlan": 19, "state": "absent"},  # removed
        ],
    )
    subs = result["interfaces"]["gig7"]["interface"]["subinterfaces"]
    assert subs["18"]["interface"] is not None  # kept sub is configured
    assert subs["19"]["interface"] is None  # absent sub → null payload


def test_configure_absent_subinterface_triggers_change_when_exists() -> None:
    # Sub VLAN 19 is on the device; config marks it state:absent → changed.
    mgr = _make_manager()
    _set_config(
        mgr,
        {
            "ifaces.yaml": {
                "interfaces": [
                    {
                        "edge-1": [
                            {
                                "name": "gig7",
                                "lan": "lan-1",
                                "ipv4": "10.1.1.1/24",
                                "subinterfaces": [
                                    {"vlan": 18, "lan": "lan-7", "ipv4": "10.1.17.1/24"},
                                    {"vlan": 19, "state": "absent"},
                                ],
                            }
                        ]
                    }
                ]
            }
        },
    )
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info(
            interfaces=[
                _iface(
                    "gig7",
                    lan="lan-1",
                    ipv4=_addr(address="10.1.1.1/24"),
                    ipv6=_addr(dhcp=True),
                    subinterfaces=[
                        {
                            "vlan": 18,
                            "lan": "lan-7",
                            "enabled": True,
                            "ipv4": {"address": "10.1.17.1/24", "dhcpClient": False},
                            "ipv6": {"dhcpClient": True},
                        },
                        {
                            "vlan": 19,
                            "lan": "lan-1",
                            "enabled": True,
                            "ipv4": {"address": "10.1.19.1/24", "dhcpClient": False},
                            "ipv6": {"dhcpClient": True},
                        },
                    ],
                )
            ]
        )
    )

    result = mgr.configure_interfaces("ifaces.yaml")

    assert result["changed"] is True
    assert result["configured_devices"] == ["edge-1"]
    mgr.execute_concurrent_tasks.assert_called_once()
    # The absent sub must be rendered explicitly in the diff.
    diff = result["diff_plan"][0]
    after_subs = diff["after"]["interfaces"]["gig7"]["subinterfaces"]
    before_subs = diff["before"]["interfaces"]["gig7"]["subinterfaces"]
    assert after_subs[19] == {"state": "absent"}
    assert before_subs[19] == {"lan": "lan-1"}


def test_configure_absent_subinterface_skipped_when_already_gone() -> None:
    # Sub VLAN 19 is absent in config AND not on the device → no change.
    mgr = _make_manager()
    _set_config(
        mgr,
        {
            "ifaces.yaml": {
                "interfaces": [
                    {
                        "edge-1": [
                            {
                                "name": "gig7",
                                "lan": "lan-1",
                                "ipv4": "10.1.1.1/24",
                                "subinterfaces": [
                                    {"vlan": 18, "lan": "lan-7", "ipv4": "10.1.17.1/24"},
                                    {"vlan": 19, "state": "absent"},
                                ],
                            }
                        ]
                    }
                ]
            }
        },
    )
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info(
            interfaces=[
                _iface(
                    "gig7",
                    lan="lan-1",
                    ipv4=_addr(address="10.1.1.1/24"),
                    ipv6=_addr(dhcp=True),
                    subinterfaces=[
                        {
                            "vlan": 18,
                            "lan": "lan-7",
                            "enabled": True,
                            "ipv4": {"address": "10.1.17.1/24", "dhcpClient": False},
                            "ipv6": {"dhcpClient": True},
                        }
                        # vlan 19 is already gone from the device
                    ],
                )
            ]
        )
    )

    result = mgr.configure_interfaces("ifaces.yaml")

    assert result["changed"] is False
    assert result["skipped_devices"] == ["edge-1"]
    mgr.execute_concurrent_tasks.assert_not_called()


def test_configure_absent_main_interface_triggers_change_when_configured() -> None:
    # Main interface gig7 is marked state:absent and is currently on lan-1 → changed.
    mgr = _make_manager()
    _set_config(
        mgr,
        {
            "ifaces.yaml": {
                "interfaces": [
                    {
                        "edge-1": [
                            {"name": "gig7", "state": "absent"},
                        ]
                    }
                ]
            }
        },
    )
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info(
            interfaces=[
                _iface("gig7", lan="lan-1", ipv4=_addr(address="10.1.1.1/24"), ipv6=_addr(dhcp=True))
            ]
        )
    )

    result = mgr.configure_interfaces("ifaces.yaml")

    assert result["changed"] is True
    assert result["configured_devices"] == ["edge-1"]
    mgr.execute_concurrent_tasks.assert_called_once()
    # The diff after must show state: absent; before must show the current lan.
    diff = result["diff_plan"][0]
    assert diff["after"]["interfaces"]["gig7"] == {"state": "absent"}
    assert diff["before"]["interfaces"]["gig7"]["lan"] == "lan-1"


def test_configure_absent_main_interface_skipped_when_already_default() -> None:
    # Main interface is already on the enterprise default LAN with no subs → no change.
    mgr = _make_manager()
    _set_config(
        mgr,
        {
            "ifaces.yaml": {
                "interfaces": [
                    {
                        "edge-1": [
                            {"name": "gig7", "state": "absent"},
                        ]
                    }
                ]
            }
        },
    )
    # "default-ent1" is the default LAN computed from get_enterprise_id="ent1".
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info(
            interfaces=[_iface("gig7", lan="default-ent1")]
        )
    )

    result = mgr.configure_interfaces("ifaces.yaml")

    assert result["changed"] is False
    assert result["skipped_devices"] == ["edge-1"]
    mgr.execute_concurrent_tasks.assert_not_called()


def test_configure_absent_only_subinterface_no_main_config() -> None:
    # Interface has no LAN/circuit on main, only a sub to remove.  Device has sub 1 → changed.
    mgr = _make_manager()
    _set_config(
        mgr,
        {
            "ifaces.yaml": {
                "interfaces": [
                    {
                        "edge-1": [
                            {
                                "name": "gig4",
                                "subinterfaces": [{"vlan": 1, "state": "absent"}],
                            }
                        ]
                    }
                ]
            }
        },
    )
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info(
            interfaces=[
                _iface(
                    "gig4",
                    lan="lan-x",
                    subinterfaces=[
                        {
                            "vlan": 1,
                            "lan": "seg-3",
                            "enabled": True,
                            "ipv4": {"address": "10.1.1.1/24", "dhcpClient": False},
                            "ipv6": {"dhcpClient": True},
                        }
                    ],
                )
            ]
        )
    )

    result = mgr.configure_interfaces("ifaces.yaml")

    assert result["changed"] is True
    assert result["configured_devices"] == ["edge-1"]
    # The payload for gig4 must have a null subinterface entry for vlan 1.
    pushed = mgr.execute_concurrent_tasks.call_args[0][1]
    device_payload = next(iter(pushed.values()))
    edge = device_payload["edge"]
    sub_payload = edge["interfaces"]["gig4"]["interface"]["subinterfaces"]
    assert sub_payload["1"]["interface"] is None


def test_configure_absent_wan_main_interface_left_untouched() -> None:
    # state:absent is LAN-only.  A WAN interface (circuit-attached, LAN at default) marked
    # absent must NOT be reset — no change, no push.
    mgr = _make_manager()
    _set_config(
        mgr,
        {
            "ifaces.yaml": {
                "interfaces": [
                    {
                        "edge-1": [
                            {"name": "gig5", "state": "absent"},
                        ]
                    }
                ]
            }
        },
    )
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info(
            interfaces=[_iface("gig5", lan="default-ent1", circuit="c-wan-1")]
        )
    )

    result = mgr.configure_interfaces("ifaces.yaml")

    assert result["changed"] is False
    assert result["skipped_devices"] == ["edge-1"]
    mgr.execute_concurrent_tasks.assert_not_called()


def test_configure_absent_wan_subinterface_left_untouched() -> None:
    # A WAN subinterface (circuit-attached on the device) marked absent is LAN-only-excluded:
    # it must NOT be deleted → no change.
    mgr = _make_manager()
    _set_config(
        mgr,
        {
            "ifaces.yaml": {
                "interfaces": [
                    {
                        "edge-1": [
                            {
                                "name": "gig5",
                                "subinterfaces": [{"vlan": 1001, "state": "absent"}],
                            }
                        ]
                    }
                ]
            }
        },
    )
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info(
            interfaces=[
                _iface(
                    "gig5",
                    lan="default-ent1",
                    circuit="c-wan-1",
                    subinterfaces=[
                        {
                            "vlan": 1001,
                            "circuit": "c-wan-1.1001",
                            "ipv4": {"address": "100.200.30.1/24", "dhcpClient": False},
                            "ipv6": {"dhcpClient": True},
                        }
                    ],
                )
            ]
        )
    )

    result = mgr.configure_interfaces("ifaces.yaml")

    assert result["changed"] is False
    assert result["skipped_devices"] == ["edge-1"]
    mgr.execute_concurrent_tasks.assert_not_called()


def test_deconfigure_interfaces_merge_device_not_both_configured_and_skipped() -> None:
    # Stage 1 (circuit route cleanup) skips edge-1 (no static routes); stage 2 (interface
    # deconfigure) configures edge-1.  The merged result must list edge-1 only as configured.
    mgr = _make_manager()
    mgr.deconfigure_wan_circuits_interfaces = MagicMock(
        return_value={
            "changed": False,
            "configured_devices": [],
            "skipped_devices": ["edge-1"],
            "deconfigured_circuits": [],
            "skipped_circuits": ["c-1"],
            "diff_plan": [],
        }
    )
    mgr.deconfigure = MagicMock(
        return_value={
            "changed": True,
            "configured_devices": ["edge-1"],
            "skipped_devices": [],
            "diff_plan": [],
        }
    )

    merged = mgr.deconfigure_interfaces("ifaces.yaml", "circuits.yaml")

    assert merged["configured_devices"] == ["edge-1"]
    assert merged["skipped_devices"] == []
    # Invariant: no device appears in both lists.
    assert set(merged["configured_devices"]).isdisjoint(merged["skipped_devices"])
