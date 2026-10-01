# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for GraphiantPortalClient helpers (no live SDK / API)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from ansible_collections.graphiant.naas.plugins.module_utils.libs.gcsdk_client import (
    ApiException,
    GraphiantPortalClient,
    ValidationError,
)


def _make_client() -> GraphiantPortalClient:
    """Bypass __init__ (requires live SDK) and inject mock attributes."""
    with patch.object(GraphiantPortalClient, "__init__", return_value=None):
        client = GraphiantPortalClient()
    client.api = MagicMock()
    client.bearer_token = "test-token"
    return client


# ---- get_matched_services_for_customer: None-guard regression tests ----


def test_get_matched_services_for_customer_none_response_returns_empty() -> None:
    """API returning None must not raise TypeError — regression for getattr guard."""
    client = _make_client()
    client.api.v1_extranet_b2b_customers_id_matches_summary_get.return_value = None

    result = client.get_matched_services_for_customer(customer_id=42)

    assert result == []


def test_get_matched_services_for_customer_response_without_matches_attr_returns_empty() -> None:
    """Response object with no 'matches' attribute returns empty list without error."""
    client = _make_client()
    response = MagicMock(spec=[])  # no attributes
    client.api.v1_extranet_b2b_customers_id_matches_summary_get.return_value = response

    result = client.get_matched_services_for_customer(customer_id=42)

    assert result == []


def test_get_matched_services_for_customer_returns_matches() -> None:
    """
    Valid response with a matches list is returned as-is. Regression: the generic
    endpoint renamed the response wrapper field from "services" to "matches".
    """
    client = _make_client()
    matches = [MagicMock(), MagicMock()]
    response = MagicMock()
    response.matches = matches
    client.api.v1_extranet_b2b_customers_id_matches_summary_get.return_value = response

    result = client.get_matched_services_for_customer(customer_id=42)

    assert result == matches
    client.api.v1_extranet_b2b_customers_id_matches_summary_get.assert_called_once_with(
        authorization="test-token", id=42
    )


# ---- _raise_for_raw_status: regression for silently-swallowed raw call_api() errors ----
#
# Live tenant testing found that a raw api_client.call_api() error response (e.g. HTTP 500
# with a JSON error body) was being parsed and returned as if it were a success, because the
# raw param_serialize()/call_api() pattern — unlike the SDK's typed generated methods — never
# raises based on the HTTP status code on its own.


def test_raise_for_raw_status_does_not_raise_for_2xx() -> None:
    response = MagicMock(status=200, data=b'{"id": 123}')
    GraphiantPortalClient._raise_for_raw_status(response)  # must not raise


@pytest.mark.parametrize("status", [400, 404, 500])
def test_raise_for_raw_status_raises_for_non_2xx(status: int) -> None:
    response = MagicMock(status=status, data=b'{"errorCode":13,"displayError":"sites are required"}')
    with pytest.raises(ApiException):
        GraphiantPortalClient._raise_for_raw_status(response)


# ---- get_data_exchange_services_summary: raw generic-endpoint calls (both service types) ----
#
# Confirmed via live testing that GET /v1/extranet/b2b/services/summary?serviceType=<type>
# returns entries for peering_service the same way it already did for client_to_server, so the
# old /v1/extranets-b2b-general/services-summary endpoint is no longer called here at all.


def _raw_summary_response(payload: dict) -> MagicMock:
    response = MagicMock(status=200, data=json.dumps(payload).encode())
    response.read = MagicMock()
    return response


def test_get_data_exchange_services_summary_merges_both_types() -> None:
    client = _make_client()
    client.api.api_client.param_serialize.return_value = ("GET", "url", {}, None, {})
    client.api.api_client.call_api.side_effect = [
        _raw_summary_response(
            {
                "services": [
                    {
                        "id": 1,
                        "serviceName": "peer-1",
                        "serviceType": "peering_service",
                        "status": "ACTIVE",
                        "isPublisher": True,
                        "totalCustomers": 2,
                    }
                ]
            }
        ),
        _raw_summary_response(
            {
                "services": [
                    {
                        "id": 2,
                        "serviceName": "c2s-1",
                        "serviceType": "client_to_server",
                        "status": "ACTIVE",
                        "isPublisher": True,
                        "totalCustomers": 0,
                    }
                ]
            }
        ),
    ]

    result = client.get_data_exchange_services_summary()

    types_by_id = {s.id: s.type for s in result.info}
    assert types_by_id == {1: "peering_service", 2: "client_to_server"}
    assert client.api.api_client.call_api.call_count == 2


def test_get_data_exchange_services_summary_one_type_failure_still_returns_other() -> None:
    """
    Regression: a failure fetching one service type (e.g. tenant doesn't support it yet)
    must not prevent the other type's entries from being returned.
    """
    client = _make_client()
    client.api.api_client.param_serialize.return_value = ("GET", "url", {}, None, {})
    client.api.api_client.call_api.side_effect = [
        ApiException(status=500, reason="not supported"),
        _raw_summary_response(
            {
                "services": [
                    {
                        "id": 2,
                        "serviceName": "c2s-1",
                        "serviceType": "client_to_server",
                        "status": "ACTIVE",
                        "isPublisher": True,
                        "totalCustomers": 0,
                    }
                ]
            }
        ),
    ]

    result = client.get_data_exchange_services_summary()

    assert [s.id for s in result.info] == [2]


def test_get_data_exchange_services_summary_both_types_fail_returns_empty() -> None:
    client = _make_client()
    client.api.api_client.param_serialize.return_value = ("GET", "url", {}, None, {})
    client.api.api_client.call_api.side_effect = ApiException(status=500, reason="down")

    result = client.get_data_exchange_services_summary()

    assert result.info == []
    assert result.to_dict() == {"info": []}


def test_create_data_exchange_services_raises_on_error_response() -> None:
    """
    Regression: a producer POST that raises ApiException (e.g. HTTP 500 with a "sites are
    required" error) must propagate, not be swallowed as a successfully created service.
    """
    client = _make_client()
    client.api.v1_extranet_b2b_producer_post.side_effect = ApiException(status=500, reason="sites are required")

    with pytest.raises(ApiException):
        client.create_data_exchange_services(
            {"serviceName": "svc", "type": "client_to_server", "policy": {"sites": []}}
        )


def test_create_data_exchange_services_client_to_server_returns_id_on_success() -> None:
    client = _make_client()
    client.api.v1_extranet_b2b_producer_post.return_value = MagicMock(
        model_dump=MagicMock(return_value={"id": 123})
    )

    result = client.create_data_exchange_services(
        {"serviceName": "svc", "type": "client_to_server", "policy": {"sites": []}}
    )

    assert result == {"id": 123}
    kwargs = client.api.v1_extranet_b2b_producer_post.call_args.kwargs
    assert kwargs["v1_extranet_b2b_producer_post_request"]["serviceType"] == "client_to_server"


def test_create_data_exchange_services_service_type_key() -> None:
    """"serviceType" (matching the API field name directly) is the primary config key."""
    client = _make_client()
    client.api.v1_extranet_b2b_producer_post.return_value = MagicMock(
        model_dump=MagicMock(return_value={"id": 789})
    )

    result = client.create_data_exchange_services(
        {"serviceName": "svc", "serviceType": "client_to_server", "policy": {"sites": []}}
    )

    assert result == {"id": 789}
    kwargs = client.api.v1_extranet_b2b_producer_post.call_args.kwargs
    assert kwargs["v1_extranet_b2b_producer_post_request"]["serviceType"] == "client_to_server"


def test_create_data_exchange_services_service_type_takes_precedence_over_legacy_type() -> None:
    """When both are present, "serviceType" wins over the legacy "type" alias."""
    client = _make_client()
    client.api.v1_extranet_b2b_producer_post.return_value = MagicMock(
        model_dump=MagicMock(return_value={"id": 790})
    )

    client.create_data_exchange_services(
        {"serviceName": "svc", "serviceType": "client_to_server", "type": "peering_service", "policy": {"sites": []}}
    )

    kwargs = client.api.v1_extranet_b2b_producer_post.call_args.kwargs
    assert kwargs["v1_extranet_b2b_producer_post_request"]["serviceType"] == "client_to_server"


def test_create_data_exchange_services_peering_translates_site_and_type() -> None:
    """
    Regression: peering_service configs use "site" (singular) and a "type" key inside
    policy — both must be translated for the generic producer API, which uses "sites"
    (plural, same inner shape) and forbids "type" inside policy.
    """
    client = _make_client()
    client.api.v1_extranet_b2b_producer_post.return_value = MagicMock(
        model_dump=MagicMock(return_value={"id": 456})
    )

    result = client.create_data_exchange_services(
        {
            "serviceName": "svc",
            "type": "peering_service",
            "policy": {
                "type": "peering_service",
                "serviceLanSegment": 1,
                "site": [{"sites": [1, 2], "siteLists": []}],
            },
        }
    )

    assert result == {"id": 456}
    kwargs = client.api.v1_extranet_b2b_producer_post.call_args.kwargs
    request_body = kwargs["v1_extranet_b2b_producer_post_request"]
    assert request_body["serviceType"] == "peering_service"
    assert "type" not in request_body["policy"]
    assert "site" not in request_body["policy"]
    assert request_body["policy"]["sites"] == [{"sites": [1, 2], "siteLists": []}]


# ---- check_mode: regression for schema/SDK-version mismatches silently passing --check ----
#
# check_mode previously only json.dumps'd the raw dict, so a payload that wouldn't pass
# pydantic schema validation — or an installed graphiant-sdk too old to even have the
# request model (pre-26.7.0) — would pass `--check` and then fail on the real run.


def test_create_data_exchange_services_check_mode_validates_payload() -> None:
    client = _make_client()
    client.check_mode = True

    result = client.create_data_exchange_services(
        {
            "serviceName": "svc",
            "type": "peering_service",
            "policy": {"serviceLanSegment": 1, "site": [{"sites": [1], "siteLists": []}]},
        }
    )

    assert result == {"id": 0}
    client.api.v1_extranet_b2b_producer_post.assert_not_called()


def test_create_data_exchange_services_check_mode_raises_on_invalid_payload() -> None:
    client = _make_client()
    client.check_mode = True

    with pytest.raises(ValidationError):
        client.create_data_exchange_services(
            {"serviceName": "svc", "policy": {"serviceLanSegment": "not-an-int"}}
        )


def test_edit_data_exchange_service_check_mode_validates_payload() -> None:
    client = _make_client()
    client.check_mode = True

    result = client.edit_data_exchange_service(7707, {"policy": {"prefixTags": [{"prefix": "10.1.1.0/24"}]}})

    assert result.id == 7707
    client.api.v1_extranet_b2b_producer_id_put.assert_not_called()


def test_edit_data_exchange_service_check_mode_raises_on_invalid_payload() -> None:
    client = _make_client()
    client.check_mode = True

    with pytest.raises(ValidationError):
        client.edit_data_exchange_service(7707, {"policy": {"serviceLanSegment": "not-an-int"}})


def test_edit_data_exchange_service_translates_peering_shape() -> None:
    """
    Regression: peering_service update payloads carry a top-level "id" and a
    policy.type/"site" (singular) — "id" must be dropped, "type" dropped, and "site"
    renamed to "sites" (plural, same inner shape) for the generic PUT schema.
    """
    client = _make_client()
    client.api.v1_extranet_b2b_producer_id_put.return_value = MagicMock()

    client.edit_data_exchange_service(
        8417,
        {
            "id": 8417,
            "policy": {
                "serviceLanSegment": 523387,
                "type": "peering_service",
                "site": [{"sites": [13894, 13893], "siteLists": []}],
                "description": "de-service-1 desc",
                "prefixTags": [{"prefix": "10.1.1.0/24", "tag": "s-1-prefix1"}],
                "globalObjectOps": {},
            },
        },
    )

    kwargs = client.api.v1_extranet_b2b_producer_id_put.call_args.kwargs
    assert kwargs["id"] == 8417
    body = kwargs["v1_extranet_b2b_producer_id_put_request"]
    assert "type" not in body["policy"]
    assert "site" not in body["policy"]
    assert body["policy"]["sites"] == [{"sites": [13894, 13893], "siteLists": []}]


def test_edit_data_exchange_service_client_to_server_shape_passes_through() -> None:
    """client_to_server update payloads already use "sites" and have no "type" to drop."""
    client = _make_client()
    client.api.v1_extranet_b2b_producer_id_put.return_value = MagicMock()

    client.edit_data_exchange_service(
        8418,
        {"policy": {"prefixTags": [{"prefix": "10.48.52.154/31"}], "sites": [{"sites": [13894], "siteLists": []}]}},
    )

    kwargs = client.api.v1_extranet_b2b_producer_id_put.call_args.kwargs
    body = kwargs["v1_extranet_b2b_producer_id_put_request"]
    assert body["policy"]["sites"] == [{"sites": [13894], "siteLists": []}]


def test_edit_data_exchange_service_raises_on_error_response() -> None:
    client = _make_client()
    client.api.v1_extranet_b2b_producer_id_put.side_effect = ApiException(status=500, reason="invalid update")

    with pytest.raises(ApiException):
        client.edit_data_exchange_service(8417, {"id": 8417, "policy": {"type": "peering_service"}})


# ---- create_data_exchange_customers: peering -> generic extranet customers migration ----


def test_create_data_exchange_customers_translates_admin_email_and_returns_id() -> None:
    """
    Regression: existing configs use "adminEmail" (singular) — must be translated to
    "adminEmails" (plural) since the generic invite schema renamed the field.
    """
    client = _make_client()
    client.api.v1_extranet_b2b_customers_post.return_value = MagicMock(
        model_dump=MagicMock(return_value={"id": 789})
    )

    result = client.create_data_exchange_customers(
        {
            "name": "FinanceInc",
            "type": "non_graphiant_peer",
            "invite": {"adminEmail": ["finance@financeinc.com"], "maximumNumberOfSites": 2},
        }
    )

    assert result == {"id": 789}
    kwargs = client.api.v1_extranet_b2b_customers_post.call_args.kwargs
    request_body = kwargs["v1_extranet_b2b_customers_post_request"]
    assert "adminEmail" not in request_body["invite"]
    assert request_body["invite"]["adminEmails"] == ["finance@financeinc.com"]
    assert request_body["invite"]["maximumNumberOfSites"] == 2


def test_create_data_exchange_customers_raises_on_error_response() -> None:
    client = _make_client()
    client.api.v1_extranet_b2b_customers_post.side_effect = ApiException(status=500, reason="invalid customer")

    with pytest.raises(ApiException):
        client.create_data_exchange_customers(
            {
                "name": "FinanceInc",
                "type": "non_graphiant_peer",
                "invite": {"adminEmail": [], "maximumNumberOfSites": 1},
            }
        )


def test_create_data_exchange_customers_check_mode_validates_payload() -> None:
    client = _make_client()
    client.check_mode = True

    result = client.create_data_exchange_customers(
        {
            "name": "FinanceInc",
            "type": "non_graphiant_peer",
            "invite": {"adminEmail": ["finance@financeinc.com"], "maximumNumberOfSites": 2},
        }
    )

    assert result == {"id": 0}
    client.api.v1_extranet_b2b_customers_post.assert_not_called()


def test_create_data_exchange_customers_check_mode_raises_on_invalid_payload() -> None:
    client = _make_client()
    client.check_mode = True

    with pytest.raises(ValidationError):
        client.create_data_exchange_customers(
            {"name": "FinanceInc", "type": "non_graphiant_peer", "invite": {"maximumNumberOfSites": "not-an-int"}}
        )


# ---- get_data_exchange_customer_details: peering -> generic extranet customers migration ----


def test_get_data_exchange_customer_details_translates_admin_emails() -> None:
    """
    Regression: callers (data_exchange_manager.py) read "emails"/"numSites" from this
    dict, unchanged from the old peering response shape — the generic response renamed
    "emails" to "adminEmails", so it must be translated back.
    """
    client = _make_client()
    client.api.v1_extranet_b2b_customers_id_details_get.return_value = MagicMock(
        model_dump=MagicMock(
            return_value={
                "name": "FinanceInc",
                "type": "non_graphiant_peer",
                "status": "B2B_PEERING_SERVICE_STATUS_INACTIVE",
                "numSites": 2,
                "adminEmails": ["finance@financeinc.com"],
            }
        )
    )

    result = client.get_data_exchange_customer_details(4070)

    assert result["emails"] == ["finance@financeinc.com"]
    assert "adminEmails" not in result
    assert result["numSites"] == 2
    client.api.v1_extranet_b2b_customers_id_details_get.assert_called_once_with(
        authorization="test-token", id=4070
    )


def test_get_data_exchange_customer_details_raises_on_error_response() -> None:
    client = _make_client()
    client.api.v1_extranet_b2b_customers_id_details_get.side_effect = ApiException(status=404, reason="not found")

    with pytest.raises(ApiException):
        client.get_data_exchange_customer_details(4070)


# ---- edit_data_exchange_customer: peering -> generic extranet customers migration ----


def test_edit_data_exchange_customer_translates_admin_email_and_drops_id_status() -> None:
    """
    Regression: the generic PUT body is {"invite": {...}} only — the old peering-shaped
    update_payload's "id"/"status" keys must be dropped, and "adminEmail" (singular)
    translated to "adminEmails" (plural).
    """
    client = _make_client()
    client.api.v1_extranet_b2b_customers_id_put.return_value = MagicMock()

    client.edit_data_exchange_customer(
        4070,
        {
            "id": 4070,
            "status": "",
            "invite": {"adminEmail": ["finance@financeinc.com", "admin@financeinc.com"], "maximumNumberOfSites": 2},
        },
    )

    kwargs = client.api.v1_extranet_b2b_customers_id_put.call_args.kwargs
    assert kwargs["id"] == 4070
    body = kwargs["v1_extranet_b2b_customers_id_put_request"]
    assert body == {
        "invite": {
            "adminEmails": ["finance@financeinc.com", "admin@financeinc.com"],
            "maximumNumberOfSites": 2,
        }
    }


def test_edit_data_exchange_customer_raises_on_error_response() -> None:
    client = _make_client()
    client.api.v1_extranet_b2b_customers_id_put.side_effect = ApiException(status=500, reason="invalid update")

    with pytest.raises(ApiException):
        client.edit_data_exchange_customer(4070, {"invite": {"adminEmail": [], "maximumNumberOfSites": 1}})


def test_edit_data_exchange_customer_check_mode_validates_payload() -> None:
    client = _make_client()
    client.check_mode = True

    result = client.edit_data_exchange_customer(
        4070, {"invite": {"adminEmail": ["finance@financeinc.com"], "maximumNumberOfSites": 2}}
    )

    assert result.id == 4070
    client.api.v1_extranet_b2b_customers_id_put.assert_not_called()


def test_edit_data_exchange_customer_check_mode_raises_on_invalid_payload() -> None:
    client = _make_client()
    client.check_mode = True

    with pytest.raises(ValidationError):
        client.edit_data_exchange_customer(4070, {"invite": {"maximumNumberOfSites": "not-an-int"}})


# ---- delete_data_exchange_customer: peering -> generic extranet customers migration ----


def test_delete_data_exchange_customer_calls_generic_endpoint() -> None:
    client = _make_client()
    client.api.v1_extranet_b2b_customers_id_delete.return_value = MagicMock()

    client.delete_data_exchange_customer(4070)

    client.api.v1_extranet_b2b_customers_id_delete.assert_called_once_with(authorization="test-token", id=4070)


def test_delete_data_exchange_customer_raises_on_error_response() -> None:
    client = _make_client()
    client.api.v1_extranet_b2b_customers_id_delete.side_effect = ApiException(status=404, reason="not found")

    with pytest.raises(ApiException):
        client.delete_data_exchange_customer(4070)


def test_delete_data_exchange_customer_check_mode_does_not_call_api() -> None:
    client = _make_client()
    client.check_mode = True

    client.delete_data_exchange_customer(4070)

    client.api.v1_extranet_b2b_customers_id_delete.assert_not_called()


# ---- get_data_exchange_customers_summary: peering -> generic extranet customers migration ----


def test_get_data_exchange_customers_summary_calls_generic_endpoint() -> None:
    client = _make_client()
    response = MagicMock(customers=[MagicMock(), MagicMock()])
    client.api.v1_extranet_b2b_customers_summary_get.return_value = response

    result = client.get_data_exchange_customers_summary()

    assert result is response
    client.api.v1_extranet_b2b_customers_summary_get.assert_called_once_with(authorization="test-token")


def test_get_data_exchange_customers_summary_raises_on_error_response() -> None:
    client = _make_client()
    client.api.v1_extranet_b2b_customers_summary_get.side_effect = ApiException(status=500, reason="server error")

    with pytest.raises(ApiException):
        client.get_data_exchange_customers_summary()


# ---- get_matching_customers_for_service: peering -> generic extranet producer migration ----


def test_get_matching_customers_for_service_translates_item_fields() -> None:
    """
    Regression: the generic endpoint renames the response wrapper field from "info" to
    "customers", and each item's "name"/"adminEmails"/"type" must be translated back to
    "customer_name"/"emails"/"peer_type" — the attribute names callers already read
    (data_exchange_manager.py).
    """
    client = _make_client()
    item = MagicMock(
        customer_id="cust-1",
        admin_emails=["finance@financeinc.com"],
        match_id=6532,
        matched_services=1,
        type="non_graphiant_peer",
        status="EXTRANET_SERVICE_STATUS_ACTIVE",
        updated_at=None,
    )
    item.name = "FinanceInc"  # "name" is a reserved MagicMock constructor kwarg, set separately
    client.api.v1_extranet_b2b_producer_id_customers_get.return_value = MagicMock(customers=[item])

    result = client.get_matching_customers_for_service(8417)

    assert len(result) == 1
    assert result[0].customer_name == "FinanceInc"
    assert result[0].emails == ["finance@financeinc.com"]
    assert result[0].peer_type == "non_graphiant_peer"
    assert result[0].match_id == 6532
    assert result[0].status == "EXTRANET_SERVICE_STATUS_ACTIVE"
    client.api.v1_extranet_b2b_producer_id_customers_get.assert_called_once_with(
        authorization="test-token", id=8417
    )


def test_get_matching_customers_for_service_none_response_returns_empty() -> None:
    client = _make_client()
    client.api.v1_extranet_b2b_producer_id_customers_get.return_value = None

    result = client.get_matching_customers_for_service(8417)

    assert result == []


def test_get_matching_customers_for_service_raises_returns_none() -> None:
    client = _make_client()
    client.api.v1_extranet_b2b_producer_id_customers_get.side_effect = ApiException(status=404, reason="not found")

    result = client.get_matching_customers_for_service(8417)

    assert result is None


# ---- match_service_to_customer: peering -> generic extranet matches migration ----


def test_match_service_to_customer_translates_nat_to_peer_to_peer() -> None:
    """
    Regression: the old peering-shaped payload's flat "nat" list (each {"prefix",
    "outsideNatPrefix"}) must map onto the generic schema's
    "match.natTranslationMode.peerToPeer.prefixes" (same item shape, nested deeper);
    "id"/"service.id" must become "customerId"/"match.serviceId".
    """
    client = _make_client()
    client.api.v1_extranet_b2b_matches_post.return_value = MagicMock(match_id=6532)

    match_config = {
        "id": 4071,
        "service": {
            "id": 8417,
            "servicePrefixes": [{"prefix": "10.1.1.0/24", "tag": "s-1-prefix1"}],
            "nat": [{"prefix": "10.101.1.0/24", "outsideNatPrefix": "170.101.1.0/24"}],
        },
    }

    result = client.match_service_to_customer(match_config)

    assert result.match_id == 6532
    kwargs = client.api.v1_extranet_b2b_matches_post.call_args.kwargs
    request_body = kwargs["v1_extranet_b2b_matches_post_request"]
    assert request_body == {
        "customerId": 4071,
        "match": {
            "serviceId": 8417,
            "servicePrefixes": [{"prefix": "10.1.1.0/24", "tag": "s-1-prefix1"}],
            "natTranslationMode": {
                "peerToPeer": {"prefixes": [{"prefix": "10.101.1.0/24", "outsideNatPrefix": "170.101.1.0/24"}]}
            },
        },
    }


def test_match_service_to_customer_omits_nat_translation_mode_when_no_nat() -> None:
    client = _make_client()
    client.api.v1_extranet_b2b_matches_post.return_value = MagicMock(match_id=6533)

    client.match_service_to_customer(
        {"id": 4071, "service": {"id": 8417, "servicePrefixes": [{"prefix": "10.1.1.0/24"}], "nat": []}}
    )

    kwargs = client.api.v1_extranet_b2b_matches_post.call_args.kwargs
    request_body = kwargs["v1_extranet_b2b_matches_post_request"]
    assert "natTranslationMode" not in request_body["match"]


def test_match_service_to_customer_accepts_nat_translation_mode_directly() -> None:
    """
    Regression: "service.natTranslationMode" (the new-shape key) must be accepted as an
    alternative to "nat", passed through as-is (no double-wrapping).
    """
    client = _make_client()
    client.api.v1_extranet_b2b_matches_post.return_value = MagicMock(match_id=6532)
    nat_translation_mode = {"peerToPeer": {"prefixes": [{"prefix": "10.101.1.0/24", "outsideNatPrefix": None}]}}

    client.match_service_to_customer(
        {
            "id": 4071,
            "service": {
                "id": 8417,
                "servicePrefixes": [{"prefix": "10.1.1.0/24"}],
                "natTranslationMode": nat_translation_mode,
            },
        }
    )

    kwargs = client.api.v1_extranet_b2b_matches_post.call_args.kwargs
    request_body = kwargs["v1_extranet_b2b_matches_post_request"]
    assert request_body["match"]["natTranslationMode"] == nat_translation_mode


def test_match_service_to_customer_nat_translation_mode_wins_over_nat() -> None:
    client = _make_client()
    client.api.v1_extranet_b2b_matches_post.return_value = MagicMock(match_id=6532)
    nat_translation_mode = {"peerToPeer": {"prefixes": [{"prefix": "10.101.1.0/24"}]}}

    client.match_service_to_customer(
        {
            "id": 4071,
            "service": {
                "id": 8417,
                "servicePrefixes": [],
                "nat": [{"prefix": "10.999.1.0/24", "outsideNatPrefix": "170.999.1.0/24"}],
                "natTranslationMode": nat_translation_mode,
            },
        }
    )

    kwargs = client.api.v1_extranet_b2b_matches_post.call_args.kwargs
    request_body = kwargs["v1_extranet_b2b_matches_post_request"]
    assert request_body["match"]["natTranslationMode"] == nat_translation_mode


def test_match_service_to_customer_raises_on_error_response() -> None:
    client = _make_client()
    client.api.v1_extranet_b2b_matches_post.side_effect = ApiException(status=500, reason="match already exists")

    with pytest.raises(ApiException):
        client.match_service_to_customer(
            {"id": 4071, "service": {"id": 8417, "servicePrefixes": [{"prefix": "10.1.1.0/24"}], "nat": []}}
        )


def test_match_service_to_customer_check_mode_validates_payload() -> None:
    client = _make_client()
    client.check_mode = True

    result = client.match_service_to_customer(
        {
            "id": 4071,
            "service": {
                "id": 8417,
                "servicePrefixes": [{"prefix": "10.1.1.0/24", "tag": "s-1-prefix1"}],
                "nat": [{"prefix": "10.101.1.0/24", "outsideNatPrefix": "170.101.1.0/24"}],
            },
        }
    )

    assert result.match_id == 0
    client.api.v1_extranet_b2b_matches_post.assert_not_called()


def test_match_service_to_customer_check_mode_raises_on_invalid_payload() -> None:
    client = _make_client()
    client.check_mode = True

    with pytest.raises(ValidationError):
        client.match_service_to_customer({"id": "not-an-int", "service": {"id": 8417, "servicePrefixes": []}})


# ---- accept_data_exchange_service: peering -> generic extranet matches migration ----


def _acceptance_payload() -> dict:
    """
    Already in the generic API's own shape — this is what DataExchangeManager.
    _resolve_acceptance_names_to_ids now builds (list->dict / nat translation happens
    there, not in gcsdk_client.py anymore).
    """
    return {
        "id": 8417,
        "policy": {
            "sites": [{"sites": [13894, 13893], "siteLists": []}],
            "consumerLanSegments": {"523387": {"consumerPrefixes": ["10.101.2.0/24"]}},
            "natTranslationMode": {
                "peerToPeer": {"prefixes": [{"prefix": "10.101.1.0/24", "outsideNatPrefix": "170.101.1.0/24"}]}
            },
            "siteToSiteVpn": {"regionId": 5, "emails": ["a@b.com"]},
            "globalObjectOps": {},
        },
    }


def test_accept_data_exchange_service_passes_through_policy() -> None:
    """
    Regression: the only transform left here is top-level "id" -> "serviceId"; "policy"
    is passed through unchanged (already built in the generic shape by the caller).
    """
    client = _make_client()
    client.api.v1_extranet_b2b_matches_match_id_consumer_post.return_value = MagicMock()

    client.accept_data_exchange_service(6534, _acceptance_payload())

    kwargs = client.api.v1_extranet_b2b_matches_match_id_consumer_post.call_args.kwargs
    assert kwargs["match_id"] == 6534
    body = kwargs["v1_extranet_b2b_matches_match_id_consumer_post_request"]
    assert body["serviceId"] == 8417
    assert body["policy"]["sites"] == [{"sites": [13894, 13893], "siteLists": []}]
    assert body["policy"]["consumerLanSegments"] == {"523387": {"consumerPrefixes": ["10.101.2.0/24"]}}
    assert body["policy"]["natTranslationMode"] == {
        "peerToPeer": {"prefixes": [{"prefix": "10.101.1.0/24", "outsideNatPrefix": "170.101.1.0/24"}]}
    }
    assert body["policy"]["siteToSiteVpn"] == {"regionId": 5, "emails": ["a@b.com"]}


def test_accept_data_exchange_service_client_to_server_omits_nat_translation_mode() -> None:
    """
    Regression: confirmed against a real client_to_server acceptance capture (portal UI) —
    that payload has no "natTranslationMode" key at all (client_to_server NAT is
    producer-side, set at service creation, not per-acceptance). Everything else (sites,
    consumerLanSegments, siteToSiteVpn, globalObjectOps) is structurally identical to
    peering_service.
    """
    client = _make_client()
    client.api.v1_extranet_b2b_matches_match_id_consumer_post.return_value = MagicMock()
    payload = _acceptance_payload()
    del payload["policy"]["natTranslationMode"]

    client.accept_data_exchange_service(6537, payload)

    kwargs = client.api.v1_extranet_b2b_matches_match_id_consumer_post.call_args.kwargs
    body = kwargs["v1_extranet_b2b_matches_match_id_consumer_post_request"]
    assert "natTranslationMode" not in body["policy"]
    assert body["policy"]["sites"] == [{"sites": [13894, 13893], "siteLists": []}]
    assert body["policy"]["consumerLanSegments"] == {"523387": {"consumerPrefixes": ["10.101.2.0/24"]}}


def test_accept_data_exchange_service_raises_on_error_response() -> None:
    client = _make_client()
    client.api.v1_extranet_b2b_matches_match_id_consumer_post.side_effect = ApiException(
        status=500, reason="invalid acceptance"
    )

    with pytest.raises(ApiException):
        client.accept_data_exchange_service(6534, _acceptance_payload())


def test_accept_data_exchange_service_check_mode_does_not_call_api() -> None:
    client = _make_client()
    client.check_mode = True

    result = client.accept_data_exchange_service(6534, _acceptance_payload())

    assert result is not None
    client.api.v1_extranet_b2b_matches_match_id_consumer_post.assert_not_called()


def test_accept_data_exchange_service_check_mode_raises_on_invalid_payload() -> None:
    client = _make_client()
    client.check_mode = True

    with pytest.raises(ValidationError):
        client.accept_data_exchange_service(6534, {"id": 8417, "policy": {"sites": "not-a-list"}})


# ---- Local Extranet: gcsdk_client wire-level coverage ----
#
# Single-tenant flat policy resource (create/get/edit/delete/apply at /v1/extranets), unlike
# Data Exchange's producer/customer/match split. get_local_extranet_policies and
# edit_local_extranet_policy use the raw param_serialize()/call_api() pattern (see
# _raise_for_raw_status above); the rest are typed SDK-bound calls.


def _raw_json_response(payload: dict, status: int = 200) -> MagicMock:
    response = MagicMock(status=status, data=json.dumps(payload).encode())
    response.read = MagicMock()
    return response


def test_create_local_extranet_policy_returns_id_on_success() -> None:
    client = _make_client()
    response = MagicMock()
    response.id = None
    response.policy = MagicMock(id=555)
    response.model_dump.return_value = {"policy": {"name": "local-extranet-policy-1"}}
    client.api.v1_extranets_post.return_value = response

    result = client.create_local_extranet_policy(
        {"name": "local-extranet-policy-1", "type": "enterprise", "sharedSegment": 1, "targetSegments": [2, 3]}
    )

    assert result["id"] == 555
    kwargs = client.api.v1_extranets_post.call_args.kwargs
    assert kwargs["v1_extranets_post_request"]["policy"]["sharedSegment"] == 1


def test_create_local_extranet_policy_raises_on_error_response() -> None:
    client = _make_client()
    client.api.v1_extranets_post.side_effect = ApiException(status=500, reason="sites are required")

    with pytest.raises(ApiException):
        client.create_local_extranet_policy({"name": "local-extranet-policy-1", "sharedSegment": 1})


def test_create_local_extranet_policy_check_mode_validates_payload() -> None:
    client = _make_client()
    client.check_mode = True

    result = client.create_local_extranet_policy(
        {"name": "local-extranet-policy-1", "type": "enterprise", "sharedSegment": 1, "targetSegments": [2, 3]}
    )

    assert result == {"id": 0}
    client.api.v1_extranets_post.assert_not_called()


def test_create_local_extranet_policy_check_mode_raises_on_invalid_payload() -> None:
    client = _make_client()
    client.check_mode = True

    with pytest.raises(ValidationError):
        client.create_local_extranet_policy({"name": "local-extranet-policy-1", "sharedSegment": "not-an-int"})


def test_get_local_extranet_policies_parses_raw_response() -> None:
    client = _make_client()
    client.api.api_client.param_serialize.return_value = ("GET", "url", {}, None, {})
    client.api.api_client.call_api.return_value = _raw_json_response(
        {"policies": [{"id": 1, "name": "local-extranet-policy-1"}]}
    )

    result = client.get_local_extranet_policies()

    assert len(result) == 1
    assert result[0].id == 1
    assert result[0].name == "local-extranet-policy-1"


def test_get_local_extranet_policies_passes_type_filter_query_param() -> None:
    client = _make_client()
    client.api.api_client.param_serialize.return_value = ("GET", "url", {}, None, {})
    client.api.api_client.call_api.return_value = _raw_json_response({"policies": []})

    client.get_local_extranet_policies(type_filter="enterprise")

    kwargs = client.api.api_client.param_serialize.call_args.kwargs
    assert kwargs["query_params"] == {"type": "enterprise"}


def test_get_local_extranet_policies_returns_empty_list_on_error() -> None:
    """
    Regression: unlike most gcsdk_client getters, this one swallows the error and returns []
    rather than propagating — callers (get_local_extranet_policy_by_name, is-in-use checks)
    depend on a plain empty list, not an exception, when the endpoint is unreachable.
    """
    client = _make_client()
    client.api.api_client.param_serialize.return_value = ("GET", "url", {}, None, {})
    client.api.api_client.call_api.return_value = _raw_json_response(
        {"errorCode": 13, "displayError": "boom"}, status=500
    )

    result = client.get_local_extranet_policies()

    assert result == []


def test_get_local_extranet_policy_by_name_found() -> None:
    client = _make_client()
    policy = MagicMock(id=7)
    policy.name = "local-extranet-policy-1"  # "name" is a reserved MagicMock() constructor kwarg
    with patch.object(client, "get_local_extranet_policies", return_value=[policy]):
        result = client.get_local_extranet_policy_by_name("local-extranet-policy-1")

    assert result is policy


def test_get_local_extranet_policy_by_name_not_found() -> None:
    client = _make_client()
    with patch.object(client, "get_local_extranet_policies", return_value=[]):
        result = client.get_local_extranet_policy_by_name("missing-policy")

    assert result is None


def test_get_local_extranet_policy_details_returns_policy_dict() -> None:
    client = _make_client()
    policy_obj = MagicMock()
    policy_obj.to_dict.return_value = {"id": 42, "name": "local-extranet-policy-1"}
    client.api.v1_extranets_id_get.return_value = MagicMock(policy=policy_obj)

    result = client.get_local_extranet_policy_details(42)

    assert result == {"id": 42, "name": "local-extranet-policy-1"}


def test_get_local_extranet_policy_details_raises_on_error_response() -> None:
    client = _make_client()
    client.api.v1_extranets_id_get.side_effect = ApiException(status=404, reason="not found")

    with pytest.raises(ApiException):
        client.get_local_extranet_policy_details(42)


def test_edit_local_extranet_policy_success() -> None:
    client = _make_client()
    client.api.api_client.param_serialize.return_value = ("PUT", "url", {}, None, {})
    client.api.api_client.call_api.return_value = _raw_json_response({"policy": {"id": 42}})

    result = client.edit_local_extranet_policy(42, {"name": "local-extranet-policy-1", "type": 2, "sharedSegment": 1})

    assert result["id"] == 42
    kwargs = client.api.api_client.param_serialize.call_args.kwargs
    assert kwargs["path_params"] == {"id": 42}
    assert kwargs["body"]["policy"]["type"] == 2


def test_edit_local_extranet_policy_raises_on_non_2xx_status() -> None:
    """
    Regression: a raw call_api() error response must actually raise (see
    _raise_for_raw_status above) rather than being parsed as if it were a success.
    """
    client = _make_client()
    client.api.api_client.param_serialize.return_value = ("PUT", "url", {}, None, {})
    client.api.api_client.call_api.return_value = _raw_json_response(
        {"errorCode": 13, "displayError": "policy not found"}, status=500
    )

    with pytest.raises(ApiException):
        client.edit_local_extranet_policy(42, {"name": "local-extranet-policy-1"})


def test_edit_local_extranet_policy_check_mode_does_not_call_api() -> None:
    client = _make_client()
    client.check_mode = True

    result = client.edit_local_extranet_policy(42, {"name": "local-extranet-policy-1"})

    assert result == {"id": 42}
    client.api.api_client.call_api.assert_not_called()


def test_delete_local_extranet_policy_success() -> None:
    client = _make_client()
    client.api.v1_extranets_id_delete.return_value = MagicMock()

    client.delete_local_extranet_policy(42)

    client.api.v1_extranets_id_delete.assert_called_once_with(authorization="test-token", id=42)


def test_delete_local_extranet_policy_raises_on_error_response() -> None:
    client = _make_client()
    client.api.v1_extranets_id_delete.side_effect = ApiException(status=404, reason="not found")

    with pytest.raises(ApiException):
        client.delete_local_extranet_policy(42)


def test_delete_local_extranet_policy_check_mode_does_not_call_api() -> None:
    client = _make_client()
    client.check_mode = True

    client.delete_local_extranet_policy(42)

    client.api.v1_extranets_id_delete.assert_not_called()


def test_apply_local_extranet_policy_without_target_devices_omits_key() -> None:
    client = _make_client()
    client.api.v1_extranets_id_apply_post.return_value = MagicMock(
        model_dump=MagicMock(return_value={"devices": [], "jobId": 99})
    )

    result = client.apply_local_extranet_policy(42)

    assert result == {"devices": [], "jobId": 99}
    kwargs = client.api.v1_extranets_id_apply_post.call_args.kwargs
    assert kwargs["v1_extranets_id_apply_post_request"] == {}


def test_apply_local_extranet_policy_with_target_devices_includes_key() -> None:
    client = _make_client()
    client.api.v1_extranets_id_apply_post.return_value = MagicMock(
        model_dump=MagicMock(return_value={"devices": [], "jobId": 100})
    )

    client.apply_local_extranet_policy(42, target_device_ids=[1, 2])

    kwargs = client.api.v1_extranets_id_apply_post.call_args.kwargs
    assert kwargs["v1_extranets_id_apply_post_request"] == {"targetDevices": [1, 2]}


def test_apply_local_extranet_policy_raises_on_error_response() -> None:
    client = _make_client()
    client.api.v1_extranets_id_apply_post.side_effect = ApiException(status=500, reason="apply failed")

    with pytest.raises(ApiException):
        client.apply_local_extranet_policy(42)


def test_apply_local_extranet_policy_check_mode_does_not_call_api() -> None:
    client = _make_client()
    client.check_mode = True

    result = client.apply_local_extranet_policy(42, target_device_ids=[1])

    assert result == {"devices": [], "jobId": 0}
    client.api.v1_extranets_id_apply_post.assert_not_called()


def test_get_local_extranet_policy_device_status_returns_devices() -> None:
    client = _make_client()
    devices = [MagicMock(), MagicMock()]
    client.api.v1_extranets_id_status_get.return_value = MagicMock(devices=devices)

    result = client.get_local_extranet_policy_device_status(42)

    assert result == devices


def test_get_local_extranet_policy_device_status_raises_on_error_response() -> None:
    client = _make_client()
    client.api.v1_extranets_id_status_get.side_effect = ApiException(status=500, reason="failed")

    with pytest.raises(ApiException):
        client.get_local_extranet_policy_device_status(42)


def test_get_local_extranet_lan_segments_usage_passes_params() -> None:
    client = _make_client()
    response = MagicMock()
    client.api.v1_extranets_monitoring_lan_segments_get.return_value = response

    result = client.get_local_extranet_lan_segments_usage(policy_id=42, is_provider=True)

    assert result is response
    client.api.v1_extranets_monitoring_lan_segments_get.assert_called_once_with(
        authorization="test-token", id=42, is_provider=True
    )


def test_get_local_extranet_lan_segments_usage_raises_on_error_response() -> None:
    client = _make_client()
    client.api.v1_extranets_monitoring_lan_segments_get.side_effect = ApiException(status=500, reason="failed")

    with pytest.raises(ApiException):
        client.get_local_extranet_lan_segments_usage()


def test_get_local_extranet_nat_usage_returns_response() -> None:
    client = _make_client()
    response = MagicMock()
    client.api.v1_extranets_monitoring_nat_usage_get.return_value = response

    result = client.get_local_extranet_nat_usage(42)

    assert result is response


def test_get_local_extranet_nat_usage_raises_on_error_response() -> None:
    client = _make_client()
    client.api.v1_extranets_monitoring_nat_usage_get.side_effect = ApiException(status=500, reason="failed")

    with pytest.raises(ApiException):
        client.get_local_extranet_nat_usage(42)


# ---- put_devices_bringup / device lifecycle upgrade scheduling ----


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.gcsdk_client.time.sleep")
def test_put_devices_bringup_maps_friendly_status_names(_mock_sleep: MagicMock) -> None:
    client = _make_client()

    assert client.put_devices_bringup([1], "activated") is True
    assert client.api.v1_devices_bringup_put.call_args.kwargs["v1_devices_bringup_put_request"]["status"] == "Allowed"

    assert client.put_devices_bringup([1], "deactivated") is True
    assert client.api.v1_devices_bringup_put.call_args.kwargs["v1_devices_bringup_put_request"]["status"] == "Denied"

    assert client.put_devices_bringup([1], "decommissioned") is True
    assert client.api.v1_devices_bringup_put.call_args.kwargs["v1_devices_bringup_put_request"]["status"] == "Removed"

    assert client.put_devices_bringup([1], "staging") is True
    assert client.api.v1_devices_bringup_put.call_args.kwargs["v1_devices_bringup_put_request"]["status"] == "Pending"

    assert client.put_devices_bringup([1], "maintenance") is True
    assert (
        client.api.v1_devices_bringup_put.call_args.kwargs["v1_devices_bringup_put_request"]["status"]
        == "Maintenance"
    )


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.gcsdk_client.time.sleep")
def test_put_devices_bringup_returns_false_on_api_error(_mock_sleep: MagicMock) -> None:
    client = _make_client()
    client.api.v1_devices_bringup_put.side_effect = ApiException(status=500, reason="failed")

    assert client.put_devices_bringup([1], "activated") is False


def test_put_devices_bringup_check_mode_skips_api_call() -> None:
    client = _make_client()
    client.check_mode = True

    assert client.put_devices_bringup([1], "activated") is True
    client.api.v1_devices_bringup_put.assert_not_called()


def test_get_edges_summary_returns_list() -> None:
    client = _make_client()
    edge_1 = MagicMock(device_id=100)
    edge_2 = MagicMock(device_id=200)
    client.api.v1_edges_summary_get.return_value = MagicMock(edges_summary=[edge_1, edge_2])

    assert client.get_edges_summary() == [edge_1, edge_2]


def test_get_edges_summary_filters_by_device_id() -> None:
    client = _make_client()
    edge_1 = MagicMock(device_id=100)
    edge_2 = MagicMock(device_id=200)
    client.api.v1_edges_summary_get.return_value = MagicMock(edges_summary=[edge_1, edge_2])

    assert client.get_edges_summary(device_id=200) is edge_2


def test_get_edges_summary_returns_empty_list_when_api_omits_edges_summary() -> None:
    """
    ``GET /v1/edges-summary`` returns a bare ``{}`` (no ``edgesSummary`` key at all, not even an
    empty array) when zero devices match — e.g. every device in the enterprise has just been
    decommissioned. The SDK model then has ``edges_summary=None``, not ``[]``; this must still come
    back as ``[]``, not ``None``, since every caller (``_fetch_edges_by_hostname`` et al.) iterates
    the result directly and a bare ``None`` crashes with ``TypeError: 'NoneType' object is not
    iterable`` — exactly what a live run hit once every device in a test enterprise was
    decommissioned in the same run.
    """
    client = _make_client()
    client.api.v1_edges_summary_get.return_value = MagicMock(edges_summary=None)

    assert client.get_edges_summary() == []
    assert client.get_edges_summary(device_id=100) == []


def test_get_edges_summary_with_upgrade_passes_upgrade_summary_flag() -> None:
    client = _make_client()
    edge_cpe = MagicMock(role="cpe")
    edge_gateway = MagicMock(role="gateway")
    client.api.v1_edges_summary_get.return_value = MagicMock(edges_summary=[edge_cpe, edge_gateway])

    result = client.get_edges_summary_with_upgrade()

    client.api.v1_edges_summary_get.assert_called_once_with(authorization="test-token", upgrade_summary=True)
    assert result == [edge_cpe, edge_gateway]


def test_get_edges_summary_with_upgrade_filters_by_role() -> None:
    client = _make_client()
    edge_cpe = MagicMock(role="cpe")
    edge_gateway = MagicMock(role="gateway")
    client.api.v1_edges_summary_get.return_value = MagicMock(edges_summary=[edge_cpe, edge_gateway])

    result = client.get_edges_summary_with_upgrade(role="cpe")

    assert result == [edge_cpe]


def test_get_edges_summary_with_upgrade_filters_by_device_id() -> None:
    client = _make_client()
    edge_1 = MagicMock(role="cpe", device_id=100)
    edge_2 = MagicMock(role="cpe", device_id=200)
    client.api.v1_edges_summary_get.return_value = MagicMock(edges_summary=[edge_1, edge_2])

    assert client.get_edges_summary_with_upgrade(device_id=200) is edge_2
    assert client.get_edges_summary_with_upgrade(device_id=999) is None


# ---- poll_upgrade_schedule_completion_batch: terminal-state detection, shared per-round fetch ----


def test_poll_upgrade_schedule_completion_batch_returns_success_on_first_attempt() -> None:
    client = _make_client()
    edge = MagicMock(device_id=100)
    edge.upgrade_summary.schedule.state = "Success"
    client.api.v1_edges_summary_get.return_value = MagicMock(edges_summary=[edge])

    outcomes = client.poll_upgrade_schedule_completion_batch([100], timeout=60, wait=10)

    assert outcomes == {100: ("Success", None)}


def test_poll_upgrade_schedule_completion_batch_returns_failed_with_reason() -> None:
    client = _make_client()
    edge = MagicMock(device_id=100)
    edge.upgrade_summary.schedule.state = "Failed"
    edge.upgrade_summary.schedule.failure_reason = "Internal error"
    client.api.v1_edges_summary_get.return_value = MagicMock(edges_summary=[edge])

    outcomes = client.poll_upgrade_schedule_completion_batch([100], timeout=60, wait=10)

    assert outcomes == {100: ("Failed", "Internal error")}


def test_poll_upgrade_schedule_completion_batch_treats_intermediate_states_as_in_progress() -> None:
    """
    Any non-terminal state (the real portal was observed cycling through Idle ->
    ScheduledDownload -> Downloading -> Installing -> ScheduledActivation -> InMaintenance ->
    Activating) keeps polling instead of being misread as done; a short timeout here proves the
    loop doesn't stop early on these.
    """
    client = _make_client()
    edge = MagicMock(device_id=100)
    edge.upgrade_summary.schedule.state = "Downloading"
    client.api.v1_edges_summary_get.return_value = MagicMock(edges_summary=[edge])

    outcomes = client.poll_upgrade_schedule_completion_batch([100], timeout=0.05, wait=0.01)

    assert outcomes == {100: (None, None)}
    assert client.api.v1_edges_summary_get.call_count >= 1


def test_poll_upgrade_schedule_completion_batch_device_not_found_is_in_progress() -> None:
    """A device that disappears from edges-summary mid-poll must not raise — treated the same as
    any other non-terminal state (still in progress) until the timeout."""
    client = _make_client()
    client.api.v1_edges_summary_get.return_value = MagicMock(edges_summary=[])

    outcomes = client.poll_upgrade_schedule_completion_batch([100], timeout=0.05, wait=0.01)

    assert outcomes == {100: (None, None)}


def test_poll_upgrade_schedule_completion_batch_uses_one_shared_fetch_per_round_for_multiple_devices() -> None:
    """
    The whole point of the batch poller: N devices must not multiply the number of
    GET /v1/edges-summary calls — one shared fetch per round covers all of them, and a device
    stops being checked (removed from the next round) as soon as it reaches a terminal state.
    """
    client = _make_client()
    edge_1_round_1 = MagicMock(device_id=100)
    edge_1_round_1.upgrade_summary.schedule.state = "Success"
    edge_2_round_1 = MagicMock(device_id=200)
    edge_2_round_1.upgrade_summary.schedule.state = "Downloading"
    edge_2_round_2 = MagicMock(device_id=200)
    edge_2_round_2.upgrade_summary.schedule.state = "Success"
    client.api.v1_edges_summary_get.side_effect = [
        MagicMock(edges_summary=[edge_1_round_1, edge_2_round_1]),  # round 1: 100 done, 200 still going
        MagicMock(edges_summary=[edge_2_round_2]),  # round 2: only 200 still needs checking
    ]

    outcomes = client.poll_upgrade_schedule_completion_batch([100, 200], timeout=60, wait=0.01)

    assert outcomes == {100: ("Success", None), 200: ("Success", None)}
    # Exactly one GET per round (2 rounds), regardless of there being 2 devices to watch.
    assert client.api.v1_edges_summary_get.call_count == 2


def test_get_software_releases_summary_returns_summaries() -> None:
    client = _make_client()
    summary = MagicMock()
    client.api.v1_software_releases_summary_get.return_value = MagicMock(summaries=[summary])

    result = client.get_software_releases_summary()

    client.api.v1_software_releases_summary_get.assert_called_once_with(authorization="test-token")
    assert result == [summary]


def test_get_software_releases_summary_returns_empty_list_when_none() -> None:
    client = _make_client()
    client.api.v1_software_releases_summary_get.return_value = MagicMock(summaries=None)

    assert client.get_software_releases_summary() == []


def test_put_devices_upgrade_schedule_builds_payload() -> None:
    client = _make_client()
    device_versions = [{"deviceId": 100, "version": {"release": "Latest"}}]

    assert client.put_devices_upgrade_schedule(device_versions=device_versions, action="InstallActivate") is True

    kwargs = client.api.v1_devices_upgrade_schedule_put.call_args.kwargs
    payload = kwargs["v1_devices_upgrade_schedule_put_request"]
    assert payload["action"] == "InstallActivate"
    assert payload["deviceVersions"] == device_versions
    assert "seconds" in payload["ts"]


def test_put_devices_upgrade_schedule_uses_explicit_ts() -> None:
    client = _make_client()
    ts = {"seconds": 123, "nanos": 456}

    client.put_devices_upgrade_schedule(device_versions=[], action="Install", ts=ts)

    payload = client.api.v1_devices_upgrade_schedule_put.call_args.kwargs["v1_devices_upgrade_schedule_put_request"]
    assert payload["ts"] == ts


def test_put_devices_upgrade_schedule_returns_false_on_api_error() -> None:
    client = _make_client()
    client.api.v1_devices_upgrade_schedule_put.side_effect = ApiException(status=500, reason="failed")

    assert client.put_devices_upgrade_schedule(device_versions=[], action="InstallActivate") is False


def test_put_devices_upgrade_schedule_check_mode_skips_api_call() -> None:
    client = _make_client()
    client.check_mode = True

    assert client.put_devices_upgrade_schedule(device_versions=[], action="InstallActivate") is True
    client.api.v1_devices_upgrade_schedule_put.assert_not_called()


# ---- verify_device_portal_status: tt_conn_count threshold ----
# Only the immediate-success path is exercised here (no retries triggered): the decorated method
# is wrapped in `@poller(timeout=180, wait=15)`, so a case that's meant to fail would busy-loop
# for real wall-clock seconds in a test run — not worth it for this fix.


def test_verify_device_portal_status_ready_with_tt_conn_count_exactly_two_succeeds() -> None:
    client = _make_client()
    edge_summary = MagicMock(portal_status="Ready", tt_conn_count=2)
    client.get_edges_summary = MagicMock(return_value=edge_summary)

    client.verify_device_portal_status(100)  # must not raise

    client.get_edges_summary.assert_called_once_with(device_id=100)


def test_verify_device_portal_status_ready_with_tt_conn_count_above_two_succeeds() -> None:
    """
    More than 2 tunnel-terminator connections is fine — only fewer than 2 is a real problem.
    Previously this required an exact match (tt_conn_count == 2), which incorrectly treated a
    device with extra connections as never reaching Ready.
    """
    client = _make_client()
    edge_summary = MagicMock(portal_status="Ready", tt_conn_count=3)
    client.get_edges_summary = MagicMock(return_value=edge_summary)

    client.verify_device_portal_status(100)  # must not raise
