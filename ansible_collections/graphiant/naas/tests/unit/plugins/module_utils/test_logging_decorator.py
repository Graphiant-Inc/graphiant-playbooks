# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for capture_library_logs."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from ansible_collections.graphiant.naas.plugins.module_utils.logging_decorator import capture_library_logs


@capture_library_logs
def _sample_info(module) -> dict:
    logging.getLogger("Graphiant_playbook").info("u")
    return {
        "changed": False,
        "result_msg": "hello",
    }


@capture_library_logs
def _sample_raises(_module) -> None:
    logging.getLogger("Graphiant_playbook").info("before err")
    raise RuntimeError("boom from sample")


@capture_library_logs
def _sample_no_result_msg(_module) -> dict:
    logging.getLogger("Graphiant_playbook").info("n")
    return {"changed": False}


def test_no_detailed_logs() -> None:
    mod = MagicMock()
    mod.params = {"detailed_logs": False}
    r = _sample_info(mod)
    assert r.get("result_msg") == "hello"


def test_detailed_logs_appends_to_result_msg() -> None:
    mod = MagicMock()
    mod.params = {"detailed_logs": True}
    r = _sample_info(mod)
    assert "hello" in (r.get("result_msg") or "")
    assert "Detailed logs" in (r.get("result_msg") or "")


@patch("ansible_collections.graphiant.naas.plugins.module_utils.logging_decorator._setup_logger", None)
def test_detailed_logs_uses_root_logger_when_setup_unavailable() -> None:
    mod = MagicMock()
    mod.params = {"detailed_logs": True}
    r = _sample_info(mod)
    assert "hello" in (r.get("result_msg") or "")


def test_detailed_logs_exception_includes_captured() -> None:
    mod = MagicMock()
    mod.params = {"detailed_logs": True}
    with pytest.raises(RuntimeError, match="Detailed logs before exception") as exc:
        _sample_raises(mod)
    # Decorator re-wraps: message contains original + "Detailed logs before exception"
    assert "Detailed logs" in str(exc.value)


def test_detailed_logs_no_result_msg_still_runs() -> None:
    mod = MagicMock()
    mod.params = {"detailed_logs": True}
    r = _sample_no_result_msg(mod)
    assert r.get("changed") is False
