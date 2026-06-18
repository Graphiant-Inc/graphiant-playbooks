# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for SecurityPolicyManager (no live API)."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from ansible_collections.graphiant.naas.plugins.module_utils.libs.exceptions import ConfigurationError
from ansible_collections.graphiant.naas.plugins.module_utils.libs.security_policy_manager import (
    SecurityPolicyManager,
    _YAML_KEY,
    SECURITY_POLICY_KEYS,
    SECURITY_RULESETS_KEYS,
)


def _mgr() -> SecurityPolicyManager:
    return SecurityPolicyManager(MagicMock())


def test_normalize_ruleset_implicit_rule_action() -> None:
    m = _mgr()
    ruleset = {
        "name": "rs1",
        "implicitRuleAction": "reject",
        "rules": [
            {
                "seq": 1,
                "logging": True,
                "match": {"ipProtocol": "tcp", "destinationNetwork": "0.0.0.0/0"},
                "action": "accept",
            }
        ],
    }
    normalized = m._normalize_ruleset_body(ruleset)
    assert normalized["implicitRuleAction"] == "reject"
    rule_body = normalized["rules"]["1"]["rule"]
    assert rule_body["action"] == "accept"
    assert rule_body["logging"] is True


def test_security_policy_constants() -> None:
    assert SECURITY_POLICY_KEYS[0] == "trafficPolicy"
    assert SECURITY_RULESETS_KEYS[0] == "securityRulesets"
    assert _YAML_KEY == "SecurityPolicyObject"


def test_normalize_match_api_shape() -> None:
    m = _mgr()
    normalized = m._normalize_rule_body(
        {
            "seq": 1,
            "match": {
                "ipProtocol": "tcp",
                "sourceNetwork": "0.0.0.0/0",
                "destinationNetwork": "0.0.0.0/0",
                "sourcePort": 53,
                "destinationPort": 53,
            },
            "action": "accept",
        }
    )
    match = normalized["match"]
    assert match["sourceNetwork"] == {"sourceNetwork": "0.0.0.0/0"}
    assert match["destinationNetwork"] == {"destinationNetwork": "0.0.0.0/0"}
    assert match["sourcePort"] == "53"
    assert match["destinationPort"] == "53"
    assert match["ipProtocol"] == "tcp"
    assert match["protocol"] == {"ipProtocol": "tcp"}


def test_normalize_match_application_builtin_and_custom() -> None:
    m = _mgr()
    builtin_rule = m._normalize_rule_body(
        {
            "seq": 1,
            "match": {"applicationBuiltin": "Office 365"},
            "action": "accept",
        }
    )
    assert builtin_rule["match"]["application"] == {"match": {"builtin": "Office 365"}}

    custom_rule = m._normalize_rule_body(
        {
            "seq": 2,
            "match": {"applicationCustom": "whitehouse.gov"},
            "action": "reject",
        }
    )
    assert custom_rule["match"]["application"] == {"match": {"custom": "whitehouse.gov"}}

    api_shape = m._normalize_rule_body(
        {
            "seq": 3,
            "match": {"application": {"match": {"custom": "whitehouse.gov"}}},
            "action": "reject",
        }
    )
    assert api_shape["match"]["application"] == {"match": {"custom": "whitehouse.gov"}}


def test_normalize_match_application_switch_builtin_to_custom() -> None:
    m = _mgr()
    normalized = m._normalize_rule_body(
        {
            "seq": 1,
            "match": {
                "application": {"match": {"builtin": "WhatsApp"}},
                "applicationCustom": "graphiant_dia_ping",
            },
            "action": "accept",
        }
    )
    assert normalized["match"]["application"] == {"match": {"custom": "graphiant_dia_ping"}}


def test_normalize_match_application_switch_custom_to_builtin() -> None:
    m = _mgr()
    normalized = m._normalize_rule_body(
        {
            "seq": 1,
            "match": {
                "application": {"match": {"custom": "graphiant_dia_ping"}},
                "applicationBuiltin": "Facebook",
            },
            "action": "accept",
        }
    )
    assert normalized["match"]["application"] == {"match": {"builtin": "Facebook"}}


def test_normalize_match_network_only() -> None:
    m = _mgr()
    normalized = m._normalize_rule_body(
        {
            "seq": 150,
            "match": {
                "ipProtocol": "udp",
                "destinationNetwork": "10.1.1.1/32",
            },
            "action": "accept",
        }
    )
    match = normalized["match"]
    assert match["destinationNetwork"] == {"destinationNetwork": "10.1.1.1/32"}
    assert match["ipProtocol"] == "udp"
    assert "application" not in match


def test_normalize_match_application_only() -> None:
    m = _mgr()
    normalized = m._normalize_rule_body(
        {
            "seq": 160,
            "match": {
                "applicationBuiltin": "WhatsApp",
            },
            "action": "accept",
        }
    )
    match = normalized["match"]
    assert match["application"] == {"match": {"builtin": "WhatsApp"}}
    assert "destinationNetwork" not in match
    assert "sourceNetwork" not in match
    assert "ipProtocol" not in match


def test_normalize_match_rejects_application_and_network_together() -> None:
    m = _mgr()
    with pytest.raises(ConfigurationError, match="cannot combine application and network/L4"):
        m._normalize_rule_body(
            {
                "seq": 1,
                "match": {
                    "applicationBuiltin": "WhatsApp",
                    "destinationNetwork": "10.1.1.1/32",
                    "ipProtocol": "tcp",
                },
                "action": "accept",
            }
        )


def test_normalize_match_content_filter_and_domain_list() -> None:
    m = _mgr()
    normalized = m._normalize_rule_body(
        {
            "seq": 10,
            "match": {
                "ipProtocol": "tcp",
                "domainCategoryIds": ["cat-1"],
                "domainWildcards": ["*.example.com"],
            },
            "action": "reject",
        }
    )
    match = normalized["match"]
    assert match["contentFilter"] == {"match": {"domainCategoryIds": ["cat-1"]}}
    assert match["domainList"] == {"match": {"domainWildcards": ["*.example.com"]}}


def test_zones_payload_directional() -> None:
    m = _mgr()
    out = m._zones_payload_from_yaml(
        [{"fromZone": "zone-DIA", "toZone": "zone-lan-1", "ruleset": "My-Ruleset"}],
        operation="attach_to_zone_pairs",
    )
    assert out["zone-DIA"]["zone"]["pairs"]["zone-lan-1"]["pair"]["ruleset"] == "My-Ruleset"
    assert "zone-lan-1" not in out


def test_zones_detach_payload_clears_pair() -> None:
    m = _mgr()
    out = m._zones_payload_from_yaml(
        [{"fromZone": "zone-DIA", "toZone": "zone-lan-1-test"}],
        operation="detach_from_zone_pairs",
    )
    assert out["zone-DIA"]["zone"]["pairs"]["zone-lan-1-test"] == {}


def test_zone_pairs_detach_idempotent_when_cleared() -> None:
    m = _mgr()
    desired_zones = m._zones_payload_from_yaml(
        [{"fromZone": "zone-DIA", "toZone": "zone-lan-1-test"}],
        operation="detach_from_zone_pairs",
    )
    device = {
        "device": {
            "trafficPolicy": {
                "zonePairs": [
                    {
                        "inside": "zone-DIA",
                        "outside": "zone-lan-1-test",
                        "tcpProtection": False,
                    }
                ]
            }
        }
    }
    assert m._zone_attachments_need_update(desired_zones, device) is False


def test_zone_pairs_from_device_get_shape() -> None:
    m = _mgr()
    device = {
        "device": {
            "trafficPolicy": {
                "zonePairs": [
                    {
                        "inside": "zone-DIA",
                        "outside": "zone-lan-1-test",
                        "ruleset": "G-30000056600-Edge-1-Security-Policy-DIA-LAN-1-TEST",
                        "tcpProtection": False,
                    }
                ]
            }
        }
    }
    pairs = m._extract_zone_pairs_from_device(device)
    assert m._zone_pair_matches(
        pairs,
        "zone-DIA",
        "zone-lan-1-test",
        "Edge-1-Security-Policy-DIA-LAN-1-TEST",
        False,
    )


def test_ruleset_idempotency_network_rule_protocol_get_shape() -> None:
    m = _mgr()
    desired_rs = {
        "Edge-1-Security-Policy-Same-LAN-1": {
            "ruleset": {
                "name": "Edge-1-Security-Policy-Same-LAN-1",
                "description": "Security policy for edge-1 Same LAN",
                "implicitRuleAction": "reject",
                "rules": {
                    "150": {
                        "rule": {
                            "seq": 150,
                            "logging": True,
                            "match": {
                                "ipProtocol": "tcp",
                                "protocol": {"ipProtocol": "tcp"},
                                "destinationNetwork": {"destinationNetwork": "10.2.1.101/32"},
                            },
                            "uplinkPolicerRate": {"rate": 5000},
                            "uplinkBurstRate": {"rate": 10000},
                            "action": "reject",
                        }
                    }
                },
            }
        }
    }
    device = {
        "device": {
            "trafficPolicy": {
                "securityRulesets": [
                    {
                        "name": "G-30000056600-Edge-1-Security-Policy-Same-LAN-1",
                        "description": "Security policy for edge-1 Same LAN",
                        "rules": [
                            {
                                "seq": 150,
                                "logging": True,
                                "match": {
                                    "ipProtocol": "tcp",
                                    "destinationNetwork": {"destinationNetwork": "10.2.1.101/32"},
                                },
                                "uplinkPolicerRate": 5000,
                                "uplinkBurstRate": 10000,
                                "action": "reject",
                            }
                        ],
                    }
                ]
            }
        }
    }
    assert m._security_rulesets_need_update(desired_rs, device) is False


def test_ruleset_idempotency_missing_downlink_when_equal_to_uplink() -> None:
    m = _mgr()
    desired_rs = {
        "Edge-1-Security-Policy-LAN-1-TEST-DIA": {
            "ruleset": {
                "name": "Edge-1-Security-Policy-LAN-1-TEST-DIA",
                "description": "Security policy for edge-1 LAN-1-TEST to DIA",
                "implicitRuleAction": "reject",
                "rules": {
                    "150": {
                        "rule": {
                            "seq": 150,
                            "logging": True,
                            "match": {"application": {"match": {"builtin": "Facebook"}}},
                            "action": "inspect",
                            "uplinkPolicerRate": {"rate": 5000},
                            "uplinkBurstRate": {"rate": 10000},
                            "downlinkPolicerRate": {"rate": 5000},
                            "downlinkBurstRate": {"rate": 10000},
                        }
                    }
                },
            }
        }
    }
    device = {
        "device": {
            "trafficPolicy": {
                "securityRulesets": [
                    {
                        "name": "G-30000056600-Edge-1-Security-Policy-LAN-1-TEST-DIA",
                        "description": "Security policy for edge-1 LAN-1-TEST to DIA",
                        "rules": [
                            {
                                "seq": 150,
                                "logging": True,
                                "match": {"application": {"match": {"builtin": "Facebook"}}},
                                "action": "inspect",
                                "uplinkPolicerRate": 5000,
                                "uplinkBurstRate": 10000,
                            }
                        ],
                    }
                ]
            }
        }
    }
    assert m._security_rulesets_need_update(desired_rs, device) is False


def test_ruleset_idempotency_reject_rule_omits_meter_rates_on_get() -> None:
    m = _mgr()
    desired_rs = {
        "Edge-1-Security-Policy-LAN-1-TEST-DIA": {
            "ruleset": {
                "name": "Edge-1-Security-Policy-LAN-1-TEST-DIA",
                "rules": {
                    "170": {
                        "rule": {
                            "seq": 170,
                            "logging": True,
                            "match": {"application": {"match": {"custom": "graphiant_dia_ping"}}},
                            "action": "reject",
                            "uplinkPolicerRate": {"rate": 5000},
                            "uplinkBurstRate": {"rate": 10000},
                        }
                    }
                },
            }
        }
    }
    device = {
        "device": {
            "trafficPolicy": {
                "securityRulesets": [
                    {
                        "name": "Edge-1-Security-Policy-LAN-1-TEST-DIA",
                        "rules": [
                            {
                                "seq": 170,
                                "logging": True,
                                "match": {"application": {"match": {"custom": "graphiant_dia_ping"}}},
                                "action": "reject",
                            }
                        ],
                    }
                ]
            }
        }
    }
    assert m._security_rulesets_need_update(desired_rs, device) is False


def test_ruleset_idempotency_action_dict_on_get() -> None:
    m = _mgr()
    desired_rs = {
        "Edge-1-Security-Policy-LAN-1-TEST-DIA": {
            "ruleset": {
                "name": "Edge-1-Security-Policy-LAN-1-TEST-DIA",
                "rules": {
                    "150": {
                        "rule": {
                            "seq": 150,
                            "logging": True,
                            "match": {"application": {"match": {"builtin": "Facebook"}}},
                            "action": "inspect",
                        }
                    },
                    "170": {
                        "rule": {
                            "seq": 170,
                            "logging": True,
                            "match": {"application": {"match": {"custom": "graphiant_dia_ping"}}},
                            "action": "reject",
                        }
                    },
                },
            }
        }
    }
    device = {
        "device": {
            "trafficPolicy": {
                "securityRulesets": [
                    {
                        "name": "G-30000056600-Edge-1-Security-Policy-LAN-1-TEST-DIA",
                        "rules": [
                            {
                                "seq": 150,
                                "logging": True,
                                "match": {"application": {"match": {"builtin": "Facebook"}}},
                                "action": {"action": "inspect"},
                            },
                            {
                                "seq": 170,
                                "logging": True,
                                "match": {"application": {"match": {"custom": "graphiant_dia_ping"}}},
                                "action": "reject",
                            },
                        ],
                    }
                ]
            }
        }
    }
    assert m._security_rulesets_need_update(desired_rs, device) is False


def test_ruleset_idempotency_drop_equivalent_to_reject_on_get() -> None:
    m = _mgr()
    desired_rs = {
        "rs1": {
            "ruleset": {
                "name": "rs1",
                "rules": {
                    "10": {
                        "rule": {
                            "seq": 10,
                            "logging": True,
                            "match": {"application": {"match": {"custom": "my-app"}}},
                            "action": "drop",
                        }
                    }
                },
            }
        }
    }
    device = {
        "device": {
            "trafficPolicy": {
                "securityRulesets": [
                    {
                        "name": "rs1",
                        "rules": [
                            {
                                "seq": 10,
                                "logging": True,
                                "match": {"application": {"match": {"custom": "my-app"}}},
                                "action": "reject",
                            }
                        ],
                    }
                ]
            }
        }
    }
    assert m._security_rulesets_need_update(desired_rs, device) is False


def test_ruleset_idempotency_generated_name_and_meter_rates() -> None:
    m = _mgr()
    desired_rs = {
        "rs1": {
            "ruleset": {
                "name": "rs1",
                "description": "test",
                "implicitRuleAction": "reject",
                "rules": {
                    "150": {
                        "rule": {
                            "seq": 150,
                            "logging": True,
                            "match": {"application": {"match": {"builtin": "WhatsApp"}}},
                            "uplinkPolicerRate": {"rate": 5000},
                            "uplinkBurstRate": {"rate": 10000},
                            "action": "accept",
                        }
                    }
                },
            }
        }
    }
    device = {
        "device": {
            "trafficPolicy": {
                "securityRulesets": [
                    {
                        "name": "G-30000056600-rs1",
                        "description": "test",
                        "rules": [
                            {
                                "seq": 150,
                                "logging": True,
                                "match": {"application": {"match": {"builtin": "WhatsApp"}}},
                                "uplinkPolicerRate": 5000,
                                "uplinkBurstRate": 10000,
                                "action": "accept",
                            }
                        ],
                    }
                ]
            }
        }
    }
    assert m._security_rulesets_need_update(desired_rs, device) is False
