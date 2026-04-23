# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for vpn_mappings (pure functions)."""

from __future__ import annotations

import pytest

from ansible_collections.graphiant.naas.plugins.module_utils.libs import vpn_mappings as vm


@pytest.mark.parametrize(
    "fn,inp,expected",
    [
        (vm.map_ike_encryption, "AES 256 CBC", "aes256"),
        (vm.map_ike_encryption, "unknown-keep", "unknown-keep"),
        (vm.map_ike_integrity, "SHA256", "sha256"),
        (vm.map_ike_dh_group, "Group 20", "ecp384"),
        (vm.map_ipsec_encryption, "AES 128 GCM", "aes128gcm128"),
        (vm.map_ipsec_integrity, "None", "integrity_none"),
        (vm.map_perfect_forward_secrecy, "Group 14", "modp2048"),
    ],
)
def test_map_functions(fn, inp, expected) -> None:
    assert fn(inp) == expected


def test_map_vpn_profile() -> None:
    d = {
        "vpnProfile": {
            "ikeEncryptionAlg": "AES 256 CBC",
            "ikeIntegrity": "SHA256",
            "ikeDhGroup": "Group 20",
            "ipsecEncryptionAlg": "AES 256 GCM",
            "ipsecIntegrity": "SHA512",
            "perfectForwardSecrecy": "Group 19",
        }
    }
    out = vm.map_vpn_profile(d)
    p = out["vpnProfile"]
    assert p["ikeEncryptionAlg"] == "aes256"
    assert p["ikeDhGroup"] == "ecp384"
    assert p["perfectForwardSecrecy"] == "ecp256"


def test_map_vpn_profile_no_vpn_key() -> None:
    d = {"other": 1}
    assert vm.map_vpn_profile(d) == d


def test_map_vpn_profiles() -> None:
    rows = [
        {"vpnProfile": {"ikeEncryptionAlg": "None"}},
        {"vpnProfile": {"ikeEncryptionAlg": "AES 256 CBC"}},
    ]
    out = vm.map_vpn_profiles(rows)
    assert out[0]["vpnProfile"]["ikeEncryptionAlg"] == "encryption_none"
    assert out[1]["vpnProfile"]["ikeEncryptionAlg"] == "aes256"
