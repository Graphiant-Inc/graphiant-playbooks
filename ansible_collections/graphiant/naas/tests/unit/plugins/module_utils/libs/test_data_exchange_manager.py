# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for data_exchange_manager helpers (no live API)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ansible_collections.graphiant.naas.plugins.module_utils.libs.data_exchange_manager import (
    DataExchangeManager,
)
from ansible_collections.graphiant.naas.plugins.module_utils.libs.exceptions import ConfigurationError


def _make_manager() -> DataExchangeManager:
    config_utils = MagicMock()
    config_utils.gsdk = MagicMock()
    config_utils.template = MagicMock()
    return DataExchangeManager(config_utils)


def test_validate_routing_policies_no_global_object_ops() -> None:
    mgr = _make_manager()
    mgr._validate_global_object_ops_routing_policies(  # pylint: disable=protected-access
        {}, "svc1"
    )
    mgr.gsdk.get_global_routing_policy_summaries.assert_not_called()


def test_validate_routing_policies_not_dict_ops() -> None:
    mgr = _make_manager()
    mgr._validate_global_object_ops_routing_policies(  # pylint: disable=protected-access
        {"globalObjectOps": "bad"}, "svc1"
    )
    mgr.gsdk.get_global_routing_policy_summaries.assert_not_called()


def test_validate_routing_policies_uses_existing_names() -> None:
    mgr = _make_manager()
    policy_config = {
        "globalObjectOps": {
            "1": {
                "routingPolicyOps": {"p1": {}, "p2": {}},
            }
        }
    }
    with pytest.raises(ConfigurationError, match="not found for service"):
        mgr._validate_global_object_ops_routing_policies(  # pylint: disable=protected-access
            policy_config,
            "my-service",
            existing_policy_names=set(),  # empty -> all missing
        )
    mgr.gsdk.get_global_routing_policy_summaries.assert_not_called()


def test_validate_routing_policies_success_with_existing() -> None:
    mgr = _make_manager()
    policy_config = {
        "globalObjectOps": {
            "1": {
                "routingPolicyOps": {"Policy-A": {}},
            }
        }
    }
    mgr._validate_global_object_ops_routing_policies(  # pylint: disable=protected-access
        policy_config,
        "svc",
        existing_policy_names={"Policy-A", "Policy-B"},
    )
    mgr.gsdk.get_global_routing_policy_summaries.assert_not_called()


def test_validate_routing_policies_fetches_from_gsdk() -> None:
    mgr = _make_manager()
    mgr.gsdk.get_global_routing_policy_summaries.return_value = [
        {"name": "Policy-A"},
    ]
    policy_config = {
        "globalObjectOps": {
            "1": {
                "routingPolicyOps": {"Policy-A": {}},
            }
        }
    }
    mgr._validate_global_object_ops_routing_policies(  # pylint: disable=protected-access
        policy_config,
        "svc",
    )
    mgr.gsdk.get_global_routing_policy_summaries.assert_called_once()
