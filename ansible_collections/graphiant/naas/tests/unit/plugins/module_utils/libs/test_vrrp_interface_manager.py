# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""
Unit tests for VRRPInterfaceManager.

Two areas are covered:

1. Payload builders -- the pure-Python ``_build_vrrp_interface`` /
   ``_vrrp_group_block`` that replaced the Jinja2 template
   templates/vrrp_interfaces_template.yaml.

2. Field-level idempotency and ``--diff`` -- ``configure`` compares desired VRRP
   groups against live state and skips unchanged devices; all operations emit a
   per-device ``diff_plan``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from ansible_collections.graphiant.naas.plugins.module_utils.libs.vrrp_interface_manager import VRRPInterfaceManager


def test_build_vrrp_main_interface_add_full_group() -> None:
    result = VRRPInterfaceManager._build_vrrp_interface(
        "GigabitEthernet7/0/0",
        action="add",
        vrrp_ipv4={
            "enabled": True,
            "virtualRouterId": 1,
            "priority": 120,
            "virtualIp": "10.1.11.100",
            "preempt": True,
            "allowInterOperability": True,
            "trackedInterfaces": [{"interface": "GigabitEthernet5/0/0", "priorityDecrement": 20}],
        },
    )
    assert result == {
        "interfaces": {
            "GigabitEthernet7/0/0": {
                "interface": {
                    "ipv4": {
                        "vrrp": {
                            "group": {
                                "enabled": True,
                                "allowInterOperability": True,
                                "virtualRouterId": 1,
                                "description": "GigabitEthernet7/0/0 VRRP group 1",
                                "priority": 120,
                                "virtualIp": "10.1.11.100",
                                "preempt": True,
                                "trackedInterfaces": [{"interface": "GigabitEthernet5/0/0", "priorityDecrement": 20}],
                            }
                        }
                    }
                }
            }
        }
    }


def test_build_vrrp_add_defaults() -> None:
    # Only the required fields are given; the rest fall back to template defaults.
    group = VRRPInterfaceManager._build_vrrp_interface(
        "gig1",
        action="add",
        vrrp_ipv4={"virtualRouterId": 5, "virtualIp": "10.0.0.1"},
    )["interfaces"]["gig1"]["interface"]["ipv4"]["vrrp"]["group"]
    assert group["enabled"] is True
    assert group["allowInterOperability"] is False
    assert group["priority"] == 100
    assert group["preempt"] is False
    assert group["description"] == "gig1 VRRP group 5"
    assert "trackedInterfaces" not in group  # omitted when not provided


def test_build_vrrp_subinterface_keys_are_strings_values_int() -> None:
    result = VRRPInterfaceManager._build_vrrp_interface(
        "GigabitEthernet8/0/0",
        action="add",
        vlan=28,
        vrrp_ipv4={"virtualRouterId": 10, "virtualIp": "10.3.177.100"},
        vrrp_ipv6={"virtualRouterId": 11, "virtualIp": "2001:10:3:177::100"},
    )
    interface = result["interfaces"]["GigabitEthernet8/0/0"]["interface"]
    subs = interface["subinterfaces"]
    # Key is the quoted vlan (string); inner "vlan" stays an int.
    assert set(subs) == {"28"}
    sub = subs["28"]["interface"]
    assert sub["vlan"] == 28
    assert sub["ipv4"]["vrrp"]["group"]["virtualRouterId"] == 10
    assert sub["ipv6"]["vrrp"]["group"]["virtualRouterId"] == 11


def test_build_vrrp_enable_toggles_enabled_only() -> None:
    result = VRRPInterfaceManager._build_vrrp_interface("gig1", action="enable", vrrp_ipv4={})
    assert result["interfaces"]["gig1"]["interface"] == {"ipv4": {"vrrp": {"group": {"enabled": True}}}}


def test_build_vrrp_delete_toggles_enabled_only() -> None:
    result = VRRPInterfaceManager._build_vrrp_interface(
        "gig1",
        action="delete",
        vrrp_ipv4={"virtualRouterId": 1, "virtualIp": "10.0.0.1"},
        vrrp_ipv6={"virtualRouterId": 2, "virtualIp": "2001::1"},
    )
    assert result["interfaces"]["gig1"]["interface"] == {
        "ipv4": {"vrrp": {"group": {"enabled": False}}},
        "ipv6": {"vrrp": {"group": {"enabled": False}}},
    }


def test_build_vrrp_only_requested_family_included() -> None:
    result = VRRPInterfaceManager._build_vrrp_interface(
        "gig1",
        action="add",
        vrrp_ipv6={"virtualRouterId": 2, "virtualIp": "2001::1"},
    )
    interface = result["interfaces"]["gig1"]["interface"]
    assert "ipv4" not in interface
    assert "ipv6" in interface


# ===========================================================================
# Idempotency / diff helpers and operations
# ===========================================================================


def _make_manager() -> VRRPInterfaceManager:
    config_utils = MagicMock()
    config_utils.gsdk = MagicMock()
    config_utils.template = MagicMock()
    mgr = VRRPInterfaceManager(config_utils)
    mgr.gsdk.enterprise_info = {"company_name": "acme"}
    mgr.gsdk.get_device_id = MagicMock(return_value=101)
    # Never hit the real concurrent executor / API in unit tests.
    mgr.execute_concurrent_tasks = MagicMock()
    return mgr


def _vrrp_group(
    enabled=True,
    priority=100,
    virtual_ip="10.1.11.100",
    preempt=False,
    allow=False,
    tracked=None,
    description=None,
) -> SimpleNamespace:
    """
    Mimic the SDK GET ``vrrp_group`` object (``ManaV2VrrpGroup``).

    Field names mirror the real GET model: the virtual IP is ``virtual_ip_address``
    (not ``virtual_ip``) and there is no ``virtual_router_id``.
    """
    return SimpleNamespace(
        enabled=enabled,
        priority=priority,
        virtual_ip_address=virtual_ip,
        preempt=preempt,
        allow_inter_operability=allow,
        tracked_interfaces=tracked,
        description=description,
    )


def _intf(name, ipv4=None, ipv6=None, subinterfaces=None) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        ipv4=SimpleNamespace(vrrp_group=ipv4) if ipv4 is not None else None,
        ipv6=SimpleNamespace(vrrp_group=ipv6) if ipv6 is not None else None,
        subinterfaces=subinterfaces or [],
    )


def _subintf(vlan, ipv4=None, ipv6=None) -> SimpleNamespace:
    return SimpleNamespace(
        vlan=vlan,
        ipv4=SimpleNamespace(vrrp_group=ipv4) if ipv4 is not None else None,
        ipv6=SimpleNamespace(vrrp_group=ipv6) if ipv6 is not None else None,
    )


def _device_info(interfaces) -> SimpleNamespace:
    return SimpleNamespace(device=SimpleNamespace(interfaces=interfaces))


_FULL_IPV4 = {
    "enabled": True,
    "virtualRouterId": 1,
    "priority": 120,
    "virtualIp": "10.1.11.100",
    "preempt": True,
    "allowInterOperability": True,
    "trackedInterfaces": [{"interface": "GigabitEthernet5/0/0", "priorityDecrement": 20}],
}


def _matching_group() -> SimpleNamespace:
    return _vrrp_group(
        enabled=True,
        priority=120,
        virtual_ip="10.1.11.100",
        preempt=True,
        allow=True,
        tracked=[SimpleNamespace(interface="GigabitEthernet5/0/0", priority_decrement=20)],
    )


def test_normalized_config_and_get_match_for_identical_vrrp() -> None:
    desired = VRRPInterfaceManager._normalized_vrrp_from_config(_FULL_IPV4)
    current = VRRPInterfaceManager._normalized_vrrp_from_get(_matching_group())
    assert not VRRPInterfaceManager._sparse_differs(desired, current)


def test_normalized_sparse_differs_on_priority() -> None:
    desired = VRRPInterfaceManager._normalized_vrrp_from_config(_FULL_IPV4)
    current = VRRPInterfaceManager._normalized_vrrp_from_get(_matching_group())
    current["priority"] = 100
    assert VRRPInterfaceManager._sparse_differs(desired, current)


def test_configure_skips_when_vrrp_matches() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(
        return_value={"vrrp_config": [{"edge-1": [{"name": "GigabitEthernet7/0/0", "vrrp_ipv4": _FULL_IPV4}]}]}
    )
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info([_intf("GigabitEthernet7/0/0", ipv4=_matching_group())])
    )

    result = mgr.configure_vrrp_interfaces("f.yaml")

    assert result["changed"] is False
    assert result["configured_devices"] == []
    assert result["skipped_devices"] == ["edge-1"]
    assert result["configured_interfaces"] == []
    assert result["skipped_interfaces"] == [{"device": "edge-1", "interface": "GigabitEthernet7/0/0", "vlan": None}]
    assert result["diff_plan"] == []
    mgr.execute_concurrent_tasks.assert_not_called()


def test_configure_changed_on_priority_drift_records_diff() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(
        return_value={"vrrp_config": [{"edge-1": [{"name": "GigabitEthernet7/0/0", "vrrp_ipv4": _FULL_IPV4}]}]}
    )
    drifted = _matching_group()
    drifted.priority = 100  # device priority differs from desired (120)
    mgr.gsdk.get_device_info = MagicMock(return_value=_device_info([_intf("GigabitEthernet7/0/0", ipv4=drifted)]))

    result = mgr.configure_vrrp_interfaces("f.yaml")

    assert result["changed"] is True
    assert result["configured_devices"] == ["edge-1"]
    assert result["skipped_devices"] == []
    assert len(result["diff_plan"]) == 1
    entry = result["diff_plan"][0]
    assert entry["device"] == "edge-1"
    assert entry["branch"] == "edge"
    assert entry["after"]["GigabitEthernet7/0/0"]["ipv4"]["priority"] == 120
    assert entry["before"]["GigabitEthernet7/0/0"]["ipv4"]["priority"] == 100
    assert result["configured_interfaces"] == [{"device": "edge-1", "interface": "GigabitEthernet7/0/0", "vlan": None}]
    assert result["skipped_interfaces"] == []
    mgr.execute_concurrent_tasks.assert_called_once()


def test_configure_changed_when_group_absent_on_device() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(
        return_value={"vrrp_config": [{"edge-1": [{"name": "GigabitEthernet7/0/0", "vrrp_ipv4": _FULL_IPV4}]}]}
    )
    # Interface exists but has no VRRP group configured yet.
    mgr.gsdk.get_device_info = MagicMock(return_value=_device_info([_intf("GigabitEthernet7/0/0")]))

    result = mgr.configure_vrrp_interfaces("f.yaml")

    assert result["changed"] is True
    assert result["configured_devices"] == ["edge-1"]
    assert result["diff_plan"][0]["before"]["GigabitEthernet7/0/0"]["ipv4"] == {}


def test_configure_pushes_only_changed_interface() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(
        return_value={
            "vrrp_config": [
                {
                    "edge-1": [
                        {"name": "GigabitEthernet7/0/0", "vrrp_ipv4": _FULL_IPV4},
                        {"name": "GigabitEthernet9/0/0", "vrrp_ipv4": _FULL_IPV4},
                    ]
                }
            ]
        }
    )
    # Gi7 already matches the device; Gi9 differs (priority drift) and must be pushed.
    gi9_drift = _matching_group()
    gi9_drift.priority = 100
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info(
            [
                _intf("GigabitEthernet7/0/0", ipv4=_matching_group()),
                _intf("GigabitEthernet9/0/0", ipv4=gi9_drift),
            ]
        )
    )

    result = mgr.configure_vrrp_interfaces("f.yaml")

    assert result["changed"] is True
    assert result["configured_devices"] == ["edge-1"]
    assert result["configured_interfaces"] == [{"device": "edge-1", "interface": "GigabitEthernet9/0/0", "vlan": None}]
    assert result["skipped_interfaces"] == [{"device": "edge-1", "interface": "GigabitEthernet7/0/0", "vlan": None}]
    # Only the changed interface is in the pushed payload and in the diff.
    pushed_config = mgr.execute_concurrent_tasks.call_args[0][1]
    assert set(pushed_config[101]["edge"]["interfaces"]) == {"GigabitEthernet9/0/0"}
    assert set(result["diff_plan"][0]["after"]) == {"GigabitEthernet9/0/0"}


def test_configure_subinterface_drift_detected() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(
        return_value={
            "vrrp_config": [
                {
                    "edge-1": [
                        {
                            "name": "GigabitEthernet8/0/0",
                            "vlan": 28,
                            "vrrp_ipv4": {"virtualRouterId": 10, "virtualIp": "10.3.177.100", "priority": 120},
                        }
                    ]
                }
            ]
        }
    )
    sub_group = _vrrp_group(enabled=True, priority=100, virtual_ip="10.3.177.100")
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info([_intf("GigabitEthernet8/0/0", subinterfaces=[_subintf(28, ipv4=sub_group)])])
    )

    result = mgr.configure_vrrp_interfaces("f.yaml")

    assert result["changed"] is True
    assert "GigabitEthernet8/0/0.28" in result["diff_plan"][0]["after"]


def test_enable_records_diff_plan() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(
        return_value={"vrrp_config": [{"edge-1": [{"name": "GigabitEthernet7/0/0", "vrrp_ipv4": _FULL_IPV4}]}]}
    )
    # VRRP exists but is currently disabled -> enable will flip it on.
    disabled = _matching_group()
    disabled.enabled = False
    mgr.gsdk.get_device_info = MagicMock(return_value=_device_info([_intf("GigabitEthernet7/0/0", ipv4=disabled)]))

    result = mgr.enable_vrrp_interfaces("f.yaml")

    assert result["changed"] is True
    assert len(result["diff_plan"]) == 1
    entry = result["diff_plan"][0]
    assert entry["after"]["GigabitEthernet7/0/0"]["ipv4"] == {"enabled": True}
    assert entry["before"]["GigabitEthernet7/0/0"]["ipv4"] == {"enabled": False}


def test_deconfigure_records_diff_plan() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(
        return_value={"vrrp_config": [{"edge-1": [{"name": "GigabitEthernet7/0/0", "vrrp_ipv4": _FULL_IPV4}]}]}
    )
    # VRRP is currently enabled -> deconfigure will disable it.
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info([_intf("GigabitEthernet7/0/0", ipv4=_matching_group())])
    )

    result = mgr.deconfigure_vrrp_interfaces("f.yaml")

    assert result["changed"] is True
    assert len(result["diff_plan"]) == 1
    entry = result["diff_plan"][0]
    assert entry["after"]["GigabitEthernet7/0/0"]["ipv4"] == {"enabled": False}
    assert entry["before"]["GigabitEthernet7/0/0"]["ipv4"] == {"enabled": True}


def test_deconfigure_skips_when_already_disabled() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(
        return_value={"vrrp_config": [{"edge-1": [{"name": "GigabitEthernet7/0/0", "vrrp_ipv4": _FULL_IPV4}]}]}
    )
    disabled = _matching_group()
    disabled.enabled = False
    mgr.gsdk.get_device_info = MagicMock(return_value=_device_info([_intf("GigabitEthernet7/0/0", ipv4=disabled)]))

    result = mgr.deconfigure_vrrp_interfaces("f.yaml")

    assert result["changed"] is False
    assert result["diff_plan"] == []
    mgr.execute_concurrent_tasks.assert_not_called()


def test_build_vrrp_present_empty_tracked_emits_clear_sentinel() -> None:
    # Present-but-empty trackedInterfaces (``trackedInterfaces:`` -> None, or ``[]``)
    # emits the API clear sentinel ``[{}]`` (an empty list is ignored by the merge PUT).
    for value in (None, []):
        group = VRRPInterfaceManager._build_vrrp_interface(
            "gig1",
            action="add",
            vrrp_ipv4={"virtualRouterId": 1, "virtualIp": "10.0.0.1", "trackedInterfaces": value},
        )["interfaces"]["gig1"]["interface"]["ipv4"]["vrrp"]["group"]
        assert group["trackedInterfaces"] == [{}]


def test_configure_detects_tracked_interface_removal() -> None:
    mgr = _make_manager()
    # Config clears trackedInterfaces (YAML ``trackedInterfaces:`` parses as None);
    # everything else matches the device, so the removal is the only drift.
    cleared = dict(_FULL_IPV4, trackedInterfaces=None)
    mgr.render_config_file = MagicMock(
        return_value={"vrrp_config": [{"edge-1": [{"name": "GigabitEthernet7/0/0", "vrrp_ipv4": cleared}]}]}
    )
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info([_intf("GigabitEthernet7/0/0", ipv4=_matching_group())])
    )

    result = mgr.configure_vrrp_interfaces("f.yaml")

    assert result["changed"] is True
    entry = result["diff_plan"][0]
    assert entry["before"]["GigabitEthernet7/0/0"]["ipv4"]["trackedInterfaces"] == [["GigabitEthernet5/0/0", 20]]
    # Diff shows the logical cleared state ([]); the payload uses the API sentinel.
    assert entry["after"]["GigabitEthernet7/0/0"]["ipv4"]["trackedInterfaces"] == []
    pushed = mgr.execute_concurrent_tasks.call_args[0][1]
    group = pushed[101]["edge"]["interfaces"]["GigabitEthernet7/0/0"]["interface"]["ipv4"]["vrrp"]["group"]
    assert group["trackedInterfaces"] == [{}]


def test_configure_cleared_tracked_is_idempotent_once_device_has_none() -> None:
    mgr = _make_manager()
    cleared = dict(_FULL_IPV4, trackedInterfaces=None)
    mgr.render_config_file = MagicMock(
        return_value={"vrrp_config": [{"edge-1": [{"name": "GigabitEthernet7/0/0", "vrrp_ipv4": cleared}]}]}
    )
    # Device already has no tracked interfaces -> a cleared config must be a no-op.
    no_tracked = _vrrp_group(
        enabled=True, priority=120, virtual_ip="10.1.11.100", preempt=True, allow=True, tracked=None
    )
    mgr.gsdk.get_device_info = MagicMock(return_value=_device_info([_intf("GigabitEthernet7/0/0", ipv4=no_tracked)]))

    result = mgr.configure_vrrp_interfaces("f.yaml")

    assert result["changed"] is False
    assert result["skipped_devices"] == ["edge-1"]
    mgr.execute_concurrent_tasks.assert_not_called()
