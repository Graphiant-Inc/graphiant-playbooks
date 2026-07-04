# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for NtpManager."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from ansible_collections.graphiant.naas.plugins.module_utils.libs.ntp_manager import NtpManager
from ansible_collections.graphiant.naas.plugins.module_utils.libs.exceptions import ConfigurationError


def _make_manager() -> NtpManager:
    config_utils = MagicMock()
    config_utils.gsdk = MagicMock()
    return NtpManager(config_utils)


# ---------------------------------------------------------------------------
# _norm_domains
# ---------------------------------------------------------------------------

def test_norm_domains_sorts_and_strips() -> None:
    assert NtpManager._norm_domains(["b.com", " a.com "]) == ["a.com", "b.com"]


def test_norm_domains_none_returns_empty() -> None:
    assert NtpManager._norm_domains(None) == []


def test_norm_domains_filters_none_entries() -> None:
    assert NtpManager._norm_domains([None, "x.com", None]) == ["x.com"]


def test_norm_domains_non_list_raises() -> None:
    with pytest.raises(ConfigurationError, match="list"):
        NtpManager._norm_domains("not-a-list")


# ---------------------------------------------------------------------------
# _payload_differs_from_existing
# ---------------------------------------------------------------------------

def _device_info(name: str, domains: list) -> dict:
    return {"device": {"ntp": {"name": name, "domains": domains}}}


def test_payload_differs_returns_true_when_domains_changed() -> None:
    mgr = _make_manager()
    payload = {"edge": {"ntpGlobalObject": {"pool-1": {"config": {"name": "pool-1", "domains": ["time.google.com"]}}}}}
    device_info = _device_info("pool-1", ["old.ntp.com"])
    assert mgr._payload_differs_from_existing(payload, device_info) is True


def test_payload_differs_returns_false_when_already_matches() -> None:
    mgr = _make_manager()
    payload = {"edge": {"ntpGlobalObject": {"pool-1": {"config": {"name": "pool-1", "domains": ["time.google.com"]}}}}}
    device_info = _device_info("pool-1", ["time.google.com"])
    assert mgr._payload_differs_from_existing(payload, device_info) is False


def test_payload_differs_deconfigure_no_op_when_already_absent() -> None:
    mgr = _make_manager()
    # config=None means deconfigure; if the object doesn't exist, no change needed
    payload = {"edge": {"ntpGlobalObject": {"ghost": {"config": None}}}}
    device_info = _device_info("pool-1", ["time.google.com"])
    assert mgr._payload_differs_from_existing(payload, device_info) is False


def test_payload_differs_deconfigure_returns_true_when_object_exists() -> None:
    mgr = _make_manager()
    payload = {"edge": {"ntpGlobalObject": {"pool-1": {"config": None}}}}
    device_info = _device_info("pool-1", ["time.google.com"])
    assert mgr._payload_differs_from_existing(payload, device_info) is True


def test_payload_differs_empty_payload_returns_false() -> None:
    mgr = _make_manager()
    assert mgr._payload_differs_from_existing({}, _device_info("pool-1", [])) is False


# ---------------------------------------------------------------------------
# _ntp_snapshot_from_device
# ---------------------------------------------------------------------------

def test_ntp_snapshot_from_device_returns_normalized_map() -> None:
    mgr = _make_manager()
    device_info = _device_info("pool-1", ["b.com", "a.com"])
    snap = mgr._ntp_snapshot_from_device(device_info)
    assert snap == {"pool-1": {"config": {"name": "pool-1", "domains": ["a.com", "b.com"]}}}


def test_ntp_snapshot_from_device_returns_empty_when_no_ntp() -> None:
    mgr = _make_manager()
    assert mgr._ntp_snapshot_from_device({"device": {}}) == {}


# ---------------------------------------------------------------------------
# apply_ntp — idempotency (skips push when no diff)
# ---------------------------------------------------------------------------

def test_apply_ntp_skips_when_no_diff() -> None:
    mgr = _make_manager()
    mgr.gsdk.get_device_id.return_value = 42
    device_info = _device_info("pool-1", ["time.google.com"])
    info_mock = MagicMock()
    info_mock.to_dict.return_value = device_info
    mgr.gsdk.get_device_info.return_value = info_mock

    with patch.object(mgr, "render_config_file", return_value={
        "ntpGlobalObject": [{"edge-1": {"ntps": [{"name": "pool-1", "domains": ["time.google.com"]}]}}]
    }):
        result = mgr.apply_ntp("f.yaml", operation="configure")

    assert result["changed"] is False
    assert "edge-1" in result["skipped_devices"]
    assert result["configured_devices"] == []
    mgr.gsdk.put_device_config_raw.assert_not_called()


def test_apply_ntp_sets_diff_plan_when_change_needed() -> None:
    mgr = _make_manager()
    mgr.gsdk.get_device_id.return_value = 42
    device_info = _device_info("pool-1", ["old.ntp.com"])
    info_mock = MagicMock()
    info_mock.to_dict.return_value = device_info
    mgr.gsdk.get_device_info.return_value = info_mock

    with patch.object(mgr, "render_config_file", return_value={
        "ntpGlobalObject": [{"edge-1": {"ntps": [{"name": "pool-1", "domains": ["time.google.com"]}]}}]
    }), patch.object(mgr, "execute_concurrent_tasks"):
        result = mgr.apply_ntp("f.yaml", operation="configure")

    assert result["diff_plan"]
    entry = result["diff_plan"][0]
    assert entry["device"] == "edge-1"
    assert entry["branch"] == "edge.ntpGlobalObject"
    assert "pool-1" in entry["before"]
    assert "pool-1" in entry["after"]


def test_apply_ntp_unsupported_operation_raises() -> None:
    mgr = _make_manager()
    with patch.object(mgr, "render_config_file", return_value={
        "ntpGlobalObject": [{"edge-1": {"ntps": []}}]
    }):
        with pytest.raises(ConfigurationError, match="Unsupported"):
            mgr.apply_ntp("f.yaml", operation="reset")
