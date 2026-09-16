# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for graphiant_data_assurance module (mocked Ansible + connection)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ansible_collections.graphiant.naas.plugins.modules import graphiant_data_assurance


def _base_params() -> dict:
    return {
        "host": "https://api.example.com",
        "username": "u",
        "password": "p",
        "access_token": None,
        "data_assurance_config_file": "sample_data_assurance_policies.yaml",
        "operation": "configure",
        "state": "present",
        "detailed_logs": False,
    }


def test_execute_with_logging_no_change_adds_skipped_count_to_message() -> None:
    module = MagicMock()
    module.params = {"detailed_logs": False}
    out = graphiant_data_assurance.execute_with_logging(
        module,
        lambda: {
            "changed": False,
            "configured": [],
            "skipped": ["p1", "p2"],
        },
    )
    assert out["changed"] is False
    assert "skipped 2 policies" in out["result_msg"]


def test_execute_with_logging_single_skip_uses_singular() -> None:
    module = MagicMock()
    module.params = {"detailed_logs": False}
    out = graphiant_data_assurance.execute_with_logging(
        module,
        lambda: {"changed": False, "configured": [], "skipped": ["p1"]},
    )
    assert "skipped 1 policy" in out["result_msg"]


def test_execute_with_logging_reraises_and_logs_on_failure() -> None:
    module = MagicMock()
    module.params = {"detailed_logs": True}

    def boom():
        raise ValueError("nope")

    try:
        graphiant_data_assurance.execute_with_logging(module, boom)
    except ValueError as e:
        assert str(e) == "nope"
    else:  # pragma: no cover - failure path must raise
        raise AssertionError("expected ValueError to propagate")


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_data_assurance.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_data_assurance.AnsibleModule")
def test_main_configure(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod.params = _base_params()
    mod.params["operation"] = "configure"
    mock_ansible_module.return_value = mod

    data_assurance = MagicMock()
    data_assurance.configure.return_value = {
        "changed": False,
        "configured": [],
        "skipped": ["x"],
    }
    gc = MagicMock()
    gc.data_assurance = data_assurance
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_data_assurance.main()
    data_assurance.configure.assert_called_once()
    assert data_assurance.configure.call_args[0][0] == "sample_data_assurance_policies.yaml"


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_data_assurance.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_data_assurance.AnsibleModule")
def test_main_configure_passes_inline_params(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod.params = _base_params()
    mod.params["data_assurance_config_file"] = None
    mod.params["DataAssurancePolicies"] = [{"name": "p1", "flexAlgo": "x"}]
    mod.params["ContentFilterPolicies"] = [{"name": "cf1", "categories": ["Gambling"]}]
    mock_ansible_module.return_value = mod

    data_assurance = MagicMock()
    data_assurance.configure.return_value = {"changed": True, "configured": ["p1", "cf1"], "skipped": []}
    gc = MagicMock()
    gc.data_assurance = data_assurance
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_data_assurance.main()
    data_assurance.configure.assert_called_once()
    kwargs = data_assurance.configure.call_args.kwargs
    assert kwargs["data_assurance_policies"] == [{"name": "p1", "flexAlgo": "x"}]
    assert kwargs["content_filter_policies"] == [{"name": "cf1", "categories": ["Gambling"]}]
    assert data_assurance.configure.call_args[0][0] is None


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_data_assurance.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_data_assurance.AnsibleModule")
def test_main_deconfigure(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod.params = _base_params()
    mod.params["operation"] = "deconfigure"
    mod.params["state"] = "absent"
    mock_ansible_module.return_value = mod

    data_assurance = MagicMock()
    data_assurance.deconfigure.return_value = {
        "changed": True,
        "deleted": ["p1"],
        "skipped": [],
    }
    gc = MagicMock()
    gc.data_assurance = data_assurance
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_data_assurance.main()
    data_assurance.deconfigure.assert_called_once()
    assert data_assurance.deconfigure.call_args[0][0] == "sample_data_assurance_policies.yaml"


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_data_assurance.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_data_assurance.AnsibleModule")
def test_main_defaults_operation_from_state_absent(mock_ansible_module, mock_get_connection) -> None:
    mod = MagicMock()
    mod.check_mode = False
    mod.params = _base_params()
    mod.params["operation"] = None
    mod.params["state"] = "absent"
    mock_ansible_module.return_value = mod

    data_assurance = MagicMock()
    data_assurance.deconfigure.return_value = {"changed": False, "deleted": [], "skipped": []}
    gc = MagicMock()
    gc.data_assurance = data_assurance
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_data_assurance.main()
    data_assurance.deconfigure.assert_called_once()
    data_assurance.configure.assert_not_called()
