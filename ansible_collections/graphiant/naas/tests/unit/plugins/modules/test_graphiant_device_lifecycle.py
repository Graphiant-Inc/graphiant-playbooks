# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for graphiant_device_lifecycle module (mocked Ansible + connection)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ansible_collections.graphiant.naas.plugins.module_utils.libs.exceptions import ConfigurationError
from ansible_collections.graphiant.naas.plugins.modules import graphiant_device_lifecycle


def _base_params(**overrides) -> dict:
    params = {
        "host": "https://api.example.com",
        "username": "u",
        "password": "p",
        "access_token": None,
        "operation": "change_state",
        "config_file": None,
        "device": "edge-1-sdktest",
        "lifecycle_state": "staging",
        "release": None,
        "upgrade_action": "InstallActivate",
        "ts": None,
        "verify_for_insync": True,
        "state": "present",
        "detailed_logs": False,
    }
    params.update(overrides)
    return params


def _mock_module(params: dict) -> MagicMock:
    mod = MagicMock()
    mod.check_mode = False
    mod.params = params
    return mod


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.AnsibleModule")
def test_main_missing_file_and_device_fails(mock_ansible_module: MagicMock, _mock_get_connection: MagicMock) -> None:
    mod = _mock_module(_base_params(config_file=None, device="   "))
    mock_ansible_module.return_value = mod
    graphiant_device_lifecycle.main()
    mod.fail_json.assert_called_once()
    err = mod.fail_json.call_args[1].get("msg", "")
    assert "config_file" in err or "device" in err


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.AnsibleModule")
def test_main_change_state_call_args(mock_ansible_module: MagicMock, _mock_get_connection: MagicMock) -> None:
    mod = _mock_module(_base_params())
    mock_ansible_module.return_value = mod
    manager = MagicMock()
    manager.change_state.return_value = {
        "changed": True,
        "configured_devices": ["edge-1-sdktest"],
        "skipped_devices": [],
        "not_insync_devices": [],
        "diff_plan": [],
    }
    gc = MagicMock()
    gc.device_lifecycle = manager
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle.main()

    _ckwargs = manager.change_state.call_args.kwargs
    assert _ckwargs["config_yaml_file"] is None
    assert _ckwargs["module_params"] == {"device": "edge-1-sdktest", "lifecycle_state": "staging"}
    assert _ckwargs["verify_for_insync"] is True
    mod.exit_json.assert_called_once()
    payload = mod.exit_json.call_args[1]
    assert payload["changed"] is True
    assert payload["configured_devices"] == ["edge-1-sdktest"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.AnsibleModule")
def test_main_change_state_fails_when_device_not_ready(
    mock_ansible_module: MagicMock, _mock_get_connection: MagicMock
) -> None:
    # portalStatus reaching Ready after a lifecycle change is a requirement, not merely
    # informational — a non-empty not_insync_devices must fail the task even though the state
    # change itself (configured_devices) succeeded.
    mod = _mock_module(_base_params())
    mock_ansible_module.return_value = mod
    manager = MagicMock()
    manager.change_state.return_value = {
        "changed": True,
        "configured_devices": ["edge-1-sdktest", "edge-2-sdktest"],
        "skipped_devices": [],
        "insync_devices": ["edge-2-sdktest"],
        "not_insync_devices": ["edge-1-sdktest"],
        "diff_plan": [],
    }
    gc = MagicMock()
    gc.device_lifecycle = manager
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle.main()

    mod.exit_json.assert_not_called()
    mod.fail_json.assert_called_once()
    payload = mod.fail_json.call_args[1]
    assert payload["not_insync_devices"] == ["edge-1-sdktest"]
    assert payload["insync_devices"] == ["edge-2-sdktest"]
    assert payload["configured_devices"] == ["edge-1-sdktest", "edge-2-sdktest"]
    assert "edge-1-sdktest" in payload["msg"]
    # A device that DID reach Ready must be distinguishable in msg from one that didn't, since
    # configured_devices alone lists both without saying which passed.
    assert "reached Ready: edge-2-sdktest" in payload["msg"]
    # The summary must read as a failure, not the unqualified success message — a playbook (or a
    # human) glancing at just the first line of msg should not see "Successfully changed ...".
    assert not payload["msg"].startswith("Successfully changed")
    assert payload["msg"].startswith("Device lifecycle state changed, but 1 device(s) did not reach Ready")


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.AnsibleModule")
def test_main_change_state_not_ready_msg_keeps_detailed_logs_suffix_after_summary(
    mock_ansible_module: MagicMock, _mock_get_connection: MagicMock
) -> None:
    # With detailed_logs: true, capture_library_logs appends "\n\nDetailed logs:\n<captured log
    # lines>" to result_msg. The failure summary must replace the success text but the detailed
    # logs must still follow it (not get dropped, and not have the failure note tacked on after
    # them where it's easy to miss in a long log dump).
    mod = _mock_module(_base_params(detailed_logs=True))
    mock_ansible_module.return_value = mod
    manager = MagicMock()

    def _fake_change_state(**_kwargs):
        import logging

        logging.getLogger("Graphiant_playbook").info("some library log line")
        return {
            "changed": True,
            "configured_devices": ["edge-1-sdktest"],
            "skipped_devices": [],
            "not_insync_devices": ["edge-1-sdktest"],
            "diff_plan": [],
        }

    manager.change_state.side_effect = _fake_change_state
    gc = MagicMock()
    gc.device_lifecycle = manager
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle.main()

    payload = mod.fail_json.call_args[1]
    msg = payload["msg"]
    assert msg.startswith("Device lifecycle state changed, but 1 device(s) did not reach Ready")
    marker = "\n\nDetailed logs:\n"
    assert marker in msg
    # The failure summary comes before the detailed logs, not appended after them.
    assert msg.index("did not reach Ready") < msg.index(marker)
    assert "some library log line" in msg[msg.index(marker):]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.AnsibleModule")
def test_main_change_state_check_mode_msg_says_would(
    mock_ansible_module: MagicMock, _mock_get_connection: MagicMock
) -> None:
    # A check-mode run must not read like a real change happened (changed=true alone isn't
    # obvious enough at a glance — the message needs to say so too).
    mod = _mock_module(_base_params())
    mod.check_mode = True
    mock_ansible_module.return_value = mod
    manager = MagicMock()
    manager.change_state.return_value = {
        "changed": True,
        "configured_devices": ["edge-1-sdktest"],
        "skipped_devices": [],
        "not_insync_devices": [],
        "diff_plan": [],
    }
    gc = MagicMock()
    gc.device_lifecycle = manager
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle.main()

    payload = mod.exit_json.call_args[1]
    assert payload["msg"].startswith("[check_mode]")
    assert "would" in payload["msg"].lower()


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.AnsibleModule")
def test_main_change_state_no_input(mock_ansible_module: MagicMock, _mock_get_connection: MagicMock) -> None:
    mod = _mock_module(_base_params(config_file="sample_device_lifecycle.yaml", device=None, lifecycle_state=None))
    mock_ansible_module.return_value = mod
    manager = MagicMock()
    manager.change_state.return_value = {"no_input": True, "changed": False}
    gc = MagicMock()
    gc.device_lifecycle = manager
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle.main()

    mod.exit_json.assert_called_once()
    assert "nothing to do" in (mod.exit_json.call_args[1].get("msg", "") or "").lower()


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.AnsibleModule")
def test_main_change_state_decommission_guard_fails_cleanly(
    mock_ansible_module: MagicMock, _mock_get_connection: MagicMock
) -> None:
    mod = _mock_module(_base_params(lifecycle_state="decommissioned"))
    mock_ansible_module.return_value = mod
    manager = MagicMock()
    manager.change_state.side_effect = ConfigurationError(
        "Device 'edge-1-sdktest' must be Deactivated before it can be Decommissioned (current status: 'active')."
    )
    gc = MagicMock()
    gc.device_lifecycle = manager
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle.main()

    mod.fail_json.assert_called_once()
    err = mod.fail_json.call_args[1].get("msg", "")
    assert "must be Deactivated" in err


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.AnsibleModule")
def test_main_schedule_upgrade_call_args(mock_ansible_module: MagicMock, _mock_get_connection: MagicMock) -> None:
    mod = _mock_module(
        _base_params(operation="schedule_upgrade", lifecycle_state=None, release="Latest", upgrade_action="Install")
    )
    mock_ansible_module.return_value = mod
    manager = MagicMock()
    manager.schedule_upgrade.return_value = {"changed": True, "configured_devices": ["edge-1-sdktest"]}
    gc = MagicMock()
    gc.device_lifecycle = manager
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle.main()

    ckwargs = manager.schedule_upgrade.call_args.kwargs
    assert ckwargs["module_params"] == {"device": "edge-1-sdktest", "release": "Latest"}
    assert ckwargs["action"] == "Install"
    mod.exit_json.assert_called_once()
    assert mod.exit_json.call_args[1]["changed"] is True


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.AnsibleModule")
def test_main_schedule_upgrade_with_diff_mode(mock_ansible_module: MagicMock, _mock_get_connection: MagicMock) -> None:
    mod = _mock_module(_base_params(operation="schedule_upgrade", lifecycle_state=None, release="Latest"))
    mod._diff = True
    mock_ansible_module.return_value = mod
    manager = MagicMock()
    manager.schedule_upgrade.return_value = {
        "changed": True,
        "configured_devices": ["edge-1-sdktest"],
        "diff_plan": [
            {
                "device": "edge-1-sdktest",
                "branch": "schedule_upgrade",
                "before": {"release": "Latest", "version": "2604.1"},
                "after": {"release": "Latest", "version": "2610.1"},
            }
        ],
    }
    gc = MagicMock()
    gc.device_lifecycle = manager
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle.main()

    mod.exit_json.assert_called_once()
    payload = mod.exit_json.call_args[1]
    assert "diff" in payload
    assert "2604.1" in payload["diff"]["before"]
    assert "2610.1" in payload["diff"]["after"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.AnsibleModule")
def test_main_schedule_upgrade_check_mode_msg_says_would(
    mock_ansible_module: MagicMock, _mock_get_connection: MagicMock
) -> None:
    mod = _mock_module(
        _base_params(operation="schedule_upgrade", lifecycle_state=None, release="Latest", upgrade_action="Install")
    )
    mod.check_mode = True
    mock_ansible_module.return_value = mod
    manager = MagicMock()
    manager.schedule_upgrade.return_value = {"changed": True, "configured_devices": ["edge-1-sdktest"]}
    gc = MagicMock()
    gc.device_lifecycle = manager
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle.main()

    payload = mod.exit_json.call_args[1]
    assert payload["msg"].startswith("[check_mode]")
    assert "would" in payload["msg"].lower()


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.AnsibleModule")
def test_main_schedule_upgrade_no_change_when_device_already_on_release(
    mock_ansible_module: MagicMock, _mock_get_connection: MagicMock
) -> None:
    mod = _mock_module(
        _base_params(operation="schedule_upgrade", lifecycle_state=None, release="Stable", upgrade_action="Install")
    )
    mock_ansible_module.return_value = mod
    manager = MagicMock()
    manager.schedule_upgrade.return_value = {
        "changed": False,
        "configured_devices": [],
        "skipped_devices": ["edge-1-sdktest"],
        "completed_devices": [],
        "failed_devices": [],
        "in_progress_devices": [],
    }
    gc = MagicMock()
    gc.device_lifecycle = manager
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle.main()

    mod.fail_json.assert_not_called()
    mod.exit_json.assert_called_once()
    payload = mod.exit_json.call_args[1]
    assert payload["changed"] is False
    assert payload["skipped_devices"] == ["edge-1-sdktest"]
    assert "already on the requested release" in payload["msg"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.AnsibleModule")
def test_main_schedule_upgrade_fails_when_device_schedule_failed(
    mock_ansible_module: MagicMock, _mock_get_connection: MagicMock
) -> None:
    mod = _mock_module(
        _base_params(operation="schedule_upgrade", lifecycle_state=None, release="Latest", upgrade_action="Install")
    )
    mock_ansible_module.return_value = mod
    manager = MagicMock()
    manager.schedule_upgrade.return_value = {
        "changed": True,
        "configured_devices": ["edge-1-sdktest"],
        "completed_devices": [],
        "failed_devices": ["edge-1-sdktest"],
        "in_progress_devices": [],
    }
    gc = MagicMock()
    gc.device_lifecycle = manager
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle.main()

    mod.exit_json.assert_not_called()
    mod.fail_json.assert_called_once()
    payload = mod.fail_json.call_args[1]
    assert payload["failed_devices"] == ["edge-1-sdktest"]
    assert payload["configured_devices"] == ["edge-1-sdktest"]
    assert "edge-1-sdktest" in payload["msg"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.AnsibleModule")
def test_main_rollback_fails_when_device_schedule_failed(
    mock_ansible_module: MagicMock, _mock_get_connection: MagicMock
) -> None:
    mod = _mock_module(_base_params(operation="rollback", lifecycle_state=None))
    mock_ansible_module.return_value = mod
    manager = MagicMock()
    manager.rollback.return_value = {
        "changed": True,
        "configured_devices": ["edge-1-sdktest"],
        "skipped_devices": [],
        "completed_devices": [],
        "failed_devices": ["edge-1-sdktest"],
        "in_progress_devices": [],
    }
    gc = MagicMock()
    gc.device_lifecycle = manager
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle.main()

    mod.exit_json.assert_not_called()
    mod.fail_json.assert_called_once()
    payload = mod.fail_json.call_args[1]
    assert payload["failed_devices"] == ["edge-1-sdktest"]
    assert "edge-1-sdktest" in payload["msg"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.AnsibleModule")
def test_main_schedule_upgrade_fails_when_device_not_insync_after_success(
    mock_ansible_module: MagicMock, _mock_get_connection: MagicMock
) -> None:
    """A device whose schedule completed (Success) but did not reach portalStatus=Ready
    afterward still fails the task, the same way a schedule Failed does."""
    mod = _mock_module(
        _base_params(operation="schedule_upgrade", lifecycle_state=None, release="Latest", upgrade_action="Install")
    )
    mock_ansible_module.return_value = mod
    manager = MagicMock()
    manager.schedule_upgrade.return_value = {
        "changed": True,
        "configured_devices": ["edge-1-sdktest"],
        "completed_devices": ["edge-1-sdktest"],
        "failed_devices": [],
        "in_progress_devices": [],
        "insync_devices": [],
        "not_insync_devices": ["edge-1-sdktest"],
    }
    gc = MagicMock()
    gc.device_lifecycle = manager
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle.main()

    mod.exit_json.assert_not_called()
    mod.fail_json.assert_called_once()
    payload = mod.fail_json.call_args[1]
    assert payload["not_insync_devices"] == ["edge-1-sdktest"]
    assert payload["failed_devices"] == []
    assert "edge-1-sdktest" in payload["msg"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.AnsibleModule")
def test_main_schedule_upgrade_fails_when_device_not_connected(
    mock_ansible_module: MagicMock, _mock_get_connection: MagicMock
) -> None:
    """A device with no portal connectivity (not_connected_devices) fails the task even though
    another device in the same batch was scheduled successfully."""
    mod = _mock_module(
        _base_params(operation="schedule_upgrade", lifecycle_state=None, release="Latest", upgrade_action="Install")
    )
    mock_ansible_module.return_value = mod
    manager = MagicMock()
    manager.schedule_upgrade.return_value = {
        "changed": True,
        "configured_devices": ["edge-2-sdktest"],
        "skipped_devices": [],
        "not_connected_devices": ["edge-1-sdktest"],
        "completed_devices": [],
        "failed_devices": [],
        "in_progress_devices": [],
        "insync_devices": [],
        "not_insync_devices": [],
    }
    gc = MagicMock()
    gc.device_lifecycle = manager
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle.main()

    mod.exit_json.assert_not_called()
    mod.fail_json.assert_called_once()
    payload = mod.fail_json.call_args[1]
    assert payload["not_connected_devices"] == ["edge-1-sdktest"]
    assert "edge-1-sdktest" in payload["msg"]
    assert "Upgrade scheduled, but" in payload["msg"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.AnsibleModule")
def test_main_schedule_upgrade_fails_when_every_device_not_connected(
    mock_ansible_module: MagicMock, _mock_get_connection: MagicMock
) -> None:
    """When EVERY device in the batch is not_connected (nothing actually scheduled, changed is
    false), the message must not claim 'Upgrade scheduled' since nothing was."""
    mod = _mock_module(
        _base_params(operation="schedule_upgrade", lifecycle_state=None, release="Latest", upgrade_action="Install")
    )
    mock_ansible_module.return_value = mod
    manager = MagicMock()
    manager.schedule_upgrade.return_value = {
        "changed": False,
        "configured_devices": [],
        "skipped_devices": [],
        "not_connected_devices": ["edge-1-sdktest"],
        "completed_devices": [],
        "failed_devices": [],
        "in_progress_devices": [],
        "insync_devices": [],
        "not_insync_devices": [],
    }
    gc = MagicMock()
    gc.device_lifecycle = manager
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle.main()

    mod.exit_json.assert_not_called()
    mod.fail_json.assert_called_once()
    payload = mod.fail_json.call_args[1]
    assert payload["not_connected_devices"] == ["edge-1-sdktest"]
    assert "No devices were scheduled" in payload["msg"]
    assert "Upgrade scheduled" not in payload["msg"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.AnsibleModule")
def test_main_schedule_upgrade_schedule_in_progress_does_not_fail(
    mock_ansible_module: MagicMock, _mock_get_connection: MagicMock
) -> None:
    """Unlike not_connected_devices, schedule_in_progress_devices is a soft skip (like
    skipped_devices) — it must NOT fail the task, even when it's the only reason changed=False."""
    mod = _mock_module(
        _base_params(operation="schedule_upgrade", lifecycle_state=None, release="Latest", upgrade_action="Install")
    )
    mock_ansible_module.return_value = mod
    manager = MagicMock()
    manager.schedule_upgrade.return_value = {
        "changed": False,
        "configured_devices": [],
        "skipped_devices": [],
        "not_connected_devices": [],
        "schedule_in_progress_devices": ["edge-1-sdktest"],
        "completed_devices": [],
        "failed_devices": [],
        "in_progress_devices": [],
        "insync_devices": [],
        "not_insync_devices": [],
    }
    gc = MagicMock()
    gc.device_lifecycle = manager
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle.main()

    mod.fail_json.assert_not_called()
    mod.exit_json.assert_called_once()
    payload = mod.exit_json.call_args[1]
    assert payload["changed"] is False
    assert payload["schedule_in_progress_devices"] == ["edge-1-sdktest"]
    assert "(1 device(s) skipped)" in payload["msg"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.AnsibleModule")
def test_main_rollback_schedule_in_progress_does_not_fail(
    mock_ansible_module: MagicMock, _mock_get_connection: MagicMock
) -> None:
    mod = _mock_module(_base_params(operation="rollback", lifecycle_state=None))
    mock_ansible_module.return_value = mod
    manager = MagicMock()
    manager.rollback.return_value = {
        "changed": False,
        "configured_devices": [],
        "skipped_devices": [],
        "schedule_in_progress_devices": ["edge-1-sdktest"],
        "completed_devices": [],
        "failed_devices": [],
        "in_progress_devices": [],
        "insync_devices": [],
        "not_insync_devices": [],
    }
    gc = MagicMock()
    gc.device_lifecycle = manager
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle.main()

    mod.fail_json.assert_not_called()
    mod.exit_json.assert_called_once()
    payload = mod.exit_json.call_args[1]
    assert payload["changed"] is False
    assert payload["schedule_in_progress_devices"] == ["edge-1-sdktest"]
    assert "(1 device(s) skipped)" in payload["msg"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.AnsibleModule")
def test_main_schedule_upgrade_succeeds_with_mixed_configured_and_schedule_in_progress(
    mock_ansible_module: MagicMock, _mock_get_connection: MagicMock
) -> None:
    """A batch where one device was actually scheduled (changed=True) and another was held back
    as schedule_in_progress must still succeed overall — the busy device doesn't block the rest
    and doesn't itself count as a failure."""
    mod = _mock_module(
        _base_params(operation="schedule_upgrade", lifecycle_state=None, release="Latest", upgrade_action="Install")
    )
    mock_ansible_module.return_value = mod
    manager = MagicMock()
    manager.schedule_upgrade.return_value = {
        "changed": True,
        "configured_devices": ["edge-2-sdktest"],
        "skipped_devices": [],
        "not_connected_devices": [],
        "schedule_in_progress_devices": ["edge-1-sdktest"],
        "completed_devices": ["edge-2-sdktest"],
        "failed_devices": [],
        "in_progress_devices": [],
        "insync_devices": ["edge-2-sdktest"],
        "not_insync_devices": [],
    }
    gc = MagicMock()
    gc.device_lifecycle = manager
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle.main()

    mod.fail_json.assert_not_called()
    mod.exit_json.assert_called_once()
    payload = mod.exit_json.call_args[1]
    assert payload["changed"] is True
    assert payload["schedule_in_progress_devices"] == ["edge-1-sdktest"]
    assert payload["configured_devices"] == ["edge-2-sdktest"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.AnsibleModule")
def test_main_rollback_fails_when_device_not_insync_after_success(
    mock_ansible_module: MagicMock, _mock_get_connection: MagicMock
) -> None:
    mod = _mock_module(_base_params(operation="rollback", lifecycle_state=None))
    mock_ansible_module.return_value = mod
    manager = MagicMock()
    manager.rollback.return_value = {
        "changed": True,
        "configured_devices": ["edge-1-sdktest"],
        "skipped_devices": [],
        "completed_devices": ["edge-1-sdktest"],
        "failed_devices": [],
        "in_progress_devices": [],
        "insync_devices": [],
        "not_insync_devices": ["edge-1-sdktest"],
    }
    gc = MagicMock()
    gc.device_lifecycle = manager
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle.main()

    mod.exit_json.assert_not_called()
    mod.fail_json.assert_called_once()
    payload = mod.fail_json.call_args[1]
    assert payload["not_insync_devices"] == ["edge-1-sdktest"]
    assert "edge-1-sdktest" in payload["msg"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.AnsibleModule")
def test_main_rollback_with_diff_mode(mock_ansible_module: MagicMock, _mock_get_connection: MagicMock) -> None:
    mod = _mock_module(_base_params(operation="rollback", lifecycle_state=None))
    mod._diff = True
    mock_ansible_module.return_value = mod
    manager = MagicMock()
    manager.rollback.return_value = {
        "changed": True,
        "configured_devices": ["edge-1-sdktest"],
        "diff_plan": [
            {
                "device": "edge-1-sdktest",
                "branch": "rollback",
                "before": {"release": "Latest", "version": "2609.1"},
                "after": {"release": "Stable", "version": "2512.1"},
            }
        ],
    }
    gc = MagicMock()
    gc.device_lifecycle = manager
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle.main()

    mod.exit_json.assert_called_once()
    payload = mod.exit_json.call_args[1]
    assert "diff" in payload
    assert "2609.1" in payload["diff"]["before"]
    assert "2512.1" in payload["diff"]["after"]


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.AnsibleModule")
def test_main_rollback_check_mode_msg_says_would(
    mock_ansible_module: MagicMock, _mock_get_connection: MagicMock
) -> None:
    mod = _mock_module(_base_params(operation="rollback", lifecycle_state=None))
    mod.check_mode = True
    mock_ansible_module.return_value = mod
    manager = MagicMock()
    manager.rollback.return_value = {"changed": True, "configured_devices": ["edge-1-sdktest"]}
    gc = MagicMock()
    gc.device_lifecycle = manager
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle.main()

    payload = mod.exit_json.call_args[1]
    assert payload["msg"].startswith("[check_mode]")
    assert "would" in payload["msg"].lower()


# get_status/read-only tests live in test_graphiant_device_lifecycle_info.py (separate module).


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.AnsibleModule")
def test_main_operation_not_resolved_from_config_file(
    mock_ansible_module: MagicMock, _mock_get_connection: MagicMock
) -> None:
    """
    operation is module-parameter only (one invocation runs exactly one operation for the whole
    batch): a top-level 'operation' key in config_file is never read, even when present, unlike
    verify_for_insync/wait_for_completion which can still be set per device in that same file.
    """
    mod = _mock_module(
        _base_params(operation=None, config_file="sample_device_lifecycle.yaml", device=None, lifecycle_state=None)
    )
    mock_ansible_module.return_value = mod
    manager = MagicMock()
    gc = MagicMock()
    gc.device_lifecycle = manager
    gc.config_utils.render_config_file.return_value = {"operation": "schedule_upgrade"}
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle.main()

    gc.config_utils.render_config_file.assert_not_called()
    manager.schedule_upgrade.assert_not_called()
    manager.change_state.assert_not_called()
    mod.exit_json.assert_not_called()
    mod.fail_json.assert_called_once()
    assert "operation" in mod.fail_json.call_args[1]["msg"].lower()


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.AnsibleModule")
def test_main_explicit_operation_overrides_config_file_and_skips_peek(
    mock_ansible_module: MagicMock, _mock_get_connection: MagicMock
) -> None:
    mod = _mock_module(_base_params(operation="change_state", config_file="sample_device_lifecycle.yaml"))
    mock_ansible_module.return_value = mod
    manager = MagicMock()
    manager.change_state.return_value = {"changed": True, "configured_devices": ["edge-1-sdktest"]}
    gc = MagicMock()
    gc.device_lifecycle = manager
    # If the file were read for 'operation', this would derail dispatch to rollback instead.
    gc.config_utils.render_config_file.return_value = {"operation": "rollback"}
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle.main()

    gc.config_utils.render_config_file.assert_not_called()
    manager.change_state.assert_called_once()
    manager.rollback.assert_not_called()


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_device_lifecycle.AnsibleModule")
def test_main_operation_missing_everywhere_fails_cleanly(
    mock_ansible_module: MagicMock, _mock_get_connection: MagicMock
) -> None:
    mod = _mock_module(
        _base_params(operation=None, config_file="sample_device_lifecycle.yaml", device=None, lifecycle_state=None)
    )
    mock_ansible_module.return_value = mod
    manager = MagicMock()
    gc = MagicMock()
    gc.device_lifecycle = manager
    gc.config_utils.render_config_file.return_value = {"device_lifecycle": []}
    _mock_get_connection.return_value = MagicMock(graphiant_config=gc)

    graphiant_device_lifecycle.main()

    mod.exit_json.assert_not_called()
    mod.fail_json.assert_called_once()
    assert "operation" in mod.fail_json.call_args[1]["msg"].lower()
