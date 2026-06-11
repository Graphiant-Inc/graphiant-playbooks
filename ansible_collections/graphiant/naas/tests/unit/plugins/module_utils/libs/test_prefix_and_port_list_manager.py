# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for PrefixAndPortListManager (no live API)."""

from __future__ import annotations

from unittest.mock import MagicMock

from ansible_collections.graphiant.naas.plugins.module_utils.libs.prefix_and_port_list import (
    PrefixAndPortListManager,
)


def _mgr() -> PrefixAndPortListManager:
    return PrefixAndPortListManager(MagicMock())


def _network_lists_payload(network_lists):
    return {"edge": {"trafficPolicy": {"networkLists": network_lists}}}


def _port_lists_payload(port_lists):
    return {"edge": {"trafficPolicy": {"portLists": port_lists}}}


def _device_network_lists(lists):
    return {"device": {"edge": {"trafficPolicy": {"networkLists": lists}}}}


def _device_port_lists(lists):
    return {"device": {"edge": {"trafficPolicy": {"portLists": lists}}}}


def test_load_section_preserves_list_shaped_device_config() -> None:
    m = _mgr()
    yaml_cfg = {
        "networkLists": [
            {
                "edge-1-sdktest": [
                    {
                        "name": "demo_prefix_list_1",
                        "networks": ["1.1.1.1/32", "2.2.2.2/32"],
                    }
                ]
            }
        ]
    }
    m.render_config_file = lambda _path: yaml_cfg
    loaded = m._load_section("sample_prefix_and_port_list.yaml", "networkLists")
    assert loaded["edge-1-sdktest"] == yaml_cfg["networkLists"][0]["edge-1-sdktest"]


def test_build_device_payload_from_list_shaped_yaml() -> None:
    m = _mgr()
    yaml_cfg = {
        "networkLists": [
            {
                "edge-1-sdktest": [
                    {
                        "name": "demo_prefix_list_1",
                        "networks": ["1.1.1.1/32", "2.2.2.2/32"],
                    }
                ]
            }
        ]
    }
    m.render_config_file = lambda _path: yaml_cfg
    payload = m._build_device_payload("edge-1-sdktest", "sample_prefix_and_port_list.yaml", "create", "network")
    assert payload == {
        "edge": {
            "trafficPolicy": {
                "networkLists": {
                    "demo_prefix_list_1": {
                        "list": {
                            "name": "demo_prefix_list_1",
                            "networks": ["1.1.1.1/32", "2.2.2.2/32"],
                        }
                    }
                }
            }
        }
    }


def test_normalize_list_items_merges_split_yaml_shape() -> None:
    m = _mgr()
    raw = [{"name": "demo_prefix_list_1"}, {"networks": ["1.1.1.1/32", "2.2.2.2/32"]}]
    items = m._normalize_list_items(raw, value_field="networks")
    assert items == [{"name": "demo_prefix_list_1", "networks": ["1.1.1.1/32", "2.2.2.2/32"]}]


def test_network_lists_from_yaml_create_shape() -> None:
    m = _mgr()
    out = m._network_lists_from_yaml(
        [{"name": "demo_prefix_list_1", "networks": ["2.2.2.2/32", "1.1.1.1/32"]}],
        operation="create",
    )
    assert out == {
        "demo_prefix_list_1": {
            "list": {"name": "demo_prefix_list_1", "networks": ["1.1.1.1/32", "2.2.2.2/32"]},
        }
    }


def test_network_lists_from_yaml_delete_shape() -> None:
    m = _mgr()
    out = m._network_lists_from_yaml([{"name": "demo_prefix_list_1"}], operation="delete")
    assert out == {"demo_prefix_list_1": {"list": None}}


def test_network_lists_from_yaml_create_state_absent() -> None:
    m = _mgr()
    out = m._network_lists_from_yaml(
        [{"name": "testing_prefix_list", "networks": ["10.1.1.0/24"], "state": "absent"}],
        operation="create",
    )
    assert out == {"testing_prefix_list": {"list": None}}


def test_port_lists_from_yaml_create_state_absent() -> None:
    m = _mgr()
    out = m._port_lists_from_yaml(
        [{"name": "web_ports", "ports": [80, 443], "state": "absent"}],
        operation="create",
    )
    assert out == {"web_ports": {"list": None}}


def test_build_device_payload_mixed_present_and_absent() -> None:
    m = _mgr()
    yaml_cfg = {
        "networkLists": [
            {
                "edge-1-sdktest": [
                    {"name": "graphiant_dia_prefix", "networks": ["1.1.1.1/32", "8.8.8.8/32"]},
                    {"name": "testing_prefix_list", "networks": ["10.1.1.0/24"], "state": "absent"},
                ]
            }
        ],
        "portLists": [
            {
                "edge-1-sdktest": [
                    {"name": "web_ports", "ports": [80, 443]},
                    {"name": "testing_port_list", "ports": [123], "state": "absent"},
                ]
            }
        ],
    }
    m.render_config_file = lambda _path: yaml_cfg
    payload = m._build_device_payload("edge-1-sdktest", "sample_prefix_and_port_list.yaml", "create", "both")
    nl = payload["edge"]["trafficPolicy"]["networkLists"]
    pl = payload["edge"]["trafficPolicy"]["portLists"]
    assert nl["graphiant_dia_prefix"]["list"]["networks"] == ["1.1.1.1/32", "8.8.8.8/32"]
    assert nl["testing_prefix_list"] == {"list": None}
    assert pl["web_ports"]["list"]["ports"] == [80, 443]
    assert pl["testing_port_list"] == {"list": None}


def test_payload_differs_false_when_create_state_absent_already_gone() -> None:
    m = _mgr()
    desired = _network_lists_payload(
        {
            "testing_prefix_list": {"list": None},
            "graphiant_dia_prefix": {"list": {"name": "graphiant_dia_prefix", "networks": ["1.1.1.1/32"]}},
        }
    )
    device_info = _device_network_lists([{"name": "graphiant_dia_prefix", "networks": ["1.1.1.1/32"]}])
    assert m._payload_differs(desired, device_info) is False


def test_payload_differs_false_when_network_list_matches() -> None:
    m = _mgr()
    desired = _network_lists_payload(
        {
            "demo_prefix_list_1": {
                "list": {"name": "demo_prefix_list_1", "networks": ["1.1.1.1/32", "2.2.2.2/32"]},
            }
        }
    )
    device_info = _device_network_lists(
        [{"name": "demo_prefix_list_1", "networks": ["2.2.2.2/32", "1.1.1.1/32"]}]
    )
    assert m._payload_differs(desired, device_info) is False


def test_payload_differs_true_when_network_list_missing() -> None:
    m = _mgr()
    desired = _network_lists_payload(
        {"demo_prefix_list_1": {"list": {"name": "demo_prefix_list_1", "networks": ["1.1.1.1/32"]}}}
    )
    device_info = {"device": {"edge": {"trafficPolicy": {"networkLists": []}}}}
    assert m._payload_differs(desired, device_info) is True


def test_payload_differs_false_when_delete_target_already_absent() -> None:
    m = _mgr()
    desired = _network_lists_payload({"demo_prefix_list_1": {"list": None}})
    device_info = {"device": {"edge": {"trafficPolicy": {"networkLists": []}}}}
    assert m._payload_differs(desired, device_info) is False


def test_payload_differs_true_when_port_list_differs() -> None:
    m = _mgr()
    desired = _port_lists_payload({"demo_port_list_1": {"list": {"name": "demo_port_list_1", "ports": [100, 200]}}})
    device_info = _device_port_lists([{"name": "demo_port_list_1", "ports": [100]}])
    assert m._payload_differs(desired, device_info) is True


def test_traffic_policy_lists_diff_create_network_list() -> None:
    m = _mgr()
    device = {"edge": {"trafficPolicy": {"networkLists": []}}}
    payload = _network_lists_payload(
        {
            "demo_prefix_list_1": {
                "list": {"name": "demo_prefix_list_1", "networks": ["1.1.1.1/32", "2.2.2.2/32"]},
            }
        }
    )
    before, after = m._traffic_policy_lists_diff(device, payload)
    assert before["networkLists"]["demo_prefix_list_1"] is None
    assert after["networkLists"]["demo_prefix_list_1"] == {
        "name": "demo_prefix_list_1",
        "networks": ["1.1.1.1/32", "2.2.2.2/32"],
    }


def test_traffic_policy_lists_diff_delete_network_list() -> None:
    m = _mgr()
    device = _device_network_lists([{"name": "demo_prefix_list_1", "networks": ["1.1.1.1/32"]}])["device"]
    payload = _network_lists_payload({"demo_prefix_list_1": {"list": None}})
    before, after = m._traffic_policy_lists_diff(device, payload)
    assert before["networkLists"]["demo_prefix_list_1"] == {
        "name": "demo_prefix_list_1",
        "networks": ["1.1.1.1/32"],
    }
    assert after["networkLists"]["demo_prefix_list_1"] is None
