# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for GraphiantPortalClient helpers (no live SDK / API)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ansible_collections.graphiant.naas.plugins.module_utils.libs.gcsdk_client import GraphiantPortalClient


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
