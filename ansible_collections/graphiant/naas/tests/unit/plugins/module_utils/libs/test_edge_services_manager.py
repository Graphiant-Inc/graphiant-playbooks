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


def test_dpi_snapshot_from_device_edge_traffic_policy() -> None:
    """DPI snapshot reads dpiApplications from device.edge.trafficPolicy like other edge services."""
    device = {
        "dns": {"mode": "DNSModeStatic"},
        "edge": {
            "trafficPolicy": {
                "dpiApplications": {
                    "app1": {"application": {"name": "app1", "ipProtocol": "tcp"}},
                }
            }
        },
    }
    snap = EdgeServicesManager._dpi_snapshot_from_device(device)
    assert snap["app1"]["name"] == "app1"
    assert snap["app1"]["ipProtocol"] == "tcp"


def test_coerce_dpi_applications_list_to_map() -> None:
    raw = [
        {
            "application": {
                "name": "whitehouse.gov",
                "ipProtocol": "tcp",
                "destinationNetwork": "192.0.66.180/32",
            }
        }
    ]
    out = EdgeServicesManager._coerce_dpi_applications_map(raw)
    assert "whitehouse.gov" in out.keys()
    assert out["whitehouse.gov"]["name"] == "whitehouse.gov"


def test_build_edge_payload_dpi_injects_name_from_map_key() -> None:
    mgr = _make_manager()
    current = {
        "role": "cpe",
        "edge": {
            "trafficPolicy": {
                "portLists": {"web_ports": {"list": {"name": "web_ports", "ports": [80, 443]}}},
                "networkLists": {
                    "graphiant_dia_prefix": {"list": {"name": "graphiant_dia_prefix", "networks": ["1.1.1.1/32"]}}
                },
            }
        },
    }
    cfg = {
        "dpiApplications": {
            "whitehouse.gov": {
                "application": {
                    "ipProtocol": "tcp",
                    "destinationNetwork": "192.0.66.180/32",
                    "destinationPortList": "web_ports",
                }
            }
        }
    }
    edge = mgr._build_edge_payload("edge-1", cfg, current)
    app = edge["trafficPolicy"]["dpiApplications"]["whitehouse.gov"]["application"]
    assert app["name"] == "whitehouse.gov"
    assert app["ipProtocol"] == "tcp"
    assert app["destinationPortList"] == "web_ports"


def test_build_edge_payload_skips_dpi_yaml_nulls_vs_sparse_get() -> None:
    """Explicit nulls in YAML must match portal GET that omits unset application fields."""
    mgr = _make_manager()
    get_app = {
        "name": "whitehouse.gov",
        "ipProtocol": "tcp",
        "destinationNetwork": "192.0.66.180/32",
        "destinationPortList": "web_ports",
    }
    current = {
        "role": "cpe",
        "edge": {
            "trafficPolicy": {
                "dpiApplications": {"whitehouse.gov": {"application": get_app}},
                "portLists": {"web_ports": {"list": {"name": "web_ports", "ports": [80, 443]}}},
            }
        },
    }
    cfg = {
        "dpiApplications": {
            "whitehouse.gov": {
                "application": {
                    "ipProtocol": "tcp",
                    "sourceNetwork": None,
                    "sourceNetworkList": None,
                    "sourcePort": None,
                    "sourcePortList": None,
                    "destinationNetwork": "192.0.66.180/32",
                    "destinationNetworkList": None,
                    "destinationPort": None,
                    "destinationPortList": "web_ports",
                }
            }
        }
    }
    edge = mgr._build_edge_payload("edge-1", cfg, current)
    assert "trafficPolicy" not in edge


def test_build_edge_payload_updates_source_when_yaml_nulls_destination() -> None:
    """Non-null source fields are pushed; explicit null destination fields are omitted from PUT."""
    mgr = _make_manager()
    current = {
        "role": "cpe",
        "trafficPolicy": {
            "dpiApplications": [
                {
                    "name": "graphiant_dia_ping_via_IP",
                    "ipProtocol": "tcp",
                    "destinationNetwork": "192.0.66.180/32",
                    "destinationPortList": "web_ports",
                },
            ],
            "portLists": [{"name": "web_ports", "ports": [80, 443]}],
            "networkLists": [{"name": "graphiant_dia_prefix", "networks": ["1.1.1.1/32"]}],
        },
    }
    cfg = {
        "dpiApplications": {
            "graphiant_dia_ping_via_IP": {
                "application": {
                    "ipProtocol": "tcp",
                    "sourceNetwork": None,
                    "sourceNetworkList": "graphiant_dia_prefix",
                    "sourcePort": 80,
                    "sourcePortList": None,
                    "destinationNetwork": None,
                    "destinationNetworkList": None,
                    "destinationPort": None,
                    "destinationPortList": None,
                }
            }
        }
    }
    edge = mgr._build_edge_payload("edge-1", cfg, current)
    app = edge["trafficPolicy"]["dpiApplications"]["graphiant_dia_ping_via_IP"]["application"]
    assert app["sourceNetworkList"] == "graphiant_dia_prefix"
    assert app["sourcePort"] == 80
    assert "destinationNetwork" not in app
    assert "destinationPortList" not in app


def test_build_edge_payload_skips_dpi_when_only_null_field_changes() -> None:
    """Explicit nulls alone do not trigger updates (portal cannot clear nested fields via null)."""
    mgr = _make_manager()
    current = {
        "role": "cpe",
        "trafficPolicy": {
            "dpiApplications": [
                {
                    "name": "graphiant_dia_ping_via_IP",
                    "ipProtocol": "tcp",
                    "sourceNetworkList": "graphiant_dia_prefix",
                    "sourcePort": 80,
                    "destinationNetwork": "8.8.8.8/32",
                },
            ],
            "networkLists": [{"name": "graphiant_dia_prefix", "networks": ["1.1.1.1/32"]}],
        },
    }
    cfg = {
        "dpiApplications": {
            "graphiant_dia_ping_via_IP": {
                "application": {
                    "ipProtocol": "tcp",
                    "sourceNetwork": None,
                    "sourceNetworkList": None,
                    "sourcePort": None,
                    "sourcePortList": None,
                    "destinationNetwork": "8.8.8.8/32",
                    "destinationNetworkList": None,
                    "destinationPort": None,
                    "destinationPortList": None,
                }
            }
        }
    }
    edge = mgr._build_edge_payload("edge-1", cfg, current)
    assert "trafficPolicy" not in edge


def test_build_edge_payload_dpi_put_only_sends_changed_fields() -> None:
    """Explicit nulls in YAML must not be re-sent when portal already has the field unset."""
    mgr = _make_manager()
    get_app = {
        "name": "whitehouse.gov",
        "ipProtocol": "tcp",
        "destinationNetwork": "192.0.66.180/32",
        "destinationPortList": "web_ports",
    }
    current = {
        "role": "cpe",
        "trafficPolicy": {
            "dpiApplications": [{"name": "whitehouse.gov", **{k: v for k, v in get_app.items() if k != "name"}}],
            "portLists": [{"name": "web_ports", "ports": [80, 443]}],
        },
    }
    cfg = {
        "dpiApplications": {
            "whitehouse.gov": {
                "application": {
                    "ipProtocol": "tcp",
                    "sourceNetwork": None,
                    "sourceNetworkList": None,
                    "sourcePort": None,
                    "sourcePortList": None,
                    "destinationNetwork": "192.0.66.180/32",
                    "destinationNetworkList": None,
                    "destinationPort": None,
                    "destinationPortList": "web_ports",
                }
            }
        }
    }
    edge = mgr._build_edge_payload("edge-1", cfg, current)
    assert "trafficPolicy" not in edge


def test_build_edge_payload_skips_dpi_when_get_returns_zero_ports() -> None:
    mgr = _make_manager()
    get_app = {
        "name": "graphiant_dia_ping",
        "ipProtocol": "icmp",
        "sourcePort": 0,
        "destinationPort": 0,
        "destinationNetworkList": "graphiant_dia_prefix",
    }
    current = {
        "role": "cpe",
        "edge": {
            "trafficPolicy": {
                "dpiApplications": {"graphiant_dia_ping": {"application": get_app}},
                "networkLists": {
                    "graphiant_dia_prefix": {"list": {"name": "graphiant_dia_prefix", "networks": ["1.1.1.1/32"]}}
                },
            }
        },
    }
    cfg = {
        "dpiApplications": {
            "graphiant_dia_ping": {
                "application": {
                    "ipProtocol": "icmp",
                    "destinationNetworkList": "graphiant_dia_prefix",
                }
            }
        }
    }
    edge = mgr._build_edge_payload("edge-1", cfg, current)
    assert "trafficPolicy" not in edge


def test_dpi_idempotent_when_portal_omits_unknown_ip_protocol() -> None:
    """Portal GET may drop ipProtocol after PUT with UnknownIPProtocol; must not re-push."""
    desired = {
        "ipProtocol": "UnknownIPProtocol",
        "destinationNetwork": "8.8.8.8/32",
        "sourceNetworkList": None,
    }
    before = {"name": "graphiant_dia_ping_via_IP", "destinationNetwork": "8.8.8.8/32"}
    assert EdgeServicesManager._dpi_applications_equal(before, desired, "graphiant_dia_ping_via_IP") is True

    mgr = _make_manager()
    current = {
        "role": "cpe",
        "trafficPolicy": {
            "dpiApplications": [
                {"name": "graphiant_dia_ping_via_IP", "destinationNetwork": "8.8.8.8/32"},
            ],
        },
    }
    cfg = {
        "dpiApplications": {
            "graphiant_dia_ping_via_IP": {
                "application": {
                    "ipProtocol": "UnknownIPProtocol",
                    "sourceNetwork": None,
                    "sourceNetworkList": None,
                    "sourcePort": None,
                    "sourcePortList": None,
                    "destinationNetwork": "8.8.8.8/32",
                    "destinationNetworkList": None,
                    "destinationPort": None,
                    "destinationPortList": None,
                }
            }
        }
    }
    edge = mgr._build_edge_payload("edge-2", cfg, current)
    assert "trafficPolicy" not in edge


def test_build_edge_payload_skips_dpi_when_portal_description_not_in_yaml() -> None:
    """Portal GET may include description; YAML without it should still be idempotent."""
    mgr = _make_manager()
    current = {
        "role": "cpe",
        "trafficPolicy": {
            "dpiApplications": [
                {
                    "name": "whitehouse.gov",
                    "description": "TCP app using destination prefix and port list",
                    "ipProtocol": "tcp",
                    "destinationNetwork": "192.0.66.180/32",
                    "destinationPortList": "web_ports",
                },
            ],
            "portLists": [{"id": 1, "name": "web_ports", "ports": [80, 443]}],
        },
    }
    cfg = {
        "dpiApplications": {
            "whitehouse.gov": {
                "application": {
                    "ipProtocol": "tcp",
                    "destinationNetwork": "192.0.66.180/32",
                    "destinationPortList": "web_ports",
                }
            }
        }
    }
    edge = mgr._build_edge_payload("edge-1", cfg, current)
    assert "trafficPolicy" not in edge


def test_build_edge_payload_skips_dpi_when_unchanged() -> None:
    mgr = _make_manager()
    app = {
        "name": "whitehouse.gov",
        "description": None,
        "ipProtocol": "tcp",
        "sourceNetwork": None,
        "sourceNetworkList": None,
        "sourcePort": None,
        "sourcePortList": None,
        "destinationNetwork": "192.0.66.180/32",
        "destinationNetworkList": None,
        "destinationPort": None,
        "destinationPortList": "web_ports",
    }
    current = {
        "role": "cpe",
        "edge": {
            "trafficPolicy": {
                "dpiApplications": {"whitehouse.gov": {"application": app}},
                "portLists": {"web_ports": {"list": {"name": "web_ports", "ports": [80, 443]}}},
            }
        },
    }
    cfg = {"dpiApplications": {"whitehouse.gov": {"application": dict(app)}}}
    edge = mgr._build_edge_payload("edge-1", cfg, current)
    assert "trafficPolicy" not in edge


def test_build_edge_payload_dpi_remove_application() -> None:
    mgr = _make_manager()
    current = {
        "role": "cpe",
        "edge": {
            "trafficPolicy": {
                "dpiApplications": {
                    "old-app": {
                        "application": {"name": "old-app", "ipProtocol": "icmp"},
                    }
                }
            }
        },
    }
    cfg = {"dpiApplications": {"old-app": {"state": "absent"}}}
    edge = mgr._build_edge_payload("edge-1", cfg, current)
    assert edge["trafficPolicy"]["dpiApplications"]["old-app"] == {"application": None}


def test_validate_dpi_unknown_port_list_fails() -> None:
    mgr = _make_manager()
    current = {"edge": {"trafficPolicy": {"portLists": {}}}}
    desired = {
        "app1": {
            "application": {
                "name": "app1",
                "ipProtocol": "tcp",
                "destinationPortList": "missing_ports",
            }
        }
    }
    with pytest.raises(ConfigurationError, match="missing_ports"):
        mgr._validate_dpi_list_references("edge-1", desired, current)
