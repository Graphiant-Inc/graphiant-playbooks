# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for NatPolicyManager (no live API)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ansible_collections.graphiant.naas.plugins.module_utils.libs.nat_policy_manager import NatPolicyManager


def _mgr() -> NatPolicyManager:
    return NatPolicyManager(MagicMock())


def _nat_rulesets_payload(rulesets):
    return {"edge": {"natPolicy": {"natRulesets": rulesets}}}


def _device_rulesets_payload(rulesets):
    return {"device": {"edge": {"natPolicy": {"natRulesets": rulesets}}}}


def _ruleset(name="rs1", rules=None, **extra):
    body = {"name": name, **extra}
    if rules is not None:
        body["rules"] = rules
    return {"ruleset": body}


def _rule(seq=10, **extra):
    return {"rule": {"seq": seq, **extra}}


# ---------------------------------------------------------------------------
# _normalize
# ---------------------------------------------------------------------------

def test_normalize_sorts_dict_keys() -> None:
    m = _mgr()
    assert m._normalize({"b": 1, "a": 2}) == {"a": 2, "b": 1}


# ---------------------------------------------------------------------------
# _payload_differs — rulesets (no change expected)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("case", "desired_rulesets", "existing_rulesets"),
    [
        (
            "exact ruleset and rule match",
            {
                "rs1": _ruleset(
                    rules={
                        "10": _rule(
                            type="OneToOne",
                            originalSrcIpPrefix="1.1.1.1/32",
                            translatedSrcIpPrefix="3.3.3.3/32",
                        )
                    }
                )
            },
            {
                "rs1": _ruleset(
                    rules={
                        "10": _rule(
                            type="OneToOne",
                            originalSrcIpPrefix="1.1.1.1/32",
                            translatedSrcIpPrefix="3.3.3.3/32",
                        )
                    }
                )
            },
        ),
        (
            "existing has extra API defaults",
            {
                "rs1": _ruleset(
                    rules={
                        "10": _rule(
                            type="OneToOne",
                            originalSrcIpPrefix="1.1.1.1/32",
                            translatedSrcIpPrefix="3.3.3.3/32",
                        )
                    }
                )
            },
            {
                "rs1": _ruleset(
                    description="",
                    rules={
                        "10": _rule(
                            type="OneToOne",
                            originalSrcIpPrefix="1.1.1.1/32",
                            translatedSrcIpPrefix="3.3.3.3/32",
                            advertisePreNatPrefixes=False,
                        )
                    },
                )
            },
        ),
        (
            "existing omits optional name and originalDstIpPrefix",
            {
                "rs1": _ruleset(
                    rules={
                        "10": _rule(
                            type="PAT",
                            originalSrcIpPrefix="4.4.4.4/32",
                            translatedSrcIpPrefix="6.6.6.6/32",
                        )
                    }
                )
            },
            {
                "rs1": _ruleset(
                    rules={
                        "10": _rule(
                            type="PAT",
                            originalSrcIpPrefix="4.4.4.4/32",
                            translatedSrcIpPrefix="6.6.6.6/32",
                        )
                    }
                )
            },
        ),
        (
            "existing returns rules as list",
            {
                "rs1": _ruleset(
                    rules={
                        "10": _rule(
                            type="OneToOne",
                            originalSrcIpPrefix="1.1.1.1/32",
                            translatedSrcIpPrefix="3.3.3.3/32",
                        )
                    }
                )
            },
            {
                "rs1": {
                    "ruleset": {
                        "name": "rs1",
                        "rules": [
                            {
                                "seq": 10,
                                "type": "OneToOne",
                                "originalSrcIpPrefix": "1.1.1.1/32",
                                "translatedSrcIpPrefix": "3.3.3.3/32",
                            }
                        ],
                    }
                }
            },
        ),
        (
            "existing rulesets keyed by internal ID",
            {
                "rs1": _ruleset(
                    rules={
                        "10": _rule(
                            type="OneToOne",
                            originalSrcIpPrefix="1.1.1.1/32",
                            translatedSrcIpPrefix="3.3.3.3/32",
                        )
                    }
                )
            },
            {
                "3001": _ruleset(
                    rules={
                        "10": _rule(
                            type="OneToOne",
                            originalSrcIpPrefix="1.1.1.1/32",
                            translatedSrcIpPrefix="3.3.3.3/32",
                        )
                    }
                )
            },
        ),
    ],
)
def test_payload_differs_false_for_equivalent_existing_shapes(case, desired_rulesets, existing_rulesets) -> None:
    m = _mgr()
    assert (
        m._payload_differs(
            _nat_rulesets_payload(desired_rulesets),
            _device_rulesets_payload(existing_rulesets),
        )
        is False
    )


# ---------------------------------------------------------------------------
# _payload_differs — rulesets (change expected)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("case", "desired", "device_info"),
    [
        (
            "translated prefix changed",
            _nat_rulesets_payload(
                {
                    "rs1": _ruleset(
                        rules={
                            "10": _rule(
                                type="OneToOne",
                                originalSrcIpPrefix="1.1.1.1/32",
                                translatedSrcIpPrefix="9.9.9.9/32",
                            )
                        }
                    )
                }
            ),
            _device_rulesets_payload(
                {
                    "rs1": _ruleset(
                        rules={
                            "10": _rule(
                                type="OneToOne",
                                originalSrcIpPrefix="1.1.1.1/32",
                                translatedSrcIpPrefix="3.3.3.3/32",
                            )
                        }
                    )
                }
            ),
        ),
        (
            "rule type changed",
            _nat_rulesets_payload(
                {"rs1": _ruleset(rules={"10": _rule(
                    type="PAT", originalSrcIpPrefix="1.1.1.1/32", translatedSrcIpPrefix="3.3.3.3/32",
                )})}
            ),
            _device_rulesets_payload(
                {"rs1": _ruleset(rules={"10": _rule(
                    type="OneToOne", originalSrcIpPrefix="1.1.1.1/32", translatedSrcIpPrefix="3.3.3.3/32",
                )})}
            ),
        ),
        (
            "missing ruleset",
            _nat_rulesets_payload({"rs1": _ruleset(description="x")}),
            _device_rulesets_payload({}),
        ),
        (
            "deconfigure when ruleset still present",
            _nat_rulesets_payload({"rs1": {"ruleset": None}}),
            _device_rulesets_payload({"rs1": _ruleset()}),
        ),
        (
            "deconfigure when existing ruleset is raw body",
            _nat_rulesets_payload({"rs1": {"ruleset": None}}),
            _device_rulesets_payload({"rs1": {"name": "rs1"}}),
        ),
        (
            "deconfigure when existing rulesets are list",
            _nat_rulesets_payload({"rs1": {"ruleset": None}}),
            _device_rulesets_payload([_ruleset()]),
        ),
    ],
)
def test_payload_differs_true_for_real_ruleset_changes(case, desired, device_info) -> None:
    m = _mgr()
    assert m._payload_differs(desired, device_info) is True


def test_payload_differs_deconfigure_idempotent_when_absent() -> None:
    m = _mgr()
    desired = _nat_rulesets_payload({"rs1": {"ruleset": None}})
    device_info = _device_rulesets_payload({})
    assert m._payload_differs(desired, device_info) is False


# ---------------------------------------------------------------------------
# _rulesets_from_yaml
# ---------------------------------------------------------------------------

def test_rulesets_from_yaml_list_configure() -> None:
    m = _mgr()
    out = m._rulesets_from_yaml([{"name": "rs1", "description": "d"}], operation="configure")
    assert out == {"rs1": {"ruleset": {"name": "rs1", "description": "d"}}}


def test_rulesets_from_yaml_defaults_ruleset_name_from_key() -> None:
    m = _mgr()
    out = m._rulesets_from_yaml(
        {"rs1": {"ruleset": {"description": "d"}}},
        operation="configure",
    )
    assert out == {"rs1": {"ruleset": {"name": "rs1", "description": "d"}}}


def test_rulesets_from_yaml_builds_rule_keys_from_seq() -> None:
    m = _mgr()
    out = m._rulesets_from_yaml(
        {
            "rs1": {
                "ruleset": {
                    "name": "NatPolicyRuleSet1",
                    "rules": [
                        {
                            "seq": 10,
                            "type": "OneToOne",
                            "originalSrcIpPrefix": "1.1.1.1/32",
                            "translatedSrcIpPrefix": "3.3.3.3/32",
                            "advertisePreNatPrefixes": True,
                        },
                        {
                            "seq": 20,
                            "type": "PAT",
                            "originalSrcIpPrefix": "4.4.4.4/32",
                            "translatedSrcIpPrefix": "6.6.6.6/32",
                        },
                    ],
                }
            }
        },
        operation="configure",
    )
    assert out == {
        "rs1": {
            "ruleset": {
                "name": "NatPolicyRuleSet1",
                "rules": {
                    "10": {
                        "rule": {
                            "seq": 10,
                            "type": "OneToOne",
                            "originalSrcIpPrefix": "1.1.1.1/32",
                            "translatedSrcIpPrefix": "3.3.3.3/32",
                            "advertisePreNatPrefixes": True,
                        }
                    },
                    "20": {
                        "rule": {
                            "seq": 20,
                            "type": "PAT",
                            "originalSrcIpPrefix": "4.4.4.4/32",
                            "translatedSrcIpPrefix": "6.6.6.6/32",
                        }
                    },
                },
            }
        }
    }


def test_rulesets_from_yaml_dict_deconfigure() -> None:
    m = _mgr()
    out = m._rulesets_from_yaml({"x": {"ruleset": {"name": "x"}}, "y": {}}, operation="deconfigure")
    assert out == {"x": {"ruleset": None}, "y": {"ruleset": None}}


def test_rulesets_from_yaml_ruleset_state_absent() -> None:
    m = _mgr()
    out = m._rulesets_from_yaml([{"name": "rs1", "state": "absent"}], operation="configure")
    assert out == {"rs1": {"ruleset": None}}


def test_rulesets_from_yaml_rule_state_absent_list() -> None:
    m = _mgr()
    out = m._rulesets_from_yaml(
        [{"name": "rs1", "rules": [{"seq": 10, "state": "absent"}]}],
        operation="configure",
    )
    assert out == {"rs1": {"ruleset": {"name": "rs1", "rules": {"10": {"rule": None}}}}}


def test_rulesets_from_yaml_rule_state_absent_dict() -> None:
    m = _mgr()
    out = m._rulesets_from_yaml(
        {"rs1": {"ruleset": {"name": "rs1", "rules": {"10": {"seq": 10, "state": "absent"}}}}},
        operation="configure",
    )
    assert out == {"rs1": {"ruleset": {"name": "rs1", "rules": {"10": {"rule": None}}}}}


def test_rulesets_from_yaml_rule_delete_strips_state_field() -> None:
    m = _mgr()
    out = m._rulesets_from_yaml(
        [
            {
                "name": "rs1",
                "rules": [
                    {
                        "seq": 10,
                        "type": "OneToOne",
                        "originalSrcIpPrefix": "1.1.1.1/32",
                        "translatedSrcIpPrefix": "3.3.3.3/32",
                        "state": "present",
                    }
                ],
            }
        ],
        operation="configure",
    )
    rule = out["rs1"]["ruleset"]["rules"]["10"]["rule"]
    assert "state" not in rule
    assert rule["type"] == "OneToOne"


# ---------------------------------------------------------------------------
# _payload_differs — rule delete
# ---------------------------------------------------------------------------

def test_payload_differs_true_when_rule_delete_needed() -> None:
    m = _mgr()
    desired = _nat_rulesets_payload(
        {"rs1": _ruleset(name="rs1", rules={"10": {"rule": None}})}
    )
    device_info = _device_rulesets_payload(
        {
            "rs1": _ruleset(
                rules={
                    "10": _rule(
                        type="OneToOne",
                        originalSrcIpPrefix="1.1.1.1/32",
                        translatedSrcIpPrefix="3.3.3.3/32",
                    )
                }
            )
        }
    )
    assert m._payload_differs(desired, device_info) is True


def test_payload_differs_false_when_rule_already_absent() -> None:
    m = _mgr()
    desired = _nat_rulesets_payload({"rs1": _ruleset(name="rs1", rules={"10": {"rule": None}})})
    device_info = _device_rulesets_payload({"rs1": _ruleset(rules={"20": _rule(seq=20, type="PAT")})})
    assert m._payload_differs(desired, device_info) is False


# ---------------------------------------------------------------------------
# _segments_payload_from_yaml
# ---------------------------------------------------------------------------

def test_segments_payload_shorthand() -> None:
    m = _mgr()
    out = m._segments_payload_from_yaml({"lan-1": "NatPolicyRuleSet1"}, operation="attach_to_lan_segments")
    assert out == {"lan-1": {"natRuleset": {"ruleset": "NatPolicyRuleSet1"}}}


def test_segments_payload_api_shape() -> None:
    m = _mgr()
    out = m._segments_payload_from_yaml(
        {"lan-1": {"natRuleset": {"ruleset": "NatPolicyRuleSet1"}}},
        operation="attach_to_lan_segments",
    )
    assert out == {"lan-1": {"natRuleset": {"ruleset": "NatPolicyRuleSet1"}}}


def test_segments_payload_ruleset_key_shorthand() -> None:
    m = _mgr()
    out = m._segments_payload_from_yaml(
        {"lan-1": {"ruleset": "NatPolicyRuleSet1"}},
        operation="attach_to_lan_segments",
    )
    assert out == {"lan-1": {"natRuleset": {"ruleset": "NatPolicyRuleSet1"}}}


def test_segments_payload_detach() -> None:
    m = _mgr()
    out = m._segments_payload_from_yaml({"lan-1": "ignored"}, operation="detach_from_lan_segments")
    assert out == {"lan-1": {"natRuleset": {"ruleset": None}}}


# ---------------------------------------------------------------------------
# _payload_differs — segments
# ---------------------------------------------------------------------------

def test_segment_attach_differs_false_when_ref_matches() -> None:
    m = _mgr()
    desired = {"edge": {"segments": {"lan-1": {"natRuleset": {"ruleset": "NatPolicyRuleSet1"}}}}}
    device_info = {
        "device": {
            "edge": {
                "segments": {
                    "lan-1": {"natRuleset": {"ruleset": "NatPolicyRuleSet1"}},
                }
            }
        }
    }
    assert m._payload_differs(desired, device_info) is False


def test_segment_attach_differs_false_when_api_uses_generated_ruleset_name() -> None:
    m = _mgr()
    desired = {"edge": {"segments": {"lan-1": {"natRuleset": {"ruleset": "NatPolicyRuleSet1"}}}}}
    device_info = {
        "device": {
            "edge": {
                "segments": {
                    "lan-1": {"natRuleset": {"ruleset": "G-30000056289-NatPolicyRuleSet1"}},
                }
            }
        }
    }
    assert m._payload_differs(desired, device_info) is False


def test_segment_attach_differs_true_when_ref_missing() -> None:
    m = _mgr()
    desired = {"edge": {"segments": {"lan-1": {"natRuleset": {"ruleset": "NatPolicyRuleSet1"}}}}}
    device_info = {"device": {"edge": {"segments": {"lan-1": {}}}}}
    assert m._payload_differs(desired, device_info) is True


def test_segment_attach_differs_true_when_segment_not_found() -> None:
    m = _mgr()
    desired = {"edge": {"segments": {"lan-1": {"natRuleset": {"ruleset": "NatPolicyRuleSet1"}}}}}
    device_info = {"device": {"edge": {"segments": {"other-segment": {}}}}}
    assert m._payload_differs(desired, device_info) is True


def test_segment_detach_differs_false_when_already_clear() -> None:
    m = _mgr()
    desired = {"edge": {"segments": {"lan-1": {"natRuleset": {"ruleset": None}}}}}
    device_info = {"device": {"edge": {"segments": {"lan-1": {}}}}}
    assert m._payload_differs(desired, device_info) is False


def test_segment_detach_differs_true_when_existing_ref_is_string() -> None:
    m = _mgr()
    desired = {"edge": {"segments": {"lan-1": {"natRuleset": {"ruleset": None}}}}}
    device_info = {
        "device": {
            "edge": {
                "segments": {
                    "lan-1": {"natRuleset": {"ruleset": "NatPolicyRuleSet1"}},
                }
            }
        }
    }
    assert m._payload_differs(desired, device_info) is True


# ---------------------------------------------------------------------------
# _nat_policy_diff
# ---------------------------------------------------------------------------

def test_nat_policy_diff_rulesets_changed_rule() -> None:
    m = _mgr()
    device_dict = {
        "edge": {
            "natPolicy": {
                "natRulesets": [
                    {
                        "name": "rs1",
                        "rules": [
                            {"seq": 10, "type": "OneToOne",
                             "originalSrcIpPrefix": "1.1.1.1/32", "translatedSrcIpPrefix": "3.3.3.3/32"},
                            {"seq": 20, "type": "PAT",
                             "originalSrcIpPrefix": "4.4.4.4/32", "translatedSrcIpPrefix": "6.6.6.6/32"},
                        ],
                    }
                ]
            }
        }
    }
    payload = _nat_rulesets_payload(
        {
            "rs1": _ruleset(
                rules={
                    "10": _rule(
                        type="OneToOne",
                        originalSrcIpPrefix="1.1.1.1/32",
                        translatedSrcIpPrefix="9.9.9.9/32",  # changed
                    ),
                    "20": _rule(
                        seq=20,
                        type="PAT",
                        originalSrcIpPrefix="4.4.4.4/32",
                        translatedSrcIpPrefix="6.6.6.6/32",  # unchanged
                    ),
                }
            )
        }
    )
    before, after, branch = m._nat_policy_diff(device_dict, payload)
    assert branch == "edge.natPolicy.natRulesets"
    assert "10" in before["natRulesets"]["rs1"]["rules"]
    assert "10" in after["natRulesets"]["rs1"]["rules"]
    assert "20" not in before["natRulesets"]["rs1"].get("rules", {})
    assert before["natRulesets"]["rs1"]["rules"]["10"]["translatedSrcIpPrefix"] == "3.3.3.3/32"
    assert after["natRulesets"]["rs1"]["rules"]["10"]["translatedSrcIpPrefix"] == "9.9.9.9/32"


def test_nat_policy_diff_rulesets_rule_delete() -> None:
    m = _mgr()
    device_dict = {
        "edge": {
            "natPolicy": {
                "natRulesets": [
                    {
                        "name": "rs1",
                        "rules": [
                            {"seq": 10, "type": "OneToOne",
                             "originalSrcIpPrefix": "1.1.1.1/32", "translatedSrcIpPrefix": "3.3.3.3/32"},
                        ],
                    }
                ]
            }
        }
    }
    payload = _nat_rulesets_payload({"rs1": _ruleset(rules={"10": {"rule": None}})})
    before, after, branch = m._nat_policy_diff(device_dict, payload)
    assert branch == "edge.natPolicy.natRulesets"
    assert "10" in before["natRulesets"]["rs1"]["rules"]
    assert after["natRulesets"]["rs1"]["rules"]["10"] is None


def test_nat_policy_diff_segments() -> None:
    m = _mgr()
    device_dict = {
        "edge": {
            "segments": {
                "lan-1": {"natRuleset": {"ruleset": "G-100-rs1"}},
            }
        }
    }
    payload = {"edge": {"segments": {"lan-1": {"natRuleset": {"ruleset": "rs1"}}}}}
    before, after, branch = m._nat_policy_diff(device_dict, payload)
    assert branch == "edge.segments"
    assert before["segments"]["lan-1"]["ruleset"] == "G-100-rs1"
    assert after["segments"]["lan-1"]["ruleset"] == "rs1"
