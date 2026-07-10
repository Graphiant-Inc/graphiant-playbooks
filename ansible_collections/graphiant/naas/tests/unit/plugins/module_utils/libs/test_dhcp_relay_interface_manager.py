# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for DHCP relay interface manager."""

from __future__ import annotations

from ansible_collections.graphiant.naas.plugins.module_utils.libs.dhcp_relay_interface_manager import (
    DhcpRelayInterfaceManager,
)


def test_relay_servers_from_config_list() -> None:
    assert DhcpRelayInterfaceManager._relay_servers_from_config(["10.1.1.1", "10.2.1.1"]) == [
        "10.1.1.1",
        "10.2.1.1",
    ]


def test_relay_servers_from_config_dict() -> None:
    assert DhcpRelayInterfaceManager._relay_servers_from_config(
        {"relayServers": ["2001:10:1:1::1"]}
    ) == ["2001:10:1:1::1"]


def test_build_dhcp_relay_subinterface_payload() -> None:
    rendered = DhcpRelayInterfaceManager.build_dhcp_relay_interfaces_payload(
        action="add",
        name="GigabitEthernet5/0/0",
        vlan=1,
        dhcpRelayIpv4={"relayServers": ["10.1.1.1", "10.2.1.1"]},
        dhcpRelayIpv6=["2001:10:1:1::1"],
    )
    iface = rendered["interfaces"]["GigabitEthernet5/0/0"]["interface"]["subinterfaces"]["1"]["interface"]
    assert iface["ipv4"]["dhcp"]["dhcpRelay"]["relayServers"] == ["10.1.1.1", "10.2.1.1"]
    assert iface["ipv6"]["dhcp"]["dhcpRelay"]["relayServers"] == ["2001:10:1:1::1"]


def test_build_dhcp_relay_main_interface_payload() -> None:
    rendered = DhcpRelayInterfaceManager.build_dhcp_relay_interfaces_payload(
        action="add",
        name="GigabitEthernet7/0/0",
        dhcpRelayIpv4=["10.1.11.1"],
    )
    iface = rendered["interfaces"]["GigabitEthernet7/0/0"]["interface"]
    assert iface["ipv4"]["dhcp"]["dhcpRelay"]["relayServers"] == ["10.1.11.1"]
    assert "ipv6" not in iface


def test_build_dhcp_relay_delete_payload() -> None:
    rendered = DhcpRelayInterfaceManager.build_dhcp_relay_interfaces_payload(
        action="delete",
        name="GigabitEthernet7/0/0",
        dhcpRelayIpv4={},
        dhcpRelayIpv6={},
    )
    iface = rendered["interfaces"]["GigabitEthernet7/0/0"]["interface"]
    assert iface["ipv4"]["dhcp"]["dhcpRelay"] == {"relayServers": []}
    assert iface["ipv6"]["dhcp"]["dhcpRelay"] == {"relayServers": []}


def test_has_relay_config() -> None:
    assert DhcpRelayInterfaceManager._has_relay_config({"dhcpRelayIpv4": ["10.1.1.1"]}) is True
    assert DhcpRelayInterfaceManager._has_relay_config({"name": "eth0"}) is False


def test_relay_state_matches_configure() -> None:
    existing = {"ipv4": ["10.1.1.1"], "ipv6": []}
    desired = {"ipv4": ["10.1.1.1"], "ipv6": []}
    assert DhcpRelayInterfaceManager._relay_state_matches(existing, desired, ["ipv4"]) is True
    desired2 = {"ipv4": ["10.2.1.1"], "ipv6": []}
    assert DhcpRelayInterfaceManager._relay_state_matches(existing, desired2, ["ipv4"]) is False


def test_relay_state_matches_deconfigure() -> None:
    existing = {"ipv4": ["10.1.1.1"], "ipv6": []}
    desired = {"ipv4": [], "ipv6": []}
    assert DhcpRelayInterfaceManager._relay_state_matches(existing, desired, ["ipv4"]) is False
    assert DhcpRelayInterfaceManager._relay_state_matches({"ipv4": [], "ipv6": []}, desired, ["ipv4"]) is True


def test_per_af_state_absent_desired() -> None:
    cfg = {"name": "GigabitEthernet8/0/0", "vlan": 30, "dhcpRelayIpv4": {"state": "absent"}}
    desired = DhcpRelayInterfaceManager._desired_relay_state(cfg, "add")
    assert desired["ipv4"] == []


def test_per_af_state_absent_block() -> None:
    block = DhcpRelayInterfaceManager._dhcp_relay_block({"state": "absent"}, "add")
    assert block == {"dhcp": {"dhcpRelay": {"relayServers": []}}}


def test_per_af_state_absent_with_servers_overrides() -> None:
    cfg = {"name": "GigabitEthernet8/0/0", "dhcpRelayIpv4": {"relayServers": ["10.1.1.1"], "state": "absent"}}
    desired = DhcpRelayInterfaceManager._desired_relay_state(cfg, "add")
    assert desired["ipv4"] == []


def test_per_af_state_present_overrides_delete() -> None:
    cfg = {"name": "GigabitEthernet8/0/0", "dhcpRelayIpv4": {"relayServers": ["10.1.1.1"], "state": "present"}}
    desired = DhcpRelayInterfaceManager._desired_relay_state(cfg, "delete")
    assert desired["ipv4"] == ["10.1.1.1"]


def test_merge_dhcp_relay_payload_two_subinterfaces_same_parent() -> None:
    edge: dict = {"interfaces": {}}
    payload_vlan28 = DhcpRelayInterfaceManager.build_dhcp_relay_interfaces_payload(
        action="add",
        name="GigabitEthernet8/0/0",
        vlan=28,
        dhcpRelayIpv4=["10.3.177.1"],
    )
    payload_vlan29 = DhcpRelayInterfaceManager.build_dhcp_relay_interfaces_payload(
        action="add",
        name="GigabitEthernet8/0/0",
        vlan=29,
        dhcpRelayIpv4=["10.2.18.1"],
    )
    DhcpRelayInterfaceManager.merge_dhcp_relay_payload(edge, payload_vlan28)
    DhcpRelayInterfaceManager.merge_dhcp_relay_payload(edge, payload_vlan29)

    subs = edge["interfaces"]["GigabitEthernet8/0/0"]["interface"]["subinterfaces"]
    assert subs["28"]["interface"]["ipv4"]["dhcp"]["dhcpRelay"]["relayServers"] == ["10.3.177.1"]
    assert subs["29"]["interface"]["ipv4"]["dhcp"]["dhcpRelay"]["relayServers"] == ["10.2.18.1"]


def test_validate_interface_entry_unknown_raises() -> None:
    from ansible_collections.graphiant.naas.plugins.module_utils.libs.exceptions import ConfigurationError

    class _Sub:
        def __init__(self, vlan: int) -> None:
            self.vlan = vlan

    class _Iface:
        def __init__(self, name: str, subinterfaces=None) -> None:
            self.name = name
            self.subinterfaces = subinterfaces or []

    class _Device:
        def __init__(self, interfaces) -> None:
            self.interfaces = interfaces

    class _Gcs:
        def __init__(self, interfaces) -> None:
            self.device = _Device(interfaces)

    gcs = _Gcs([_Iface("GigabitEthernet8/0/0", [_Sub(28)])])

    try:
        DhcpRelayInterfaceManager._validate_interface_entry(
            "edge-1", gcs, "GigabitEthernet8/0/0", vlan=99
        )
        assert False, "expected ConfigurationError"
    except ConfigurationError as exc:
        assert "does not exist" in str(exc)
        assert "GigabitEthernet8/0/0.99" in str(exc)
