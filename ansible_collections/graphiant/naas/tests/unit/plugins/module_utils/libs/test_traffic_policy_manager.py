# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for TrafficPolicyManager (no live API)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ansible_collections.graphiant.naas.plugins.module_utils.libs.traffic_policy_manager import TrafficPolicyManager


def _mgr() -> TrafficPolicyManager:
    return TrafficPolicyManager(MagicMock())


def test_normalize_sorts_dict_keys() -> None:
    m = _mgr()
    assert m._normalize({"b": 1, "a": 2}) == {"a": 2, "b": 1}


def _rulesets_payload(rulesets):
    return {"edge": {"trafficPolicy": {"trafficRulesets": rulesets}}}


def _device_rulesets_payload(rulesets, *, snake_case=False):
    traffic_policy_key = "traffic_policy" if snake_case else "trafficPolicy"
    traffic_rulesets_key = "traffic_rulesets" if snake_case else "trafficRulesets"
    return {"device": {"edge": {traffic_policy_key: {traffic_rulesets_key: rulesets}}}}


def _ruleset(name="rs1", rules=None, **extra):
    body = {"name": name, **extra}
    if rules is not None:
        body["rules"] = rules
    return {"ruleset": body}


def _rule(seq=10, match=None, action=None, **extra):
    body = {"seq": seq, **extra}
    if match is not None:
        body["match"] = match
    if action is not None:
        body["action"] = action
    return {"rule": body}


@pytest.mark.parametrize(
    ("case", "desired_rulesets", "existing_rulesets"),
    [
        (
            "exact ruleset match",
            {"rs1": _ruleset(rules={"10": _rule()})},
            {"rs1": _ruleset(rules={"10": _rule()})},
        ),
        (
            "existing has API defaults and omits null backup label",
            {
                "rs1": _ruleset(
                    rules={
                        "10": _rule(
                            action={
                                "primaryCircuitLabel": {"label": "internet_dia_1"},
                                "backupCircuitLabel": {"label": None},
                            }
                        )
                    }
                )
            },
            {
                "rs1": _ruleset(
                    description="",
                    rules={
                        "10": _rule(
                            name="",
                            action={"primaryCircuitLabel": {"label": "internet_dia_1"}},
                            match={},
                        )
                    },
                )
            },
        ),
        (
            "existing omits ruleset name and returns rules as list",
            {"rs1": _ruleset(rules={"10": _rule(action={"logging": True})})},
            {"rs1": {"ruleset": {"rules": [{"seq": 10, "action": {"logging": True}}]}}},
        ),
        (
            "existing rulesets keyed by internal ID",
            {"rs1": _ruleset(rules={"10": _rule(action={"logging": True})})},
            {"3001": _ruleset(rules={"10": _rule(action={"logging": True})})},
        ),
        (
            "existing uses scalar match shorthand",
            {
                "rs1": _ruleset(
                    rules={
                        "10": _rule(
                            match={
                                "application": {"match": {"builtin": "Office 365"}},
                                "destinationNetwork": {"destinationNetwork": "0.0.0.0/0"},
                            },
                            action={"setSlaClass": {"class": "Gold"}},
                        )
                    }
                )
            },
            {
                "rs1": _ruleset(
                    rules={
                        "10": _rule(
                            match={"application": "Office 365", "destinationNetwork": "0.0.0.0/0"},
                            action={"setSlaClass": "Gold"},
                        )
                    }
                )
            },
        ),
        (
            "existing uses SLA class alias",
            {"rs1": _ruleset(rules={"10": _rule(action={"setSlaClass": {"class": "Gold"}})})},
            {"rs1": _ruleset(rules={"10": _rule(action={"slaClass": "Gold"})})},
        ),
        (
            "existing omits logging false",
            {"rs1": _ruleset(rules={"10": _rule(action={"logging": False})})},
            {"rs1": _ruleset(rules={"10": _rule(action={})})},
        ),
        (
            "existing uses DSCP shorthand",
            {
                "rs1": _ruleset(
                    rules={
                        "10": _rule(
                            match={"dscp": {"match": {"codePoint": 1}}},
                            action={"remark": {"val": {"codePoint": 3}}},
                        )
                    }
                )
            },
            {"rs1": _ruleset(rules={"10": _rule(match={"dscpCodePoint": 1}, action={"remarkCodePoint": 3})})},
        ),
        (
            "existing uses unwrapped DSCP match",
            {
                "rs1": _ruleset(
                    rules={
                        "10": _rule(
                            match={"dscp": {"match": {"codePoint": 1}}},
                            action={"remark": {"val": {"codePoint": 3}}},
                        )
                    }
                )
            },
            {
                "rs1": _ruleset(
                    rules={
                        "10": _rule(
                            match={"dscp": {"codePoint": 1}},
                            action={"remark": {"codePoint": 3}},
                        )
                    }
                )
            },
        ),
        (
            "existing uses DSCP value key",
            {
                "rs1": _ruleset(
                    rules={
                        "10": _rule(
                            match={"dscp": {"match": {"codePoint": 1}}},
                            action={"remark": {"val": {"codePoint": 3}}},
                        )
                    }
                )
            },
            {"rs1": _ruleset(rules={"10": _rule(match={"dscp": {"value": 1}}, action={"remark": {"value": 3}})})},
        ),
        (
            "existing omits icmpType zero",
            {
                "rs1": _ruleset(
                    rules={
                        "10": _rule(
                            match={
                                "ipProtocol": "icmp",
                                "icmpType": 0,
                                "destinationNetwork": {"destinationNetwork": "0.0.0.0/0"},
                            }
                        )
                    }
                )
            },
            {
                "rs1": _ruleset(
                    rules={
                        "10": _rule(
                            match={
                                "ipProtocol": "icmp",
                                "protocol": "icmp",
                                "destinationNetwork": "0.0.0.0/0",
                            }
                        )
                    }
                )
            },
        ),
    ],
)
def test_payload_differs_false_for_equivalent_existing_shapes(case, desired_rulesets, existing_rulesets) -> None:
    m = _mgr()
    assert m._payload_differs(_rulesets_payload(desired_rulesets), _device_rulesets_payload(existing_rulesets)) is False


@pytest.mark.parametrize(
    ("case", "desired", "device_info"),
    [
        (
            "logging false differs from existing true",
            _rulesets_payload({"rs1": _ruleset(rules={"10": _rule(action={"logging": False})})}),
            _device_rulesets_payload({"rs1": _ruleset(rules={"10": _rule(action={"logging": True})})}),
        ),
        (
            "desired value changed",
            _rulesets_payload({"rs1": _ruleset(rules={"10": _rule(action={"setSlaClass": {"class": "Gold"}})})}),
            _device_rulesets_payload(
                {"rs1": _ruleset(rules={"10": _rule(action={"setSlaClass": {"class": "Silver"}})})}
            ),
        ),
        (
            "missing ruleset",
            _rulesets_payload({"rs1": _ruleset(description="x")}),
            _device_rulesets_payload({}),
        ),
        (
            "deconfigure when ruleset still present",
            _rulesets_payload({"rs1": {"ruleset": None}}),
            _device_rulesets_payload({"rs1": _ruleset()}),
        ),
        (
            "deconfigure when existing ruleset is raw body",
            _rulesets_payload({"rs1": {"ruleset": None}}),
            _device_rulesets_payload({"rs1": {"name": "rs1"}}),
        ),
        (
            "deconfigure when existing rulesets are snake case",
            _rulesets_payload({"rs1": {"ruleset": None}}),
            _device_rulesets_payload({"rs1": {"name": "rs1"}}, snake_case=True),
        ),
        (
            "deconfigure when existing rulesets are list",
            _rulesets_payload({"rs1": {"ruleset": None}}),
            _device_rulesets_payload([_ruleset()]),
        ),
    ],
)
def test_payload_differs_true_for_real_ruleset_changes(case, desired, device_info) -> None:
    m = _mgr()
    assert m._payload_differs(desired, device_info) is True


def test_payload_differs_deconfigure_idempotent_when_absent() -> None:
    m = _mgr()
    desired = _rulesets_payload({"rs1": {"ruleset": None}})
    device_info = _device_rulesets_payload({})
    assert m._payload_differs(desired, device_info) is False


def test_rulesets_from_yaml_list_configure() -> None:
    m = _mgr()
    out = m._rulesets_from_yaml([{"name": "a", "description": "d"}], operation="configure")
    assert out == {"a": {"ruleset": {"name": "a", "description": "d"}}}


def test_rulesets_from_yaml_defaults_ruleset_name_from_key() -> None:
    m = _mgr()
    out = m._rulesets_from_yaml(
        {"rs1": {"ruleset": {"description": "d", "rules": [{"seq": 2000000000}]}}},
        operation="configure",
    )
    assert out == {
        "rs1": {
            "ruleset": {
                "name": "rs1",
                "description": "d",
                "rules": {"2000000000": {"rule": {"seq": 2000000000}}},
            }
        }
    }


def test_rulesets_from_yaml_builds_rule_keys_from_seq() -> None:
    m = _mgr()
    out = m._rulesets_from_yaml(
        {
            "rs1": {
                "ruleset": {
                    "name": "rs1",
                    "rules": [
                        {
                            "seq": 10,
                            "match": {"ipProtocol": "icmp"},
                            "action": {
                                "primaryCircuitLabel": "internet_dia_1",
                                "backupCircuitLabel": "internet_dia_2",
                            },
                        },
                        {"seq": 2000000000},
                    ],
                }
            }
        },
        operation="configure",
    )
    assert out == {
        "rs1": {
            "ruleset": {
                "name": "rs1",
                "rules": {
                    "10": {
                        "rule": {
                            "seq": 10,
                            "match": {"ipProtocol": "icmp"},
                            "action": {
                                "primaryCircuitLabel": {"label": "internet_dia_1"},
                                "backupCircuitLabel": {"label": "internet_dia_2"},
                            },
                        }
                    },
                    "2000000000": {"rule": {"seq": 2000000000}},
                },
            }
        }
    }


def test_rulesets_from_yaml_defaults_missing_backup_circuit_label_to_null() -> None:
    m = _mgr()
    out = m._rulesets_from_yaml(
        {
            "rs1": {
                "ruleset": {
                    "name": "rs1",
                    "rules": [
                        {
                            "seq": 10,
                            "primaryCircuitLabel": "internet_dia_1",
                        },
                    ],
                }
            }
        },
        operation="configure",
    )
    assert out["rs1"]["ruleset"]["rules"]["10"]["rule"]["action"] == {
        "primaryCircuitLabel": {"label": "internet_dia_1"},
        "backupCircuitLabel": {"label": None},
    }


def test_rulesets_from_yaml_dict_deconfigure() -> None:
    m = _mgr()
    out = m._rulesets_from_yaml({"x": {"ruleset": {"name": "x"}}, "y": {}}, operation="deconfigure")
    assert out == {"x": {"ruleset": None}, "y": {"ruleset": None}}


def test_segments_payload_shorthand_and_api_shape() -> None:
    m = _mgr()
    assert m._segments_payload_from_yaml({"vrf-blue": "rs-a"}, operation="attach_to_lan_segments") == {
        "vrf-blue": {"trafficRuleset": {"ruleset": "rs-a"}}
    }
    assert m._segments_payload_from_yaml(
        {"vrf-blue": {"trafficRuleset": {"ruleset": "rs-b"}}},
        operation="attach_to_lan_segments",
    ) == {"vrf-blue": {"trafficRuleset": {"ruleset": "rs-b"}}}


def test_segments_payload_detach() -> None:
    m = _mgr()
    assert m._segments_payload_from_yaml({"vrf-blue": "ignored"}, operation="detach_from_lan_segments") == {
        "vrf-blue": {"trafficRuleset": {"ruleset": None}}
    }


def test_segment_attach_differs_false_when_ref_matches() -> None:
    m = _mgr()
    desired = {"edge": {"segments": {"vrf-blue": {"trafficRuleset": {"ruleset": "new-ruleset-2"}}}}}
    device_info = {
        "device": {
            "edge": {
                "segments": {
                    "vrf-blue": {"trafficRuleset": {"ruleset": "new-ruleset-2"}},
                }
            }
        }
    }
    assert m._payload_differs(desired, device_info) is False


def test_segment_attach_differs_false_when_api_uses_generated_ruleset_name() -> None:
    m = _mgr()
    desired = {"edge": {"segments": {"vrf-blue": {"trafficRuleset": {"ruleset": "new-ruleset-2"}}}}}
    device_info = {
        "device": {
            "edge": {
                "segments": {
                    "vrf-blue": {"trafficRuleset": {"ruleset": "G-30000056289-new-ruleset-2"}},
                }
            }
        }
    }
    assert m._payload_differs(desired, device_info) is False


def test_segment_attach_differs_false_for_nested_api_ref_shape() -> None:
    m = _mgr()
    desired = {"edge": {"segments": {"vrf-blue": {"trafficRuleset": {"ruleset": "new-ruleset-2"}}}}}
    device_info = {
        "device": {
            "edge": {
                "vrfs": {
                    "123": {
                        "name": "vrf-blue",
                        "policy": {"traffic_ruleset": {"ruleset_name": "G-30000056289-new-ruleset-2"}},
                    }
                }
            }
        }
    }
    assert m._payload_differs(desired, device_info) is False


def test_segment_attach_differs_true_when_ref_missing() -> None:
    m = _mgr()
    desired = {"edge": {"segments": {"vrf-blue": {"trafficRuleset": {"ruleset": "new-ruleset-2"}}}}}
    device_info = {"device": {"edge": {"segments": {"vrf-blue": {}}}}}
    assert m._payload_differs(desired, device_info) is True


def test_segment_detach_differs_false_when_already_clear() -> None:
    m = _mgr()
    desired = {"edge": {"segments": {"vrf-blue": {"trafficRuleset": {"ruleset": None}}}}}
    device_info = {"device": {"edge": {"segments": {"vrf-blue": {}}}}}
    assert m._payload_differs(desired, device_info) is False


def test_segment_detach_differs_false_when_existing_ref_is_null_string() -> None:
    m = _mgr()
    desired = {"edge": {"segments": {"vrf-blue": {"trafficRuleset": {"ruleset": None}}}}}
    device_info = {"device": {"edge": {"segments": {"vrf-blue": {"trafficRuleset": "null"}}}}}
    assert m._payload_differs(desired, device_info) is False


def test_segment_detach_differs_true_when_existing_ref_is_string() -> None:
    m = _mgr()
    desired = {"edge": {"segments": {"vrf-blue": {"trafficRuleset": {"ruleset": None}}}}}
    device_info = {
        "device": {
            "edge": {
                "segments": {
                    "vrf-blue": {"trafficRuleset": "new-ruleset-2"},
                }
            }
        }
    }
    assert m._payload_differs(desired, device_info) is True


def test_segment_update_differs_true_when_segment_lookup_misses() -> None:
    m = _mgr()
    desired = {"edge": {"segments": {"vrf-blue": {"trafficRuleset": {"ruleset": None}}}}}
    device_info = {"device": {"edge": {"segments": {"other-segment": {}}}}}
    assert m._payload_differs(desired, device_info) is True


def test_rules_from_yaml_state_absent_list() -> None:
    m = _mgr()
    out = m._rules_from_yaml([{"seq": 500, "state": "absent"}])
    assert out == {"500": {"rule": None}}


def test_rules_from_yaml_state_absent_dict() -> None:
    m = _mgr()
    out = m._rules_from_yaml({"500": {"seq": 500, "state": "absent"}})
    assert out == {"500": {"rule": None}}


def test_rulesets_from_yaml_ruleset_state_absent_list() -> None:
    m = _mgr()
    out = m._rulesets_from_yaml([{"name": "rs1", "state": "absent"}], operation="configure")
    assert out == {"rs1": {"ruleset": None}}


def test_rulesets_from_yaml_configure_rule_delete_only() -> None:
    m = _mgr()
    out = m._rulesets_from_yaml(
        [{"name": "rs1", "rules": [{"seq": 500, "state": "absent"}]}],
        operation="configure",
    )
    assert out == {"rs1": {"ruleset": {"name": "rs1", "rules": {"500": {"rule": None}}}}}


def test_payload_differs_true_when_rule_delete_needed() -> None:
    m = _mgr()
    desired = _rulesets_payload(
        {
            "rs1": _ruleset(
                name="rs1",
                rules={"500": {"rule": None}},
            )
        }
    )
    device_info = _device_rulesets_payload(
        {
            "rs1": _ruleset(
                rules={
                    "500": _rule(
                        seq=500,
                        match={"application": {"match": {"builtin": "NetFlix"}}},
                    )
                }
            )
        }
    )
    assert m._payload_differs(desired, device_info) is True


def test_payload_differs_false_when_rule_already_absent() -> None:
    m = _mgr()
    desired = _rulesets_payload({"rs1": _ruleset(name="rs1", rules={"500": {"rule": None}})})
    device_info = _device_rulesets_payload({"rs1": _ruleset(rules={"10": _rule()})})
    assert m._payload_differs(desired, device_info) is False


def test_traffic_policy_diff_rulesets() -> None:
    m = _mgr()
    device_dict = {
        "edge": {
            "trafficPolicy": {
                "trafficRulesets": [
                    {
                        "name": "rs1",
                        "rules": [
                            {"seq": 10, "match": {}, "action": {"primaryCircuitLabel": {"label": "dia"}}},
                            {"seq": 20, "match": {}, "action": {"primaryCircuitLabel": {"label": "same"}}},
                        ],
                    }
                ]
            }
        }
    }
    payload = _rulesets_payload(
        {
            "rs1": _ruleset(
                rules={
                    "10": _rule(
                        match={},
                        action={"primaryCircuitLabel": {"label": "internet_dia_1"}},
                    ),
                    "20": _rule(
                        seq=20,
                        match={},
                        action={"primaryCircuitLabel": {"label": "same"}},
                    ),
                }
            )
        }
    )
    before, after, branch = m._traffic_policy_diff(device_dict, payload)
    assert branch == "edge.trafficPolicy.trafficRulesets"
    assert "10" in before["trafficRulesets"]["rs1"]["rules"]
    assert "10" in after["trafficRulesets"]["rs1"]["rules"]
    assert "20" not in before["trafficRulesets"]["rs1"]["rules"]
    assert before["trafficRulesets"]["rs1"]["rules"]["10"]["action"]["primaryCircuitLabel"]["label"] == "dia"
    assert (
        after["trafficRulesets"]["rs1"]["rules"]["10"]["action"]["primaryCircuitLabel"]["label"]
        == "internet_dia_1"
    )


def test_traffic_policy_diff_rulesets_rule_delete() -> None:
    m = _mgr()
    device_dict = {
        "edge": {
            "trafficPolicy": {
                "trafficRulesets": [
                    {
                        "name": "rs1",
                        "rules": [{"seq": 500, "match": {}, "action": {"primaryCircuitLabel": {"label": "dia"}}}],
                    }
                ]
            }
        }
    }
    payload = _rulesets_payload({"rs1": _ruleset(rules={"500": {"rule": None}})})
    before, after, branch = m._traffic_policy_diff(device_dict, payload)
    assert branch == "edge.trafficPolicy.trafficRulesets"
    assert "500" in before["trafficRulesets"]["rs1"]["rules"]
    assert after["trafficRulesets"]["rs1"]["rules"]["500"] is None


def test_traffic_policy_diff_segments() -> None:
    m = _mgr()
    device_dict = {
        "edge": {
            "segments": {
                "lan-1": {"trafficRuleset": {"ruleset": "G-100-rs1"}},
            }
        }
    }
    payload = {"edge": {"segments": {"lan-1": {"trafficRuleset": {"ruleset": "rs1"}}}}}
    before, after, branch = m._traffic_policy_diff(device_dict, payload)
    assert branch == "edge.segments"
    assert before["segments"]["lan-1"]["ruleset"] == "G-100-rs1"
    assert after["segments"]["lan-1"]["ruleset"] == "rs1"
