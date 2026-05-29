# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for device_config_common helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ansible_collections.graphiant.naas.plugins.module_utils.libs.device_config_common import (
    ansible_diff_from_plan,
    coerce_str,
    device_not_found_message,
    fetch_device_by_name,
    load_device_list_yaml_config,
    normalized_device_type,
)
from ansible_collections.graphiant.naas.plugins.module_utils.libs.exceptions import (
    ConfigurationError,
    DeviceNotFoundError,
)


def test_coerce_str() -> None:
    assert coerce_str(None) == ""
    assert coerce_str("  x  ") == "x"


def test_normalized_device_type() -> None:
    assert normalized_device_type(None) is None
    assert normalized_device_type("edge") == "edge"
    with pytest.raises(ConfigurationError, match="device_type"):
        normalized_device_type("invalid")


def test_load_device_list_yaml_config_from_params() -> None:
    def render(_path: str) -> dict:
        return {}

    def build_row(mp: dict) -> dict:
        return {"name": mp["name"]} if mp.get("name") else {}

    def merge(merged: dict, ov: dict) -> dict:
        merged.update(ov)
        return merged

    def validate(_name: str, cfg: dict) -> dict:
        return cfg

    out = load_device_list_yaml_config(
        "device_system",
        None,
        {"device": "edge-1", "name": "edge-1"},
        render,
        missing_input_error="need file or device",
        build_row_from_params=build_row,
        merge_override=merge,
        validate_device_cfg=validate,
    )
    assert out == {"edge-1": {"name": "edge-1"}}


def test_fetch_device_by_name_not_found() -> None:
    gsdk = MagicMock()
    gsdk.get_device_id.return_value = None
    with pytest.raises(DeviceNotFoundError, match="edge-missing"):
        fetch_device_by_name(gsdk, "edge-missing", "Acme")


def test_device_not_found_message() -> None:
    msg = device_not_found_message("edge-missing", "Acme")
    assert "edge-missing" in msg and "Acme" in msg


def test_ansible_diff_from_plan() -> None:
    diff_plan = [
        {
            "device": "edge-1",
            "branch": "edge",
            "before": {"name": "a"},
            "after": {"name": "b"},
        }
    ]
    d = ansible_diff_from_plan(diff_plan)
    assert "edge-1" in d["before"] and "edge-1" in d["after"]
    assert '"a"' in d["before"] and '"b"' in d["after"]
