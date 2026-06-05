# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for macsec_manager."""

from __future__ import annotations

import pytest

from ansible_collections.graphiant.naas.plugins.module_utils.libs.exceptions import ConfigurationError
from ansible_collections.graphiant.naas.plugins.module_utils.libs.macsec_manager import MacsecManager


def _make_manager() -> MacsecManager:
    from unittest.mock import MagicMock

    config_utils = MagicMock()
    config_utils.gsdk = MagicMock()
    return MacsecManager(config_utils)


def test_deconfigure_not_supported() -> None:
    mgr = _make_manager()
    with pytest.raises(ConfigurationError, match="Deconfigure is not supported"):
        mgr.deconfigure("any.yaml")


def test_normalize_start_time_datetime_string() -> None:
    assert MacsecManager._normalize_start_time_seconds("2029-12-11 11:12:13") == 1891681933


def test_normalize_start_time_iso_datetime_string() -> None:
    assert MacsecManager._normalize_start_time_seconds("2029-12-11T17:12:13Z") == 1891703533


def test_normalize_start_time_unix_seconds() -> None:
    assert MacsecManager._normalize_start_time_seconds(1780452971) == 1780452971
    assert MacsecManager._normalize_start_time_seconds("1780452971") == 1780452971


def test_normalize_start_time_invalid_string_fails() -> None:
    with pytest.raises(ConfigurationError, match="UTC datetime string"):
        MacsecManager._normalize_start_time_seconds("not-a-date")


def test_validate_psk_aes128_cak_length() -> None:
    psk = MacsecManager._validate_psk_entry(
        {
            "nickname": "key1",
            "startTime": 1780452971,
            "cak": "12345123451234512345123451234512",
            "ckn": "23",
            "cipherSuite": "AES_128_CMAC",
        },
        require_secrets=True,
    )
    assert psk["cakCryptographicAlgorithm"] == "AES_128_CMAC"


def test_validate_psk_aes128_cak_wrong_length_fails() -> None:
    with pytest.raises(ConfigurationError, match="cak must be 32"):
        MacsecManager._validate_psk_entry(
            {
                "nickname": "key1",
                "startTime": 1780452971,
                "cak": "abc",
                "ckn": "23",
                "cipherSuite": "AES_128_CMAC",
            },
            require_secrets=True,
        )


def test_build_interface_macsec_put_lag_payload() -> None:
    mgr = _make_manager()
    current_device = {
        "role": "cpe",
        "interfaces": [
            {
                "name": "LAG1",
                "type": "lag",
                "macsec": {},
            }
        ],
    }
    cfg = {
        "interfaces": {
            "LAG1": {
                "enabled": True,
                "encryptionEnforcementMode": "MACSEC_ENFORCEMENT_MODE_MUST_ENCRYPT",
                "keyServerPriority": 200,
                "presharedKeys": [
                    {
                        "nickname": "macsec-key-1",
                        "startTime": "2029-12-11 11:12:13",
                        "cak": "868a0a53ea9b6cd4d516b9c26b587efbc5856326a6996d0655cb1851ee99f4df",
                        "ckn": "853c6a4eb4f21c58a5bfeb9600dd26e8e045ded866b02a45f5f52cebadcd5956",
                        "cipherSuite": "AES_256_CMAC",
                        "useXpnForCipherSuite": True,
                    }
                ],
                "sakConfiguration": {
                    "replayProtectionWindowSize": 64,
                    "rekeyInterval": 3600,
                },
            }
        }
    }
    edge, _after = mgr._build_edge_payload("edge-1-sdktest", cfg, current_device)
    assert "lagInterfaces" in edge
    macsec = edge["lagInterfaces"]["LAG1"]["interface"]["macsec"]["macsec"]
    assert macsec["enabled"] is True
    assert macsec["encryptionEnforcementMode"] == "MACSEC_ENFORCEMENT_MODE_MUST_ENCRYPT"
    assert "pskConfigurationsByNickname" in macsec
    assert macsec["pskConfigurationsByNickname"]["macsec-key-1"]["psk"]["startTime"]["seconds"] == 1891681933
    assert "globalSakConfiguration" in macsec
    sak = macsec["globalSakConfiguration"]["sak"]
    assert sak["nullableRekeyInterval"]["rekeyInterval"] == 3600
    assert sak["nullableReplayProtectionWindowSize"]["replayProtectionWindowSize"] == 64
    MacsecManager._expand_macsec_put_for_sdk(macsec, {}, _after["LAG1"])
    assert macsec["sakConfigurationsByLagMemberInterfaceId"] == {}


def test_build_interface_macsec_put_ethernet_payload() -> None:
    mgr = _make_manager()
    current_device = {
        "role": "cpe",
        "interfaces": [{"name": "GigabitEthernet7/0/0", "type": "ethernet", "macsec": {}}],
    }
    cfg = {
        "interfaces": {
            "GigabitEthernet7/0/0": {
                "enabled": True,
                "encryptionEnforcementMode": "MACSEC_ENFORCEMENT_MODE_MUST_ENCRYPT",
                "keyServerPriority": 255,
                "presharedKeys": [
                    {
                        "nickname": "key1",
                        "startTime": 1780452971,
                        "cak": "12345123451234512345123451234512",
                        "ckn": "23",
                        "cipherSuite": "AES_128_CMAC",
                    }
                ],
                "sakConfiguration": {"replayProtectionWindowSize": 61, "rekeyInterval": 3600},
            }
        }
    }
    edge, _after = mgr._build_edge_payload("edge-1-sdktest", cfg, current_device)
    assert "interfaces" in edge
    assert "GigabitEthernet7/0/0" in edge["interfaces"]


def test_build_edge_payload_skips_when_unchanged() -> None:
    mgr = _make_manager()
    current_device = {
        "role": "cpe",
        "interfaces": [
            {
                "name": "LAG1",
                "type": "lag",
                "macsec": {
                    "enabled": True,
                    "encryptionEnforcementMode": "MACSEC_ENFORCEMENT_MODE_MUST_ENCRYPT",
                    "keyServerPriority": 200,
                    "pskConfigurations": [
                        {
                            "nickname": "macsec-key-1",
                            "startTime": {"seconds": 1891681933},
                            "cak": "868a0a53ea9b6cd4d516b9c26b587efbc5856326a6996d0655cb1851ee99f4df",
                            "ckn": "853c6a4eb4f21c58a5bfeb9600dd26e8e045ded866b02a45f5f52cebadcd5956",
                            "cakCryptographicAlgorithm": "AES_256_CMAC",
                            "useXpnForCipherSuite": True,
                        }
                    ],
                    "sakConfigurations": [{"rekeyInterval": 3600, "replayProtectionWindowSize": 64}],
                },
            }
        ],
    }
    cfg = {
        "interfaces": {
            "LAG1": {
                "enabled": True,
                "encryptionEnforcementMode": "MACSEC_ENFORCEMENT_MODE_MUST_ENCRYPT",
                "keyServerPriority": 200,
            }
        }
    }
    edge, after = mgr._build_edge_payload("edge-1-sdktest", cfg, current_device)
    assert edge == {}
    assert after == {}


def test_build_edge_payload_enable_only_partial() -> None:
    mgr = _make_manager()
    current_device = {
        "role": "cpe",
        "interfaces": [
            {
                "name": "LAG1",
                "type": "lag",
                "macsec": {
                    "enabled": False,
                    "encryptionEnforcementMode": "MACSEC_ENFORCEMENT_MODE_MUST_ENCRYPT",
                    "pskConfigurations": [
                        {
                            "nickname": "macsec-key-1",
                            "startTime": {"seconds": 1891681933},
                            "cak": "868a0a53ea9b6cd4d516b9c26b587efbc5856326a6996d0655cb1851ee99f4df",
                            "ckn": "853c6a4eb4f21c58a5bfeb9600dd26e8e045ded866b02a45f5f52cebadcd5956",
                            "cakCryptographicAlgorithm": "AES_256_CMAC",
                        }
                    ],
                    "sakConfigurations": [{"rekeyInterval": 3600, "replayProtectionWindowSize": 64}],
                },
            }
        ],
    }
    cfg = {"interfaces": {"LAG1": {"enabled": True}}}
    edge, _after = mgr._build_edge_payload("edge-1-sdktest", cfg, current_device)
    macsec = edge["lagInterfaces"]["LAG1"]["interface"]["macsec"]["macsec"]
    assert macsec == {"enabled": True}


def test_build_edge_payload_sak_with_existing_psk_yaml_does_not_repush_psk() -> None:
    """Portal GET omits CAK; YAML listing an existing key must not trigger a PSK PUT."""
    mgr = _make_manager()
    current_device = {
        "role": "cpe",
        "interfaces": [
            {
                "name": "LAG1",
                "type": "lag",
                "macsec": {
                    "enabled": True,
                    "encryptionEnforcementMode": "MACSEC_ENFORCEMENT_MODE_MUST_ENCRYPT",
                    "pskConfigurations": [
                        {
                            "nickname": "macsec-key-1",
                            "startTime": {"seconds": 1843462800},
                            "ckn": "853c6a4eb4f21c58a5bfeb9600dd26e8e045ded866b02a45f5f52cebadcd5956",
                            "cakCryptographicAlgorithm": "AES_256_CMAC",
                            "useXpnForCipherSuite": True,
                        }
                    ],
                    "sakConfigurations": [{"rekeyInterval": 3600, "replayProtectionWindowSize": 64}],
                },
            }
        ],
    }
    cfg = {
        "interfaces": {
            "LAG1": {
                "presharedKeys": [
                    {
                        "nickname": "macsec-key-1",
                        "startTime": "2028-06-01 09:00:00",
                        "ckn": "853c6a4eb4f21c58a5bfeb9600dd26e8e045ded866b02a45f5f52cebadcd5956",
                        "cak": "868a0a53ea9b6cd4d516b9c26b587efbc5856326a6996d0655cb1851ee99f4df",
                        "cipherSuite": "AES_256_CMAC",
                        "useXpnForCipherSuite": True,
                    }
                ],
                "sakConfiguration": {"replayProtectionWindowSize": 65},
            }
        }
    }
    edge, _after = mgr._build_edge_payload("edge-1-sdktest", cfg, current_device)
    macsec = edge["lagInterfaces"]["LAG1"]["interface"]["macsec"]["macsec"]
    assert "pskConfigurationsByNickname" not in macsec
    assert macsec == {
        "globalSakConfiguration": {
            "sak": {"nullableReplayProtectionWindowSize": {"replayProtectionWindowSize": 65}}
        }
    }


def test_build_edge_payload_existing_psk_ckn_change_fails() -> None:
    mgr = _make_manager()
    current_device = {
        "role": "cpe",
        "interfaces": [
            {
                "name": "LAG1",
                "type": "lag",
                "macsec": {
                    "enabled": True,
                    "pskConfigurations": [
                        {
                            "nickname": "macsec-key-1",
                            "startTime": {"seconds": 1843462800},
                            "ckn": "853c6a4eb4f21c58a5bfeb9600dd26e8e045ded866b02a45f5f52cebadcd5956",
                            "cakCryptographicAlgorithm": "AES_256_CMAC",
                        }
                    ],
                },
            }
        ],
    }
    cfg = {
        "interfaces": {
            "LAG1": {
                "presharedKeys": [
                    {
                        "nickname": "macsec-key-1",
                        "startTime": "2028-06-01 09:00:00",
                        "ckn": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
                        "cak": "868a0a53ea9b6cd4d516b9c26b587efbc5856326a6996d0655cb1851ee99f4df",
                        "cipherSuite": "AES_256_CMAC",
                    }
                ],
            }
        }
    }
    with pytest.raises(ConfigurationError, match="cannot be updated in place"):
        mgr._build_edge_payload("edge-1-sdktest", cfg, current_device)


def test_build_edge_payload_sak_update_partial() -> None:
    mgr = _make_manager()
    current_device = {
        "role": "cpe",
        "interfaces": [
            {
                "name": "LAG1",
                "type": "lag",
                "macsec": {
                    "enabled": True,
                    "encryptionEnforcementMode": "MACSEC_ENFORCEMENT_MODE_MUST_ENCRYPT",
                    "pskConfigurations": [
                        {
                            "nickname": "macsec-key-1",
                            "startTime": {"seconds": 1891681933},
                            "cak": "868a0a53ea9b6cd4d516b9c26b587efbc5856326a6996d0655cb1851ee99f4df",
                            "ckn": "853c6a4eb4f21c58a5bfeb9600dd26e8e045ded866b02a45f5f52cebadcd5956",
                            "cakCryptographicAlgorithm": "AES_256_CMAC",
                        }
                    ],
                    "sakConfigurations": [{"rekeyInterval": 3600, "replayProtectionWindowSize": 62}],
                },
            }
        ],
    }
    cfg = {"interfaces": {"LAG1": {"sakConfiguration": {"replayProtectionWindowSize": 64}}}}
    edge, _after = mgr._build_edge_payload("edge-1-sdktest", cfg, current_device)
    macsec = edge["lagInterfaces"]["LAG1"]["interface"]["macsec"]["macsec"]
    assert macsec == {
        "globalSakConfiguration": {
            "sak": {"nullableReplayProtectionWindowSize": {"replayProtectionWindowSize": 64}}
        }
    }


def test_expand_macsec_put_for_sdk_disable_partial() -> None:
    delta = {"enabled": False}
    current = {
        "enabled": True,
        "encryptionEnforcementMode": "MACSEC_ENFORCEMENT_MODE_MUST_ENCRYPT",
        "sakConfiguration": {"rekeyInterval": 3600, "replayProtectionWindowSize": 64},
        "presharedKeys": {"macsec-key-1": {"nickname": "macsec-key-1", "ckn": "ab", "cak": "1" * 64}},
    }
    MacsecManager._expand_macsec_put_for_sdk(delta, current, current)
    assert delta["enabled"] is False
    assert delta["encryptionEnforcementMode"] == "MACSEC_ENFORCEMENT_MODE_MUST_ENCRYPT"
    assert "globalSakConfiguration" in delta
    assert delta["pskConfigurationsByNickname"] == {}
    assert delta["sakConfigurationsByLagMemberInterfaceId"] == {}


def test_expand_macsec_put_for_sdk_key_server_priority_partial() -> None:
    delta = {"keyServerPriority": 201}
    current = {
        "enabled": True,
        "encryptionEnforcementMode": "MACSEC_ENFORCEMENT_MODE_MUST_ENCRYPT",
        "keyServerPriority": 200,
        "sakConfiguration": {"rekeyInterval": 3600, "replayProtectionWindowSize": 64},
    }
    MacsecManager._expand_macsec_put_for_sdk(delta, current, current)
    assert delta["keyServerPriority"] == 201
    assert delta["enabled"] is True
    assert delta["sakConfigurationsByLagMemberInterfaceId"] == {}


def test_build_edge_payload_disable_only() -> None:
    mgr = _make_manager()
    current_device = {
        "role": "cpe",
        "interfaces": [
            {
                "name": "LAG1",
                "type": "lag",
                "macsec": {
                    "enabled": True,
                    "encryptionEnforcementMode": "MACSEC_ENFORCEMENT_MODE_MUST_ENCRYPT",
                    "pskConfigurations": [
                        {
                            "nickname": "macsec-key-1",
                            "startTime": {"seconds": 1891681933},
                            "cak": "868a0a53ea9b6cd4d516b9c26b587efbc5856326a6996d0655cb1851ee99f4df",
                            "ckn": "853c6a4eb4f21c58a5bfeb9600dd26e8e045ded866b02a45f5f52cebadcd5956",
                            "cakCryptographicAlgorithm": "AES_256_CMAC",
                        }
                    ],
                },
            }
        ],
    }
    cfg = {"interfaces": {"LAG1": {"enabled": False}}}
    edge, _after = mgr._build_edge_payload("edge-1-sdktest", cfg, current_device)
    macsec = edge["lagInterfaces"]["LAG1"]["interface"]["macsec"]["macsec"]
    assert macsec == {"enabled": False}


def test_build_edge_payload_psk_delete() -> None:
    mgr = _make_manager()
    current_device = {
        "role": "cpe",
        "interfaces": [
            {
                "name": "GigabitEthernet7/0/0",
                "type": "ethernet",
                "macsec": {
                    "enabled": True,
                    "pskConfigurations": [
                        {
                            "nickname": "key1",
                            "startTime": {"seconds": 1891703533},
                            "cak": "12345123451234512345123451234512",
                            "ckn": "23",
                            "cakCryptographicAlgorithm": "AES_128_CMAC",
                        },
                        {
                            "nickname": "key2",
                            "startTime": {"seconds": 1891725133},
                            "cak": "1234512345123451234512345123451312345123451234512345123451234513",
                            "ckn": "24",
                            "cakCryptographicAlgorithm": "AES_256_CMAC",
                        },
                    ],
                },
            }
        ],
    }
    cfg = {
        "interfaces": {
            "GigabitEthernet7/0/0": {
                "presharedKeys": [{"nickname": "key1", "state": "absent"}],
            }
        }
    }
    edge, _after = mgr._build_edge_payload("edge-1-sdktest", cfg, current_device)
    psk_put = edge["interfaces"]["GigabitEthernet7/0/0"]["interface"]["macsec"]["macsec"][
        "pskConfigurationsByNickname"
    ]
    assert psk_put["key1"] == {"psk": None}


def test_validate_interface_unknown_fails() -> None:
    mgr = _make_manager()
    current = {"interfaces": [{"name": "GigabitEthernet7/0/0", "type": "ethernet"}]}
    with pytest.raises(ConfigurationError, match="does not exist"):
        mgr._validate_interface_entries("edge-1", {"LAG99": {}}, current)


def test_inject_vault_psk_secrets() -> None:
    mgr = _make_manager()
    by_name = {
        "edge-1-sdktest": {
            "interfaces": {
                "LAG1": {
                    "presharedKeys": [
                        {
                            "nickname": "macsec-key-1",
                            "startTime": "2029-12-11 11:12:13",
                            "ckn": "853c6a4eb4f21c58a5bfeb9600dd26e8e045ded866b02a45f5f52cebadcd5956",
                            "cipherSuite": "AES_256_CMAC",
                        }
                    ]
                }
            }
        }
    }
    vault = {
        "edge-1-sdktest": {
            "LAG1": {
                "853c6a4eb4f21c58a5bfeb9600dd26e8e045ded866b02a45f5f52cebadcd5956": (
                    "868a0a53ea9b6cd4d516b9c26b587efbc5856326a6996d0655cb1851ee99f4df"
                ),
            }
        }
    }
    mgr._inject_vault_psk_secrets(by_name, vault)
    psk = by_name["edge-1-sdktest"]["interfaces"]["LAG1"]["presharedKeys"][0]
    assert psk["cak"].startswith("868a0a53")


def test_lookup_vault_cak_by_ckn_case_insensitive() -> None:
    vault = {"AbCd": "12345123451234512345123451234512"}
    assert (
        MacsecManager._lookup_vault_cak_by_ckn(vault, "abcd")
        == "12345123451234512345123451234512"
    )


def test_inject_vault_psk_secrets_skips_explicit_yaml_cak() -> None:
    mgr = _make_manager()
    by_name = {
        "edge-1-sdktest": {
            "interfaces": {
                "LAG1": {
                    "presharedKeys": [
                        {
                            "nickname": "macsec-key-1",
                            "startTime": "2029-12-11 11:12:13",
                            "ckn": "853c6a4eb4f21c58a5bfeb9600dd26e8e045ded866b02a45f5f52cebadcd5956",
                            "cak": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                            "cipherSuite": "AES_256_CMAC",
                        }
                    ]
                }
            }
        }
    }
    vault = {
        "edge-1-sdktest": {
            "LAG1": {
                "853c6a4eb4f21c58a5bfeb9600dd26e8e045ded866b02a45f5f52cebadcd5956": (
                    "868a0a53ea9b6cd4d516b9c26b587efbc5856326a6996d0655cb1851ee99f4df"
                ),
            }
        }
    }
    mgr._inject_vault_psk_secrets(by_name, vault)
    psk = by_name["edge-1-sdktest"]["interfaces"]["LAG1"]["presharedKeys"][0]
    assert psk["cak"].startswith("aaaaaaaa")


def test_validate_psk_secrets_present_missing_device_in_vault() -> None:
    by_name = {
        "edge-2-sdktest2": {
            "interfaces": {
                "LAG1": {
                    "presharedKeys": [
                        {
                            "nickname": "macsec-key-lag1",
                            "ckn": "1a2b3c4d5e6f7890abcdef1234567890abcdef1234567890abcdef1234567890",
                            "cipherSuite": "AES_256_CMAC",
                        }
                    ]
                }
            }
        }
    }
    vault = {
        "edge-1-sdktest": {"LAG1": {"ab": "1" * 64}},
        "edge-2-sdktest": {
            "LAG1": {
                "1a2b3c4d5e6f7890abcdef1234567890abcdef1234567890abcdef1234567890": "2" * 64
            }
        },
    }
    with pytest.raises(ConfigurationError, match="device 'edge-2-sdktest2'") as exc:
        MacsecManager._validate_psk_secrets_present(by_name, vault)
    msg = str(exc.value)
    assert "interface 'LAG1'" in msg
    assert "nickname 'macsec-key-lag1'" in msg
    assert "Known device keys: ['edge-1-sdktest', 'edge-2-sdktest']" in msg


def test_validate_psk_secrets_present_missing_ckn_in_vault() -> None:
    by_name = {
        "edge-1-sdktest": {
            "interfaces": {
                "LAG1": {
                    "presharedKeys": [
                        {
                            "nickname": "macsec-key-1",
                            "ckn": "missing-ckn",
                            "cipherSuite": "AES_256_CMAC",
                        }
                    ]
                }
            }
        }
    }
    vault = {"edge-1-sdktest": {"LAG1": {"other-ckn": "1" * 64}}}
    with pytest.raises(ConfigurationError, match="no CAK for ckn 'missing-ckn'") as exc:
        MacsecManager._validate_psk_secrets_present(by_name, vault)
    msg = str(exc.value)
    assert "device 'edge-1-sdktest'" in msg
    assert "interface 'LAG1'" in msg
    assert "Known ckn keys on that interface: ['other-ckn']" in msg


def test_validate_psk_secrets_present_missing_interface_in_vault() -> None:
    by_name = {
        "edge-1-sdktest": {
            "interfaces": {
                "GigabitEthernet8/0/0": {
                    "presharedKeys": [
                        {
                            "nickname": "key1",
                            "ckn": "31",
                            "cipherSuite": "AES_128_CMAC",
                        }
                    ]
                }
            }
        }
    }
    vault = {"edge-1-sdktest": {"LAG1": {"31": "1" * 32}}}
    with pytest.raises(ConfigurationError, match="interface 'GigabitEthernet8/0/0'") as exc:
        MacsecManager._validate_psk_secrets_present(by_name, vault)
    assert "Known interface keys: ['LAG1']" in str(exc.value)


def test_redact_psk_for_diff() -> None:
    redacted = MacsecManager._redact_psk_for_diff(
        {
            "key1": {
                "nickname": "key1",
                "cak": "12345123451234512345123451234512",
                "ckn": "23",
            }
        }
    )
    assert "cak" not in redacted["key1"]
    assert redacted["key1"]["cakConfigured"] is True
