# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""
Unit tests for GlobalConfigManager (mocked), aligned with tests/test.py global_config flows.

Live tests load YAML with global_prefix_sets / routing_policies; here we assert routing when
keys are absent vs present without calling the portal.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ansible_collections.graphiant.naas.plugins.module_utils.libs.global_config_manager import (
    GlobalConfigManager,
)


def _mgr() -> GlobalConfigManager:
    cu = MagicMock()
    cu.gsdk = MagicMock()
    return GlobalConfigManager(cu)


@patch.object(GlobalConfigManager, "render_config_file", return_value={})
def test_configure_empty_render_skips_sub_ops(_mock_render: MagicMock) -> None:
    """No recognized top-level keys -> no prefix/BGP sub-configure (idempotent no-op)."""
    mgr = _mgr()
    r = mgr.configure("sample_global_prefix_lists.yaml")
    assert r["changed"] is False
    assert r["failed"] is False
    assert r["details"] == {}


@patch.object(GlobalConfigManager, "configure_prefix_sets", return_value={"changed": True})
@patch.object(
    GlobalConfigManager,
    "render_config_file",
    return_value={"global_prefix_sets": {"demo": {"prefixSet": {"name": "demo"}}}},
)
def test_configure_invokes_prefix_sets_when_key_present(
    _mock_render: MagicMock, m_prefix: MagicMock
) -> None:
    """Mirrors test_configure_global_config_prefix_lists routing into configure_prefix_sets."""
    mgr = _mgr()
    r = mgr.configure("sample_global_prefix_lists.yaml")
    m_prefix.assert_called_once_with("sample_global_prefix_lists.yaml")
    assert r["changed"] is True
    assert "prefix_sets" in r["details"]
