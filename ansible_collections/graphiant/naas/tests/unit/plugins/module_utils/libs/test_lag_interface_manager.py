# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""
Unit tests for LagInterfaceManager.

Two areas are covered:

1. Payload builders -- the pure-Python ``_ip_block`` / ``_build_subinterface`` /
   ``_build_lag_interface`` / ``_apply_lag`` that replaced the Jinja2 template
   templates/lag_interfaces_template.yaml. These assert the generated payload is
   byte-for-byte what the template produced for each action.

2. Manager wiring -- ``configure_lag_interfaces`` / ``deconfigure_lag_interfaces``
   feed the builders and push the expected per-device payload.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from ansible_collections.graphiant.naas.plugins.module_utils.libs.exceptions import ConfigurationError
from ansible_collections.graphiant.naas.plugins.module_utils.libs.lag_interface_manager import LagInterfaceManager

# ===========================================================================
# Payload builders
# ===========================================================================


def test_ip_block_static_vs_dhcp() -> None:
    assert LagInterfaceManager._ip_block("10.0.0.1/24") == {"address": {"address": "10.0.0.1/24"}}
    # Absent / falsy address falls back to a DHCP-disabled block.
    assert LagInterfaceManager._ip_block(None) == {"dhcp": {"dhcpClient": False}}
    assert LagInterfaceManager._ip_block("") == {"dhcp": {"dhcpClient": False}}


def test_build_lag_add_full_payload() -> None:
    result = LagInterfaceManager._build_lag_interface(
        "LAG1",
        action="add",
        segment="seg1",
        alias="LAG1-alias",
        adminStatus=False,
        mtu=9000,
        ipv4="10.0.0.1/24",
        ipv6="2001:db8::1/64",
        lacpMode="PASSIVE",
        lacpTimer="FAST",
        lagMembers=["Gi0/0", "Gi0/1"],
        interfaceMemberIds=[10, 11],
    )
    assert result == {
        "lagInterfaces": {
            "LAG1": {
                "interface": {
                    "segment": "seg1",
                    "alias": "LAG1-alias",
                    "adminStatus": False,
                    "mtu": 9000,
                    "ipv4": {"address": {"address": "10.0.0.1/24"}},
                    "ipv6": {"address": {"address": "2001:db8::1/64"}},
                    "lacp": {"mode": "PASSIVE", "timer": "FAST"},
                    "lagMembers": {"10": {"interface": 10}, "11": {"interface": 11}},
                }
            }
        }
    }


def test_build_lag_add_defaults() -> None:
    # Only the required name/segment given; the rest fall back to template defaults.
    interface = LagInterfaceManager._build_lag_interface("LAG1", action="add", segment="seg1")["lagInterfaces"]["LAG1"][
        "interface"
    ]
    assert interface["adminStatus"] is True
    assert interface["mtu"] == 1500
    assert interface["lacp"] == {"mode": "ACTIVE", "timer": "SLOW"}
    assert interface["ipv4"] == {"dhcp": {"dhcpClient": False}}
    assert interface["ipv6"] == {"dhcp": {"dhcpClient": False}}
    assert "alias" not in interface  # omitted when not provided
    assert "lagMembers" not in interface  # omitted when no members


def test_build_lag_member_keys_are_strings_values_int() -> None:
    members = LagInterfaceManager._build_lag_interface(
        "LAG1",
        action="add",
        segment="seg1",
        lagMembers=["Gi0/0"],
        interfaceMemberIds=[42],
    )["lagInterfaces"]["LAG1"]["interface"]["lagMembers"]
    # Key is the quoted interface id (string); inner "interface" stays an int.
    assert set(members) == {"42"}
    assert members["42"] == {"interface": 42}


def test_build_lag_add_members_emits_id_remove_members_emits_empty() -> None:
    add = LagInterfaceManager._build_lag_interface(
        "LAG1", action="add_lag_members", lagMembers=["Gi0/0"], interfaceMemberIds=[5]
    )["lagInterfaces"]["LAG1"]["interface"]
    assert add["lagMembers"] == {"5": {"interface": 5}}
    # add_lag_members only emits the members section (no segment/mtu/lacp).
    assert set(add) == {"lagMembers"}

    remove = LagInterfaceManager._build_lag_interface(
        "LAG1", action="remove_lag_members", lagMembers=["Gi0/0"], interfaceMemberIds=[5]
    )["lagInterfaces"]["LAG1"]["interface"]
    assert remove["lagMembers"] == {"5": {}}


def test_build_lag_update_lacp_only_sends_provided_fields() -> None:
    both = LagInterfaceManager._build_lag_interface(
        "LAG1", action="update_lacp_configs", lacpMode="ACTIVE", lacpTimer="FAST"
    )["lagInterfaces"]["LAG1"]["interface"]
    assert both == {"lacp": {"mode": "ACTIVE", "timer": "FAST"}}

    timer_only = LagInterfaceManager._build_lag_interface("LAG1", action="update_lacp_configs", lacpTimer="SLOW")[
        "lagInterfaces"
    ]["LAG1"]["interface"]
    assert timer_only == {"lacp": {"timer": "SLOW"}}


def test_build_lag_delete_subinterfaces_null_interface() -> None:
    result = LagInterfaceManager._build_lag_interface(
        "LAG1", action="delete", subinterfaces=[{"vlan": 101}, {"vlan": "102"}]
    )
    subs = result["lagInterfaces"]["LAG1"]["interface"]["subinterfaces"]
    # Keys are strings; each deleted subinterface is null.
    assert subs == {"101": {"interface": None}, "102": {"interface": None}}


def test_build_lag_delete_lag_targets_interfaces_section() -> None:
    result = LagInterfaceManager._build_lag_interface("LAG1", action="delete_lag")
    assert result == {"interfaces": {"LAG1": {"interface": None}}}


def test_build_subinterface_add_full_and_keys() -> None:
    result = LagInterfaceManager._build_lag_interface(
        "LAG1",
        action="add",
        segment="seg1",
        subinterfaces=[
            {
                "vlan": "101",
                "segment": "sub-seg",
                "alias": "sub-alias",
                "adminStatus": False,
                "ipv4": "10.1.1.1/24",
            }
        ],
    )
    subs = result["lagInterfaces"]["LAG1"]["interface"]["subinterfaces"]
    # Outer key is the quoted vlan (string); inner "vlan" is coerced to int.
    assert set(subs) == {"101"}
    body = subs["101"]["interface"]
    assert body["vlan"] == 101
    assert body["adminStatus"] is False
    assert body["segment"] == "sub-seg"
    assert body["alias"] == "sub-alias"
    assert body["description"] == "101_sub-seg"
    assert body["ipv4"] == {"address": {"address": "10.1.1.1/24"}}
    assert body["ipv6"] == {"dhcp": {"dhcpClient": False}}


def test_build_subinterface_admin_status_falls_back_to_enabled_then_true() -> None:
    # adminStatus absent -> use ``enabled``.
    enabled = LagInterfaceManager._build_subinterface({"vlan": 101, "segment": "s", "enabled": False})
    assert enabled["adminStatus"] is False
    # Neither adminStatus nor enabled -> default True.
    default = LagInterfaceManager._build_subinterface({"vlan": 101, "segment": "s"})
    assert default["adminStatus"] is True


def test_build_subinterface_description_default_and_missing_segment() -> None:
    body = LagInterfaceManager._build_subinterface({"vlan": 55})
    # No description/segment -> "<vlan>_" and segment renders as "".
    assert body["description"] == "55_"
    assert body["segment"] == ""
    # alias omitted when not provided.
    assert "alias" not in body


# ===========================================================================
# _apply_lag merge semantics
# ===========================================================================


def test_apply_lag_merges_into_lag_interfaces_section() -> None:
    mgr = _make_manager()
    payload: dict = {"lagInterfaces": {}}
    mgr._apply_lag(payload, action="add", name="LAG1", segment="seg1")
    assert "LAG1" in payload["lagInterfaces"]


def test_apply_lag_delete_lag_merges_into_interfaces_section() -> None:
    mgr = _make_manager()
    payload: dict = {"interfaces": {}}
    mgr._apply_lag(payload, action="delete_lag", name="LAG1")
    assert payload["interfaces"]["LAG1"] == {"interface": None}


def test_apply_lag_missing_name_raises() -> None:
    mgr = _make_manager()
    with pytest.raises(ConfigurationError, match="Missing required parameters"):
        mgr._apply_lag({"lagInterfaces": {}}, action="add", segment="seg1")


# ===========================================================================
# Manager wiring
# ===========================================================================


def _make_manager() -> LagInterfaceManager:
    config_utils = MagicMock()
    config_utils.gsdk = MagicMock()
    config_utils.template = MagicMock()
    mgr = LagInterfaceManager(config_utils)
    mgr.gsdk.enterprise_info = {"company_name": "acme"}
    mgr.gsdk.get_device_id = MagicMock(return_value=101)
    # Never hit the real concurrent executor / API in unit tests.
    mgr.execute_concurrent_tasks = MagicMock()
    return mgr


def _device_info(interfaces) -> SimpleNamespace:
    return SimpleNamespace(device=SimpleNamespace(interfaces=interfaces))


def test_configure_add_builds_and_pushes_payload() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(
        return_value={
            "lagInterfaces": [{"edge-1": [{"name": "LAG1", "segment": "seg1", "lagMembers": ["Gi0/0", "Gi0/1"]}]}]
        }
    )
    # Two member interfaces resolve to ids 10/11; no existing LAG on the device.
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info([SimpleNamespace(name="Gi0/0", id=10), SimpleNamespace(name="Gi0/1", id=11)])
    )

    result = mgr.configure_lag_interfaces("f.yaml", action="add")

    assert result["changed"] is True
    assert result["created_lags"] == [{"device": "edge-1", "lag": "LAG1"}]
    assert result["updated_lags"] == []

    pushed = mgr.execute_concurrent_tasks.call_args[0][1]
    interface = pushed[101]["edge"]["lagInterfaces"]["LAG1"]["interface"]
    assert interface["segment"] == "seg1"
    assert interface["lagMembers"] == {"10": {"interface": 10}, "11": {"interface": 11}}


def test_configure_update_existing_lag_reports_updated() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(
        return_value={"lagInterfaces": [{"edge-1": [{"name": "LAG1", "segment": "seg1"}]}]}
    )
    mgr.gsdk.get_device_info = MagicMock(return_value=_device_info([]))
    # LAG already exists -> it is reported as updated, not created.
    mgr._get_existing_lag_info = MagicMock(
        return_value={"LAG1": {"alias": None, "id": 1, "subinterfaces": {}, "member_ids": set(), "lacp_config": {}}}
    )

    result = mgr.configure_lag_interfaces("f.yaml", action="add")

    assert result["created_lags"] == []
    assert result["updated_lags"] == [{"device": "edge-1", "lag": "LAG1"}]


def test_deconfigure_deletes_subinterfaces_then_main() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(return_value={"lagInterfaces": [{"edge-1": [{"name": "LAG1"}]}]})
    mgr.gsdk.get_device_info = MagicMock(return_value=_device_info([]))
    # Existing LAG with one subinterface -> both deletion steps run.
    mgr._get_existing_lag_info = MagicMock(
        return_value={"LAG1": {"alias": None, "id": 1, "subinterfaces": {101: {"alias": None}}, "member_ids": set()}}
    )

    result = mgr.deconfigure_lag_interfaces("f.yaml")

    assert result["changed"] is True
    assert result["deconfigured_lags"] == [{"device": "edge-1", "lag": "LAG1"}]
    assert result["deconfigured_devices"] == ["edge-1"]  # device names, not IDs
    assert result["skipped_lags"] == []

    # Two pushes: subinterface deletion, then main-interface deletion.
    assert mgr.execute_concurrent_tasks.call_count == 2
    sub_push = mgr.execute_concurrent_tasks.call_args_list[0][0][1]
    main_push = mgr.execute_concurrent_tasks.call_args_list[1][0][1]
    assert sub_push[101]["edge"]["lagInterfaces"]["LAG1"]["interface"]["subinterfaces"] == {"101": {"interface": None}}
    assert main_push[101]["edge"]["interfaces"]["LAG1"] == {"interface": None}


def test_deconfigure_skips_missing_lag() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(return_value={"lagInterfaces": [{"edge-1": [{"name": "LAG1"}]}]})
    mgr.gsdk.get_device_info = MagicMock(return_value=_device_info([]))
    mgr._get_existing_lag_info = MagicMock(return_value={})  # LAG not present -> skip

    result = mgr.deconfigure_lag_interfaces("f.yaml")

    assert result["changed"] is False
    assert result["deconfigured_lags"] == []
    assert result["skipped_lags"] == [{"device": "edge-1", "lag": "LAG1", "reason": "does not exist"}]
    mgr.execute_concurrent_tasks.assert_not_called()


# ===========================================================================
# Field-level idempotency + diff (configure/add path)
# ===========================================================================


def _addr(address=None, dhcp_client=False) -> SimpleNamespace:
    """Mimic the SDK ``ManaV2InterfaceAddress`` (``address`` / ``dhcp_client``)."""
    return SimpleNamespace(address=address, dhcp_client=dhcp_client)


def _lag_iface(
    name="LAG1",
    lan="seg1",
    enabled=True,
    mtu=1500,
    ipv4=None,
    ipv6=None,
    members=None,
    mode="ACTIVE",
    timer="SLOW",
    alias=None,
    subinterfaces=None,
) -> SimpleNamespace:
    """Mimic an SDK LAG main interface (``ManaV2Interface`` with ``lag_interface``)."""
    lag = SimpleNamespace(
        members=members or [],
        lacp_config=SimpleNamespace(mode=mode, timer=timer),
        id=1,
        minimum_members=1,
    )
    return SimpleNamespace(
        name=name,
        lan=lan,
        enabled=enabled,
        max_transmission_unit=mtu,
        configured_max_transmission_unit=mtu,
        ipv4=ipv4,
        ipv6=ipv6,
        lag_interface=lag,
        alias=alias,
        subinterfaces=subinterfaces or [],
    )


def test_norm_ip_config_matches_get_for_dhcp_disabled_default() -> None:
    # An omitted address means the LAG builder sends dhcp.dhcpClient=false (not DHCP on).
    desired = LagInterfaceManager._norm_ip_from_config(None)
    assert desired == {"dhcpClient": False}
    assert LagInterfaceManager._norm_ip_from_get(None) == desired
    assert LagInterfaceManager._norm_ip_from_get(_addr(dhcp_client=False)) == desired


def test_norm_ip_static_address_compared_by_address() -> None:
    assert LagInterfaceManager._norm_ip_from_config("10.0.0.1/24") == {"address": "10.0.0.1/24"}
    assert LagInterfaceManager._norm_ip_from_get(_addr(address="10.0.0.1/24")) == {"address": "10.0.0.1/24"}


def test_norm_ip_canonicalizes_equivalent_ipv6_forms() -> None:
    # The device GET can return a different textual form of the same IPv6 address
    # than the config (e.g. ``2001:10:1::1/64`` vs ``2001:10:1:0::1/64``); both must
    # canonicalize to the same value so an unchanged LAG is not reported as drifted.
    desired = LagInterfaceManager._norm_ip_from_config("2001:10:1::1/64")
    current = LagInterfaceManager._norm_ip_from_get(_addr(address="2001:10:1:0::1/64"))
    assert desired == current == {"address": "2001:10:1::1/64"}
    assert not LagInterfaceManager._sparse_differs(desired, current)
    # A non-IP string is left untouched.
    assert LagInterfaceManager._canonical_ip("not-an-ip") == "not-an-ip"


def test_configure_add_skips_when_ipv6_form_differs_only() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(
        return_value={
            "lagInterfaces": [{"edge-1": [{"name": "LAG1", "segment": "seg1", "ipv6": "2001:10:1::1/64"}]}]
        }
    )
    # Device reports the same IPv6 in expanded form -> must be treated as no change.
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info([_lag_iface("LAG1", lan="seg1", ipv6=_addr(address="2001:10:1:0::1/64"))])
    )

    result = mgr.configure_lag_interfaces("f.yaml", action="add")

    assert result["changed"] is False
    assert result["skipped_lags"] == [{"device": "edge-1", "lag": "LAG1"}]
    mgr.execute_concurrent_tasks.assert_not_called()


def test_configure_add_skips_when_lag_matches() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(
        return_value={"lagInterfaces": [{"edge-1": [{"name": "LAG1", "segment": "seg1"}]}]}
    )
    # Device LAG already matches the desired defaults (segment, mtu, LACP, DHCP-off).
    mgr.gsdk.get_device_info = MagicMock(return_value=_device_info([_lag_iface("LAG1", lan="seg1")]))

    result = mgr.configure_lag_interfaces("f.yaml", action="add")

    assert result["changed"] is False
    assert result["skipped_lags"] == [{"device": "edge-1", "lag": "LAG1"}]
    assert result["skipped_devices"] == ["edge-1"]
    assert result["created_lags"] == []
    assert result["updated_lags"] == []
    assert result["diff_plan"] == []
    mgr.execute_concurrent_tasks.assert_not_called()


def test_configure_add_pushes_and_records_diff_on_mtu_drift() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(
        return_value={"lagInterfaces": [{"edge-1": [{"name": "LAG1", "segment": "seg1", "mtu": 9000}]}]}
    )
    mgr.gsdk.get_device_info = MagicMock(return_value=_device_info([_lag_iface("LAG1", lan="seg1", mtu=1500)]))

    result = mgr.configure_lag_interfaces("f.yaml", action="add")

    assert result["changed"] is True
    assert result["updated_lags"] == [{"device": "edge-1", "lag": "LAG1"}]
    assert result["configured_devices"] == ["edge-1"]  # device names, not IDs
    assert result["skipped_lags"] == []
    assert len(result["diff_plan"]) == 1
    entry = result["diff_plan"][0]
    assert entry["device"] == "edge-1"
    assert entry["branch"] == "edge"
    assert entry["before"]["LAG1"]["mtu"] == 1500
    assert entry["after"]["LAG1"]["mtu"] == 9000
    mgr.execute_concurrent_tasks.assert_called_once()


def test_configure_add_new_lag_before_is_empty() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(
        return_value={"lagInterfaces": [{"edge-1": [{"name": "LAG1", "segment": "seg1"}]}]}
    )
    # No LAG on the device -> treated as a create; before is empty.
    mgr.gsdk.get_device_info = MagicMock(return_value=_device_info([]))

    result = mgr.configure_lag_interfaces("f.yaml", action="add")

    assert result["changed"] is True
    assert result["created_lags"] == [{"device": "edge-1", "lag": "LAG1"}]
    assert result["diff_plan"][0]["before"]["LAG1"] == {}


def test_configure_add_unreadable_field_biases_to_push() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(
        return_value={"lagInterfaces": [{"edge-1": [{"name": "LAG1", "segment": "seg1"}]}]}
    )
    # LAG present but its segment can't be read back (lan=None) -> must push, not skip.
    mgr.gsdk.get_device_info = MagicMock(return_value=_device_info([_lag_iface("LAG1", lan=None)]))

    result = mgr.configure_lag_interfaces("f.yaml", action="add")

    assert result["changed"] is True
    assert result["skipped_lags"] == []


def test_configure_update_lacp_records_diff() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(
        return_value={"lagInterfaces": [{"edge-1": [{"name": "LAG1", "lacpMode": "PASSIVE", "lacpTimer": "FAST"}]}]}
    )
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info([_lag_iface("LAG1", lan="seg1", mode="ACTIVE", timer="SLOW")])
    )

    result = mgr.configure_lag_interfaces("f.yaml", action="update_lacp_configs")

    entry = result["diff_plan"][0]
    assert entry["before"]["LAG1"]["lacp"] == {"mode": "ACTIVE", "timer": "SLOW"}
    assert entry["after"]["LAG1"]["lacp"] == {"mode": "PASSIVE", "timer": "FAST"}


def test_configure_add_skips_when_live_has_extra_members() -> None:
    # Config lists member Gi0/0 (id 10); the live LAG already has 10 *and* an extra
    # member 11 the config omits. A merge PUT only adds, so desired ⊆ live means no
    # drift -- the LAG must be skipped, not pushed on every run.
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(
        return_value={"lagInterfaces": [{"edge-1": [{"name": "LAG1", "segment": "seg1", "lagMembers": ["Gi0/0"]}]}]}
    )
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info(
            [SimpleNamespace(name="Gi0/0", id=10), _lag_iface("LAG1", lan="seg1", members=[10, 11])]
        )
    )

    result = mgr.configure_lag_interfaces("f.yaml", action="add")

    assert result["changed"] is False
    assert result["skipped_lags"] == [{"device": "edge-1", "lag": "LAG1"}]
    mgr.execute_concurrent_tasks.assert_not_called()


def test_configure_add_pushes_when_desired_member_missing_from_live() -> None:
    # Desired member (id 11) is not among the live members -> a real add -> push.
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(
        return_value={"lagInterfaces": [{"edge-1": [{"name": "LAG1", "segment": "seg1", "lagMembers": ["Gi0/1"]}]}]}
    )
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info([SimpleNamespace(name="Gi0/1", id=11), _lag_iface("LAG1", lan="seg1", members=[10])])
    )

    result = mgr.configure_lag_interfaces("f.yaml", action="add")

    assert result["changed"] is True
    assert result["updated_lags"] == [{"device": "edge-1", "lag": "LAG1"}]


def test_configure_add_omitted_segment_is_idempotent() -> None:
    # Config omits segment; the live LAG carries a real segment. The builder renders
    # an omitted segment as "" (a merge PUT that never asserts a value), so segment
    # must not be compared -- otherwise the LAG reports changed on every run.
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(return_value={"lagInterfaces": [{"edge-1": [{"name": "LAG1"}]}]})
    mgr.gsdk.get_device_info = MagicMock(return_value=_device_info([_lag_iface("LAG1", lan="seg1")]))

    result = mgr.configure_lag_interfaces("f.yaml", action="add")

    assert result["changed"] is False
    assert result["skipped_lags"] == [{"device": "edge-1", "lag": "LAG1"}]
    mgr.execute_concurrent_tasks.assert_not_called()


def test_build_lag_add_omitted_segment_renders_empty_string() -> None:
    # Payload parity with the former Jinja template: an omitted segment is "".
    interface = LagInterfaceManager._build_lag_interface("LAG1", action="add")["lagInterfaces"]["LAG1"]["interface"]
    assert interface["segment"] == ""


def test_build_lag_accepts_sub_interfaces_spelling() -> None:
    # The builder must honor the ``sub_interfaces`` spelling (as the diff does), or a
    # LAG configured with it would report changed yet never push its subinterfaces.
    result = LagInterfaceManager._build_lag_interface(
        "LAG1",
        action="add",
        segment="seg1",
        sub_interfaces=[{"vlan": "101", "segment": "sub-seg"}],
    )
    subs = result["lagInterfaces"]["LAG1"]["interface"]["subinterfaces"]
    assert set(subs) == {"101"}
    assert subs["101"]["interface"]["vlan"] == 101


def test_configure_add_sub_interfaces_spelling_is_idempotent() -> None:
    # A LAG whose live subinterface matches a config using ``sub_interfaces`` must skip.
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(
        return_value={
            "lagInterfaces": [
                {"edge-1": [{"name": "LAG1", "segment": "seg1", "sub_interfaces": [{"vlan": 101, "segment": "s"}]}]}
            ]
        }
    )
    live_sub = SimpleNamespace(vlan=101, enabled=True, lan="s", ipv4=None, ipv6=None, alias=None)
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info([_lag_iface("LAG1", lan="seg1", subinterfaces=[live_sub])])
    )

    result = mgr.configure_lag_interfaces("f.yaml", action="add")

    assert result["changed"] is False
    assert result["skipped_lags"] == [{"device": "edge-1", "lag": "LAG1"}]


def test_configure_add_null_lacp_mode_defaults_consistently() -> None:
    # lacpMode: null must default to ACTIVE in both the builder and the diff, so a LAG
    # already in ACTIVE/SLOW is not reported as drifted.
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(
        return_value={"lagInterfaces": [{"edge-1": [{"name": "LAG1", "segment": "seg1", "lacpMode": None}]}]}
    )
    mgr.gsdk.get_device_info = MagicMock(
        return_value=_device_info([_lag_iface("LAG1", lan="seg1", mode="ACTIVE", timer="SLOW")])
    )

    result = mgr.configure_lag_interfaces("f.yaml", action="add")

    assert result["changed"] is False
    assert result["skipped_lags"] == [{"device": "edge-1", "lag": "LAG1"}]


def test_deconfigure_records_diff_plan() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(return_value={"lagInterfaces": [{"edge-1": [{"name": "LAG1"}]}]})
    mgr.gsdk.get_device_info = MagicMock(return_value=_device_info([]))
    mgr._get_existing_lag_info = MagicMock(
        return_value={"LAG1": {"alias": None, "id": 1, "subinterfaces": {101: {"alias": None}}, "member_ids": set()}}
    )

    result = mgr.deconfigure_lag_interfaces("f.yaml")

    entry = result["diff_plan"][0]
    assert entry["before"]["LAG1"] == {"interface": "present", "subinterfaces": ["101"]}
    assert entry["after"]["LAG1"] == {"interface": None}
