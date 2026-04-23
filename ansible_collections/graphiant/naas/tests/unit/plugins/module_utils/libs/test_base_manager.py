# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for BaseManager (mocked ConfigUtils / gsdk)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ansible_collections.graphiant.naas.plugins.module_utils.libs.base_manager import BaseManager
from ansible_collections.graphiant.naas.plugins.module_utils.libs.exceptions import (
    APIError,
    ConfigurationError,
    DeviceNotFoundError,
    SiteNotFoundError,
)


class _ConcreteManager(BaseManager):
    def configure(self, config_yaml_file: str):
        return {"ok": True}

    def deconfigure(self, config_yaml_file: str):
        return {"ok": True}


def _make_config_utils() -> MagicMock:
    cu = MagicMock()
    cu.gsdk = MagicMock()
    cu.template = MagicMock()
    return cu


def test_render_config_file_success() -> None:
    cu = _make_config_utils()
    cu.render_config_file = MagicMock(return_value={"a": 1})
    m = _ConcreteManager(cu)
    assert m.render_config_file("f.yaml") == {"a": 1}


def test_render_config_file_none_raises() -> None:
    cu = _make_config_utils()
    cu.render_config_file = MagicMock(return_value=None)
    m = _ConcreteManager(cu)
    with pytest.raises(ConfigurationError, match="Failed to load"):
        m.render_config_file("missing.yaml")


def test_get_device_id() -> None:
    cu = _make_config_utils()
    cu.gsdk.get_device_id.return_value = 7
    m = _ConcreteManager(cu)
    assert m.get_device_id("d1") == 7


def test_get_device_id_not_found() -> None:
    cu = _make_config_utils()
    cu.gsdk.get_device_id.return_value = None
    m = _ConcreteManager(cu)
    with pytest.raises(DeviceNotFoundError, match="d1"):
        m.get_device_id("d1")


def test_get_site_id() -> None:
    cu = _make_config_utils()
    cu.gsdk.get_site_id.return_value = 3
    m = _ConcreteManager(cu)
    assert m.get_site_id("s1") == 3


def test_get_site_id_not_found() -> None:
    cu = _make_config_utils()
    cu.gsdk.get_site_id.return_value = None
    m = _ConcreteManager(cu)
    with pytest.raises(SiteNotFoundError, match="s1"):
        m.get_site_id("s1")


def test_render_config_file_wraps_exception() -> None:
    cu = _make_config_utils()
    cu.render_config_file = MagicMock(side_effect=ValueError("boom"))
    m = _ConcreteManager(cu)
    with pytest.raises(ConfigurationError, match="Error rendering"):
        m.render_config_file("f.yaml")


def test_execute_concurrent_tasks_api_error() -> None:
    cu = _make_config_utils()
    cu.concurrent_task_execution = MagicMock(side_effect=RuntimeError("ce"))
    m = _ConcreteManager(cu)
    with pytest.raises(APIError, match="concurrent tasks"):
        m.execute_concurrent_tasks(len, {"a": 1})
