# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for edge_services_manager."""

from __future__ import annotations

import pytest

from ansible_collections.graphiant.naas.plugins.module_utils.libs.edge_services_manager import (
    EdgeServicesManager,
)
from ansible_collections.graphiant.naas.plugins.module_utils.libs.exceptions import ConfigurationError


def _make_manager() -> EdgeServicesManager:
    from unittest.mock import MagicMock

    config_utils = MagicMock()
    config_utils.gsdk = MagicMock()
    return EdgeServicesManager(config_utils)


def test_deconfigure_not_supported() -> None:
    mgr = _make_manager()
    with pytest.raises(ConfigurationError, match="Deconfigure is not supported"):
        mgr.deconfigure("any.yaml")


def test_dhcp_subnet_key() -> None:
    assert EdgeServicesManager._dhcp_subnet_key("GigabitEthernet6/0/0.2192", "10.1.1.0/24") == (
        "GigabitEthernet6/0/0.2192-10.1.1.0/24"
    )


def test_build_edge_payload_dns_api_nesting() -> None:
    """PUT body uses edge.dns.dns.{cloudflare|static|dynamic} per portal API."""
    mgr = _make_manager()
    current = {"dns": {"mode": "DNSModeDynamic"}, "role": "cpe"}
    cfg = {"dns": {"mode": "DNSModeCloudflare"}}
    edge = mgr._build_edge_payload("edge-1", cfg, current)
    assert edge["dns"] == {"dns": {"cloudflare": {}}}
    assert edge["dns"]["dns"] == {"cloudflare": {}}


def test_validate_dhcp_interface_unknown_fails() -> None:
    mgr = _make_manager()
    current = {
        "segments": [{"name": "lan-7-test"}],
        "interfaces": [{"name": "GigabitEthernet8/0/0", "subinterfaces": {"28": {}}}],
    }
    entries = [
        {
            "segment": "lan-7-test",
            "interface": "GigabitEthernet8/0/0.18",
            "ipPrefix": "10.3.177.0/24",
            "subnet": {"name": "n"},
        }
    ]
    with pytest.raises(ConfigurationError, match="GigabitEthernet8/0/0.18"):
        mgr._validate_dhcp_entries("edge-3-sdktest", entries, current)


def test_validate_dhcp_segment_unknown_fails() -> None:
    mgr = _make_manager()
    current = {"segments": [{"name": "real-seg"}]}
    entries = [
        {
            "segment": "missing-seg",
            "interface": "GigabitEthernet1/0/0",
            "ipPrefix": "10.0.0.0/24",
            "subnet": {"name": "n"},
        }
    ]
    with pytest.raises(ConfigurationError, match="missing-seg"):
        mgr._validate_dhcp_entries("edge-1", entries, current)


def test_static_lease_mac_normalized_for_idempotency() -> None:
    from_get = EdgeServicesManager._normalize_static_leases_from_get(
        {"10.1.11.201": {"lease": {"ipAddress": "10.1.11.201", "macAddress": "00:1a:2b:3c:4d:5e"}}}
    )
    from_yaml = EdgeServicesManager._normalize_dhcp_subnet_from_yaml(
        {
            "staticLeases": {
                "10.1.11.201": {
                    "lease": {"ipAddress": "10.1.11.201", "macAddress": "00:1A:2B:3C:4D:5E"}
                }
            }
        }
    )
    assert from_get == from_yaml["staticLeases"]


def test_inject_vault_lws_passwords() -> None:
    mgr = _make_manager()
    by_name = {
        "edge-3-sdktest": {"localWebServerPasswordForce": True},
        "edge-1-sdktest": {},
    }
    mgr._inject_vault_lws_passwords(by_name, {"edge-3-sdktest": "SecretPass1"})
    assert by_name["edge-3-sdktest"]["localWebServerPassword"] == "SecretPass1"
    assert "localWebServerPassword" not in by_name["edge-1-sdktest"]


def test_inject_vault_lws_passwords_skips_explicit() -> None:
    mgr = _make_manager()
    by_name = {"edge-1-sdktest": {"localWebServerPassword": "ExplicitPass1"}}
    mgr._inject_vault_lws_passwords(by_name, {"edge-1-sdktest": "VaultPass1"})
    assert by_name["edge-1-sdktest"]["localWebServerPassword"] == "ExplicitPass1"


def test_build_edge_payload_skips_dns_when_unchanged() -> None:
    mgr = _make_manager()
    current = {
        "role": "cpe",
        "dns": {
            "mode": "DNSModeStatic",
            "staticServersV2": {
                "primaryIpv4Server": {"ipv4": "8.8.8.8"},
            },
        },
    }
    cfg = {
        "dns": {
            "mode": "DNSModeStatic",
            "static": {"primaryIpv4": "8.8.8.8"},
        }
    }
    edge = mgr._build_edge_payload("edge-1", cfg, current)
    assert "dns" not in edge


def test_validate_dhcp_segment_ok_when_present() -> None:
    mgr = _make_manager()
    current = {
        "segments": [{"name": "real-seg"}],
        "interfaces": [{"name": "GigabitEthernet1/0/0"}],
    }
    entries = [
        {
            "segment": "real-seg",
            "interface": "GigabitEthernet1/0/0",
            "ipPrefix": "10.0.0.0/24",
            "subnet": {"name": "n"},
        }
    ]
    mgr._validate_dhcp_entries("edge-1", entries, current)


def test_build_dns_put_cloudflare() -> None:
    body = EdgeServicesManager._build_dns_put({"mode": "DNSModeCloudflare"})
    assert body == {"dns": {"cloudflare": {}}}


def test_build_dns_put_static() -> None:
    body = EdgeServicesManager._build_dns_put(
        {
            "mode": "DNSModeStatic",
            "static": {
                "primaryIpv4": "8.8.8.8",
                "secondaryIpv4": "8.8.4.4",
            },
        }
    )
    assert body["dns"]["static"]["primaryIpv4V2"] == {"address": "8.8.8.8"}


def test_validate_lws_force_without_password_fails() -> None:
    mgr = _make_manager()
    with pytest.raises(ConfigurationError, match="localWebServerPasswordForce is true"):
        mgr._validate_lws_password_sources(
            {"edge-3-sdktest": {"localWebServerPasswordForce": True, "dns": {"mode": "DNSModeDynamic"}}}
        )


def test_validate_lws_force_with_vault_password_ok() -> None:
    mgr = _make_manager()
    mgr._validate_lws_password_sources(
        {"edge-3-sdktest": {"localWebServerPasswordForce": True, "localWebServerPassword": "SecretPass1"}}
    )


def test_validate_lws_password_rejects_weak() -> None:
    try:
        EdgeServicesManager._validate_lws_password("short1")
        raise AssertionError("expected ConfigurationError")
    except ConfigurationError:
        pass


def test_dns_snapshot_from_device_static() -> None:
    snap = EdgeServicesManager._dns_snapshot_from_device(
        {
            "dns": {
                "mode": "DNSModeStatic",
                "staticServersV2": {
                    "primaryIpv4Server": {"ipv4": "8.8.8.8", "source": "Static", "type": "Primary"},
                    "secondaryIpv4Server": {"ipv4": "8.8.4.4", "source": "Static", "type": "Secondary"},
                },
            }
        }
    )
    assert snap["mode"] == "DNSModeStatic"
    assert snap["static"]["primaryIpv4"] == "8.8.8.8"


def test_validate_lldp_wan_interface_fails() -> None:
    current = {
        "interfaces": [
            {"name": "GigabitEthernet4/0/0", "lldpEnabled": True},
            {"name": "GigabitEthernet5/0/0", "circuit": "wan-circuit", "lldpEnabled": False},
        ]
    }
    with pytest.raises(ConfigurationError, match="not a LAN interface"):
        EdgeServicesManager._validate_lldp_entries(
            "edge-1-sdktest",
            {"GigabitEthernet5/0/0": True},
            current,
        )


def test_validate_lldp_unknown_interface_fails() -> None:
    current = {
        "interfaces": [
            {"name": "GigabitEthernet4/0/0", "lldpEnabled": True},
        ]
    }
    with pytest.raises(ConfigurationError, match="does not exist"):
        EdgeServicesManager._validate_lldp_entries(
            "edge-1-sdktest",
            {"GigabitEthernet99/0/0": True},
            current,
        )


def test_lldp_snapshot_skips_wan() -> None:
    snap = EdgeServicesManager._lldp_snapshot_from_device(
        {
            "interfaces": [
                {"name": "GigabitEthernet2/0/0", "circuit": "c-wan", "lldpEnabled": True},
                {"name": "GigabitEthernet5/0/0", "lan": "seg", "lldpEnabled": False},
            ]
        }
    )
    assert "GigabitEthernet2/0/0" not in snap
    assert snap["GigabitEthernet5/0/0"] is False
