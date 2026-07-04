# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for StaticRoutesManager."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from ansible_collections.graphiant.naas.plugins.module_utils.libs.static_routes_manager import StaticRoutesManager
from ansible_collections.graphiant.naas.plugins.module_utils.libs.exceptions import ConfigurationError


def _make_manager() -> StaticRoutesManager:
    config_utils = MagicMock()
    config_utils.gsdk = MagicMock()
    return StaticRoutesManager(config_utils)


# ---------------------------------------------------------------------------
# _normalize_route
# ---------------------------------------------------------------------------

def test_normalize_route_none_returns_none() -> None:
    assert StaticRoutesManager._normalize_route(None) is None


def test_normalize_route_non_dict_returns_none() -> None:
    assert StaticRoutesManager._normalize_route("bad") is None


def test_normalize_route_int_admin_distance() -> None:
    route = {"destinationPrefix": "10.0.0.0/8", "administrativeDistance": 10, "nextHops": []}
    norm = StaticRoutesManager._normalize_route(route)
    assert norm["administrativeDistance"] == {"distance": "10"}


def test_normalize_route_dict_admin_distance() -> None:
    route = {"destinationPrefix": "10.0.0.0/8", "administrativeDistance": {"distance": 20}, "nextHops": []}
    norm = StaticRoutesManager._normalize_route(route)
    assert norm["administrativeDistance"] == {"distance": "20"}


def test_normalize_route_sorts_next_hops() -> None:
    route = {
        "destinationPrefix": "0.0.0.0/0",
        "nextHops": [
            {"nextHopAddress": "192.168.1.2"},
            {"nextHopAddress": "192.168.1.1"},
        ],
    }
    norm = StaticRoutesManager._normalize_route(route)
    addrs = [nh["nextHopAddress"] for nh in norm["nextHops"]]
    assert addrs == sorted(addrs)


def test_normalize_route_canonicalizes_outgoing_interface_aliases() -> None:
    route = {
        "destinationPrefix": "0.0.0.0/0",
        "nextHops": [{"thirdPartyIpsecTunnel": "tun0"}],
    }
    norm = StaticRoutesManager._normalize_route(route)
    assert norm["nextHops"][0]["outgoingInterface"] == "tun0"


# ---------------------------------------------------------------------------
# _build_next_hop
# ---------------------------------------------------------------------------

def test_build_next_hop_interface() -> None:
    nh = StaticRoutesManager._build_next_hop({"interface": "eth0", "nextHopAddress": "10.0.0.1"})
    assert nh == {"interface": "eth0", "nextHopAddress": "10.0.0.1"}


def test_build_next_hop_circuit() -> None:
    nh = StaticRoutesManager._build_next_hop({"circuit": "wan-1"})
    assert nh == {"circuit": "wan-1"}


def test_build_next_hop_ipsec_tunnel() -> None:
    nh = StaticRoutesManager._build_next_hop({"thirdPartyIpsecTunnel": "tun0"})
    assert nh == {"thirdPartyIpsecTunnel": "tun0"}


def test_build_next_hop_invalid_raises() -> None:
    with pytest.raises(ConfigurationError, match="Invalid nextHop"):
        StaticRoutesManager._build_next_hop({"unknown": "x"})


def test_build_next_hop_non_dict_raises() -> None:
    with pytest.raises(ConfigurationError):
        StaticRoutesManager._build_next_hop("bad")


# ---------------------------------------------------------------------------
# _build_static_routes
# ---------------------------------------------------------------------------

def test_build_static_routes_configure() -> None:
    routes = [{"destinationPrefix": "10.0.0.0/8", "nextHops": [{"interface": "eth0"}]}]
    result = StaticRoutesManager._build_static_routes(routes, "configure")
    assert "10.0.0.0/8" in result
    assert result["10.0.0.0/8"]["route"]["destinationPrefix"] == "10.0.0.0/8"


def test_build_static_routes_deconfigure_sets_null_route() -> None:
    routes = [{"destinationPrefix": "10.0.0.0/8", "nextHops": []}]
    result = StaticRoutesManager._build_static_routes(routes, "deconfigure")
    assert result["10.0.0.0/8"] == {"route": None}


def test_build_static_routes_dict_input() -> None:
    routes_dict = {"10.1.0.0/16": {"nextHops": [{"circuit": "wan-1"}]}}
    result = StaticRoutesManager._build_static_routes(routes_dict, "configure")
    assert "10.1.0.0/16" in result


def test_build_static_routes_missing_prefix_raises() -> None:
    with pytest.raises(ConfigurationError, match="destinationPrefix"):
        StaticRoutesManager._build_static_routes([{"nextHops": []}], "configure")


# ---------------------------------------------------------------------------
# _payload_differs_from_existing
# ---------------------------------------------------------------------------

def _device_info_with_routes(seg_name: str, prefix: str, next_hop_addr: str) -> dict:
    return {
        "device": {
            "edge": {
                "segments": {
                    seg_name: {
                        "staticRoutes": {
                            prefix: {
                                "route": {
                                    "destinationPrefix": prefix,
                                    "nextHops": [{"nextHopAddress": next_hop_addr}],
                                }
                            }
                        }
                    }
                }
            }
        }
    }


def test_payload_differs_returns_true_when_route_changed() -> None:
    mgr = _make_manager()
    payload = {
        "edge": {"segments": {"lan-1": {"staticRoutes": {
            "10.0.0.0/8": {"route": {"destinationPrefix": "10.0.0.0/8", "nextHops": [{"nextHopAddress": "10.0.0.2"}]}}
        }}}}
    }
    device_info = _device_info_with_routes("lan-1", "10.0.0.0/8", "10.0.0.1")
    assert mgr._payload_differs_from_existing(payload, device_info) is True


def test_payload_differs_returns_false_when_route_matches() -> None:
    mgr = _make_manager()
    payload = {
        "edge": {"segments": {"lan-1": {"staticRoutes": {
            "10.0.0.0/8": {"route": {"destinationPrefix": "10.0.0.0/8", "nextHops": [{"nextHopAddress": "10.0.0.1"}]}}
        }}}}
    }
    device_info = _device_info_with_routes("lan-1", "10.0.0.0/8", "10.0.0.1")
    assert mgr._payload_differs_from_existing(payload, device_info) is False


def test_payload_differs_deconfigure_no_op_when_already_absent() -> None:
    mgr = _make_manager()
    payload = {"edge": {"segments": {"lan-1": {"staticRoutes": {"192.168.0.0/24": {"route": None}}}}}}
    device_info = {"device": {"edge": {"segments": {"lan-1": {"staticRoutes": {}}}}}}
    assert mgr._payload_differs_from_existing(payload, device_info) is False


# ---------------------------------------------------------------------------
# apply_static_routes — idempotency and diff_plan
# ---------------------------------------------------------------------------

_YAML_CFG = {
    "staticRoutes": [
        {
            "edge-1": {
                "segments": [
                    {
                        "lanSegment": "lan-1-test",
                        "staticRoutes": [
                            {"destinationPrefix": "10.0.0.0/8", "nextHops": [{"nextHopAddress": "10.0.0.1"}]}
                        ],
                    }
                ]
            }
        }
    ]
}


def test_apply_static_routes_skips_when_no_diff() -> None:
    mgr = _make_manager()
    mgr.gsdk.get_device_id.return_value = 42
    device_info = _device_info_with_routes("lan-1-test", "10.0.0.0/8", "10.0.0.1")
    info_mock = MagicMock()
    info_mock.to_dict.return_value = device_info
    mgr.gsdk.get_device_info.return_value = info_mock

    with patch.object(mgr, "render_config_file", return_value=_YAML_CFG):
        result = mgr.apply_static_routes("f.yaml", operation="configure")

    assert result["changed"] is False
    assert "edge-1" in result["skipped_devices"]
    mgr.gsdk.put_device_config_raw.assert_not_called()


def test_apply_static_routes_sets_diff_plan_when_change_needed() -> None:
    mgr = _make_manager()
    mgr.gsdk.get_device_id.return_value = 42
    device_info = _device_info_with_routes("lan-1-test", "10.0.0.0/8", "192.168.99.1")
    info_mock = MagicMock()
    info_mock.to_dict.return_value = device_info
    mgr.gsdk.get_device_info.return_value = info_mock

    with patch.object(mgr, "render_config_file", return_value=_YAML_CFG), \
         patch.object(mgr, "execute_concurrent_tasks"):
        result = mgr.apply_static_routes("f.yaml", operation="configure")

    assert result["diff_plan"]
    entry = result["diff_plan"][0]
    assert entry["device"] == "edge-1"
    assert entry["branch"] == "edge.segments"
    assert "segments" in entry["before"]
    assert "segments" in entry["after"]


def test_apply_static_routes_unsupported_operation_raises() -> None:
    mgr = _make_manager()
    with patch.object(mgr, "render_config_file", return_value=_YAML_CFG):
        with pytest.raises(ConfigurationError, match="Unsupported"):
            mgr.apply_static_routes("f.yaml", operation="reset")
