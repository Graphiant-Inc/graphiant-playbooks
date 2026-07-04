# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for SiteToSiteVpnManager._drop_secrets."""

from __future__ import annotations

from ansible_collections.graphiant.naas.plugins.module_utils.libs.site_to_site_vpn_manager import (
    SiteToSiteVpnManager,
)

_drop_secrets = SiteToSiteVpnManager._drop_secrets


def test_drop_secrets_removes_preshared_key() -> None:
    vpn = {"name": "vpn-1", "presharedKey": "top-secret"}
    result = _drop_secrets(vpn)
    assert "presharedKey" not in result
    assert result["name"] == "vpn-1"


def test_drop_secrets_removes_md5_password() -> None:
    vpn = {"name": "vpn-1", "bgp": {"md5Password": "bgp-secret", "asn": 65001}}
    result = _drop_secrets(vpn)
    assert "md5Password" not in result["bgp"]
    assert result["bgp"]["asn"] == 65001


def test_drop_secrets_removes_both_secrets() -> None:
    vpn = {
        "name": "vpn-1",
        "presharedKey": "psk-secret",
        "bgp": {"md5Password": "bgp-secret", "remoteIp": "10.0.0.1"},
    }
    result = _drop_secrets(vpn)
    assert "presharedKey" not in result
    assert "md5Password" not in result["bgp"]
    assert result["bgp"]["remoteIp"] == "10.0.0.1"


def test_drop_secrets_handles_list() -> None:
    data = [
        {"name": "vpn-1", "presharedKey": "s1"},
        {"name": "vpn-2", "presharedKey": "s2", "md5Password": "m2"},
    ]
    result = _drop_secrets(data)
    assert isinstance(result, list)
    assert "presharedKey" not in result[0]
    assert "presharedKey" not in result[1]
    assert "md5Password" not in result[1]


def test_drop_secrets_handles_none() -> None:
    assert _drop_secrets(None) is None


def test_drop_secrets_handles_scalar() -> None:
    assert _drop_secrets("unchanged") == "unchanged"
    assert _drop_secrets(42) == 42


def test_drop_secrets_nested_list_of_dicts() -> None:
    data = {"vpns": [{"presharedKey": "s", "port": 500}]}
    result = _drop_secrets(data)
    assert "presharedKey" not in result["vpns"][0]
    assert result["vpns"][0]["port"] == 500


def test_drop_secrets_empty_bgp_dict_passes_through() -> None:
    """Static-routing VPNs show bgp: {} in API state; _drop_secrets must not corrupt it."""
    vpn = {"port": 500, "bgp": {}, "static": {"destinationPrefix": ["0.0.0.0/0"]}}
    result = _drop_secrets(vpn)
    assert result["bgp"] == {}
    assert result["static"] == {"destinationPrefix": ["0.0.0.0/0"]}


def test_drop_secrets_empty_static_dict_passes_through() -> None:
    """BGP-routing VPNs show static: {} in API state; _drop_secrets must not corrupt it."""
    vpn = {"port": 500, "bgp": {"peerAsn": 123, "md5Password": "secret"}, "static": {}}
    result = _drop_secrets(vpn)
    assert result["static"] == {}
    assert "md5Password" not in result["bgp"]
    assert result["bgp"]["peerAsn"] == 123


def test_drop_secrets_non_secret_ike_fields_pass_through() -> None:
    """localIkePeerIdentity and remoteIkePeerIdentity are not secrets and must be preserved."""
    vpn = {
        "presharedKey": "top-secret",
        "localIkePeerIdentity": "192.168.1.1",
        "remoteIkePeerIdentity": "10.0.0.1",
    }
    result = _drop_secrets(vpn)
    assert "presharedKey" not in result
    assert result["localIkePeerIdentity"] == "192.168.1.1"
    assert result["remoteIkePeerIdentity"] == "10.0.0.1"


def test_drop_secrets_bgp_address_families_list_passes_through() -> None:
    """API returns addressFamilies as a list with extra fields (id, holdTimer, keepaliveTimer);
    _drop_secrets must leave them intact since they contain no secrets."""
    vpn = {
        "bgp": {
            "peerAsn": 123,
            "holdTimer": 90,
            "keepaliveTimer": 30,
            "addressFamilies": [{"addressFamily": "ipv4", "id": 1612592}],
        }
    }
    result = _drop_secrets(vpn)
    assert result["bgp"]["holdTimer"] == 90
    assert result["bgp"]["keepaliveTimer"] == 30
    assert result["bgp"]["addressFamilies"] == [{"addressFamily": "ipv4", "id": 1612592}]


def test_drop_secrets_delete_before_snapshot_is_redacted() -> None:
    """Verify the delete diff before-snapshot pattern used in delete_site_to_site_vpn."""
    existing_s2s = {
        "vpn-1": {
            "presharedKey": "replace-with-your-preshared-key1",
            "bgp": {"md5Password": "replace-with-your-bgp-md5-password1"},
        }
    }
    to_delete = ["vpn-1"]
    before_snapshot = {"siteToSiteVpn": {n: _drop_secrets(existing_s2s.get(n)) for n in to_delete}}
    assert "presharedKey" not in before_snapshot["siteToSiteVpn"]["vpn-1"]
    assert "md5Password" not in before_snapshot["siteToSiteVpn"]["vpn-1"]["bgp"]
