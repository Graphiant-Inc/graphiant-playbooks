# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for GatewayServicesManager: config parsing, resolution, idempotency, vault, CRUD."""

from __future__ import annotations

import copy
from unittest.mock import MagicMock

import pytest

from ansible_collections.graphiant.naas.plugins.module_utils.libs.exceptions import ConfigurationError
from ansible_collections.graphiant.naas.plugins.module_utils.libs.gateway_services import GatewayServicesManager


def _make_manager() -> GatewayServicesManager:
    config_utils = MagicMock()
    config_utils.gsdk = MagicMock()
    mgr = GatewayServicesManager(config_utils)
    # Sensible defaults so _validate_* and _build_details resolve without a live portal.
    mgr.gsdk.get_region_id_by_name.return_value = 10
    mgr.gsdk.get_regions.return_value = [MagicMock(name="r", id=10)]
    mgr.gsdk.get_regions.return_value[0].name = "us-west-1 (Seattle)"
    mgr.gsdk.get_lan_segments_dict.return_value = {"lan-1-test": 20}
    mgr.gsdk.get_global_ipsec_profiles.return_value = {"Default VPN Profile": object()}
    return mgr


def _cloud_cfg(provider="aws", block=None):
    return {
        "gatewayServices": {
            "cloudGateway": [
                {
                    "region": "us-west-1 (Seattle)",
                    "speed": "1Gbps",
                    "lanSegment": "lan-1-test",
                    provider: block or {"accountId": "123456789012"},
                }
            ]
        }
    }


def _conn_cfg(name="test", routing=None, tunnels=None, vpn_profile=None):
    tunnel = tunnels or {"insideIpv4Cidr": None, "insideIpv6Cidr": None, "psk": None}
    peer = {
        "destinationAddress": "0.0.0.0",
        "ikeInitiator": False,
        "tunnel1": copy.deepcopy(tunnel),
        "tunnel2": copy.deepcopy(tunnel),
    }
    if vpn_profile is not None:
        peer["vpnProfile"] = vpn_profile
    return {
        "gatewayServices": {
            "connectivity": [
                {
                    "region": "us-west-1 (Seattle)",
                    "speed": "1Gbps",
                    "lanSegment": "lan-1-test",
                    "ipsecGatewayPeers": {
                        "name": name,
                        "routing": routing or {"static": {"destinationPrefix": ["0.0.0.0/0"]}},
                        "remotePeers": [peer],
                    },
                }
            ]
        }
    }


# --- pure helpers ------------------------------------------------------------


def test_resolve_speed_adds_s_prefix_and_defaults() -> None:
    assert GatewayServicesManager._resolve_speed("1Gbps") == "S1Gbps"
    assert GatewayServicesManager._resolve_speed("S10Gbps") == "S10Gbps"
    assert GatewayServicesManager._resolve_speed(None) == "S1Gbps"


def test_provider_block_returns_single_provider() -> None:
    provider, block = GatewayServicesManager._provider_block({"aws": {"accountId": "1"}})
    assert provider == "aws"
    assert block == {"accountId": "1"}
    assert GatewayServicesManager._provider_block({"region": "x"}) == (None, None)


def test_identity_of_cloud_and_connectivity() -> None:
    mgr = _make_manager()
    cloud = {"regionId": 10, "vrfId": 20, "aws": {"accountId": "999"}}
    assert mgr._identity_of(cloud) == ("aws", 10, 20, "999")
    conn = {"regionId": 10, "vrfId": 20, "ipsecGatewayPeers": {"name": "test"}}
    assert mgr._identity_of(conn) == ("connectivity", 10, 20, "test")
    # API GET may return the ipsec block under 'ipsecGateway'
    conn_get = {"regionId": 10, "vrfId": 20, "ipsecGateway": {"name": "test"}}
    assert mgr._identity_of(conn_get) == ("connectivity", 10, 20, "test")


def test_strip_volatile_removes_psk_cidrs_and_md5() -> None:
    ipsec = {
        "routing": {
            "bgp": {
                "peerAsn": 65001,
                "md5Password": {"md5_password": "x"},
                "addressFamilies": {"ipv4": {"addressFamily": "ipv4"}},
            }
        },
        "remotePeers": [
            {
                "remoteIkePeerIdentity": "test-peer-1",
                "tunnel1": {"insideIpv4Cidr": "a", "insideIpv6Cidr": "b", "psk": "p"},
            },
        ],
    }
    stripped = GatewayServicesManager._strip_volatile(ipsec)
    peer = stripped["remotePeers"][0]
    t1 = peer["tunnel1"]
    assert "psk" not in t1 and "insideIpv4Cidr" not in t1 and "insideIpv6Cidr" not in t1
    assert "md5Password" not in stripped["routing"]["bgp"]
    # portal-normalization artifacts excluded from comparison
    assert "remoteIkePeerIdentity" not in peer
    # empty address family (no policy refs) is dropped entirely
    assert stripped["routing"]["bgp"]["addressFamilies"] == {}
    # original is untouched (deep copy)
    assert ipsec["remotePeers"][0]["tunnel1"]["psk"] == "p"
    assert ipsec["remotePeers"][0]["remoteIkePeerIdentity"] == "test-peer-1"


def test_norm_address_families_flattens_and_drops_empty() -> None:
    fn = GatewayServicesManager._norm_address_families
    # portal's expanded shape: extra ipv6, 'family' wrappers, empty {} policies -> all dropped
    portal = {
        "ipv4": {"family": {"inboundPolicy": {}, "outboundPolicy": {}}},
        "ipv6": {"family": {"inboundPolicy": {}, "outboundPolicy": {}}},
    }
    assert fn(portal) == {}
    # config's compact shape with only the redundant addressFamily key -> also empty
    assert fn({"ipv4": {"addressFamily": "ipv4"}}) == {}
    # real policy references are kept (top-level or nested under 'family')
    assert fn({"ipv4": {"inboundPolicy": "in", "outboundPolicy": "out"}}) == {
        "ipv4": {"inboundPolicy": "in", "outboundPolicy": "out"}
    }
    assert fn({"ipv4": {"family": {"inboundPolicy": "in"}}}) == {"ipv4": {"inboundPolicy": "in"}}
    assert fn(None) == {}


def test_redact_secrets_masks_psk_and_md5() -> None:
    details = {
        "regionId": 10,
        "ipsecGatewayPeers": {
            "routing": {"bgp": {"peerAsn": 65001, "md5Password": {"md5_password": "s"}}},
            "remotePeers": [
                {
                    "tunnel1": {"insideIpv4Cidr": "169.254.0.0/30", "psk": "secret1"},
                    "tunnel2": {"insideIpv4Cidr": "169.254.0.4/30", "psk": None},
                }
            ],
        },
    }
    red = GatewayServicesManager._redact_secrets(details)
    peer = red["ipsecGatewayPeers"]["remotePeers"][0]
    assert peer["tunnel1"]["psk"] == "********"
    assert peer["tunnel1"]["insideIpv4Cidr"] == "169.254.0.0/30"  # non-secret kept
    assert peer["tunnel2"]["psk"] is None  # null left as-is (nothing to hide)
    assert red["ipsecGatewayPeers"]["routing"]["bgp"]["md5Password"] == "********"
    # original untouched (deep copy)
    assert details["ipsecGatewayPeers"]["remotePeers"][0]["tunnel1"]["psk"] == "secret1"


# --- _build_details validation ----------------------------------------------


def test_build_details_resolves_ids_and_speed() -> None:
    mgr = _make_manager()
    service = _cloud_cfg()["gatewayServices"]["cloudGateway"][0]
    details = mgr._build_details(service, "cloudGateway", {"lan-1-test": 20})
    assert details["regionId"] == 10
    assert details["vrfId"] == 20
    assert details["speed"] == "S1Gbps"
    assert details["aws"] == {"accountId": "123456789012"}


def test_build_details_unknown_region_raises() -> None:
    mgr = _make_manager()
    mgr.gsdk.get_region_id_by_name.return_value = None
    service = _cloud_cfg()["gatewayServices"]["cloudGateway"][0]
    with pytest.raises(ConfigurationError, match="region"):
        mgr._build_details(service, "cloudGateway", {"lan-1-test": 20})


def test_build_details_unknown_lan_segment_raises() -> None:
    mgr = _make_manager()
    service = _cloud_cfg()["gatewayServices"]["cloudGateway"][0]
    with pytest.raises(ConfigurationError, match="lanSegment"):
        mgr._build_details(service, "cloudGateway", {})


def test_build_details_cloud_without_provider_raises() -> None:
    mgr = _make_manager()
    service = {"region": "us-west-1 (Seattle)", "lanSegment": "lan-1-test"}
    with pytest.raises(ConfigurationError, match="one of"):
        mgr._build_details(service, "cloudGateway", {"lan-1-test": 20})


def test_create_valid_vpn_profile_passes() -> None:
    mgr = _make_manager()  # portal has "Default VPN Profile"
    mgr.render_config_file = MagicMock(return_value=_conn_cfg(vpn_profile="Default VPN Profile"))
    mgr._existing_gateways = MagicMock(return_value=[])

    result = mgr.create("cfg.yaml")

    assert result["created"] == ["connectivity:test"]
    mgr.gsdk.get_global_ipsec_profiles.assert_called_once()


def test_create_missing_vpn_profile_raises_before_push() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(return_value=_conn_cfg(vpn_profile="Nonexistent VPN Profile"))
    mgr._existing_gateways = MagicMock(return_value=[])

    with pytest.raises(ConfigurationError, match="vpnProfile"):
        mgr.create("cfg.yaml")
    # fail-fast: nothing was created
    mgr.gsdk.create_gateway_services.assert_not_called()


def test_create_no_vpn_profile_skips_portal_check() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(return_value=_conn_cfg())  # no vpnProfile set
    mgr._existing_gateways = MagicMock(return_value=[])

    mgr.create("cfg.yaml")

    mgr.gsdk.get_global_ipsec_profiles.assert_not_called()


# --- vault injection ---------------------------------------------------------


def test_inject_vault_psks_fills_null_only() -> None:
    mgr = _make_manager()
    ipsec = {
        "remotePeers": [
            {"tunnel1": {"psk": "inline-wins"}, "tunnel2": {"psk": None}},
        ]
    }
    vault = {"test": {"peer-1": {"tunnel1": "vault1", "tunnel2": "vault2"}}}
    mgr._inject_vault_psks(ipsec, "test", vault)
    peer = ipsec["remotePeers"][0]
    assert peer["tunnel1"]["psk"] == "inline-wins"  # non-null config wins
    assert peer["tunnel2"]["psk"] == "vault2"  # null filled from vault


def test_inject_vault_psks_noop_without_gateway_name() -> None:
    mgr = _make_manager()
    ipsec = {"remotePeers": [{"tunnel1": {"psk": None}}]}
    mgr._inject_vault_psks(ipsec, None, {"test": {"peer-1": {"tunnel1": "x"}}})
    assert ipsec["remotePeers"][0]["tunnel1"]["psk"] is None


def test_inject_vault_md5_fills_null_and_wraps() -> None:
    mgr = _make_manager()
    ipsec = {"routing": {"bgp": {"md5Password": None}}}
    mgr._inject_vault_md5(ipsec, "test-bgp", {"test-bgp": "secret"})
    assert ipsec["routing"]["bgp"]["md5Password"] == {"md5_password": "secret"}


def test_inject_vault_md5_no_vault_leaves_none() -> None:
    mgr = _make_manager()
    ipsec = {"routing": {"bgp": {"md5Password": None}}}
    mgr._inject_vault_md5(ipsec, "test-bgp", {})
    assert ipsec["routing"]["bgp"]["md5Password"] is None


# --- create() end-to-end (mocked gsdk) --------------------------------------


def test_create_creates_when_absent() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(return_value=_cloud_cfg())
    mgr._existing_gateways = MagicMock(return_value=[])  # nothing exists

    result = mgr.create("cfg.yaml")

    assert result["changed"] is True
    assert result["created"] == ["aws:123456789012"]
    assert result["updated"] == [] and result["skipped"] == []
    mgr.gsdk.create_gateway_services.assert_called_once()
    assert result["diff_plan"][0]["device"] == "aws:123456789012"


def test_create_skips_existing_cloud_gateway() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(return_value=_cloud_cfg())
    existing = {"regionId": 10, "vrfId": 20, "aws": {"accountId": "123456789012"}}
    mgr._existing_gateways = MagicMock(return_value=[(1, existing)])

    result = mgr.create("cfg.yaml")

    assert result["changed"] is False
    assert result["skipped"] == ["aws:123456789012"]
    mgr.gsdk.create_gateway_services.assert_not_called()
    mgr.gsdk.update_gateway_services.assert_not_called()


def test_create_skips_matching_connectivity() -> None:
    mgr = _make_manager()
    cfg = _conn_cfg()
    mgr.render_config_file = MagicMock(return_value=cfg)
    # existing details equal to what _build_details would produce (volatile fields excluded anyway)
    built = mgr._build_details(cfg["gatewayServices"]["connectivity"][0], "connectivity", {"lan-1-test": 20})
    existing = copy.deepcopy(built)
    mgr._existing_gateways = MagicMock(return_value=[(5, existing)])

    result = mgr.create("cfg.yaml")

    assert result["changed"] is False
    assert result["skipped"] == ["connectivity:test"]
    mgr.gsdk.update_gateway_services.assert_not_called()


def test_create_updates_changed_connectivity() -> None:
    mgr = _make_manager()
    cfg = _conn_cfg()
    mgr.render_config_file = MagicMock(return_value=cfg)
    # existing differs (different static prefix) -> update path
    existing = {
        "regionId": 10,
        "vrfId": 20,
        "speed": "S1Gbps",
        "ipsecGatewayPeers": {
            "name": "test",
            "routing": {"static": {"destinationPrefix": ["10.0.0.0/8"]}},
            "remotePeers": [{"tunnel1": {}, "tunnel2": {}}],
        },
    }
    mgr._existing_gateways = MagicMock(return_value=[(7, existing)])

    result = mgr.create("cfg.yaml")

    assert result["changed"] is True
    assert result["updated"] == ["connectivity:test"]
    mgr.gsdk.update_gateway_services.assert_called_once()
    assert mgr.gsdk.update_gateway_services.call_args[0][0] == 7  # gateway id
    assert result["diff_plan"][0]["device"] == "connectivity:test"


def test_create_empty_config_is_noop() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(return_value={})
    result = mgr.create("cfg.yaml")
    assert result == {"changed": False, "created": [], "updated": [], "skipped": [], "diff_plan": []}


def test_create_idempotent_against_portal_normalized_shape() -> None:
    """A BGP connectivity gateway whose only 'diffs' are portal-added fields must be skipped."""
    mgr = _make_manager()
    routing = {
        "bgp": {
            "peerAsn": 65001,
            "holdTimer": 180,
            "keepaliveTimer": 60,
            "sendCommunity": True,
            "md5Password": None,
            "addressFamilies": {"ipv4": {"addressFamily": "ipv4"}},
        }
    }
    cfg = _conn_cfg(name="test-bgp", routing=routing)
    mgr.render_config_file = MagicMock(return_value=cfg)
    desired = mgr._build_details(cfg["gatewayServices"]["connectivity"][0], "connectivity", {"lan-1-test": 20})
    # Simulate the real portal GET: adds remoteIkePeerIdentity, expands addressFamilies (extra ipv6,
    # 'family' wrappers, empty {} policies), and clears volatile tunnel fields — no real change.
    existing = copy.deepcopy(desired)
    ipsec = existing["ipsecGatewayPeers"]
    ipsec["routing"]["bgp"]["addressFamilies"] = {
        "ipv4": {"family": {"inboundPolicy": {}, "outboundPolicy": {}}},
        "ipv6": {"family": {"inboundPolicy": {}, "outboundPolicy": {}}},
    }
    for peer in ipsec["remotePeers"]:
        peer["remoteIkePeerIdentity"] = "test-bgp"
        peer["tunnel1"] = {}
        peer["tunnel2"] = {}
    mgr._existing_gateways = MagicMock(return_value=[(9, existing)])

    result = mgr.create("cfg.yaml")

    assert result["changed"] is False, f"expected idempotent skip, got: {result}"
    assert result["skipped"] == ["connectivity:test-bgp"]
    mgr.gsdk.update_gateway_services.assert_not_called()


def test_create_idempotent_when_remote_peers_reordered() -> None:
    """Peers returned by the portal in a different order than the config must still match."""
    mgr = _make_manager()
    peer_a = {
        "destinationAddress": "1.1.1.1",
        "ikeInitiator": False,
        "tunnel1": {"insideIpv4Cidr": None, "insideIpv6Cidr": None, "psk": None},
        "tunnel2": {"insideIpv4Cidr": None, "insideIpv6Cidr": None, "psk": None},
    }
    peer_b = dict(peer_a, destinationAddress="2.2.2.2")
    cfg = {
        "gatewayServices": {
            "connectivity": [
                {
                    "region": "us-west-1 (Seattle)",
                    "speed": "1Gbps",
                    "lanSegment": "lan-1-test",
                    "ipsecGatewayPeers": {
                        "name": "test",
                        "routing": {"static": {"destinationPrefix": ["0.0.0.0/0"]}},
                        "remotePeers": [peer_a, peer_b],
                    },
                }
            ]
        }
    }
    mgr.render_config_file = MagicMock(return_value=cfg)
    desired = mgr._build_details(cfg["gatewayServices"]["connectivity"][0], "connectivity", {"lan-1-test": 20})
    # portal returns the peers in the opposite order
    existing = copy.deepcopy(desired)
    existing["ipsecGatewayPeers"]["remotePeers"].reverse()
    mgr._existing_gateways = MagicMock(return_value=[(4, existing)])

    result = mgr.create("cfg.yaml")

    assert result["changed"] is False, f"expected order-insensitive skip, got: {result}"
    assert result["skipped"] == ["connectivity:test"]
    mgr.gsdk.update_gateway_services.assert_not_called()


def test_create_force_update_repushes_matching_connectivity() -> None:
    mgr = _make_manager()
    cfg = _conn_cfg()
    mgr.render_config_file = MagicMock(return_value=cfg)
    built = mgr._build_details(cfg["gatewayServices"]["connectivity"][0], "connectivity", {"lan-1-test": 20})
    existing = copy.deepcopy(built)  # already matches
    mgr._existing_gateways = MagicMock(return_value=[(5, existing)])

    # Without force: skipped (idempotent)
    assert mgr.create("cfg.yaml")["skipped"] == ["connectivity:test"]
    mgr.gsdk.update_gateway_services.assert_not_called()

    # With force_update: re-pushed even though it matches
    result = mgr.create("cfg.yaml", force_update=True)
    assert result["changed"] is True
    assert result["updated"] == ["connectivity:test"]
    assert result["skipped"] == []
    mgr.gsdk.update_gateway_services.assert_called_once()
    assert result["diff_plan"][0]["branch"] == "connectivity (forced update)"


def test_force_update_does_not_update_cloud_gateway() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(return_value=_cloud_cfg())
    existing = {"regionId": 10, "vrfId": 20, "aws": {"accountId": "123456789012"}}
    mgr._existing_gateways = MagicMock(return_value=[(1, existing)])

    result = mgr.create("cfg.yaml", force_update=True)

    assert result["changed"] is False
    assert result["skipped"] == ["aws:123456789012"]
    mgr.gsdk.update_gateway_services.assert_not_called()
    mgr.gsdk.create_gateway_services.assert_not_called()


def test_create_connectivity_redacts_psk_in_diff_but_sends_real_to_api() -> None:
    mgr = _make_manager()
    # non-null CIDRs + psk so _fill_missing_tunnel_values makes no gsdk calls
    tunnel = {"insideIpv4Cidr": "169.254.0.0/30", "insideIpv6Cidr": "fe80::/126", "psk": "real-secret"}
    mgr.render_config_file = MagicMock(return_value=_conn_cfg(tunnels=tunnel))
    mgr._existing_gateways = MagicMock(return_value=[])  # absent -> create

    result = mgr.create("cfg.yaml")

    # diff shows masked psk...
    after = result["diff_plan"][0]["after"]
    assert after["ipsecGatewayPeers"]["remotePeers"][0]["tunnel1"]["psk"] == "********"
    # ...but the real psk is what gets sent to the API
    sent = mgr.gsdk.create_gateway_services.call_args[0][0]
    assert sent["ipsecGatewayPeers"]["remotePeers"][0]["tunnel1"]["psk"] == "real-secret"


def test_existing_gateways_excludes_deleting_status() -> None:
    # 'requested_removal' is the portal status after a cloud gateway delete (async teardown).
    mgr = _make_manager()
    mgr.gsdk.get_gateway_summary.return_value.summaries = [
        {"id": 1, "status": "requested"},  # any non-removal status -> kept
        {"id": 2, "status": "requested_removal"}   # excluded
    ]
    mgr.gsdk.get_gateway_details.side_effect = lambda gid: {"details": {"regionId": 1, "id": gid}}

    result = mgr._existing_gateways()

    assert [gid for gid, _details in result] == [1]
    mgr.gsdk.get_gateway_details.assert_called_once_with(1)  # no detail fetch for excluded gateways


# --- delete() end-to-end (mocked gsdk) --------------------------------------


def test_delete_removes_existing() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(return_value=_cloud_cfg())
    existing = {"regionId": 10, "vrfId": 20, "aws": {"accountId": "123456789012"}}
    mgr._existing_gateways = MagicMock(return_value=[(3, existing)])

    result = mgr.delete("cfg.yaml")

    assert result["changed"] is True
    assert result["deleted"] == ["aws:123456789012"]
    mgr.gsdk.delete_gateway_services.assert_called_once_with(3)
    # delete populates a diff_plan (before = current gateway, after = {}) so --diff works
    entry = result["diff_plan"][0]
    assert entry["device"] == "aws:123456789012"
    assert entry["branch"] == "cloudGateway (delete)"
    assert entry["before"] == existing and entry["after"] == {}


def test_delete_redacts_secrets_in_diff() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(return_value=_conn_cfg())
    current = {
        "regionId": 10,
        "vrfId": 20,
        "ipsecGatewayPeers": {
            "name": "test",
            "remotePeers": [{"tunnel1": {"psk": "live-secret"}, "tunnel2": {"psk": None}}],
        },
    }
    mgr._existing_gateways = MagicMock(return_value=[(8, current)])

    result = mgr.delete("cfg.yaml")

    before = result["diff_plan"][0]["before"]
    assert before["ipsecGatewayPeers"]["remotePeers"][0]["tunnel1"]["psk"] == "********"


def test_delete_skips_absent() -> None:
    mgr = _make_manager()
    mgr.render_config_file = MagicMock(return_value=_cloud_cfg())
    mgr._existing_gateways = MagicMock(return_value=[])

    result = mgr.delete("cfg.yaml")

    assert result["changed"] is False
    assert result["skipped"] == ["aws:123456789012"]
    mgr.gsdk.delete_gateway_services.assert_not_called()
