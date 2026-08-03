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
