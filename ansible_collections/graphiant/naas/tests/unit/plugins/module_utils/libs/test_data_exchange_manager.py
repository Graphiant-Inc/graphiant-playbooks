# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for data_exchange_manager helpers (no live API)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ansible_collections.graphiant.naas.plugins.module_utils.libs.data_exchange_manager import (
    DataExchangeManager,
)
from ansible_collections.graphiant.naas.plugins.module_utils.libs.exceptions import ConfigurationError


def _make_manager() -> DataExchangeManager:
    config_utils = MagicMock()
    config_utils.gsdk = MagicMock()
    config_utils.template = MagicMock()
    return DataExchangeManager(config_utils)


def test_validate_routing_policies_no_global_object_ops() -> None:
    mgr = _make_manager()
    mgr._validate_global_object_ops_routing_policies(  # pylint: disable=protected-access
        {}, "svc1"
    )
    mgr.gsdk.get_global_routing_policy_summaries.assert_not_called()


def test_validate_routing_policies_not_dict_ops() -> None:
    mgr = _make_manager()
    mgr._validate_global_object_ops_routing_policies(  # pylint: disable=protected-access
        {"globalObjectOps": "bad"}, "svc1"
    )
    mgr.gsdk.get_global_routing_policy_summaries.assert_not_called()


def test_validate_routing_policies_uses_existing_names() -> None:
    mgr = _make_manager()
    policy_config = {
        "globalObjectOps": {
            "1": {
                "routingPolicyOps": {"p1": {}, "p2": {}},
            }
        }
    }
    with pytest.raises(ConfigurationError, match="not found for service"):
        mgr._validate_global_object_ops_routing_policies(  # pylint: disable=protected-access
            policy_config,
            "my-service",
            existing_policy_names=set(),  # empty -> all missing
        )
    mgr.gsdk.get_global_routing_policy_summaries.assert_not_called()


def test_validate_routing_policies_success_with_existing() -> None:
    mgr = _make_manager()
    policy_config = {
        "globalObjectOps": {
            "1": {
                "routingPolicyOps": {"Policy-A": {}},
            }
        }
    }
    mgr._validate_global_object_ops_routing_policies(  # pylint: disable=protected-access
        policy_config,
        "svc",
        existing_policy_names={"Policy-A", "Policy-B"},
    )
    mgr.gsdk.get_global_routing_policy_summaries.assert_not_called()


def test_validate_routing_policies_fetches_from_gsdk() -> None:
    mgr = _make_manager()
    mgr.gsdk.get_global_routing_policy_summaries.return_value = [
        {"name": "Policy-A"},
    ]
    policy_config = {
        "globalObjectOps": {
            "1": {
                "routingPolicyOps": {"Policy-A": {}},
            }
        }
    }
    mgr._validate_global_object_ops_routing_policies(  # pylint: disable=protected-access
        policy_config,
        "svc",
    )
    mgr.gsdk.get_global_routing_policy_summaries.assert_called_once()


# ---- helpers for update_services / create_services tests ----


def _make_service_details(service_id: int = 101, prefix_tags: list | None = None) -> dict:
    """Return a plain dict mimicking get_data_exchange_service_details() response (raw JSON)."""
    if prefix_tags is None:
        prefix_tags = [{"prefix": "10.1.1.0/24", "tag": "s-1-prefix1"}]
    return {
        "id": service_id,
        "policy": {
            "serviceName": "de-service-1",
            "policy": {
                "serviceLanSegment": 517853,
                "type": "peering_service",
                "sites": [{"sites": [13379, 13378], "siteLists": []}],
                "prefixTags": prefix_tags,
                "description": "de_service_1_description",
            },
        },
    }


def _make_existing_service(service_id: int = 101):
    mock = MagicMock()
    mock.id = service_id
    return mock


def _update_config(prefix_tags: list, service_name: str = "de-service-1") -> dict:
    return {
        "data_exchange_services": [
            {"serviceName": service_name, "policy": {"prefixTags": prefix_tags}}
        ]
    }


# ---- helpers for update_customers tests ----


def _make_customer(customer_id: int = 201):
    mock = MagicMock()
    mock.id = customer_id
    return mock


def _customer_details(emails: list, num_sites: int = 2) -> dict:
    return {"customerName": "FinanceInc", "type": "non_graphiant_peer", "emails": emails, "numSites": num_sites}


def _update_customers_config(emails: list, customer_name: str = "FinanceInc") -> dict:
    return {
        "data_exchange_customers": [
            {"name": customer_name, "invite": {"adminEmail": emails}}
        ]
    }


# ---- create_customers diff_plan tests ----


def test_create_customers_diff_plan_on_new_customer() -> None:
    mgr = _make_manager()
    mgr.config_utils.render_config_file.return_value = {
        "data_exchange_customers": [{"name": "FinanceInc", "invite": {"adminEmail": ["a@example.com"]}}]
    }
    mgr.gsdk.get_data_exchange_customer_by_name.return_value = None  # new customer

    result = mgr.create_customers("dummy.yaml")

    assert result["changed"] is True
    assert "FinanceInc" in result["created"]
    assert len(result["diff_plan"]) == 1
    entry = result["diff_plan"][0]
    assert entry["device"] == "FinanceInc"
    assert entry["branch"] == "create"
    assert entry["before"] == {}
    assert entry["after"]["name"] == "FinanceInc"
    mgr.gsdk.create_data_exchange_customers.assert_called_once()


def test_create_customers_diff_plan_drift_on_existing_customer() -> None:
    """Existing customer with different emails shows drift in diff_plan (changed=False)."""
    desired_emails = ["new@example.com"]
    current_emails = ["old@example.com"]
    mgr = _make_manager()
    mgr.config_utils.render_config_file.return_value = _update_customers_config(desired_emails)
    mgr.gsdk.get_data_exchange_customer_by_name.return_value = _make_customer()
    mgr.gsdk.get_data_exchange_customer_details.return_value = _customer_details(current_emails)

    result = mgr.create_customers("dummy.yaml", diff_mode=True)

    assert result["changed"] is False
    assert "FinanceInc" in result["skipped"]
    assert "FinanceInc" in result["drifted"]
    assert len(result["diff_plan"]) == 1
    entry = result["diff_plan"][0]
    assert entry["device"] == "FinanceInc"
    assert "update_customers" in entry["branch"]
    assert entry["before"] == {"adminEmail": current_emails}
    assert entry["after"] == {"adminEmail": desired_emails}
    mgr.gsdk.create_data_exchange_customers.assert_not_called()


def test_create_customers_no_drift_without_diff_mode() -> None:
    """Without diff_mode, existing customer with different emails produces no API call or diff_plan."""
    mgr = _make_manager()
    mgr.config_utils.render_config_file.return_value = _update_customers_config(["new@example.com"])
    mgr.gsdk.get_data_exchange_customer_by_name.return_value = _make_customer()

    result = mgr.create_customers("dummy.yaml", diff_mode=False)

    assert result["changed"] is False
    assert result["diff_plan"] == []
    assert result["drifted"] == []
    mgr.gsdk.get_data_exchange_customer_details.assert_not_called()


def test_create_customers_no_diff_when_emails_match() -> None:
    """Existing customer with same emails produces no diff_plan entry."""
    emails = ["a@example.com", "b@example.com"]
    mgr = _make_manager()
    mgr.config_utils.render_config_file.return_value = _update_customers_config(emails)
    mgr.gsdk.get_data_exchange_customer_by_name.return_value = _make_customer()
    mgr.gsdk.get_data_exchange_customer_details.return_value = _customer_details(emails)

    result = mgr.create_customers("dummy.yaml", diff_mode=True)

    assert result["changed"] is False
    assert "FinanceInc" in result["skipped"]
    assert result["drifted"] == []
    assert result["diff_plan"] == []


# ---- update_customers tests ----


def test_update_customers_customer_not_found() -> None:
    mgr = _make_manager()
    mgr.config_utils.render_config_file.return_value = _update_customers_config(["new@example.com"])
    mgr.gsdk.get_data_exchange_customer_by_name.return_value = None

    with pytest.raises(ConfigurationError, match="not found"):
        mgr.update_customers("dummy.yaml")


def test_update_customers_no_emails_raises() -> None:
    mgr = _make_manager()
    mgr.config_utils.render_config_file.return_value = _update_customers_config([])
    mgr.gsdk.get_data_exchange_customer_by_name.return_value = _make_customer()
    mgr.gsdk.get_data_exchange_customer_details.return_value = _customer_details(["old@example.com"])

    with pytest.raises(ConfigurationError, match="adminEmail"):
        mgr.update_customers("dummy.yaml")


def test_update_customers_idempotent_no_change() -> None:
    emails = ["a@example.com", "b@example.com"]
    mgr = _make_manager()
    mgr.config_utils.render_config_file.return_value = _update_customers_config(emails)
    mgr.gsdk.get_data_exchange_customer_by_name.return_value = _make_customer()
    mgr.gsdk.get_data_exchange_customer_details.return_value = _customer_details(emails)

    result = mgr.update_customers("dummy.yaml")

    assert result["changed"] is False
    assert result["updated"] == []
    assert "FinanceInc" in result["skipped"]
    assert result["diff_plan"] == []
    mgr.gsdk.edit_data_exchange_customer.assert_not_called()


def test_update_customers_idempotent_order_invariant() -> None:
    mgr = _make_manager()
    mgr.config_utils.render_config_file.return_value = _update_customers_config(["b@example.com", "a@example.com"])
    mgr.gsdk.get_data_exchange_customer_by_name.return_value = _make_customer()
    mgr.gsdk.get_data_exchange_customer_details.return_value = _customer_details(
        ["a@example.com", "b@example.com"]
    )

    result = mgr.update_customers("dummy.yaml")

    assert result["changed"] is False
    mgr.gsdk.edit_data_exchange_customer.assert_not_called()


def test_update_customers_applies_change() -> None:
    old_emails = ["old@example.com"]
    new_emails = ["new@example.com", "extra@example.com"]
    mgr = _make_manager()
    mgr.config_utils.render_config_file.return_value = _update_customers_config(new_emails)
    mgr.gsdk.get_data_exchange_customer_by_name.return_value = _make_customer(customer_id=42)
    mgr.gsdk.get_data_exchange_customer_details.return_value = _customer_details(old_emails, num_sites=3)

    result = mgr.update_customers("dummy.yaml")

    assert result["changed"] is True
    assert "FinanceInc" in result["updated"]
    assert result["skipped"] == []
    mgr.gsdk.edit_data_exchange_customer.assert_called_once()
    cid, payload = mgr.gsdk.edit_data_exchange_customer.call_args[0]
    assert cid == 42
    assert payload["invite"]["adminEmail"] == new_emails
    assert payload["invite"]["maximumNumberOfSites"] == 3
    assert payload["id"] == 42
    assert payload["status"] == ""


def test_update_customers_diff_plan_populated() -> None:
    old_emails = ["old@example.com"]
    new_emails = ["new@example.com"]
    mgr = _make_manager()
    mgr.config_utils.render_config_file.return_value = _update_customers_config(new_emails)
    mgr.gsdk.get_data_exchange_customer_by_name.return_value = _make_customer()
    mgr.gsdk.get_data_exchange_customer_details.return_value = _customer_details(old_emails)

    result = mgr.update_customers("dummy.yaml")

    assert len(result["diff_plan"]) == 1
    entry = result["diff_plan"][0]
    assert entry["device"] == "FinanceInc"
    assert entry["branch"] == "adminEmail"
    assert entry["before"] == {"adminEmail": old_emails}
    assert entry["after"] == {"adminEmail": new_emails}


def test_update_customers_preserves_num_sites() -> None:
    mgr = _make_manager()
    mgr.config_utils.render_config_file.return_value = _update_customers_config(["new@example.com"])
    mgr.gsdk.get_data_exchange_customer_by_name.return_value = _make_customer()
    mgr.gsdk.get_data_exchange_customer_details.return_value = _customer_details(["old@example.com"], num_sites=5)

    mgr.update_customers("dummy.yaml")

    call_args = mgr.gsdk.edit_data_exchange_customer.call_args[0]
    payload = call_args[1]
    assert payload["invite"]["maximumNumberOfSites"] == 5


# ---- update_services tests ----


def test_update_services_service_not_found() -> None:
    mgr = _make_manager()
    mgr.config_utils.render_config_file.return_value = _update_config(
        [{"prefix": "10.1.1.0/24", "tag": "t1"}]
    )
    mgr.gsdk.get_data_exchange_service_by_name.return_value = None

    with pytest.raises(ConfigurationError, match="not found"):
        mgr.update_services("dummy.yaml")


def test_update_services_no_policy_key_raises() -> None:
    mgr = _make_manager()
    mgr.config_utils.render_config_file.return_value = {
        "data_exchange_services": [{"serviceName": "de-service-1"}]
    }
    mgr.gsdk.get_data_exchange_service_by_name.return_value = _make_existing_service()
    mgr.gsdk.get_data_exchange_service_details.return_value = _make_service_details()

    with pytest.raises(ConfigurationError, match="prefixTags"):
        mgr.update_services("dummy.yaml")


def test_update_services_empty_prefix_tags_raises() -> None:
    mgr = _make_manager()
    mgr.config_utils.render_config_file.return_value = _update_config([])
    mgr.gsdk.get_data_exchange_service_by_name.return_value = _make_existing_service()
    mgr.gsdk.get_data_exchange_service_details.return_value = _make_service_details()

    with pytest.raises(ConfigurationError, match="prefixTags"):
        mgr.update_services("dummy.yaml")


def test_update_services_idempotent_no_change() -> None:
    tags = [{"prefix": "10.1.1.0/24", "tag": "s-1-prefix1"}]
    mgr = _make_manager()
    mgr.config_utils.render_config_file.return_value = _update_config(tags)
    mgr.gsdk.get_data_exchange_service_by_name.return_value = _make_existing_service()
    mgr.gsdk.get_data_exchange_service_details.return_value = _make_service_details(prefix_tags=tags)

    result = mgr.update_services("dummy.yaml")

    assert result["changed"] is False
    assert result["updated"] == []
    assert "de-service-1" in result["skipped"]
    assert result["diff_plan"] == []
    mgr.gsdk.edit_data_exchange_service.assert_not_called()


def test_update_services_applies_change() -> None:
    new_tags = [{"prefix": "100.1.1.0/24", "tag": "new-prefix"}]
    old_tags = [{"prefix": "10.1.1.0/24", "tag": "old"}]
    mgr = _make_manager()
    mgr.config_utils.render_config_file.return_value = _update_config(new_tags)
    mgr.gsdk.get_data_exchange_service_by_name.return_value = _make_existing_service(service_id=42)
    mgr.gsdk.get_data_exchange_service_details.return_value = _make_service_details(
        service_id=42, prefix_tags=old_tags
    )

    result = mgr.update_services("dummy.yaml")

    assert result["changed"] is True
    assert "de-service-1" in result["updated"]
    assert result["skipped"] == []
    mgr.gsdk.edit_data_exchange_service.assert_called_once()
    sid, payload = mgr.gsdk.edit_data_exchange_service.call_args[0]
    assert sid == 42
    assert payload["policy"]["prefixTags"] == new_tags


def test_update_services_diff_plan_populated() -> None:
    new_tags = [{"prefix": "100.1.1.0/24", "tag": "new-prefix"}]
    old_tags = [{"prefix": "10.1.1.0/24", "tag": "old"}]
    mgr = _make_manager()
    mgr.config_utils.render_config_file.return_value = _update_config(new_tags)
    mgr.gsdk.get_data_exchange_service_by_name.return_value = _make_existing_service()
    mgr.gsdk.get_data_exchange_service_details.return_value = _make_service_details(prefix_tags=old_tags)

    result = mgr.update_services("dummy.yaml")

    assert len(result["diff_plan"]) == 1
    entry = result["diff_plan"][0]
    assert entry["device"] == "de-service-1"
    assert entry["branch"] == "prefixTags"
    assert entry["before"] == {"prefixTags": old_tags}
    assert entry["after"] == {"prefixTags": new_tags}


def test_update_services_preserves_site_structure_in_payload() -> None:
    new_tags = [{"prefix": "100.1.1.0/24", "tag": "new"}]
    mgr = _make_manager()
    mgr.config_utils.render_config_file.return_value = _update_config(new_tags)
    mgr.gsdk.get_data_exchange_service_by_name.return_value = _make_existing_service()
    mgr.gsdk.get_data_exchange_service_details.return_value = _make_service_details(
        prefix_tags=[{"prefix": "10.0.0.0/8", "tag": "old"}]
    )

    mgr.update_services("dummy.yaml")

    call_args = mgr.gsdk.edit_data_exchange_service.call_args[0]
    payload = call_args[1]
    # GET returns "sites" key; PUT must use "site" key
    assert "site" in payload["policy"]
    assert "sites" not in payload["policy"]
    # Inner sites array should be preserved from GET response
    assert payload["policy"]["site"] == [{"sites": [13379, 13378], "siteLists": []}]


# ---- create_services diff_plan test ----


def test_create_services_diff_plan_on_new_service() -> None:
    mgr = _make_manager()
    mgr.config_utils.render_config_file.return_value = {
        "data_exchange_services": [{"serviceName": "new-svc"}]
    }
    mgr.gsdk.get_global_routing_policy_summaries.return_value = []
    mgr.gsdk.get_data_exchange_service_by_name.return_value = None  # doesn't exist yet

    result = mgr.create_services("dummy.yaml")

    assert result["changed"] is True
    assert "new-svc" in result["created"]
    assert len(result["diff_plan"]) == 1
    entry = result["diff_plan"][0]
    assert entry["device"] == "new-svc"
    assert entry["branch"] == "create"
    assert entry["before"] == {}
    assert entry["after"]["serviceName"] == "new-svc"
    mgr.gsdk.create_data_exchange_services.assert_called_once()


def test_create_services_diff_plan_drift_on_existing_service() -> None:
    """Existing service with different prefixTags shows drift in diff_plan (changed=False)."""
    desired_tags = [{"prefix": "120.1.1.0/24", "tag": "new-prefix"}]
    current_tags = [{"prefix": "10.1.1.0/24", "tag": "old-prefix"}]
    mgr = _make_manager()
    mgr.config_utils.render_config_file.return_value = {
        "data_exchange_services": [
            {"serviceName": "de-service-1", "policy": {"prefixTags": desired_tags}}
        ]
    }
    mgr.gsdk.get_global_routing_policy_summaries.return_value = []
    mgr.gsdk.get_data_exchange_service_by_name.return_value = _make_existing_service()
    mgr.gsdk.get_data_exchange_service_details.return_value = _make_service_details(prefix_tags=current_tags)

    result = mgr.create_services("dummy.yaml", diff_mode=True)

    assert result["changed"] is False
    assert "de-service-1" in result["skipped"]
    assert len(result["diff_plan"]) == 1
    entry = result["diff_plan"][0]
    assert entry["device"] == "de-service-1"
    assert entry["before"] == {"prefixTags": current_tags}
    assert entry["after"] == {"prefixTags": desired_tags}
    mgr.gsdk.create_data_exchange_services.assert_not_called()


def test_create_services_no_drift_detection_without_diff_mode() -> None:
    """Without diff_mode, existing service with different prefixTags produces no API call or diff_plan."""
    desired_tags = [{"prefix": "120.1.1.0/24", "tag": "new-prefix"}]
    mgr = _make_manager()
    mgr.config_utils.render_config_file.return_value = {
        "data_exchange_services": [
            {"serviceName": "de-service-1", "policy": {"prefixTags": desired_tags}}
        ]
    }
    mgr.gsdk.get_global_routing_policy_summaries.return_value = []
    mgr.gsdk.get_data_exchange_service_by_name.return_value = _make_existing_service()

    result = mgr.create_services("dummy.yaml", diff_mode=False)

    assert result["changed"] is False
    assert result["diff_plan"] == []
    assert result["drifted"] == []
    mgr.gsdk.get_data_exchange_service_details.assert_not_called()


def test_create_services_no_diff_plan_when_existing_matches() -> None:
    """Existing service with same prefixTags produces no diff_plan entry."""
    tags = [{"prefix": "10.1.1.0/24", "tag": "s-1-prefix1"}]
    mgr = _make_manager()
    mgr.config_utils.render_config_file.return_value = {
        "data_exchange_services": [
            {"serviceName": "de-service-1", "policy": {"prefixTags": tags}}
        ]
    }
    mgr.gsdk.get_global_routing_policy_summaries.return_value = []
    mgr.gsdk.get_data_exchange_service_by_name.return_value = _make_existing_service()
    mgr.gsdk.get_data_exchange_service_details.return_value = _make_service_details(prefix_tags=tags)

    result = mgr.create_services("dummy.yaml", diff_mode=True)

    assert result["changed"] is False
    assert "de-service-1" in result["skipped"]
    assert result["diff_plan"] == []


# ---- delete_customers tests ----


def _delete_customers_config(*names: str) -> dict:
    return {"data_exchange_customers": [{"name": n} for n in names]}


def test_delete_customers_found_is_deleted() -> None:
    """Customer that exists in portal is deleted and reported as changed."""
    mgr = _make_manager()
    mgr.config_utils.render_config_file.return_value = _delete_customers_config("FinanceInc")
    customer = MagicMock()
    customer.id = 42
    mgr.gsdk.get_data_exchange_customer_by_name.return_value = customer

    result = mgr.delete_customers("dummy.yaml")

    assert result["changed"] is True
    assert "FinanceInc" in result["deleted"]
    assert result["skipped"] == []
    mgr.gsdk.delete_data_exchange_customer.assert_called_once_with(42)


def test_delete_customers_not_found_is_skipped() -> None:
    """Customer absent from portal is skipped; changed remains False."""
    mgr = _make_manager()
    mgr.config_utils.render_config_file.return_value = _delete_customers_config("FinanceInc")
    mgr.gsdk.get_data_exchange_customer_by_name.return_value = None

    result = mgr.delete_customers("dummy.yaml")

    assert result["changed"] is False
    assert result["deleted"] == []
    assert "FinanceInc" in result["skipped"]
    mgr.gsdk.delete_data_exchange_customer.assert_not_called()


def test_delete_customers_mixed_found_and_missing() -> None:
    """Only present customers are deleted; missing ones are skipped."""
    mgr = _make_manager()
    mgr.config_utils.render_config_file.return_value = _delete_customers_config("CustomerA", "CustomerB")
    found = MagicMock()
    found.id = 10
    mgr.gsdk.get_data_exchange_customer_by_name.side_effect = [found, None]

    result = mgr.delete_customers("dummy.yaml")

    assert result["changed"] is True
    assert result["deleted"] == ["CustomerA"]
    assert result["skipped"] == ["CustomerB"]


def test_delete_customers_empty_config_returns_unchanged() -> None:
    """Missing data_exchange_customers key returns unchanged result."""
    mgr = _make_manager()
    mgr.config_utils.render_config_file.return_value = {}

    result = mgr.delete_customers("dummy.yaml")

    assert result["changed"] is False
    assert result["deleted"] == []
    mgr.gsdk.delete_data_exchange_customer.assert_not_called()


# ---- _validate_vpn_profiles_for_acceptances: ipsecGatewayPeers tests ----


def _make_acceptance_with_peers(*vpn_profiles: str) -> dict:
    """Build a minimal acceptance config using ipsecGatewayPeers."""
    return {
        "siteToSiteVpn": {
            "ipsecGatewayPeers": {
                "remotePeers": [{"name": f"peer-{i}", "vpnProfile": vp} for i, vp in enumerate(vpn_profiles, 1)]
            }
        }
    }


def test_validate_vpn_profiles_ipsec_gateway_peers_all_present() -> None:
    """ipsecGatewayPeers: all per-peer VPN profiles found in portal — no error."""
    mgr = _make_manager()
    mgr.gsdk.get_global_ipsec_profiles.return_value = {"vpnprofile-global-test": MagicMock()}
    acceptances = [_make_acceptance_with_peers("vpnprofile-global-test", "vpnprofile-global-test")]

    mgr._validate_vpn_profiles_for_acceptances(acceptances)  # pylint: disable=protected-access
    mgr.gsdk.get_global_ipsec_profiles.assert_called_once()


def test_validate_vpn_profiles_ipsec_gateway_peers_missing_raises() -> None:
    """ipsecGatewayPeers: unknown VPN profile raises ConfigurationError."""
    mgr = _make_manager()
    mgr.gsdk.get_global_ipsec_profiles.return_value = {"other-profile": MagicMock()}
    acceptances = [_make_acceptance_with_peers("vpnprofile-global-test")]

    with pytest.raises(ConfigurationError, match="vpnprofile-global-test"):
        mgr._validate_vpn_profiles_for_acceptances(acceptances)  # pylint: disable=protected-access


def test_validate_vpn_profiles_deduplicates_across_peers() -> None:
    """Same VPN profile used by multiple peers triggers only one portal lookup."""
    mgr = _make_manager()
    mgr.gsdk.get_global_ipsec_profiles.return_value = {"shared-profile": MagicMock()}
    acceptances = [_make_acceptance_with_peers("shared-profile", "shared-profile")]

    mgr._validate_vpn_profiles_for_acceptances(acceptances)  # pylint: disable=protected-access
    mgr.gsdk.get_global_ipsec_profiles.assert_called_once()


# ---- _fill_missing_tunnel_values: multi-peer tests ----


def _peer(name: str) -> dict:
    return {
        "name": name,
        "tunnel1": {"insideIpv4Cidr": None, "insideIpv6Cidr": None, "psk": None},
        "tunnel2": {"insideIpv4Cidr": None, "insideIpv6Cidr": None, "psk": None},
    }


def test_fill_missing_tunnel_values_multi_peer_fills_all_peers() -> None:
    """All tunnels across N peers are filled when values are null."""
    mgr = _make_manager()
    mgr.gsdk.get_ipsec_inside_subnet.side_effect = lambda r, s, proto: "10.0.0.0/30" if proto == "ipv4" else "::1/127"
    mgr.gsdk.get_preshared_key.return_value = "secret"

    config = {
        "siteToSiteVpn": {
            "ipsecGatewayPeers": {"remotePeers": [_peer("peer-1"), _peer("peer-2")]}
        }
    }
    mgr._fill_missing_tunnel_values(config, region_id=1, lan_segment_id=2)  # pylint: disable=protected-access

    peers = config["siteToSiteVpn"]["ipsecGatewayPeers"]["remotePeers"]
    for peer in peers:
        for tunnel_key in ("tunnel1", "tunnel2"):
            assert peer[tunnel_key]["insideIpv4Cidr"] == "10.0.0.0/30"
            assert peer[tunnel_key]["psk"] == "secret"


def test_fill_missing_tunnel_values_already_set_not_overwritten() -> None:
    """Pre-filled tunnel values are preserved when not null; no portal calls made."""
    mgr = _make_manager()
    config = {
        "siteToSiteVpn": {
            "ipsecGatewayPeers": {
                "remotePeers": [
                    {
                        "name": "peer-1",
                        "tunnel1": {"insideIpv4Cidr": "192.168.1.0/30", "insideIpv6Cidr": "::1/127", "psk": "existing"},
                        "tunnel2": {"insideIpv4Cidr": "192.168.2.0/30", "insideIpv6Cidr": "::2/127", "psk": "existing"},
                    }
                ]
            }
        }
    }
    mgr._fill_missing_tunnel_values(config, region_id=1, lan_segment_id=2)  # pylint: disable=protected-access

    peer = config["siteToSiteVpn"]["ipsecGatewayPeers"]["remotePeers"][0]
    assert peer["tunnel1"]["insideIpv4Cidr"] == "192.168.1.0/30"
    assert peer["tunnel1"]["psk"] == "existing"
    mgr.gsdk.get_ipsec_inside_subnet.assert_not_called()
    mgr.gsdk.get_preshared_key.assert_not_called()
