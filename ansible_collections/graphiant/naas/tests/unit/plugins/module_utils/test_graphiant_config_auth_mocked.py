# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""
Mocked GraphiantConfig auth paths mirroring tests/test.py live scenarios:

- test_auth_double_failure_access_token_then_password
- test_auth_invalid_token_fallback_to_valid_password (session establishes)

Uses patched GraphiantPortalClient (no portal HTTP).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ansible_collections.graphiant.naas.plugins.module_utils.libs.exceptions import (
    APIError,
    GraphiantPlaybookError,
)
from ansible_collections.graphiant.naas.plugins.module_utils.libs.graphiant_config import (
    GraphiantConfig,
)


@patch(
    "ansible_collections.graphiant.naas.plugins.module_utils.libs.config_utils.ConfigTemplates"
)
@patch(
    "ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient"
)
def test_graphiant_config_double_auth_failure_message(
    mock_portal_client: MagicMock, _mock_templates: MagicMock
) -> None:
    """Invalid token then failed password login -> GraphiantPlaybookError (integration test_auth_double_failure)."""
    inst = MagicMock()
    inst.set_bearer_token.side_effect = APIError(
        "Access token (GRAPHIANT_ACCESS_TOKEN / access_token) was not accepted by the API, "
        "then username/password login also failed. "
        "Login error: v1_auth_login_post: Got UnauthorizedException. Please verify credentials are correct."
    )
    mock_portal_client.return_value = inst
    with pytest.raises(GraphiantPlaybookError) as ctx:
        GraphiantConfig(
            base_url="https://api.example.com",
            username="u",
            password="bad",
            access_token="__invalid__",
        )
    msg = str(ctx.value)
    assert "initialization failed" in msg.lower() or "not accepted" in msg.lower()


@patch(
    "ansible_collections.graphiant.naas.plugins.module_utils.libs.config_utils.ConfigTemplates"
)
@patch(
    "ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient"
)
def test_graphiant_config_init_succeeds_when_bearer_succeeds(
    mock_portal_client: MagicMock, _mock_templates: MagicMock
) -> None:
    """set_bearer_token completes -> managers attach (integration invalid token + good password path)."""
    inst = MagicMock()
    inst.set_bearer_token.return_value = None
    mock_portal_client.return_value = inst
    gc = GraphiantConfig(
        base_url="https://api.example.com",
        username="u",
        password="good",
        access_token="__invalid_then_password_ok__",
    )
    inst.set_bearer_token.assert_called_once()
    st = gc.get_manager_status()
    assert st.get("global_config") is True
    assert st.get("sites") is True
    assert st.get("device_system") is True
