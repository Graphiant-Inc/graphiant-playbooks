# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for graphiant_gateway_services module (mocked Ansible + connection).

Covers the module-layer wiring: operation dispatch, exit payload service lists
(created/updated/skipped/deleted), state->operation derivation, and the ``--diff``
key. The manager's CRUD/idempotency logic is tested in test_gateway_services_manager.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ansible_collections.graphiant.naas.plugins.modules import graphiant_gateway_services


def _base_params(**overrides) -> dict:
    params = {
        "host": "https://api.example.com",
        "username": "u",
        "password": "p",
        "access_token": None,
        "gateway_services_config_file": "sample_gateway_services_config.yaml",
        "operation": "create",
        "state": "present",
        "detailed_logs": False,
        "force_update": False,
        "vault_gateway_ipsec_psks": {},
        "vault_gateway_bgp_md5_passwords": {},
    }
    params.update(overrides)
    return params


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_gateway_services.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_gateway_services.AnsibleModule")
def test_main_passes_force_update_to_manager(mock_ansible_module, mock_get_connection) -> None:
    result = {"changed": True, "created": [], "updated": ["connectivity:test"], "skipped": [], "diff_plan": []}
    _mod, gw = _wire(mock_ansible_module, mock_get_connection, result, _base_params(force_update=True))

    graphiant_gateway_services.main()

    # force_update flows through to the manager create() call
    assert gw.create.call_args.kwargs.get("force_update") is True


# --- execute_with_logging ----------------------------------------------------


def test_execute_with_logging_changed_summarizes_counts() -> None:
    module = MagicMock()
    module.params = {"detailed_logs": False}
    out = graphiant_gateway_services.execute_with_logging(
        module,
        lambda: {"changed": True, "created": ["a"], "updated": ["b"], "skipped": [], "deleted": []},
        success_msg="done",
    )
    assert out["changed"] is True
    assert out["created"] == ["a"] and out["updated"] == ["b"]
    assert "1 created" in out["result_msg"] and "1 updated" in out["result_msg"]


def test_execute_with_logging_no_change_reports_skipped_count() -> None:
    module = MagicMock()
    module.params = {"detailed_logs": False}
    out = graphiant_gateway_services.execute_with_logging(
        module,
        lambda: {"changed": False, "created": [], "updated": [], "skipped": ["s1", "s2"], "deleted": []},
        no_change_msg="no changes",
    )
    assert out["changed"] is False
    assert "skipped 2 services" in out["result_msg"]


# --- main() dispatch + exit payload -----------------------------------------


def _wire(mock_ansible_module, mock_get_connection, manager_result, params, diff=False):
    mod = MagicMock()
    mod.check_mode = False
    mod._diff = diff
    mod.params = params
    mock_ansible_module.return_value = mod

    gw = MagicMock()
    gw.create.return_value = manager_result
    gw.delete.return_value = manager_result
    gc = MagicMock()
    gc.gateway_services = gw
    mock_get_connection.return_value = MagicMock(graphiant_config=gc)
    return mod, gw


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_gateway_services.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_gateway_services.AnsibleModule")
def test_main_create_exit_payload(mock_ansible_module, mock_get_connection) -> None:
    result = {
        "changed": True,
        "created": ["aws:1"],
        "updated": ["connectivity:test"],
        "skipped": ["azure:k"],
        "diff_plan": [],
    }
    mod, gw = _wire(mock_ansible_module, mock_get_connection, result, _base_params())

    graphiant_gateway_services.main()

    gw.create.assert_called_once_with("sample_gateway_services_config.yaml", {}, {}, force_update=False)
    kwargs = mod.exit_json.call_args[1]
    assert kwargs["changed"] is True
    assert kwargs["operation"] == "create"
    assert kwargs["created"] == ["aws:1"]
    assert kwargs["updated"] == ["connectivity:test"]
    assert kwargs["skipped_services"] == ["azure:k"]
    assert "details" in kwargs


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_gateway_services.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_gateway_services.AnsibleModule")
def test_main_delete_via_state_absent(mock_ansible_module, mock_get_connection) -> None:
    result = {"changed": True, "deleted": ["aws:1"], "skipped": []}
    # operation omitted, state=absent -> derives delete
    params = _base_params(operation=None, state="absent")
    mod, gw = _wire(mock_ansible_module, mock_get_connection, result, params)

    graphiant_gateway_services.main()

    gw.delete.assert_called_once_with("sample_gateway_services_config.yaml")
    gw.create.assert_not_called()
    kwargs = mod.exit_json.call_args[1]
    assert kwargs["operation"] == "delete"
    assert kwargs["deleted"] == ["aws:1"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_gateway_services.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_gateway_services.AnsibleModule")
def test_main_diff_mode_sets_diff_key(mock_ansible_module, mock_get_connection) -> None:
    result = {
        "changed": True,
        "created": ["connectivity:test"],
        "updated": [],
        "skipped": [],
        "diff_plan": [
            {"device": "connectivity:test", "branch": "connectivity (create)", "before": {}, "after": {"regionId": 10}}
        ],
    }
    mod, _gw = _wire(mock_ansible_module, mock_get_connection, result, _base_params(), diff=True)

    graphiant_gateway_services.main()

    kwargs = mod.exit_json.call_args[1]
    assert "diff" in kwargs
    assert "connectivity:test" in kwargs["diff"]["before"]
    assert "connectivity:test" in kwargs["diff"]["after"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_gateway_services.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_gateway_services.AnsibleModule")
def test_main_delete_diff_mode_sets_diff_key(mock_ansible_module, mock_get_connection) -> None:
    result = {
        "changed": True,
        "deleted": ["connectivity:test"],
        "skipped": [],
        "diff_plan": [
            {"device": "connectivity:test", "branch": "connectivity (delete)", "before": {"regionId": 1}, "after": {}}
        ],
    }
    mod, _gw = _wire(mock_ansible_module, mock_get_connection, result, _base_params(operation="delete"), diff=True)

    graphiant_gateway_services.main()

    kwargs = mod.exit_json.call_args[1]
    assert "diff" in kwargs
    assert "connectivity:test" in kwargs["diff"]["before"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_gateway_services.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_gateway_services.AnsibleModule")
def test_main_no_diff_key_when_diff_mode_off(mock_ansible_module, mock_get_connection) -> None:
    result = {
        "changed": True,
        "created": ["connectivity:test"],
        "updated": [],
        "skipped": [],
        "diff_plan": [{"device": "connectivity:test", "branch": "connectivity (create)", "before": {}, "after": {}}],
    }
    mod, _gw = _wire(mock_ansible_module, mock_get_connection, result, _base_params(), diff=False)

    graphiant_gateway_services.main()

    kwargs = mod.exit_json.call_args[1]
    assert "diff" not in kwargs
