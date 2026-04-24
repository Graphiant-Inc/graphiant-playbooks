# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for DeviceSystemManager (mocked GSDK / config; no live API)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ansible_collections.graphiant.naas.plugins.module_utils.libs.device_system_manager import (
    DeviceSystemManager,
)
from ansible_collections.graphiant.naas.plugins.module_utils.libs.exceptions import (
    ConfigurationError,
)


def _device_row(
    role: str = "cpe",
    hostname: str = "dev-a",
    region: str = "us-west-1 (A)",
    site_name: str | None = "Site-A",
) -> dict:
    """GET /v1/devices style dict (inner device) for to_dict()."""
    d: dict = {
        "role": role,
        "hostname": hostname,
        "region": {"name": region},
    }
    if site_name:
        d["site"] = {"name": site_name}
    return {"device": d, "edge": {}}  # as wrapped by API


def _make_manager() -> DeviceSystemManager:
    config_utils = MagicMock()
    config_utils.gsdk = MagicMock()
    config_utils.gsdk.enterprise_info = {"company_name": "Acme"}
    return DeviceSystemManager(config_utils)


def _mock_gcs_payload(device_dict: dict) -> MagicMock:
    gcs = MagicMock()
    gcs.to_dict.return_value = device_dict
    return gcs


def test_deconfigure_not_supported() -> None:
    mgr = _make_manager()
    with pytest.raises(ConfigurationError, match="Deconfigure is not supported"):
        mgr.deconfigure("any.yaml")


@patch.object(DeviceSystemManager, "_load_device_system", return_value={})
def test_apply_no_input(_mock_load: MagicMock) -> None:
    mgr = _make_manager()
    r = mgr.apply_device_system("some.yaml", None)
    assert r.get("no_input") is True
    assert r["changed"] is False
    assert r.get("skipped_no_site") == []
    mgr.gsdk.put_device_config_raw.assert_not_called()


@patch.object(DeviceSystemManager, "execute_concurrent_tasks", autospec=True)
def test_apply_pushes_one_device_with_site(ex_mock: MagicMock) -> None:
    mgr = _make_manager()
    g = mgr.gsdk
    g.get_device_id.return_value = 100
    g.get_device_info.return_value = _mock_gcs_payload(
        _device_row(hostname="edge-1", region="us-west-1 (A)", site_name="Site-A")
    )
    g.get_site_id.return_value = 8601

    mgr.config_utils.render_config_file = MagicMock(
        return_value={
            "device_system": [
                {
                    "edge-1": {
                        "name": "edge-1",
                        "regionName": "us-west-1 (B)",
                        "site": {"name": "Site-A"},
                    }
                }
            ]
        }
    )
    r = mgr.apply_device_system("cfg.yaml", None)
    ex_mock.assert_called_once()
    assert r["changed"] is True
    assert "edge-1" in (r.get("configured_devices") or [])


@patch.object(DeviceSystemManager, "execute_concurrent_tasks", autospec=True)
def test_apply_idempotent_all_skipped(ex_mock: MagicMock) -> None:
    mgr = _make_manager()
    g = mgr.gsdk
    g.get_device_id.return_value = 100
    g.get_device_info.return_value = _mock_gcs_payload(
        _device_row(
            hostname="edge-1",
            region="us-west-1 (San Jose)",
            site_name="San Jose-sdktest",
        )
    )
    g.get_site_id.return_value = 8601

    mgr.config_utils.render_config_file = MagicMock(
        return_value={
            "device_system": [
                {
                    "edge-1": {
                        "name": "edge-1",
                        "regionName": "us-west-1 (San Jose)",
                        "site": {"name": "San Jose-sdktest"},
                    }
                }
            ]
        }
    )
    r = mgr.apply_device_system("cfg.yaml", None)
    ex_mock.assert_not_called()
    assert r["changed"] is False
    assert r.get("skipped_devices") == ["edge-1"]


@patch.object(DeviceSystemManager, "execute_concurrent_tasks", autospec=True)
def test_apply_skipped_no_site_no_portal_site_no_desired_site(ex_mock: MagicMock) -> None:
    """Device with no site on GET and wanted payload has no site — skip push, no other devices."""
    mgr = _make_manager()
    g = mgr.gsdk
    d = {
        "role": "cpe",
        "hostname": "cpe-55",
        "region": {"name": "us-east-2 (Atlanta)"},
    }
    g.get_device_id.return_value = 300_000_55_5
    g.get_device_info.return_value = _mock_gcs_payload({"device": d, "edge": {}})

    # Must request a real delta vs GET (or idempotency skips before no-site check).
    mgr.config_utils.render_config_file = MagicMock(
        return_value={
            "device_system": [
                {
                    "cpe-55": {
                        "name": "cpe-55-wanted",
                        "regionName": "us-east-2 (Atlanta)",
                    }
                }
            ]
        }
    )
    r = mgr.apply_device_system("cfg.yaml", None)
    ex_mock.assert_not_called()
    assert r.get("skipped_no_site") == ["cpe-55"]
    assert r.get("aborted_pushes_due_to_no_site") is False
    assert r.get("would_configure_devices") == []


@patch.object(DeviceSystemManager, "execute_concurrent_tasks", autospec=True)
def test_apply_aborts_pending_when_mixed_with_skipped_no_site(
    ex_mock: MagicMock,
) -> None:
    """If any device is skipped_no_site, pending pushes for other devices are not applied."""
    mgr = _make_manager()
    g = mgr.gsdk
    g.get_device_id.side_effect = lambda name: 57 if "good" in name else 55
    g.get_site_id.return_value = 8600

    def get_info(did: int) -> MagicMock:
        if did == 57:
            return _mock_gcs_payload(
                _device_row(
                    hostname="good-1",
                    site_name="Site-OK",
                    region="r1",
                )
            )
        return _mock_gcs_payload(
            {"device": {"role": "cpe", "hostname": "bad-1", "region": {"name": "r2"}}, "edge": {}}
        )

    g.get_device_info.side_effect = get_info

    mgr.config_utils.render_config_file = MagicMock(
        return_value={
            "device_system": [
                {
                    "good-1": {
                        "name": "good-1",
                        "regionName": "r1-new",
                        "site": {"name": "Site-OK"},
                    }
                },
                {
                    "bad-1": {
                        "name": "bad-1",
                        "regionName": "r2-new",
                    }
                },
            ]
        }
    )
    r = mgr.apply_device_system("cfg.yaml", None)
    ex_mock.assert_not_called()
    assert r.get("aborted_pushes_due_to_no_site") is True
    assert "good-1" in (r.get("would_configure_devices") or [])
    assert r.get("skipped_no_site") == ["bad-1"]


def test_configure_delegates_to_apply() -> None:
    mgr = _make_manager()
    with patch.object(
        DeviceSystemManager,
        "apply_device_system",
        return_value={"changed": False, "ok": 1},
    ) as m_apply:
        out = mgr.configure("a.yaml", {"device": "x", "name": "n"})
        m_apply.assert_called_once_with(
            config_yaml_file="a.yaml", module_params={"device": "x", "name": "n"}
        )
        assert out.get("ok") == 1
