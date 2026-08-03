# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for OSPFv2Manager."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from ansible_collections.graphiant.naas.plugins.module_utils.libs.ospfv2_manager import OSPFv2Manager
from ansible_collections.graphiant.naas.plugins.module_utils.libs.exceptions import ConfigurationError


def _make_manager() -> OSPFv2Manager:
    config_utils = MagicMock()
    config_utils.gsdk = MagicMock()
    return OSPFv2Manager(config_utils)


_VAULT_MD5 = {"edge-1": {"GigabitEthernet3": "vaultsecret"}}

# _build_bfd -- no defaults filled in; only None/non-dict input raises.


_BFD_FULL = {"enabled": True, "minimumInterval": 300, "multiplier": 3}


@pytest.mark.parametrize("bfd_cfg,expected", [
    (_BFD_FULL, _BFD_FULL),
    ({}, {}),
    ({"enabled": False}, {"enabled": False}),  # explicit False written, not dropped
    ({"minimumInterval": 300}, {"minimumInterval": 300}),
])
def test_build_bfd(bfd_cfg, expected) -> None:
    assert OSPFv2Manager._build_bfd(bfd_cfg) == {"bfd": expected}


@pytest.mark.parametrize("bad", ["not_a_dict", None])
def test_build_bfd_invalid_raises(bad) -> None:
    with pytest.raises(ConfigurationError):
        OSPFv2Manager._build_bfd(bad)


# _build_authentication -- YAML non-null 'key' wins; else vault (device -> interface) fills it in
# when both names are given; otherwise 'key' is omitted.


@pytest.mark.parametrize("auth_cfg", [None, {}])
def test_build_authentication_empty_or_none(auth_cfg) -> None:
    assert OSPFv2Manager._build_authentication(auth_cfg) == {"authentication": {}}


def test_build_authentication_with_key_and_key_id() -> None:
    result = OSPFv2Manager._build_authentication({"key": "secret", "keyId": 1})
    assert result == {"authentication": {"key": "secret", "keyId": 1}}


def test_build_authentication_invalid_type_raises() -> None:
    with pytest.raises(ConfigurationError):
        OSPFv2Manager._build_authentication("bad")


@pytest.mark.parametrize("extra,device_name,interface_name,vault,expected_key", [
    ({"key": "yamlkey"}, "edge-1", "GigabitEthernet3", _VAULT_MD5, "yamlkey"),  # yaml wins over vault
    ({"key": None}, "edge-1", "GigabitEthernet3", _VAULT_MD5, "vaultsecret"),  # vault fills null
    ({}, "edge-1", "GigabitEthernet3", _VAULT_MD5, "vaultsecret"),  # vault fills absent key
    ({}, "edge-1", "GigabitEthernet9", _VAULT_MD5, None),  # no vault entry for this interface
    ({}, None, None, _VAULT_MD5, None),  # missing device/interface name skips vault lookup
    ({}, "edge-1", None, _VAULT_MD5, None),
    ({}, "edge-1", "GigabitEthernet3", {}, None),  # empty vault dict
])
def test_build_authentication_vault_precedence(extra, device_name, interface_name, vault, expected_key) -> None:
    result = OSPFv2Manager._build_authentication({"keyId": 1, **extra}, device_name, interface_name, vault)
    expected = {"keyId": 1, **({"key": expected_key} if expected_key is not None else {})}
    assert result == {"authentication": expected}


# _build_interface -- is_new=True always populates type/hello/dead/retransmit/bfd (config value or
# fixed default) plus creation-only legacy flat fields (zero/false). is_new=False is a
# presence-triggered sparse update: only given *Value keys are wrapped.


def test_build_interface_existing_minimal_only_includes_name() -> None:
    result = OSPFv2Manager._build_interface({"interfaceName": "GigabitEthernet3"})
    assert result == {"GigabitEthernet3": {"interface": {"interfaceName": "GigabitEthernet3"}}}


def test_build_interface_existing_full_sparse_update() -> None:
    if_cfg = {
        "interfaceName": "GigabitEthernet3", "type": "point_to_point", "helloInterval": 10, "deadInterval": 40,
        "retransmitInterval": 5000, "authentication": {"key": "secret", "keyId": 1},
        "bfd": {"enabled": True, "minimumInterval": 300},
    }
    result = OSPFv2Manager._build_interface(if_cfg, is_new=False)
    assert result == {"GigabitEthernet3": {"interface": {
        "interfaceName": "GigabitEthernet3",
        "type": "point_to_point",
        "helloIntervalValue": {"helloInterval": 10},
        "deadIntervalValue": {"deadInterval": 40},
        "retransmitIntervalValue": {"retransmitInterval": 5000},
        "authentication": {"authentication": {"key": "secret", "keyId": 1}},
        "bfd": {"bfd": {"enabled": True, "minimumInterval": 300}},
    }}}


@pytest.mark.parametrize("is_new", [False, True])
def test_build_interface_missing_name_raises(is_new) -> None:
    with pytest.raises(ConfigurationError, match="interfaceName"):
        OSPFv2Manager._build_interface({"type": "point_to_point"}, is_new=is_new)


def test_build_interface_non_dict_raises() -> None:
    with pytest.raises(ConfigurationError):
        OSPFv2Manager._build_interface("bad")


def test_build_interface_new_minimal_fills_all_defaults() -> None:
    result = OSPFv2Manager._build_interface({"interfaceName": "GigabitEthernet3"}, is_new=True)
    assert result == {"GigabitEthernet3": {"interface": {
        "type": "point_to_point",
        "helloIntervalValue": {"helloInterval": 10},
        "deadIntervalValue": {"deadInterval": 40},
        "retransmitIntervalValue": {"retransmitInterval": 5000},
        "bfd": {"bfd": {"enabled": False, "minimumInterval": None}},
        "ifIndex": 0, "helloInterval": 0, "deadInterval": 0, "retransmitInterval": 0, "mtuIgnore": False,
    }}}


def test_build_interface_new_config_values_override_defaults_and_threads_vault() -> None:
    if_cfg = {
        "interfaceName": "GigabitEthernet3", "type": "broadcast", "helloInterval": 5, "deadInterval": 20,
        "retransmitInterval": 999, "bfd": {"enabled": True, "minimumInterval": 300},
        "authentication": {"keyId": 1},
    }
    result = OSPFv2Manager._build_interface(if_cfg, True, "edge-1", _VAULT_MD5)
    obj = result["GigabitEthernet3"]["interface"]
    assert obj["type"] == "broadcast"
    assert obj["helloIntervalValue"] == {"helloInterval": 5}
    assert obj["deadIntervalValue"] == {"deadInterval": 20}
    assert obj["retransmitIntervalValue"] == {"retransmitInterval": 999}
    assert obj["bfd"] == {"bfd": {"enabled": True, "minimumInterval": 300}}
    assert obj["authentication"] == {"authentication": {"keyId": 1, "key": "vaultsecret"}}
    # Legacy flat fields are always zero/false on a new interface, regardless of config.
    assert (obj["ifIndex"], obj["helloInterval"], obj["deadInterval"], obj["retransmitInterval"], obj["mtuIgnore"]) \
        == (0, 0, 0, 0, False)


# _build_area -- keyed by 'name'. 'existing_areas' (dict-keyed-by-name) decides new vs. existing,
# both for the area itself and per-interface: a new area requires areaId, defaults type to
# 'normal', forces interfaces to {} when omitted, and treats every interface as brand-new; an
# existing area is a sparse update, with per-interface newness based on its existing interfaces.


def test_build_area_new_requires_area_id() -> None:
    with pytest.raises(ConfigurationError, match="requires 'areaId'"):
        OSPFv2Manager._build_area({"name": "NewArea"}, {})


def test_build_area_new_defaults_type_to_normal_and_explicit_type_overrides() -> None:
    area_key, area_obj = OSPFv2Manager._build_area({"name": "NewArea", "areaId": "5"}, {})
    assert area_key == "NewArea"
    assert area_obj == {"area": {"areaId": "0.0.0.5", "type": "normal", "interfaces": {}}}
    _key, stub_obj = OSPFv2Manager._build_area({"name": "NewArea", "areaId": "5", "type": "stub"}, {})
    assert stub_obj["area"]["type"] == "stub"


def test_build_area_new_interfaces_are_all_new_and_thread_vault() -> None:
    area_cfg = {
        "name": "NewArea", "areaId": "5",
        "interfaces": [{"interfaceName": "GigabitEthernet3", "authentication": {"keyId": 1}}],
    }
    _key, area_obj = OSPFv2Manager._build_area(area_cfg, {}, "edge-1", _VAULT_MD5)
    obj = area_obj["area"]["interfaces"]["GigabitEthernet3"]["interface"]
    # Full defaults (is_new=True shape) even though only interfaceName+auth were given.
    assert obj["type"] == "point_to_point" and obj["ifIndex"] == 0
    assert obj["helloIntervalValue"] == {"helloInterval": 10}
    assert obj["authentication"] == {"authentication": {"keyId": 1, "key": "vaultsecret"}}


def test_build_area_name_not_in_existing_areas_dict_treated_as_new() -> None:
    existing_areas = {"OtherArea": {"area": {"name": "OtherArea"}}}
    with pytest.raises(ConfigurationError, match="requires 'areaId'"):
        OSPFv2Manager._build_area({"name": "NewArea"}, existing_areas)


_EXISTING_AREAS = {"CoreArea": {"area": {
    "name": "CoreArea", "areaId": "0.0.0.0", "type": "normal",
    "interfaces": {"GigabitEthernet3": {"interface": {"interfaceName": "GigabitEthernet3"}}},
}}}


def test_build_area_existing_optional_fields_and_canonicalized_area_id() -> None:
    area_key, area_obj = OSPFv2Manager._build_area({"name": "CoreArea"}, _EXISTING_AREAS)
    assert (area_key, area_obj) == ("CoreArea", {"area": {}})
    _key, type_obj = OSPFv2Manager._build_area({"name": "CoreArea", "type": "stub"}, _EXISTING_AREAS)
    assert type_obj == {"area": {"type": "stub"}}
    _key, id_obj = OSPFv2Manager._build_area({"name": "CoreArea", "areaId": "0"}, _EXISTING_AREAS)
    assert id_obj["area"]["areaId"] == "0.0.0.0"


def test_build_area_existing_interface_sparse_update_vs_new_interface_full_defaults() -> None:
    # Newness is per-interface, not per-area: an interface already in the area is a sparse
    # update, a brand-new one still gets full is_new defaults.
    area_cfg = {"name": "CoreArea", "interfaces": [
        {"interfaceName": "GigabitEthernet3", "helloInterval": 99},
        {"interfaceName": "GigabitEthernet9"},
    ]}
    _key, area_obj = OSPFv2Manager._build_area(area_cfg, _EXISTING_AREAS)
    interfaces = area_obj["area"]["interfaces"]
    assert interfaces["GigabitEthernet3"]["interface"] == {
        "helloIntervalValue": {"helloInterval": 99}, "interfaceName": "GigabitEthernet3",
    }
    new_if = interfaces["GigabitEthernet9"]["interface"]
    assert new_if["type"] == "point_to_point" and new_if["ifIndex"] == 0 and new_if["mtuIgnore"] is False


def test_build_area_existing_no_interfaces_given_key_omitted_not_forced_empty() -> None:
    # Unlike the new-area case, an existing area with no 'interfaces' given does NOT get an
    # explicit empty map -- the key is simply absent.
    _key, area_obj = OSPFv2Manager._build_area({"name": "CoreArea"}, _EXISTING_AREAS)
    assert "interfaces" not in area_obj["area"]


def test_build_area_missing_name_raises() -> None:
    with pytest.raises(ConfigurationError, match="'name'"):
        OSPFv2Manager._build_area({"areaId": "0", "interfaces": []}, {})


def test_build_area_interfaces_not_list_raises() -> None:
    with pytest.raises(ConfigurationError, match="interfaces"):
        OSPFv2Manager._build_area({"name": "NewArea", "areaId": "0", "interfaces": "bad"}, {})


def test_build_area_non_dict_raises() -> None:
    with pytest.raises(ConfigurationError):
        OSPFv2Manager._build_area("bad", {})


# _canonicalize_area_id


@pytest.mark.parametrize("area_id,expected", [
    (None, ""), ("0", "0.0.0.0"), ("1", "0.0.0.1"), (0, "0.0.0.0"), (256, "0.0.1.0"),
    ("0.0.0.0", "0.0.0.0"), ("0.0.0.5", "0.0.0.5"), ("bogus", "bogus"),
])
def test_canonicalize_area_id(area_id, expected) -> None:
    assert OSPFv2Manager._canonicalize_area_id(area_id) == expected


# _build_redistribution -- 'existing_redistribution' (dict-keyed-by-protocol) drives is_new per
# protocol: new protocols always get metric/metricType (defaulting to 1 / 'type_2' if not given);
# existing protocols are a sparse update -- only fields actually given in YAML are included.


@pytest.mark.parametrize("empty", [None, []])
def test_build_redistribution_empty_returns_empty_dict(empty) -> None:
    assert OSPFv2Manager._build_redistribution(empty) == {}


def test_build_redistribution_missing_protocol_raises() -> None:
    with pytest.raises(ConfigurationError, match="protocol"):
        OSPFv2Manager._build_redistribution([{"metric": 1}])


def test_build_redistribution_not_list_raises() -> None:
    with pytest.raises(ConfigurationError):
        OSPFv2Manager._build_redistribution({"protocol": "bgp"})


_BGP12 = {"type": "bgp", "metric": 1, "metricType": "type_2"}
_BGP_EXISTING = {"bgp": {"protocol": _BGP12}}
_OTHER_PROTOCOL_EXISTING = {"static": {"protocol": {"type": "static"}}}


_BGP71 = {"type": "bgp", "metric": 7, "metricType": "type_1"}


@pytest.mark.parametrize("entry,existing,expected_protocol_obj", [
    ({"protocol": "bgp", "metric": 1, "metricType": "type_2"}, None, _BGP12),
    ({"protocol": "bgp"}, None, _BGP12),  # new: defaults filled
    ({"protocol": "bgp", "metric": 7, "metricType": "type_1"}, {}, _BGP71),
    ({"protocol": "bgp"}, _OTHER_PROTOCOL_EXISTING, _BGP12),  # absent from existing dict -- still new
    ({"protocol": "bgp", "metric": 5}, _BGP_EXISTING, {"type": "bgp", "metric": 5}),  # sparse: metric only
    ({"protocol": "bgp", "metricType": "type_1"}, _BGP_EXISTING, {"type": "bgp", "metricType": "type_1"}),  # sparse
    ({"protocol": "bgp"}, _BGP_EXISTING, {"type": "bgp"}),  # sparse: nothing given -- only 'type' present
])
def test_build_redistribution_new_vs_existing_protocol(entry, existing, expected_protocol_obj) -> None:
    result = OSPFv2Manager._build_redistribution([entry], existing)
    assert result == {entry["protocol"]: {"protocol": expected_protocol_obj}}


def test_build_redistribution_mixed_new_and_existing_protocols_in_one_call() -> None:
    entries = [{"protocol": "bgp", "metric": 9}, {"protocol": "static"}]
    result = OSPFv2Manager._build_redistribution(entries, _BGP_EXISTING)
    assert result == {
        "bgp": {"protocol": {"type": "bgp", "metric": 9}},
        "static": {"protocol": {"type": "static", "metric": 1, "metricType": "type_2"}},
    }


# _build_configure_payload -- 'existing_ospf' ({'process': {...}} shape) drives: no existing
# process -> 'routerId' required (new OSPF process); 'defaultOriginate'/'adminDistance' require an
# area to exist after this push (existing or added in this same push); each area is built via
# _build_area against the existing areas dict, so is_new behavior flows through automatically.


def test_build_configure_payload_no_existing_process_requires_router_id() -> None:
    with pytest.raises(ConfigurationError, match="requires 'routerId'"):
        OSPFv2Manager._build_configure_payload({})


def test_build_configure_payload_no_existing_process_router_id_only() -> None:
    payload = OSPFv2Manager._build_configure_payload({"routerId": "1.1.1.1"})
    assert payload == {"process": {"manual": "1.1.1.1"}}


def test_build_configure_payload_matches_captured_payload() -> None:
    ospf_cfg = {
        "routerId": "1.1.1.1", "defaultOriginate": "disabled",
        "areas": [{"name": "CoreArea", "areaId": "0", "interfaces": [
            {"interfaceName": "Documentation Edge S2S VPN"}, {"interfaceName": "GigabitEthernet3"},
        ]}],
        "redistribution": [{"protocol": "bgp", "metric": 1, "metricType": "type_2"}],
    }
    process = OSPFv2Manager._build_configure_payload(ospf_cfg)["process"]
    assert process["manual"] == "1.1.1.1"
    assert process["defaultOriginate"] == "disabled"
    assert process["areas"]["CoreArea"]["area"]["areaId"] == "0.0.0.0"
    assert process["redistribution"] == {"bgp": {"protocol": {"type": "bgp", "metric": 1, "metricType": "type_2"}}}


def test_build_configure_payload_existing_process_router_id_optional_but_updatable() -> None:
    existing_ospf = {"process": {"manual": "1.1.1.1", "areas": {}, "redistribution": {}}}
    assert OSPFv2Manager._build_configure_payload({}, existing_ospf) == {"process": {}}
    payload = OSPFv2Manager._build_configure_payload({"routerId": "9.9.9.9"}, existing_ospf)
    assert payload["process"]["manual"] == "9.9.9.9"


def test_build_configure_payload_default_originate_valid_values_stored_as_is() -> None:
    base_cfg = {"routerId": "1.1.1.1", "areas": [{"name": "A", "areaId": "0"}]}
    for value in ("unconditional", "conditional", "disabled"):
        payload = OSPFv2Manager._build_configure_payload({**base_cfg, "defaultOriginate": value})
        assert payload["process"]["defaultOriginate"] == value


@pytest.mark.parametrize("bad_value", ["enabled", True])
def test_build_configure_payload_default_originate_invalid_value_raises(bad_value) -> None:
    existing_ospf = {"process": {"areas": {"A": {"area": {"name": "A"}}}}}
    with pytest.raises(ConfigurationError, match="defaultOriginate"):
        OSPFv2Manager._build_configure_payload({"defaultOriginate": bad_value}, existing_ospf)


@pytest.mark.parametrize("field,value", [("defaultOriginate", "disabled"), ("adminDistance", 110)])
def test_build_configure_payload_area_gated_fields_require_an_area(field, value) -> None:
    with pytest.raises(ConfigurationError, match=f"'{field}' cannot be set"):
        OSPFv2Manager._build_configure_payload({"routerId": "1.1.1.1", field: value})


def test_build_configure_payload_default_originate_allowed_with_area_added_or_existing() -> None:
    added = OSPFv2Manager._build_configure_payload(
        {"routerId": "1.1.1.1", "defaultOriginate": "disabled", "areas": [{"name": "A", "areaId": "0"}]}
    )
    assert added["process"]["defaultOriginate"] == "disabled"
    existing_ospf = {"process": {"areas": {"CoreArea": {"area": {"name": "CoreArea"}}}}}
    existing = OSPFv2Manager._build_configure_payload({"defaultOriginate": "disabled"}, existing_ospf)
    assert existing == {"process": {"defaultOriginate": "disabled"}}


def test_build_configure_payload_admin_distance_omitted_when_absent_and_wrapped_when_area_exists() -> None:
    payload = OSPFv2Manager._build_configure_payload({"routerId": "1.1.1.1"})
    assert "adminDistance" not in payload["process"]
    existing_ospf = {"process": {"areas": {"CoreArea": {"area": {"name": "CoreArea"}}}}}
    payload = OSPFv2Manager._build_configure_payload({"adminDistance": 110}, existing_ospf)
    assert payload["process"]["adminDistance"] == {"adminDistance": 110}


def test_build_configure_payload_areas_empty_list_skipped_bad_type_raises() -> None:
    payload = OSPFv2Manager._build_configure_payload({"routerId": "1.1.1.1", "areas": []})
    assert "areas" not in payload["process"]  # empty list is falsy -- skipped, not validated
    with pytest.raises(ConfigurationError, match="areas"):
        OSPFv2Manager._build_configure_payload({"routerId": "1.1.1.1", "areas": "bad"})
    with pytest.raises(ConfigurationError):
        OSPFv2Manager._build_configure_payload("bad")


def test_build_configure_payload_new_area_missing_area_id_raises() -> None:
    with pytest.raises(ConfigurationError, match="requires 'areaId'"):
        OSPFv2Manager._build_configure_payload({"routerId": "1.1.1.1", "areas": [{"name": "NewArea"}]})


def test_build_configure_payload_adding_area_to_existing_process() -> None:
    existing_ospf = {"process": {"manual": "1.1.1.1", "areas": {"CoreArea": {"area": {"name": "CoreArea"}}}}}
    payload = OSPFv2Manager._build_configure_payload({"areas": [{"name": "SecondArea", "areaId": "2"}]}, existing_ospf)
    assert payload["process"]["areas"]["SecondArea"]["area"]["type"] == "normal"
    assert payload["process"]["areas"]["SecondArea"]["area"]["interfaces"] == {}


def test_build_configure_payload_blank_but_present_existing_process_is_not_new() -> None:
    # A GET response carrying an 'ospfv2Process' key at all (even one meaning "nothing
    # configured", e.g. {'routerId': None}) normalizes to a non-empty 5-key dict -- so
    # is_new_process is False and 'routerId' isn't required (only a device with NO
    # 'ospfv2Process' key is "new").
    existing_ospf = {"process": {
        "manual": None, "defaultOriginate": None, "adminDistance": {}, "areas": {}, "redistribution": {},
    }}
    payload = OSPFv2Manager._build_configure_payload({"areas": [{"name": "A", "areaId": "0"}]}, existing_ospf)
    assert "manual" not in payload["process"]


def test_build_configure_payload_redistribution_threads_existing_state_for_sparse_vs_new() -> None:
    existing_ospf = {"process": {
        "areas": {"CoreArea": {"area": {"name": "CoreArea"}}},
        "redistribution": {"bgp": {"protocol": {"type": "bgp", "metric": 1, "metricType": "type_2"}}},
    }}
    sparse_cfg = {"redistribution": [{"protocol": "bgp", "metric": 9}]}
    sparse = OSPFv2Manager._build_configure_payload(sparse_cfg, existing_ospf)
    assert sparse["process"]["redistribution"] == {"bgp": {"protocol": {"type": "bgp", "metric": 9}}}
    new_protocol = OSPFv2Manager._build_configure_payload({"redistribution": [{"protocol": "static"}]}, existing_ospf)
    assert new_protocol["process"]["redistribution"] == {
        "static": {"protocol": {"type": "static", "metric": 1, "metricType": "type_2"}}
    }


def test_build_configure_payload_threads_vault_md5_through_new_area() -> None:
    ospf_cfg = {"routerId": "1.1.1.1", "areas": [{"name": "CoreArea", "areaId": "0", "interfaces": [
        {"interfaceName": "GigabitEthernet3", "authentication": {"keyId": 1}}
    ]}]}
    payload = OSPFv2Manager._build_configure_payload(ospf_cfg, None, "edge-1", _VAULT_MD5)
    obj = payload["process"]["areas"]["CoreArea"]["area"]["interfaces"]["GigabitEthernet3"]["interface"]
    assert obj["authentication"] == {"authentication": {"keyId": 1, "key": "vaultsecret"}}


# _build_deconfigure_payload -- result is wrapped under 'process' EXCEPT 'routerId: null' when the
# device already has zero areas/redistribution (and this push adds none) returns a bare {} -- the
# only confirmed way to fully clear the router ID. If areas/redistribution still exist, clearing
# is deferred (logged, not raised). 'adminDistance: null' clears via {}.


def test_build_deconfigure_payload_matches_captured_delete_payload() -> None:
    ospf_cfg = {"areas": [{"name": "CoreArea"}], "redistribution": [{"protocol": "bgp"}]}
    payload = OSPFv2Manager._build_deconfigure_payload(ospf_cfg)
    assert payload == {"process": {
        "areas": {"CoreArea": {"area": None}}, "redistribution": {"bgp": {"protocol": None}},
    }}


def test_build_deconfigure_payload_areas_only_and_redistribution_only() -> None:
    areas_only = OSPFv2Manager._build_deconfigure_payload({"areas": [{"name": "CoreArea"}]})
    assert areas_only == {"process": {"areas": {"CoreArea": {"area": None}}}}
    assert "redistribution" not in areas_only["process"]
    redist_only = OSPFv2Manager._build_deconfigure_payload({"redistribution": [{"protocol": "bgp"}]})
    assert redist_only == {"process": {"redistribution": {"bgp": {"protocol": None}}}}
    assert "areas" not in redist_only["process"]


def test_build_deconfigure_payload_requires_a_target() -> None:
    with pytest.raises(ConfigurationError, match="Deconfigure requires"):
        OSPFv2Manager._build_deconfigure_payload({})


@pytest.mark.parametrize("ospf_cfg,match", [({"areas": [{}]}, "'name'"), ({"redistribution": [{}]}, "'protocol'")])
def test_build_deconfigure_payload_missing_required_field_raises(ospf_cfg, match) -> None:
    with pytest.raises(ConfigurationError, match=match):
        OSPFv2Manager._build_deconfigure_payload(ospf_cfg)


def test_build_deconfigure_payload_non_dict_raises() -> None:
    with pytest.raises(ConfigurationError):
        OSPFv2Manager._build_deconfigure_payload("bad")


def test_build_deconfigure_payload_area_removal_ignores_sibling_fields() -> None:
    # Same configure-shaped entry (areaId/type/interfaces, each interface carrying its own
    # bfd/authentication/intervals) reused for deconfigure -- the whole area is still removed
    # entirely, keyed off 'name' alone, exactly as static_routes_manager keys a route removal off
    # 'destinationPrefix' alone regardless of its sibling fields. This is what lets the SAME YAML
    # file used for configure be reused for deconfigure.
    ospf_cfg = {"areas": [{
        "name": "CoreArea", "areaId": "0.0.0.0", "type": "normal",
        "interfaces": [{
            "interfaceName": "GigabitEthernet6/0/0",
            "bfd": {"enabled": True, "minimumInterval": 1000, "multiplier": 3},
            "authentication": {"keyId": 1, "key": "hello"},
        }],
    }]}
    payload = OSPFv2Manager._build_deconfigure_payload(ospf_cfg)
    assert payload == {"process": {"areas": {"CoreArea": {"area": None}}}}


def test_build_deconfigure_payload_area_and_full_removal_and_protocol() -> None:
    # Mirrors a captured payload: two whole areas removed (one bare, one carrying full
    # configure-shaped fields) and one redistribution protocol removed.
    ospf_cfg = {
        "areas": [
            {"name": "secondArea"},
            {"name": "CoreArea", "areaId": "0.0.0.0", "type": "normal", "interfaces": [
                {"interfaceName": "GigabitEthernet6/0/0"}
            ]},
        ],
        "redistribution": [{"protocol": "static"}],
    }
    payload = OSPFv2Manager._build_deconfigure_payload(ospf_cfg)
    assert payload == {"process": {
        "areas": {
            "secondArea": {"area": None},
            "CoreArea": {"area": None},
        },
        "redistribution": {"static": {"protocol": None}},
    }}


def test_build_deconfigure_payload_default_originate_turned_off_alone_is_valid_target() -> None:
    payload = OSPFv2Manager._build_deconfigure_payload({"defaultOriginate": "disabled"})
    assert payload == {"process": {"defaultOriginate": "disabled"}}


def test_build_deconfigure_payload_admin_distance_null_clears_and_absent_key_not_added() -> None:
    cleared = OSPFv2Manager._build_deconfigure_payload({"adminDistance": None, "areas": [{"name": "CoreArea"}]})
    assert cleared["process"]["adminDistance"] == {}
    absent = OSPFv2Manager._build_deconfigure_payload({"areas": [{"name": "CoreArea"}]})
    assert "adminDistance" not in absent["process"]


def test_build_deconfigure_payload_router_id_null_full_clear_when_device_already_clean() -> None:
    assert OSPFv2Manager._build_deconfigure_payload({"routerId": None}, {"process": {}}) == {}
    assert OSPFv2Manager._build_deconfigure_payload({"routerId": None}) == {}


@pytest.mark.parametrize("existing_ospf", [
    {"process": {"areas": {"CoreArea": {"area": {"name": "CoreArea"}}}}},
    {"process": {"redistribution": {"bgp": {"protocol": {"type": "bgp"}}}}},
])
def test_build_deconfigure_payload_router_id_null_deferred_when_areas_or_redistribution_exist(existing_ospf) -> None:
    # Deferred (logged), not raised -- nothing else was targeted, so the process object ends up
    # empty (still wrapped, not the bare {} full-clear form).
    payload = OSPFv2Manager._build_deconfigure_payload({"routerId": None}, existing_ospf)
    assert payload == {"process": {}}


def test_build_deconfigure_payload_router_id_null_deferred_when_this_push_adds_an_area() -> None:
    # Even a currently-clean device won't be clean after this push adds an area -- routerId
    # clearing still defers, and the area removal still builds.
    ospf_cfg = {"routerId": None, "areas": [{"name": "CoreArea"}]}
    payload = OSPFv2Manager._build_deconfigure_payload(ospf_cfg, {"process": {}})
    assert payload == {"process": {"areas": {"CoreArea": {"area": None}}}}


def test_build_deconfigure_area_validation() -> None:
    with pytest.raises(ConfigurationError, match="'name'"):
        OSPFv2Manager._build_deconfigure_area({})
    with pytest.raises(ConfigurationError):
        OSPFv2Manager._build_deconfigure_area("bad")


# _extract_ospf_from_GET_response -- translates GET-shaped 'ospfv2Process' (list-based
# areas/redistributedProtocols, device field names) into the same dict-keyed-by-name shape the
# _build_* helpers produce, dropping device-only fields (id, cost, ifIndex). Unlike _build_area, a
# missing area 'type' here defaults to 'normal'. 'adminDistance' wraps to {'adminDistance': <int>}
# when set, or {} when absent/zero.

_GET_SHAPED_PROCESS = {
    "routerId": "1.1.1.1", "defaultOriginate": "disabled", "adminDistance": 110,
    "areas": [{
        "name": "CoreArea", "areaId": "0", "type": "normal",
        "interfaces": [{
            "interface": "GigabitEthernet3", "type": "point_to_point", "helloIntervalValue": 10,
            "deadIntervalValue": 40, "retransmitIntervalValue": 5000,
            "authentication": {"keyId": 1, "key": "secret"},
            "bfd": {"enabled": True, "minimumInterval": 300, "multiplier": 3},
            "id": 999, "cost": 1, "ifIndex": 5,
        }],
    }],
    "redistributedProtocols": [{"redistType": "bgp", "metric": 1, "metricType": "type_2"}],
}


def test_extract_ospf_from_get_response_full_translation() -> None:
    result = OSPFv2Manager._extract_ospf_from_GET_response(_GET_SHAPED_PROCESS)
    assert result["manual"] == "1.1.1.1"
    assert result["defaultOriginate"] == "disabled"
    assert result["adminDistance"] == {"adminDistance": 110}
    assert result["areas"]["CoreArea"]["area"]["areaId"] == "0.0.0.0"
    assert result["areas"]["CoreArea"]["area"]["type"] == "normal"
    iface = result["areas"]["CoreArea"]["area"]["interfaces"]["GigabitEthernet3"]["interface"]
    assert iface == {
        "interfaceName": "GigabitEthernet3",
        "type": "point_to_point",
        "helloIntervalValue": {"helloInterval": 10},
        "deadIntervalValue": {"deadInterval": 40},
        "retransmitIntervalValue": {"retransmitInterval": 5000},
        "authentication": {"authentication": {"keyId": 1, "key": "secret"}},
        "bfd": {"bfd": {"enabled": True, "minimumInterval": 300, "multiplier": 3}},
    }  # device-only fields (id/cost/ifIndex) have no equivalent and are dropped
    assert result["redistribution"] == {"bgp": {"protocol": {"type": "bgp", "metric": 1, "metricType": "type_2"}}}


@pytest.mark.parametrize("process", [{"adminDistance": 0}, {}])
def test_extract_ospf_from_get_response_admin_distance_zero_or_absent_is_empty_dict(process) -> None:
    assert OSPFv2Manager._extract_ospf_from_GET_response(process)["adminDistance"] == {}


def test_extract_ospf_from_get_response_non_dict_returns_empty_dict() -> None:
    assert OSPFv2Manager._extract_ospf_from_GET_response("bad") == {}


def test_extract_ospf_from_get_response_skips_incomplete_entries() -> None:
    # area missing 'type' defaults to 'normal'; area missing 'name', an interface missing
    # 'interface', and a redistribution entry missing 'redistType' are all skipped, not raised.
    no_type = OSPFv2Manager._extract_ospf_from_GET_response({"areas": [{"name": "A"}]})
    assert no_type["areas"]["A"]["area"]["type"] == "normal"
    assert OSPFv2Manager._extract_ospf_from_GET_response({"areas": [{"areaId": "0"}]})["areas"] == {}
    no_iface = OSPFv2Manager._extract_ospf_from_GET_response({"areas": [{"name": "A", "interfaces": [{"type": "x"}]}]})
    assert no_iface["areas"]["A"]["area"]["interfaces"] == {}
    no_redist = OSPFv2Manager._extract_ospf_from_GET_response({"redistributedProtocols": [{"metric": 1}]})
    assert no_redist["redistribution"] == {}


def test_extract_ospf_from_get_response_empty_input_returns_empty_shape() -> None:
    assert OSPFv2Manager._extract_ospf_from_GET_response({}) == {
        "manual": None, "defaultOriginate": None, "adminDistance": {}, "areas": {}, "redistribution": {},
    }


# _get_existing_ospf_payload -- reads a segment's raw 'ospfv2Process' (GET shape) and routes it
# through _extract_ospf_from_GET_response, wrapped under 'process'.


def test_get_existing_ospf_payload_found_dict_and_list_shaped_segments() -> None:
    dict_shaped = {"segments": {"Karen": {"ospfv2Process": _GET_SHAPED_PROCESS}}}
    result = OSPFv2Manager._get_existing_ospf_payload(dict_shaped, "Karen")
    assert result["process"]["manual"] == "1.1.1.1"
    assert result["process"]["adminDistance"] == {"adminDistance": 110}
    list_shaped = {"segments": [{"name": "Karen", "ospfv2Process": _GET_SHAPED_PROCESS}]}
    assert OSPFv2Manager._get_existing_ospf_payload(list_shaped, "Karen")["process"]["manual"] == "1.1.1.1"


@pytest.mark.parametrize("device_dict", [{"segments": {}}, {"segments": {"Karen": {}}}])
def test_get_existing_ospf_payload_segment_or_ospfv2process_absent_returns_empty_dict(device_dict) -> None:
    assert OSPFv2Manager._get_existing_ospf_payload(device_dict, "Karen") == {}


def test_get_existing_ospf_payload_blank_but_present_ospfv2process_returns_wrapped_process() -> None:
    # An ospfv2Process attribute that IS present but represents "nothing configured" (e.g.
    # {'routerId': None}) is truthy, so it's translated rather than short-circuited to {} like the
    # "no key at all" case above.
    device_dict = {"segments": {"Karen": {"ospfv2Process": {"routerId": None}}}}
    result = OSPFv2Manager._get_existing_ospf_payload(device_dict, "Karen")
    assert result == {"process": {
        "manual": None, "defaultOriginate": None, "adminDistance": {}, "areas": {}, "redistribution": {},
    }}


def test_get_existing_ospf_payload_non_dict_returns_none() -> None:
    assert OSPFv2Manager._get_existing_ospf_payload("bad", "Karen") is None


# _lan_segment_names_from_device / _interface_names_from_device


@pytest.mark.parametrize("device_dict", [
    {"segments": [{"name": "Documentation"}, {"name": "Karen"}]},
    {"segments": {"Documentation": {}, "Karen": {}}},
])
def test_lan_segment_names_from_device(device_dict) -> None:
    assert OSPFv2Manager._lan_segment_names_from_device(device_dict) == frozenset({"Documentation", "Karen"})


def test_lan_segment_names_from_device_none() -> None:
    assert OSPFv2Manager._lan_segment_names_from_device({}) == frozenset()


def test_interface_names_from_device_main_and_sub() -> None:
    device_dict = {"interfaces": [
        {"name": "GigabitEthernet3", "subinterfaces": [{"name": "GigabitEthernet3.100"}, {"vlan": 200}]},
        {"name": "GigabitEthernet4"},
    ]}
    names = OSPFv2Manager._interface_names_from_device(device_dict)
    assert names == frozenset({"GigabitEthernet3", "GigabitEthernet3.100", "GigabitEthernet3.200", "GigabitEthernet4"})


def test_interface_names_from_device_none() -> None:
    assert OSPFv2Manager._interface_names_from_device({}) == frozenset()


# _validate_segment_and_interfaces

_VALID_DEVICE_DICT = {"segments": [{"name": "Documentation"}], "interfaces": [{"name": "GigabitEthernet3"}]}


def test_validate_segment_and_interfaces_passes_when_present() -> None:
    ospf_cfg = {"areas": [{"name": "CoreArea", "interfaces": [{"interfaceName": "GigabitEthernet3"}]}]}
    OSPFv2Manager._validate_segment_and_interfaces("edge-1", "Documentation", ospf_cfg, _VALID_DEVICE_DICT)


def test_validate_segment_and_interfaces_unknown_segment_raises() -> None:
    with pytest.raises(ConfigurationError, match="LAN segment 'Bogus'"):
        OSPFv2Manager._validate_segment_and_interfaces("edge-1", "Bogus", {}, _VALID_DEVICE_DICT)


def test_validate_segment_and_interfaces_unknown_interface_raises() -> None:
    ospf_cfg = {"areas": [{"name": "CoreArea", "interfaces": [{"interfaceName": "Bogus0"}]}]}
    with pytest.raises(ConfigurationError, match="interface 'Bogus0'"):
        OSPFv2Manager._validate_segment_and_interfaces("edge-1", "Documentation", ospf_cfg, _VALID_DEVICE_DICT)


def test_validate_segment_and_interfaces_skips_when_ospf_cfg_not_dict() -> None:
    OSPFv2Manager._validate_segment_and_interfaces("edge-1", "Documentation", [], _VALID_DEVICE_DICT)


# _normalize_ospf -- only keys actually present in 'process' are copied through (no defaulting for
# absent keys, except areas/redistribution None -> {}). 'adminDistance' is included so a diff
# there is detected.


def test_normalize_ospf_copies_only_present_keys_and_full_shape() -> None:
    partial = OSPFv2Manager._normalize_ospf({"process": {"manual": "1.1.1.1", "adminDistance": {"adminDistance": 110}}})
    assert partial == {"manual": "1.1.1.1", "adminDistance": {"adminDistance": 110}}
    process = {
        "manual": "1.1.1.1", "defaultOriginate": "disabled", "adminDistance": {"adminDistance": 110},
        "areas": {"CoreArea": {"area": {"name": "CoreArea"}}}, "redistribution": {},
    }
    full = OSPFv2Manager._normalize_ospf({"process": process})
    assert full == process and full is not process


def test_normalize_ospf_areas_and_redistribution_none_become_empty_dict() -> None:
    result = OSPFv2Manager._normalize_ospf({"process": {"areas": None, "redistribution": None}})
    assert result == {"areas": {}, "redistribution": {}}


def test_normalize_ospf_admin_distance_change_makes_configs_differ() -> None:
    base = {"process": {"manual": "1.1.1.1", "adminDistance": {"adminDistance": 110}}}
    changed = {"process": {"manual": "1.1.1.1", "adminDistance": {"adminDistance": 120}}}
    assert OSPFv2Manager._normalize_ospf(base) != OSPFv2Manager._normalize_ospf(changed)


@pytest.mark.parametrize("ospf", [None, "bad", {}])
def test_normalize_ospf_non_dict_or_missing_process_returns_none(ospf) -> None:
    assert OSPFv2Manager._normalize_ospf(ospf) is None


# _deconfigure_targets_present -- True only if something the desired payload targets for
# removal/turn-off currently exists on the device.

_DTP_AREA_EXISTS = {"process": {"areas": {"CoreArea": {"area": {"name": "CoreArea"}}}}}
_DTP_REDIST_EXISTS = {"process": {"redistribution": {"bgp": {"protocol": {"type": "bgp"}}}}}


@pytest.mark.parametrize("desired,existing,expected", [
    ({"areas": {"CoreArea": {"area": None}}}, _DTP_AREA_EXISTS, True),
    ({"areas": {"GoneArea": {"area": None}}}, _DTP_AREA_EXISTS, False),
    ({"redistribution": {"bgp": {"protocol": None}}}, _DTP_REDIST_EXISTS, True),
    ({"redistribution": {"static": {"protocol": None}}}, _DTP_REDIST_EXISTS, False),
    ({"defaultOriginate": "disabled"}, {"process": {"defaultOriginate": "enabled"}}, True),
    ({"defaultOriginate": "disabled"}, {"process": {"defaultOriginate": "disabled"}}, False),
])
def test_deconfigure_targets_present(desired, existing, expected) -> None:
    assert OSPFv2Manager._deconfigure_targets_present(desired, existing) is expected


# _payload_differs_from_existing -- 'device_dict' is the already-unwrapped GET dict (same shape
# fetch_device_by_name() hands to apply_ospf). _sparse_differs only compares keys actually present
# on the desired side (at any nesting depth); an omitted key never counts as a diff.


def _existing_device_dict(seg_name: str, router_id: str, admin_distance=None) -> dict:
    process = {
        "routerId": router_id, "defaultOriginate": "disabled",
        "areas": [{"name": "CoreArea", "areaId": "0", "type": "normal", "interfaces": []}],
        "redistributedProtocols": [],
    }
    if admin_distance is not None:
        process["adminDistance"] = admin_distance
    return {"segments": {seg_name: {"ospfv2Process": process}}, "interfaces": []}


def _desired_configure_payload(seg_name: str, process: dict) -> dict:
    return {"edge": {"segments": {seg_name: {"ospfv2": {"process": process}}}}}


@pytest.mark.parametrize("area_overrides,expect_diff", [
    ({"areaId": "0.0.0.0", "type": "normal", "interfaces": {}}, False),
    ({"areaId": "0.0.0.0", "interfaces": {}}, False),  # 'type' omitted on desired side -- not a diff
    ({"areaId": "0.0.0.0", "type": "stub", "interfaces": {}}, True),  # explicit mismatch IS a diff
])
def test_payload_differs_from_existing_area_type_comparison(area_overrides, expect_diff) -> None:
    mgr = _make_manager()
    process = {
        "manual": "1.1.1.1", "defaultOriginate": "disabled",
        "areas": {"CoreArea": {"area": {"name": "CoreArea", **area_overrides}}}, "redistribution": {},
    }
    desired_payload = _desired_configure_payload("Documentation", process)
    device_dict = _existing_device_dict("Documentation", "1.1.1.1")
    assert mgr._payload_differs_from_existing(desired_payload, device_dict, operation="configure") is expect_diff


def test_payload_differs_from_existing_router_id_change() -> None:
    mgr = _make_manager()
    desired_payload = _desired_configure_payload("Documentation", {"manual": "9.9.9.9", "areas": {}})
    device_dict = _existing_device_dict("Documentation", "1.1.1.1")
    assert mgr._payload_differs_from_existing(desired_payload, device_dict, operation="configure") is True


@pytest.mark.parametrize("desired_admin_distance,expect_diff", [(200, True), (110, False)])
def test_payload_differs_from_existing_admin_distance(desired_admin_distance, expect_diff) -> None:
    mgr = _make_manager()
    device_dict = _existing_device_dict("Documentation", "1.1.1.1", admin_distance=110)
    process = {
        "manual": "1.1.1.1", "defaultOriginate": "disabled",
        "adminDistance": {"adminDistance": desired_admin_distance},
        "areas": {"CoreArea": {"area": {"name": "CoreArea", "areaId": "0.0.0.0", "type": "normal", "interfaces": {}}}},
        "redistribution": {},
    }
    desired_payload = _desired_configure_payload("Documentation", process)
    assert mgr._payload_differs_from_existing(desired_payload, device_dict, operation="configure") is expect_diff


@pytest.mark.parametrize("area_key,expect_diff", [("CoreArea", True), ("GoneArea", False)])
def test_payload_differs_from_existing_deconfigure(area_key, expect_diff) -> None:
    mgr = _make_manager()
    desired_payload = {"edge": {"segments": {"Karen": {"ospfv2": {"process": {"areas": {area_key: {"area": None}}}}}}}}
    device_dict = _existing_device_dict("Karen", "1.1.1.1")
    assert mgr._payload_differs_from_existing(desired_payload, device_dict, operation="deconfigure") is expect_diff


# apply_ospf / configure / deconfigure -- idempotency, diff_plan, and pre-push LAN
# segment/interface validation. These go through _iter_device_payloads -> fetch_device_by_name,
# which unwraps a top-level {'device': {...}} envelope before _payload_differs_from_existing sees
# it, and also fetches 'existing_ospf' per segment to thread into both configure and deconfigure
# payload building.

_YAML_CFG = {"ospfv2": [{"edge-1-sdktest": {"segments": [{
    "lanSegment": "Documentation",
    "ospfv2": {
        "routerId": "1.1.1.1", "defaultOriginate": "disabled",
        "areas": [{"name": "CoreArea", "areaId": "0", "type": "normal", "interfaces": []}],
    },
}]}}]}


def _device_info_with_ospf(seg_name: str, router_id: str) -> dict:
    return {"device": {"segments": {seg_name: {"ospfv2Process": {
        "routerId": router_id, "defaultOriginate": "disabled",
        "areas": [{"name": "CoreArea", "areaId": "0", "type": "normal", "interfaces": []}],
        "redistributedProtocols": [],
    }}}, "interfaces": []}}


def _mock_device_info(mgr: OSPFv2Manager, device_info: dict) -> None:
    mgr.gsdk.get_device_id.return_value = 42
    info_mock = MagicMock()
    info_mock.to_dict.return_value = device_info
    mgr.gsdk.get_device_info.return_value = info_mock


def test_apply_ospf_skips_when_no_diff() -> None:
    mgr = _make_manager()
    _mock_device_info(mgr, _device_info_with_ospf("Documentation", "1.1.1.1"))
    with patch.object(mgr, "render_config_file", return_value=_YAML_CFG):
        result = mgr.apply_ospf("f.yaml", operation="configure")
    assert result["changed"] is False
    assert "edge-1-sdktest" in result["skipped_devices"]
    mgr.gsdk.put_device_config_raw.assert_not_called()


def test_apply_ospf_sets_diff_plan_when_change_needed() -> None:
    mgr = _make_manager()
    _mock_device_info(mgr, _device_info_with_ospf("Documentation", "9.9.9.9"))
    with patch.object(mgr, "render_config_file", return_value=_YAML_CFG), patch.object(mgr, "execute_concurrent_tasks"):
        result = mgr.apply_ospf("f.yaml", operation="configure")
    entry = result["diff_plan"][0]
    assert entry["device"] == "edge-1-sdktest"
    assert entry["branch"] == "edge.segments"
    assert "segments" in entry["before"] and "segments" in entry["after"]


_NO_PROCESS_DEVICE_INFO = {"device": {"segments": {"Documentation": {}}, "interfaces": []}}


@pytest.mark.parametrize("area_cfg,device_info,match", [
    # No existing OSPF process and the YAML omits 'routerId' -- _build_configure_payload's "new
    # process requires routerId" check surfaces all the way up through apply_ospf.
    ({"name": "CoreArea", "areaId": "0"}, _NO_PROCESS_DEVICE_INFO, "requires 'routerId'"),
    ({"name": "SecondArea"}, _device_info_with_ospf("Documentation", "1.1.1.1"), "requires 'areaId'"),
])
def test_apply_ospf_configure_raises_on_bad_new_process_or_area(area_cfg, device_info, match) -> None:
    mgr = _make_manager()
    cfg = {"ospfv2": [{"edge-1-sdktest": {"segments": [
        {"lanSegment": "Documentation", "ospfv2": {"areas": [area_cfg]}}
    ]}}]}
    _mock_device_info(mgr, device_info)
    with patch.object(mgr, "render_config_file", return_value=cfg):
        with pytest.raises(ConfigurationError, match=match):
            mgr.apply_ospf("f.yaml", operation="configure")


def test_apply_ospf_configure_threads_vault_md5_password_for_new_interface() -> None:
    # Adding a brand-new interface (authentication.key left null in YAML) to an existing area --
    # vault (device -> interfaceName) fills the MD5 key, and the new interface still gets full
    # is_new defaults.
    mgr = _make_manager()
    device_info = _device_info_with_ospf("Documentation", "1.1.1.1")
    device_info["device"]["interfaces"] = [{"name": "GigabitEthernet3"}]
    _mock_device_info(mgr, device_info)
    cfg = {"ospfv2": [{"edge-1-sdktest": {"segments": [{
        "lanSegment": "Documentation",
        "ospfv2": {"areas": [{
            "name": "CoreArea",
            "interfaces": [{"interfaceName": "GigabitEthernet3", "authentication": {"keyId": 1, "key": None}}],
        }]},
    }]}}]}
    vault = {"edge-1-sdktest": {"GigabitEthernet3": "vaultsecret"}}
    with patch.object(mgr, "render_config_file", return_value=cfg), patch.object(mgr, "execute_concurrent_tasks"):
        result = mgr.apply_ospf("f.yaml", operation="configure", vault_ospf_md5_passwords=vault)
    after_iface = result["diff_plan"][0]["after"]["segments"]["Documentation"]["ospfv2"]["process"]["areas"][
        "CoreArea"]["area"]["interfaces"]["GigabitEthernet3"]["interface"]
    assert after_iface["authentication"] == {"authentication": {"keyId": 1, "key": "vaultsecret"}}
    assert after_iface["type"] == "point_to_point" and after_iface["ifIndex"] == 0


def test_apply_ospf_configure_raises_when_segment_or_interface_missing() -> None:
    mgr = _make_manager()
    _mock_device_info(mgr, {"device": {"segments": {}, "interfaces": []}})
    with patch.object(mgr, "render_config_file", return_value=_YAML_CFG):
        with pytest.raises(ConfigurationError, match="LAN segment 'Documentation'"):
            mgr.apply_ospf("f.yaml", operation="configure")

    cfg = {"ospfv2": [{"edge-1-sdktest": {"segments": [{
        "lanSegment": "Documentation",
        "ospfv2": {
            "routerId": "1.1.1.1",
            "areas": [{"name": "CoreArea", "areaId": "0", "interfaces": [{"interfaceName": "GigabitEthernet9"}]}],
        },
    }]}}]}
    mgr2 = _make_manager()
    _mock_device_info(mgr2, {"device": {"segments": {"Documentation": {}}, "interfaces": []}})
    with patch.object(mgr2, "render_config_file", return_value=cfg):
        with pytest.raises(ConfigurationError, match="interface 'GigabitEthernet9'"):
            mgr2.apply_ospf("f.yaml", operation="configure")


def test_apply_ospf_deconfigure_skips_segment_validation() -> None:
    mgr = _make_manager()
    deconfigure_cfg = {"ospfv2": [{"edge-1-sdktest": {"segments": [
        {"lanSegment": "Documentation", "ospfv2": {"areas": [{"name": "CoreArea"}]}}
    ]}}]}
    _mock_device_info(mgr, {"device": {"segments": {}, "interfaces": []}})
    with patch.object(mgr, "render_config_file", return_value=deconfigure_cfg):
        result = mgr.apply_ospf("f.yaml", operation="deconfigure")
    assert result["changed"] is False


def test_apply_ospf_configure_segment_without_ospfv2_block_is_noop() -> None:
    # A segment listed with no 'ospfv2' key at all means "nothing to configure" -- skip, don't raise.
    mgr = _make_manager()
    cfg = {"ospfv2": [{"edge-1-sdktest": {"segments": [{"lanSegment": "Documentation"}]}}]}
    _mock_device_info(mgr, {"device": {"segments": {}, "interfaces": []}})
    with patch.object(mgr, "render_config_file", return_value=cfg):
        result = mgr.apply_ospf("f.yaml", operation="configure")
    assert result["changed"] is False
    assert "edge-1-sdktest" in result["skipped_devices"]


def test_apply_ospf_unsupported_operation_raises() -> None:
    mgr = _make_manager()
    with patch.object(mgr, "render_config_file", return_value=_YAML_CFG):
        with pytest.raises(ConfigurationError, match="Unsupported"):
            mgr.apply_ospf("f.yaml", operation="reset")


def test_configure_and_deconfigure_delegate_to_apply_ospf() -> None:
    mgr = _make_manager()
    with patch.object(mgr, "apply_ospf") as mock_apply:
        mgr.configure("f.yaml")
        mock_apply.assert_called_once_with("f.yaml", operation="configure", vault_ospf_md5_passwords=None)

    vault = {"edge-1": {"GigabitEthernet3": "secret"}}
    with patch.object(mgr, "apply_ospf") as mock_apply:
        mgr.configure("f.yaml", vault_ospf_md5_passwords=vault)
        mock_apply.assert_called_once_with("f.yaml", operation="configure", vault_ospf_md5_passwords=vault)

    with patch.object(mgr, "apply_ospf") as mock_apply:
        mgr.deconfigure("f.yaml")
        mock_apply.assert_called_once_with("f.yaml", operation="deconfigure")
