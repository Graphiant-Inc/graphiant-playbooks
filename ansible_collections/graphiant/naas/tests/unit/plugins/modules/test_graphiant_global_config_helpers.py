# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for get_deconfigure_summary in graphiant_global_config."""

from __future__ import annotations

from ansible_collections.graphiant.naas.plugins.modules.graphiant_global_config import get_deconfigure_summary


def test_get_deconfigure_summary_not_dict_details() -> None:
    r = get_deconfigure_summary({"details": "bad"})
    assert r == {"deleted": [], "skipped": [], "failed": False, "failed_objects": []}


def test_get_deconfigure_summary_single_op_with_failures() -> None:
    r = get_deconfigure_summary(
        {
            "details": {
                "deleted": ["a"],
                "skipped": ["b"],
                "failed_objects": ["in_use_obj"],
            }
        }
    )
    assert r["failed"] is True
    assert "in_use_obj" in r["failed_objects"]


def test_get_deconfigure_summary_generic_nested() -> None:
    r = get_deconfigure_summary(
        {
            "details": {
                "routing_policies": {
                    "x": {
                        "deleted": ["d1"],
                        "skipped": [],
                        "failed_objects": ["f1"],
                    }
                }
            }
        }
    )
    assert "d1" in r["deleted"]
    assert "f1" in r["failed_objects"]
    assert r["failed"] is True


def test_get_deconfigure_summary_empty_details() -> None:
    r = get_deconfigure_summary({})
    assert r["failed"] is False
    assert r["failed_objects"] == []


def test_get_deconfigure_summary_ignores_non_dict_subvalues() -> None:
    r = get_deconfigure_summary(
        {
            "details": {
                "str_key": "not a dict",
                "nested": {1: {2: "not dict"}},
            }
        }
    )
    assert r["deleted"] == []
    assert r["failed"] is False
