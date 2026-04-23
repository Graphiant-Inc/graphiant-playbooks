# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for poller (time.sleep mocked)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from ansible_collections.graphiant.naas.plugins.module_utils.libs import poller


def test_raise_reraises() -> None:
    try:
        1 / 0
    except Exception:
        import sys

        t, v, tb = sys.exc_info()
        with pytest.raises(ZeroDivisionError):
            poller.raise_(t, v, tb)


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.poller.time.sleep", return_value=None)
def test_timeout_poller_succeeds_first_try(_mock_sleep) -> None:
    called = [0]

    @poller.poller(timeout=1.0, wait=0.01)
    def works():
        called[0] += 1
        return "ok"

    assert works() == "ok"
    assert called[0] == 1


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.poller.time.sleep", return_value=None)
def test_timeout_poller_retries_then_succeeds(_mock_sleep) -> None:
    n = [0]

    @poller.poller(timeout=1.0, wait=0.01)
    def flaky():
        n[0] += 1
        if n[0] < 2:
            raise ValueError("retry")
        return 42

    assert flaky() == 42
    assert n[0] == 2


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.poller.time.sleep", return_value=None)
def test_timeout_poller_exhausts(_mock_sleep) -> None:
    @poller.poller(timeout=0.05, wait=0.01)
    def always_fails():
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError, match="nope"):
        always_fails()


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.poller.time.sleep", return_value=None)
def test_retry_poller_succeeds(_mock_sleep) -> None:
    n = [0]

    @poller.poller(retries=3, wait=0.01)
    def two_step():
        n[0] += 1
        if n[0] < 2:
            raise AssertionError("not yet")
        return "done"

    assert two_step() == "done"


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.poller.time.sleep", return_value=None)
def test_retry_poller_exhausts(_mock_sleep) -> None:
    @poller.poller(retries=2, wait=0.01)
    def always_fails():
        raise OSError("x")

    with pytest.raises(OSError, match="x"):
        always_fails()
