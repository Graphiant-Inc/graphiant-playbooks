# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for vpn_mappings (pure functions) and SiteToSiteVpnManager vault injection."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from ansible_collections.graphiant.naas.plugins.module_utils.libs import vpn_mappings as vm
from ansible_collections.graphiant.naas.plugins.module_utils.libs.site_to_site_vpn_manager import SiteToSiteVpnManager
from ansible_collections.graphiant.naas.plugins.module_utils.libs.exceptions import ConfigurationError


def _make_s2s_manager() -> SiteToSiteVpnManager:
    with patch.object(SiteToSiteVpnManager, "__init__", return_value=None):
        mgr = SiteToSiteVpnManager()
    mgr.gsdk = MagicMock()
    return mgr


_UNSET = object()


def _vpn(name: str, psk=None, md5=_UNSET) -> dict:
    vpn = {"name": name, "presharedKey": psk}
    if md5 is not _UNSET:
        vpn["routing"] = {"bgp": {"md5Password": md5}}
    return vpn


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


# ---- SiteToSiteVpnManager._inject_vault_secrets ----


def test_s2s_inject_psk_vault_fills_null() -> None:
    """Vault PSK is injected when YAML has null."""
    mgr = _make_s2s_manager()
    vpn = _vpn("my-vpn", psk=None)
    mgr._inject_vault_secrets(vpn, {"my-vpn": "vault-psk"}, {})  # pylint: disable=protected-access
    assert vpn["presharedKey"] == "vault-psk"


def test_s2s_inject_psk_yaml_wins_if_non_null() -> None:
    """YAML presharedKey takes precedence over vault when non-null."""
    mgr = _make_s2s_manager()
    vpn = _vpn("my-vpn", psk="yaml-psk")
    mgr._inject_vault_secrets(vpn, {"my-vpn": "vault-psk"}, {})  # pylint: disable=protected-access
    assert vpn["presharedKey"] == "yaml-psk"


def test_s2s_inject_psk_both_missing_raises() -> None:
    """ConfigurationError when presharedKey is null in YAML and absent from vault."""
    mgr = _make_s2s_manager()
    vpn = _vpn("my-vpn", psk=None)
    with pytest.raises(ConfigurationError, match="presharedKey is required"):
        mgr._inject_vault_secrets(vpn, {}, {})  # pylint: disable=protected-access


def test_s2s_inject_md5_vault_fills_null() -> None:
    """Vault md5Password is injected as ManaV2NullableMd5Password dict when YAML has null."""
    mgr = _make_s2s_manager()
    vpn = _vpn("my-vpn", psk="psk", md5=None)
    mgr._inject_vault_secrets(vpn, {"my-vpn": "psk"}, {"my-vpn": "vault-md5"})  # pylint: disable=protected-access
    assert vpn["routing"]["bgp"]["md5Password"] == {"md5_password": "vault-md5"}


def test_s2s_inject_md5_yaml_wins_if_non_null() -> None:
    """YAML md5Password takes precedence over vault when non-null."""
    mgr = _make_s2s_manager()
    vpn = _vpn("my-vpn", psk="psk", md5={"md5_password": "yaml-md5"})
    mgr._inject_vault_secrets(vpn, {"my-vpn": "psk"}, {"my-vpn": "vault-md5"})  # pylint: disable=protected-access
    assert vpn["routing"]["bgp"]["md5Password"] == {"md5_password": "yaml-md5"}


def test_s2s_inject_md5_both_missing_is_none() -> None:
    """md5Password stays None when absent from both YAML and vault (optional; no error)."""
    mgr = _make_s2s_manager()
    vpn = _vpn("my-vpn", psk="psk", md5=None)
    mgr._inject_vault_secrets(vpn, {"my-vpn": "psk"}, {})  # pylint: disable=protected-access
    assert vpn["routing"]["bgp"]["md5Password"] is None


# ---- SiteToSiteVpnManager._normalize_bgp_md5_password ----


def test_s2s_normalize_md5_plain_string_wraps_to_dict() -> None:
    """Plain string md5Password is wrapped to ManaV2NullableMd5Password dict form."""
    mgr = _make_s2s_manager()
    vpn = _vpn("my-vpn", psk="psk", md5="secret")
    mgr._normalize_bgp_md5_password(vpn)  # pylint: disable=protected-access
    assert vpn["routing"]["bgp"]["md5Password"] == {"md5_password": "secret"}


def test_s2s_normalize_md5_snake_case_dict_unchanged() -> None:
    """Dict with md5_password key (already correct form) passes through unchanged."""
    mgr = _make_s2s_manager()
    vpn = _vpn("my-vpn", psk="psk", md5={"md5_password": "secret"})
    mgr._normalize_bgp_md5_password(vpn)  # pylint: disable=protected-access
    assert vpn["routing"]["bgp"]["md5Password"] == {"md5_password": "secret"}


def test_s2s_normalize_md5_camel_case_dict_normalized() -> None:
    """Dict with camelCase md5Password key is normalized to snake_case md5_password."""
    mgr = _make_s2s_manager()
    vpn = _vpn("my-vpn", psk="psk", md5={"md5Password": "secret"})
    mgr._normalize_bgp_md5_password(vpn)  # pylint: disable=protected-access
    assert vpn["routing"]["bgp"]["md5Password"] == {"md5_password": "secret"}


def test_s2s_normalize_md5_none_unchanged() -> None:
    """None md5Password is left as None (optional field)."""
    mgr = _make_s2s_manager()
    vpn = _vpn("my-vpn", psk="psk", md5=None)
    mgr._normalize_bgp_md5_password(vpn)  # pylint: disable=protected-access
    assert vpn["routing"]["bgp"]["md5Password"] is None
