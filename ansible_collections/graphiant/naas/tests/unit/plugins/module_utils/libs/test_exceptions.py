# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for custom exception types."""

from __future__ import annotations

import pytest

from ansible_collections.graphiant.naas.plugins.module_utils.libs.exceptions import (
    APIError,
    ConfigurationError,
    DeviceNotFoundError,
    GraphiantPlaybookError,
    SiteNotFoundError,
    TemplateError,
    ValidationError,
)


@pytest.mark.parametrize(
    "exc",
    [
        ConfigurationError,
        TemplateError,
        APIError,
        DeviceNotFoundError,
        SiteNotFoundError,
        ValidationError,
    ],
)
def test_exception_subclasses(exc: type) -> None:
    assert issubclass(exc, GraphiantPlaybookError)
    e = exc("x")
    assert str(e) == "x"
    with pytest.raises(GraphiantPlaybookError):
        raise e
