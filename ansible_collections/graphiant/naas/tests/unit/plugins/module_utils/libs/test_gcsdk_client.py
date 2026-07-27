# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for GraphiantPortalClient helpers (no live SDK / API)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ansible_collections.graphiant.naas.plugins.module_utils.libs.gcsdk_client import (
    ApiException,
    GraphiantPortalClient,
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
    client.api.v1_extranets_b2b_peering_match_services_summary_id_get.return_value = None

    result = client.get_matched_services_for_customer(customer_id=42)

    assert result == []


def test_get_matched_services_for_customer_response_without_services_attr_returns_empty() -> None:
    """Response object with no 'services' attribute returns empty list without error."""
    client = _make_client()
    response = MagicMock(spec=[])  # no attributes
    client.api.v1_extranets_b2b_peering_match_services_summary_id_get.return_value = response

    result = client.get_matched_services_for_customer(customer_id=42)

    assert result == []


def test_get_matched_services_for_customer_returns_services() -> None:
    """Valid response with services list is returned as-is."""
    client = _make_client()
    services = [MagicMock(), MagicMock()]
    response = MagicMock()
    response.services = services
    client.api.v1_extranets_b2b_peering_match_services_summary_id_get.return_value = response

    result = client.get_matched_services_for_customer(customer_id=42)

    assert result == services


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


def test_create_extranet_b2b_producer_raises_on_error_response() -> None:
    """
    Regression: a raw producer POST that returns HTTP 500 with a JSON error body (e.g.
    "sites are required") must raise, not be logged/returned as a successfully created
    service with id=None.
    """
    client = _make_client()
    client.api.api_client.param_serialize.return_value = ("POST", "url", {}, {}, {})
    client.api.api_client.call_api.return_value = MagicMock(
        status=500, data=b'{"errorCode":13,"displayError":"sites are required","detailedError":"sites are required"}'
    )

    with pytest.raises(ApiException):
        client._create_extranet_b2b_producer(
            {"serviceName": "svc", "type": "client_to_server", "policy": {"sites": []}}
        )


def test_create_extranet_b2b_producer_returns_id_on_success() -> None:
    client = _make_client()
    client.api.api_client.param_serialize.return_value = ("POST", "url", {}, {}, {})
    client.api.api_client.call_api.return_value = MagicMock(status=200, data=b'{"id": 123}')

    result = client._create_extranet_b2b_producer(
        {"serviceName": "svc", "type": "client_to_server", "policy": {"sites": []}}
    )

    assert result == {"id": 123}
