# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for DeviceLifecycleManager (mocked GSDK / config; no live API)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ansible_collections.graphiant.naas.plugins.module_utils.libs.device_lifecycle_manager import (
    DeviceLifecycleManager,
)
from ansible_collections.graphiant.naas.plugins.module_utils.libs.exceptions import (
    APIError,
    ConfigurationError,
    DeviceNotFoundError,
)


class _ImmediateFuture:
    """Minimal stand-in for a ``concurrent.futures.Future`` that already ran."""

    def __init__(self, value) -> None:
        self._value = value

    def result(self, timeout=None):  # noqa: ARG002 - matches Future.result's signature
        return self._value


def _sync_concurrent_task_execution(function, config_dict):
    """
    Test double for ``ConfigUtils.concurrent_task_execution``: runs each task synchronously
    (no real threads) but keeps the same interface (dict of key -> Future-like with
    ``.result()``), so change_state's real (non-mocked) ``execute_concurrent_tasks`` call for the
    readiness poll behaves observably like production without thread non-determinism in tests.
    """
    return {key: _ImmediateFuture(function(**kwargs)) for key, kwargs in config_dict.items()}


def _make_manager() -> DeviceLifecycleManager:
    config_utils = MagicMock()
    config_utils.gsdk = MagicMock()
    config_utils.gsdk.enterprise_info = {"company_name": "Acme"}
    config_utils.gsdk.check_mode = False
    # Real GraphiantPortalClient.UPGRADE_SCHEDULE_TERMINAL_STATES, not an auto-mocked attribute —
    # needed for _schedule_in_progress_state's "state in ..." check to behave like production.
    config_utils.gsdk.UPGRADE_SCHEDULE_TERMINAL_STATES = frozenset({"Success", "Failed"})
    # Default: every upgrade-schedule poll immediately reports Success for whichever device_ids
    # are asked about, so existing schedule_upgrade/rollback tests (which don't care about
    # completion polling) aren't affected by wait_for_completion defaulting to True. Tests
    # exercising the poll itself override this per-test.
    config_utils.gsdk.poll_upgrade_schedule_completion_batch = MagicMock(
        side_effect=lambda device_ids: {device_id: ("Success", None) for device_id in device_ids}
    )
    config_utils.concurrent_task_execution = MagicMock(side_effect=_sync_concurrent_task_execution)
    return DeviceLifecycleManager(config_utils)


def _sw_version(release, version, name):
    # MagicMock(name=...) sets the mock's repr, not a `.name` attribute, so set it after creation.
    m = MagicMock(release=release, version=version)
    m.name = name
    return m


def _schedule(state):
    m = MagicMock()
    m.state = state
    return m


def _edge(hostname="edge-1", device_id=100, status="active", upgrade_summary=None, tt_conn_count=2):
    edge = MagicMock()
    edge.hostname = hostname
    edge.device_id = device_id
    edge.status = status
    edge.upgrade_summary = upgrade_summary
    # Default to "Up" (>=2) so existing tests that don't care about connectivity aren't affected
    # by schedule_upgrade's portal-connectivity skip (see test_schedule_upgrade_skips_device_*).
    edge.tt_conn_count = tt_conn_count
    return edge


def test_configure_not_supported() -> None:
    mgr = _make_manager()
    with pytest.raises(ConfigurationError, match="no 'configure' workflow"):
        mgr.configure("any.yaml")


def test_deconfigure_not_supported() -> None:
    mgr = _make_manager()
    with pytest.raises(ConfigurationError, match="Deconfigure is not applicable"):
        mgr.deconfigure("any.yaml")


# ---------------------------------------------------------------------------
# change_state
# ---------------------------------------------------------------------------


def test_change_state_no_input_returns_no_input_flag() -> None:
    mgr = _make_manager()
    mgr.config_utils.render_config_file = MagicMock(return_value={})
    r = mgr.change_state("cfg.yaml", {"device": None})
    assert r["no_input"] is True
    assert r["changed"] is False


def test_change_state_skips_when_already_desired() -> None:
    mgr = _make_manager()
    mgr.gsdk.get_edges_summary.return_value = [_edge(status="active")]
    r = mgr.change_state(None, {"device": "edge-1", "lifecycle_state": "activated"})
    assert r["changed"] is False
    assert r["skipped_devices"] == ["edge-1"]
    mgr.gsdk.put_devices_bringup.assert_not_called()


def test_change_state_pushes_when_different() -> None:
    mgr = _make_manager()
    mgr.gsdk.get_edges_summary.return_value = [_edge(status="active")]
    mgr.gsdk.put_devices_bringup.return_value = True
    r = mgr.change_state(None, {"device": "edge-1", "lifecycle_state": "staging"})
    assert r["changed"] is True
    assert r["configured_devices"] == ["edge-1"]
    assert r["insync_devices"] == ["edge-1"]
    assert r["not_insync_devices"] == []
    mgr.gsdk.put_devices_bringup.assert_called_once_with([100], "Pending")
    mgr.gsdk.verify_device_portal_status.assert_called_once_with(100)


def test_change_state_raises_when_put_devices_bringup_fails() -> None:
    """
    A genuine put_devices_bringup failure must still raise (unlike a readiness-poll timeout),
    even though it's now submitted through the same concurrent batch as the poll.
    """
    mgr = _make_manager()
    mgr.gsdk.get_edges_summary.return_value = [_edge(status="active")]
    mgr.gsdk.put_devices_bringup.return_value = False

    with pytest.raises(APIError, match="Failed to change lifecycle state"):
        mgr.change_state(None, {"device": "edge-1", "lifecycle_state": "staging"})

    mgr.gsdk.verify_device_portal_status.assert_not_called()


def test_change_state_logs_table_before_mutation(caplog) -> None:
    import logging as _logging

    mgr = _make_manager()
    mgr.gsdk.get_edges_summary.return_value = [_edge(status="active")]
    mgr.gsdk.put_devices_bringup.return_value = True

    with caplog.at_level(_logging.INFO, logger="Graphiant_playbook"):
        mgr.change_state(None, {"device": "edge-1", "lifecycle_state": "staging"})

    table_message = next(r.message for r in caplog.records if "Current state before change_state" in r.message)
    assert "edge-1" in table_message


def test_change_state_logs_table_after_mutation_reflects_new_state(caplog) -> None:
    import logging as _logging

    mgr = _make_manager()
    calls = {"n": 0}

    def _get_edges_summary():
        calls["n"] += 1
        # First call is the pre-op resolve; second is the post-op refetch after the PUT — the
        # post-op table must show the device's new state, not repeat the pre-op one.
        status = "active" if calls["n"] == 1 else "staging"
        return [_edge(status=status)]

    mgr.gsdk.get_edges_summary.side_effect = _get_edges_summary
    mgr.gsdk.put_devices_bringup.return_value = True

    with caplog.at_level(_logging.INFO, logger="Graphiant_playbook"):
        mgr.change_state(None, {"device": "edge-1", "lifecycle_state": "staging"})

    before_table = next(r.message for r in caplog.records if "Current state before change_state" in r.message)
    after_table = next(r.message for r in caplog.records if "Resulting state after change_state" in r.message)
    assert "edge-1" in after_table
    # tabulate's Lifecycle State column: pre-op shows the old value, post-op the new one.
    before_lines = [line for line in before_table.splitlines() if "edge-1" in line]
    after_lines = [line for line in after_table.splitlines() if "edge-1" in line]
    assert "activated" in before_lines[0]
    assert "staging" in after_lines[0]


def test_change_state_skips_post_op_table_in_check_mode(caplog) -> None:
    import logging as _logging

    mgr = _make_manager()
    mgr.gsdk.check_mode = True
    mgr.gsdk.get_edges_summary.return_value = [_edge(status="active")]
    mgr.gsdk.put_devices_bringup.return_value = True

    with caplog.at_level(_logging.INFO, logger="Graphiant_playbook"):
        mgr.change_state(None, {"device": "edge-1", "lifecycle_state": "staging"})

    messages = [r.message for r in caplog.records]
    assert any("Current state before change_state" in m for m in messages)
    assert not any("Resulting state after change_state" in m for m in messages)


def test_change_state_post_op_table_skips_device_that_vanished_after_decommission(caplog) -> None:
    import logging as _logging

    mgr = _make_manager()
    calls = {"n": 0}

    def _get_edges_summary():
        calls["n"] += 1
        if calls["n"] == 1:
            return [_edge(status="inactive")]
        return []  # decommissioned device disappeared from edges-summary on refetch

    mgr.gsdk.get_edges_summary.side_effect = _get_edges_summary
    mgr.gsdk.put_devices_bringup.return_value = True

    with caplog.at_level(_logging.INFO, logger="Graphiant_playbook"):
        r = mgr.change_state(None, {"device": "edge-1", "lifecycle_state": "decommissioned"})

    assert r["configured_devices"] == ["edge-1"]
    messages = [rec.message for rec in caplog.records]
    assert any("no longer resolvable for the post-op table" in m for m in messages)


def test_change_state_logs_transition_action(caplog) -> None:
    import logging as _logging

    mgr = _make_manager()
    mgr.gsdk.get_edges_summary.return_value = [_edge(status="active")]
    mgr.gsdk.put_devices_bringup.return_value = True

    with caplog.at_level(_logging.INFO, logger="Graphiant_playbook"):
        mgr.change_state(None, {"device": "edge-1", "lifecycle_state": "staging"})

    messages = [r.message for r in caplog.records]
    assert any("Changing edge-1: activated -> staging" in m for m in messages)
    assert any("✓ Changed edge-1 to staging" in m for m in messages)
    assert not any("check_mode" in m for m in messages)


def test_change_state_logs_transition_action_check_mode(caplog) -> None:
    import logging as _logging

    mgr = _make_manager()
    mgr.gsdk.check_mode = True
    mgr.gsdk.get_edges_summary.return_value = [_edge(status="active")]
    mgr.gsdk.put_devices_bringup.return_value = True

    with caplog.at_level(_logging.INFO, logger="Graphiant_playbook"):
        mgr.change_state(None, {"device": "edge-1", "lifecycle_state": "staging"})

    messages = [r.message for r in caplog.records]
    assert any("[check_mode] Would change edge-1: activated -> staging" in m for m in messages)
    assert any("[check_mode] ✓ Would change edge-1 to staging (no changes applied)" in m for m in messages)


def test_change_state_skips_readiness_poll_for_deactivate() -> None:
    mgr = _make_manager()
    mgr.gsdk.get_edges_summary.return_value = [_edge(status="active")]
    mgr.gsdk.put_devices_bringup.return_value = True
    r = mgr.change_state(None, {"device": "edge-1", "lifecycle_state": "deactivated"})
    assert r["changed"] is True
    mgr.gsdk.verify_device_portal_status.assert_not_called()


def test_change_state_verify_for_insync_false_skips_poll() -> None:
    mgr = _make_manager()
    mgr.gsdk.get_edges_summary.return_value = [_edge(status="active")]
    mgr.gsdk.put_devices_bringup.return_value = True
    r = mgr.change_state(None, {"device": "edge-1", "lifecycle_state": "staging"}, verify_for_insync=False)
    assert r["changed"] is True
    mgr.gsdk.verify_device_portal_status.assert_not_called()


def test_change_state_per_device_verify_for_insync_false_skips_poll_for_that_device_only() -> None:
    """
    verify_for_insync is a per-device setting (not a top-level YAML key): a device's own
    'verify_for_insync: false' opts it out of the readiness poll even though the module-param
    default (and the other device's own entry) is True.
    """
    mgr = _make_manager()
    mgr.config_utils.render_config_file = MagicMock(
        return_value={
            "device_lifecycle": [
                {"edge-1": {"lifecycle_state": "staging", "verify_for_insync": False}},
                {"edge-2": {"lifecycle_state": "staging"}},
            ],
        }
    )
    mgr.gsdk.get_edges_summary.return_value = [
        _edge(hostname="edge-1", device_id=100, status="active"),
        _edge(hostname="edge-2", device_id=200, status="active"),
    ]
    mgr.gsdk.put_devices_bringup.return_value = True

    r = mgr.change_state("cfg.yaml", {"device": None})

    assert r["changed"] is True
    mgr.gsdk.verify_device_portal_status.assert_called_once_with(200)
    assert r["insync_devices"] == ["edge-2"]
    assert r["not_insync_devices"] == []


def test_change_state_explicit_verify_for_insync_overrides_yaml() -> None:
    mgr = _make_manager()
    mgr.config_utils.render_config_file = MagicMock(
        return_value={
            "verify_for_insync": False,
            "device_lifecycle": [{"edge-1": {"lifecycle_state": "staging"}}],
        }
    )
    mgr.gsdk.get_edges_summary.return_value = [_edge(status="active")]
    mgr.gsdk.put_devices_bringup.return_value = True

    r = mgr.change_state("cfg.yaml", {"device": None}, verify_for_insync=True)

    assert r["changed"] is True
    mgr.gsdk.verify_device_portal_status.assert_called_once_with(100)


def test_change_state_not_ready_is_recorded_not_raised() -> None:
    mgr = _make_manager()
    mgr.gsdk.get_edges_summary.return_value = [_edge(status="active")]
    mgr.gsdk.put_devices_bringup.return_value = True
    mgr.gsdk.verify_device_portal_status.side_effect = Exception("timed out")
    r = mgr.change_state(None, {"device": "edge-1", "lifecycle_state": "staging"})
    assert r["changed"] is True
    assert r["not_insync_devices"] == ["edge-1"]
    # edge-1 was polled (it's a staging change) but failed, so it must not also show up as ready.
    assert r["insync_devices"] == []


def test_change_state_applies_multiple_devices_in_one_concurrent_batch() -> None:
    """
    Both the PUT (put_devices_bringup) and the readiness poll for several devices (here: edge-1
    and edge-2) must be submitted as a single concurrent_task_execution batch covering both
    device names, not one call per device — that's what makes both steps run concurrently
    instead of the devices waiting on each other's PUT pause / ~180s poll timeout in turn.
    """
    mgr = _make_manager()
    mgr.config_utils.render_config_file = MagicMock(
        return_value={
            "device_lifecycle": [
                {"edge-1": {"lifecycle_state": "staging"}},
                {"edge-2": {"lifecycle_state": "staging"}},
            ]
        }
    )
    mgr.gsdk.get_edges_summary.return_value = [
        _edge(hostname="edge-1", device_id=100, status="active"),
        _edge(hostname="edge-2", device_id=200, status="active"),
    ]
    mgr.gsdk.put_devices_bringup.return_value = True

    r = mgr.change_state("cfg.yaml", {"device": None}, verify_for_insync=True)

    assert r["changed"] is True
    assert set(r["configured_devices"]) == {"edge-1", "edge-2"}
    mgr.config_utils.concurrent_task_execution.assert_called_once()
    (apply_function, apply_config_dict), _kwargs = mgr.config_utils.concurrent_task_execution.call_args
    assert set(apply_config_dict) == {"edge-1", "edge-2"}
    assert apply_config_dict["edge-1"]["device_id"] == 100
    assert apply_config_dict["edge-1"]["desired"] == "staging"
    assert apply_config_dict["edge-2"]["device_id"] == 200
    assert apply_function == mgr._apply_device_change
    mgr.gsdk.put_devices_bringup.assert_any_call([100], "Pending")
    mgr.gsdk.put_devices_bringup.assert_any_call([200], "Pending")
    assert mgr.gsdk.verify_device_portal_status.call_count == 2
    mgr.gsdk.verify_device_portal_status.assert_any_call(100)
    mgr.gsdk.verify_device_portal_status.assert_any_call(200)


def test_change_state_resolves_batch_with_one_shared_fetch_per_round() -> None:
    """
    Resolving N devices must cost exactly one get_edges_summary() call per round (pre-op resolve,
    post-op refetch) — not one call per device — regardless of how many devices are in the batch.
    """
    mgr = _make_manager()
    mgr.config_utils.render_config_file = MagicMock(
        return_value={
            "device_lifecycle": [
                {"edge-1": {"lifecycle_state": "staging"}},
                {"edge-2": {"lifecycle_state": "staging"}},
                {"edge-3": {"lifecycle_state": "staging"}},
            ]
        }
    )
    mgr.gsdk.get_edges_summary.return_value = [
        _edge(hostname="edge-1", device_id=100, status="active"),
        _edge(hostname="edge-2", device_id=200, status="active"),
        _edge(hostname="edge-3", device_id=300, status="active"),
    ]
    mgr.gsdk.put_devices_bringup.return_value = True

    mgr.change_state("cfg.yaml", {"device": None})

    # Pre-op resolve (1) + post-op refetch (1) = 2, independent of the 3-device batch size.
    assert mgr.gsdk.get_edges_summary.call_count == 2


def test_change_state_insync_and_not_insync_devices_partition_configured_devices() -> None:
    """
    With one device reaching Ready and another not, insync_devices and not_insync_devices must be
    the exact complement of each other within configured_devices — neither device should be
    missing from both, or present in both.
    """
    mgr = _make_manager()
    mgr.config_utils.render_config_file = MagicMock(
        return_value={
            "device_lifecycle": [
                {"edge-1": {"lifecycle_state": "staging"}},
                {"edge-2": {"lifecycle_state": "staging"}},
            ]
        }
    )
    mgr.gsdk.get_edges_summary.return_value = [
        _edge(hostname="edge-1", device_id=100, status="active"),
        _edge(hostname="edge-2", device_id=200, status="active"),
    ]
    mgr.gsdk.put_devices_bringup.return_value = True
    mgr.gsdk.verify_device_portal_status.side_effect = lambda device_id: (
        (x for x in ()).throw(Exception("timed out")) if device_id == 200 else None
    )

    r = mgr.change_state("cfg.yaml", {"device": None}, verify_for_insync=True)

    assert set(r["configured_devices"]) == {"edge-1", "edge-2"}
    assert r["insync_devices"] == ["edge-1"]
    assert r["not_insync_devices"] == ["edge-2"]


def test_change_state_decommission_requires_deactivated() -> None:
    mgr = _make_manager()
    mgr.gsdk.get_edges_summary.return_value = [_edge(status="active")]
    with pytest.raises(ConfigurationError, match="must be Deactivated"):
        mgr.change_state(None, {"device": "edge-1", "lifecycle_state": "decommissioned"})
    mgr.gsdk.put_devices_bringup.assert_not_called()


def test_change_state_decommission_batch_collects_every_violation() -> None:
    """
    A config file with several premature decommission requests must report ALL of them in one
    ConfigurationError (like missing_devices_message's collect-all behavior), not just the first
    one encountered in iteration order — and no PUT must go out for the batch's otherwise-valid
    device either, since validation for the whole batch runs before any apply_tasks are issued.
    """
    mgr = _make_manager()
    mgr.config_utils.render_config_file = MagicMock(
        return_value={
            "device_lifecycle": [
                {"edge-1": {"lifecycle_state": "deactivated"}},
                {"edge-2": {"lifecycle_state": "decommissioned"}},
                {"edge-3": {"lifecycle_state": "decommissioned"}},
            ]
        }
    )
    mgr.gsdk.get_edges_summary.return_value = [
        _edge(hostname="edge-1", device_id=100, status="active"),
        _edge(hostname="edge-2", device_id=200, status="active"),
        _edge(hostname="edge-3", device_id=300, status="staging"),
    ]

    with pytest.raises(ConfigurationError) as exc_info:
        mgr.change_state("cfg.yaml", {"device": None})

    message = str(exc_info.value)
    assert "edge-2" in message
    assert "edge-3" in message
    assert "2 device(s)" in message
    mgr.gsdk.put_devices_bringup.assert_not_called()


def test_change_state_decommission_allowed_when_deactivated() -> None:
    mgr = _make_manager()
    mgr.gsdk.get_edges_summary.return_value = [_edge(status="inactive")]
    mgr.gsdk.put_devices_bringup.return_value = True
    r = mgr.change_state(None, {"device": "edge-1", "lifecycle_state": "decommissioned"})
    assert r["changed"] is True
    mgr.gsdk.put_devices_bringup.assert_called_once_with([100], "Removed")
    mgr.gsdk.verify_device_portal_status.assert_not_called()


def test_change_state_decommission_already_gone_is_idempotent_skip() -> None:
    # A decommissioned device is removed from edges-summary entirely, so by_hostname has no entry
    # for it; re-running decommissioned should be a no-op, not an error.
    mgr = _make_manager()
    mgr.gsdk.get_edges_summary.return_value = []
    r = mgr.change_state(None, {"device": "edge-1", "lifecycle_state": "decommissioned"})
    assert r["changed"] is False
    assert r["skipped_devices"] == ["edge-1"]
    mgr.gsdk.put_devices_bringup.assert_not_called()


def test_change_state_device_gone_for_non_decommission_state_still_raises() -> None:
    mgr = _make_manager()
    mgr.gsdk.get_edges_summary.return_value = []
    with pytest.raises(DeviceNotFoundError):
        mgr.change_state(None, {"device": "ghost", "lifecycle_state": "staging"})


def test_change_state_invalid_lifecycle_state_rejected() -> None:
    mgr = _make_manager()
    with pytest.raises(ConfigurationError, match="invalid lifecycle_state"):
        mgr.change_state(None, {"device": "edge-1", "lifecycle_state": "bogus"})


def test_change_state_missing_device_raises_not_found() -> None:
    mgr = _make_manager()
    mgr.gsdk.get_edges_summary.return_value = []
    with pytest.raises(DeviceNotFoundError):
        mgr.change_state(None, {"device": "ghost", "lifecycle_state": "activated"})


def test_change_state_multiple_missing_devices_reported_together() -> None:
    """
    Several bad device names in one config file must all surface in a single failure, not one
    fix-and-retry cycle per name — the resolution loop collects every unresolved device before
    raising, instead of stopping at the first.
    """
    mgr = _make_manager()
    mgr.config_utils.render_config_file = MagicMock(
        return_value={
            "device_lifecycle": [
                {"edge-1": {"lifecycle_state": "activated"}},
                {"ghost-1": {"lifecycle_state": "activated"}},
                {"ghost-2": {"lifecycle_state": "activated"}},
            ],
        }
    )
    mgr.gsdk.get_edges_summary.return_value = [_edge(status="active")]

    with pytest.raises(DeviceNotFoundError, match="ghost-1") as exc_info:
        mgr.change_state("cfg.yaml", {"device": None})
    assert "ghost-2" in str(exc_info.value)
    assert "edge-1" not in str(exc_info.value)
    mgr.gsdk.put_devices_bringup.assert_not_called()


def test_change_state_check_mode_still_reports_would_change() -> None:
    mgr = _make_manager()
    mgr.gsdk.check_mode = True
    mgr.gsdk.get_edges_summary.return_value = [_edge(status="active")]
    # In check_mode, put_devices_bringup itself no-ops and returns True (see gcsdk_client.py).
    mgr.gsdk.put_devices_bringup.return_value = True
    r = mgr.change_state(None, {"device": "edge-1", "lifecycle_state": "staging"})
    assert r["changed"] is True
    assert r["configured_devices"] == ["edge-1"]
    mgr.gsdk.verify_device_portal_status.assert_not_called()


# ---------------------------------------------------------------------------
# schedule_upgrade
# ---------------------------------------------------------------------------


def test_schedule_upgrade_no_input() -> None:
    mgr = _make_manager()
    mgr.config_utils.render_config_file = MagicMock(return_value={})
    r = mgr.schedule_upgrade("cfg.yaml", {"device": None})
    assert r["no_input"] is True


def test_schedule_upgrade_builds_device_versions_and_calls_gsdk() -> None:
    mgr = _make_manager()
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [_edge(hostname="edge-1", device_id=100)]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True
    r = mgr.schedule_upgrade(
        None, {"device": "edge-1", "release": "Latest"}, action="InstallActivate"
    )
    assert r["changed"] is True
    assert r["configured_devices"] == ["edge-1"]
    mgr.gsdk.put_devices_upgrade_schedule.assert_called_once_with(
        device_versions=[{"deviceId": 100, "version": {"release": "Latest"}}],
        action="InstallActivate",
        ts=None,
    )


def test_schedule_upgrade_diff_plan_shows_resolved_target_version() -> None:
    """
    diff_plan's "after" includes the release channel's current build (from release_catalog)
    when resolvable, matching the version actually compared against in the skip check.
    """
    mgr = _make_manager()
    upgrade_summary = MagicMock()
    upgrade_summary.running_version = _sw_version("Latest", "2604.1", "26.4.1")
    upgrade_summary.schedule = None
    edge = _edge(hostname="edge-1", device_id=100, upgrade_summary=upgrade_summary)
    edge.sw_version = "2604.1"
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [edge]
    mgr.gsdk.get_software_releases_summary.return_value = [_release_summary("2610.1", "Latest", "26.10.1")]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True

    r = mgr.schedule_upgrade(None, {"device": "edge-1", "release": "Latest"})

    assert r["diff_plan"] == [
        {
            "device": "edge-1",
            "branch": "schedule_upgrade",
            "before": {"release": "Latest", "version": "2604.1", "name": "26.4.1"},
            "after": {"release": "Latest", "version": "2610.1"},
        }
    ]


def test_schedule_upgrade_diff_plan_falls_back_to_release_only_when_unresolvable() -> None:
    """When the requested release isn't in release_catalog, "after" has no "version" key."""
    mgr = _make_manager()
    edge = _edge(hostname="edge-1", device_id=100)
    edge.sw_version = "2604.1"
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [edge]
    mgr.gsdk.get_software_releases_summary.return_value = []
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True

    r = mgr.schedule_upgrade(None, {"device": "edge-1", "release": "Latest"})

    assert r["diff_plan"] == [
        {
            "device": "edge-1",
            "branch": "schedule_upgrade",
            "before": None,
            "after": {"release": "Latest"},
        }
    ]


def test_schedule_upgrade_polls_and_reports_completed_devices() -> None:
    mgr = _make_manager()
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [_edge(hostname="edge-1", device_id=100)]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True
    mgr.gsdk.poll_upgrade_schedule_completion_batch.return_value = {100: ("Success", None)}

    r = mgr.schedule_upgrade(None, {"device": "edge-1", "release": "Latest"})

    assert r["changed"] is True
    assert r["completed_devices"] == ["edge-1"]
    assert r["failed_devices"] == []
    assert r["in_progress_devices"] == []
    mgr.gsdk.poll_upgrade_schedule_completion_batch.assert_called_once_with([100])


def test_schedule_upgrade_reports_failed_device_and_logs_failure_reason(caplog) -> None:
    import logging as _logging

    mgr = _make_manager()
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [_edge(hostname="edge-1", device_id=100)]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True
    mgr.gsdk.poll_upgrade_schedule_completion_batch.side_effect = None
    mgr.gsdk.poll_upgrade_schedule_completion_batch.return_value = {100: ("Failed", "Internal error")}

    with caplog.at_level(_logging.WARNING, logger="Graphiant_playbook"):
        r = mgr.schedule_upgrade(None, {"device": "edge-1", "release": "Latest"})

    assert r["changed"] is True
    assert r["failed_devices"] == ["edge-1"]
    assert r["completed_devices"] == []
    messages = [rec.message for rec in caplog.records]
    assert any("edge-1" in m and "Internal error" in m for m in messages)


def test_schedule_upgrade_poll_timeout_is_in_progress_not_failed() -> None:
    """A timeout before reaching Success/Failed is still in progress, not a failure — downloads
    and installs can genuinely take minutes."""
    mgr = _make_manager()
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [_edge(hostname="edge-1", device_id=100)]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True
    mgr.gsdk.poll_upgrade_schedule_completion_batch.side_effect = None
    mgr.gsdk.poll_upgrade_schedule_completion_batch.return_value = {100: (None, None)}

    r = mgr.schedule_upgrade(None, {"device": "edge-1", "release": "Latest"})

    assert r["changed"] is True
    assert r["in_progress_devices"] == ["edge-1"]
    assert r["failed_devices"] == []
    assert r["completed_devices"] == []


def test_schedule_upgrade_polls_for_ready_after_success_and_reports_not_insync_on_timeout() -> None:
    """
    A device whose schedule reaches Success isn't necessarily fully settled from the portal's own
    perspective yet (portalStatus can still read ConfigPullInitiated/Configuring for a while) —
    so it's also polled for Ready, same as change_state. A poll timeout here is a real failure
    (not_insync_devices), even though the schedule itself already succeeded.
    """
    mgr = _make_manager()
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [_edge(hostname="edge-1", device_id=100)]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True
    mgr.gsdk.poll_upgrade_schedule_completion_batch.side_effect = None
    mgr.gsdk.poll_upgrade_schedule_completion_batch.return_value = {100: ("Success", None)}
    mgr.gsdk.verify_device_portal_status.side_effect = Exception("timed out")

    r = mgr.schedule_upgrade(None, {"device": "edge-1", "release": "Latest"})

    assert r["completed_devices"] == ["edge-1"]
    assert r["not_insync_devices"] == ["edge-1"]
    assert r["insync_devices"] == []
    mgr.gsdk.verify_device_portal_status.assert_called_once_with(100)


def test_schedule_upgrade_ready_poll_not_run_for_failed_or_in_progress_device() -> None:
    """Only a device whose schedule reached Success is Ready-polled — Failed/timed-out devices
    have nothing to confirm yet."""
    mgr = _make_manager()
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [
        _edge(hostname="edge-1", device_id=100),
        _edge(hostname="edge-2", device_id=200),
    ]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True
    mgr.gsdk.poll_upgrade_schedule_completion_batch.side_effect = None
    mgr.gsdk.poll_upgrade_schedule_completion_batch.return_value = {
        100: ("Failed", "Internal error"),
        200: (None, None),
    }

    mgr.config_utils.render_config_file = MagicMock(
        return_value={"device_lifecycle": [{"edge-1": {"release": "Stable"}}, {"edge-2": {"release": "Stable"}}]}
    )
    r = mgr.schedule_upgrade("cfg.yaml", {"device": None})

    assert r["failed_devices"] == ["edge-1"]
    assert r["in_progress_devices"] == ["edge-2"]
    assert r["insync_devices"] == []
    assert r["not_insync_devices"] == []
    mgr.gsdk.verify_device_portal_status.assert_not_called()


def test_schedule_upgrade_ready_poll_skipped_when_verify_for_insync_false() -> None:
    mgr = _make_manager()
    mgr.config_utils.render_config_file = MagicMock(
        return_value={
            "device_lifecycle": [{"edge-1": {"release": "Stable", "verify_for_insync": False}}],
        }
    )
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [_edge(hostname="edge-1", device_id=100)]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True
    mgr.gsdk.poll_upgrade_schedule_completion_batch.side_effect = None
    mgr.gsdk.poll_upgrade_schedule_completion_batch.return_value = {100: ("Success", None)}

    r = mgr.schedule_upgrade("cfg.yaml", {"device": None})

    assert r["completed_devices"] == ["edge-1"]
    assert r["insync_devices"] == []
    assert r["not_insync_devices"] == []
    mgr.gsdk.verify_device_portal_status.assert_not_called()


def test_schedule_upgrade_wait_for_completion_false_skips_poll() -> None:
    mgr = _make_manager()
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [_edge(hostname="edge-1", device_id=100)]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True

    r = mgr.schedule_upgrade(
        None, {"device": "edge-1", "release": "Latest"}, wait_for_completion=False
    )

    assert r["changed"] is True
    assert r["completed_devices"] == []
    assert r["failed_devices"] == []
    assert r["in_progress_devices"] == []
    mgr.gsdk.poll_upgrade_schedule_completion_batch.assert_not_called()


def test_schedule_upgrade_per_device_wait_for_completion_override() -> None:
    """
    wait_for_completion is a per-device setting: a device's own 'wait_for_completion: false'
    opts it out of the completion poll even though the module-param default (and the other
    device's own entry) is True — but it is still scheduled either way.
    """
    mgr = _make_manager()
    mgr.config_utils.render_config_file = MagicMock(
        return_value={
            "device_lifecycle": [
                {"edge-1": {"release": "Stable", "wait_for_completion": False}},
                {"edge-2": {"release": "Stable"}},
            ],
        }
    )
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [
        _edge(hostname="edge-1", device_id=100),
        _edge(hostname="edge-2", device_id=200),
    ]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True

    r = mgr.schedule_upgrade("cfg.yaml", {"device": None})

    assert r["changed"] is True
    assert sorted(r["configured_devices"]) == ["edge-1", "edge-2"]
    assert r["completed_devices"] == ["edge-2"]
    mgr.gsdk.poll_upgrade_schedule_completion_batch.assert_called_once_with([200])


def test_schedule_upgrade_post_op_table_uses_one_shared_fetch_per_batch() -> None:
    """
    The post-op table refresh (_log_post_schedule_table) must cost exactly one
    get_edges_summary() call for the whole batch, not one call per scheduled device.
    """
    mgr = _make_manager()
    mgr.config_utils.render_config_file = MagicMock(
        return_value={
            "device_lifecycle": [
                {"edge-1": {"release": "Stable"}},
                {"edge-2": {"release": "Stable"}},
                {"edge-3": {"release": "Stable"}},
            ],
        }
    )
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [
        _edge(hostname="edge-1", device_id=100),
        _edge(hostname="edge-2", device_id=200),
        _edge(hostname="edge-3", device_id=300),
    ]
    mgr.gsdk.get_edges_summary.return_value = [
        _edge(hostname="edge-1", device_id=100),
        _edge(hostname="edge-2", device_id=200),
        _edge(hostname="edge-3", device_id=300),
    ]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True

    mgr.schedule_upgrade("cfg.yaml", {"device": None})

    assert mgr.gsdk.get_edges_summary.call_count == 1


def test_schedule_upgrade_check_mode_skips_poll() -> None:
    mgr = _make_manager()
    mgr.gsdk.check_mode = True
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [_edge(hostname="edge-1", device_id=100)]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True

    r = mgr.schedule_upgrade(None, {"device": "edge-1", "release": "Latest"})

    assert r["changed"] is True
    mgr.gsdk.poll_upgrade_schedule_completion_batch.assert_not_called()


def test_schedule_upgrade_logs_table_before_mutation(caplog) -> None:
    import logging as _logging

    mgr = _make_manager()
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [_edge(hostname="edge-1", device_id=100)]
    mgr.gsdk.get_software_releases_summary.return_value = [_release_summary("2512.1", "Stable", "25.12.8")]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True

    with caplog.at_level(_logging.INFO, logger="Graphiant_playbook"):
        mgr.schedule_upgrade(None, {"device": "edge-1", "release": "Stable"})

    table_message = next(r.message for r in caplog.records if "Current state before schedule_upgrade" in r.message)
    assert "edge-1" in table_message
    assert any("Release catalog" in r.message for r in caplog.records)


def test_schedule_upgrade_action_and_ts_default_when_omitted_ignores_yaml_top_level() -> None:
    """
    upgrade_action/ts apply to the whole batch (one PUT, one action/time) and so are
    module-parameter only: a top-level 'upgrade_action'/'ts' key in config_file is never read,
    even when present — only the module-param default (InstallActivate / no ts) applies here.
    """
    mgr = _make_manager()
    mgr.config_utils.render_config_file = MagicMock(
        return_value={
            "upgrade_action": "Install",
            "ts": {"seconds": 111, "nanos": 222},
            "device_lifecycle": [{"edge-1": {"release": "Stable"}}],
        }
    )
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [_edge(hostname="edge-1", device_id=100)]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True

    r = mgr.schedule_upgrade("cfg.yaml", {"device": None})

    assert r["changed"] is True
    mgr.gsdk.put_devices_upgrade_schedule.assert_called_once_with(
        device_versions=[{"deviceId": 100, "version": {"release": "Stable"}}],
        action="InstallActivate",
        ts=None,
    )


def test_schedule_upgrade_explicit_action_overrides_yaml() -> None:
    mgr = _make_manager()
    mgr.config_utils.render_config_file = MagicMock(
        return_value={
            "upgrade_action": "Install",
            "device_lifecycle": [{"edge-1": {"release": "Stable"}}],
        }
    )
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [_edge(hostname="edge-1", device_id=100)]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True

    mgr.schedule_upgrade("cfg.yaml", {"device": None}, action="InstallActivate")

    call_kwargs = mgr.gsdk.put_devices_upgrade_schedule.call_args.kwargs
    assert call_kwargs["action"] == "InstallActivate"


def test_schedule_upgrade_missing_release_raises() -> None:
    mgr = _make_manager()
    with pytest.raises(ConfigurationError, match="missing required 'release'"):
        mgr.schedule_upgrade(None, {"device": "edge-1", "release": None})


def test_schedule_upgrade_multiple_missing_devices_reported_together() -> None:
    """Several bad device names in one config file must all surface in a single failure (see
    test_change_state_multiple_missing_devices_reported_together)."""
    mgr = _make_manager()
    mgr.config_utils.render_config_file = MagicMock(
        return_value={
            "device_lifecycle": [
                {"edge-1": {"release": "Stable"}},
                {"ghost-1": {"release": "Stable"}},
                {"ghost-2": {"release": "Stable"}},
            ],
        }
    )
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [_edge(hostname="edge-1", device_id=100)]

    with pytest.raises(DeviceNotFoundError, match="ghost-1") as exc_info:
        mgr.schedule_upgrade("cfg.yaml", {"device": None})
    assert "ghost-2" in str(exc_info.value)
    assert "edge-1" not in str(exc_info.value)
    mgr.gsdk.put_devices_upgrade_schedule.assert_not_called()


def test_schedule_upgrade_api_failure_raises_api_error() -> None:
    mgr = _make_manager()
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [_edge(hostname="edge-1", device_id=100)]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = False
    from ansible_collections.graphiant.naas.plugins.module_utils.libs.exceptions import APIError

    with pytest.raises(APIError):
        mgr.schedule_upgrade(None, {"device": "edge-1", "release": "Stable"})


def test_schedule_upgrade_skips_device_already_on_requested_release_channel() -> None:
    """
    The device's current swVersion matches the build the "Stable" channel currently resolves to
    (via release_catalog) — a genuine no-op, so it must be skipped without calling the API.
    """
    mgr = _make_manager()
    edge = _edge(hostname="edge-1", device_id=100)
    edge.sw_version = "2512.202608290526"
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [edge]
    mgr.gsdk.get_software_releases_summary.return_value = [_release_summary("2512.202608290526", "Stable", "25.12.8")]

    r = mgr.schedule_upgrade(None, {"device": "edge-1", "release": "Stable"})

    assert r["changed"] is False
    assert r["skipped_devices"] == ["edge-1"]
    assert r["configured_devices"] == []
    mgr.gsdk.put_devices_upgrade_schedule.assert_not_called()


def test_schedule_upgrade_skips_device_with_no_connectivity() -> None:
    """A device with ttConnCount 0 (portal Connectivity Status Down) has nothing to deliver an
    upgrade over, so it's skipped (not_connected_devices) rather than attempted and left to fail
    at the API."""
    mgr = _make_manager()
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [_edge(hostname="edge-1", device_id=100, tt_conn_count=0)]

    r = mgr.schedule_upgrade(None, {"device": "edge-1", "release": "Latest"})

    assert r["changed"] is False
    assert r["not_connected_devices"] == ["edge-1"]
    assert r["skipped_devices"] == []
    mgr.gsdk.put_devices_upgrade_schedule.assert_not_called()


def test_schedule_upgrade_impaired_connectivity_is_sufficient() -> None:
    """ttConnCount==1 (Impaired) is enough to schedule — only a fully Down device (0) is skipped."""
    mgr = _make_manager()
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [_edge(hostname="edge-1", device_id=100, tt_conn_count=1)]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True

    r = mgr.schedule_upgrade(None, {"device": "edge-1", "release": "Latest"})

    assert r["changed"] is True
    assert r["configured_devices"] == ["edge-1"]
    assert r["not_connected_devices"] == []


def test_schedule_upgrade_mixed_connectivity_skips_one_schedules_the_other() -> None:
    mgr = _make_manager()
    mgr.config_utils.render_config_file = MagicMock(
        return_value={
            "device_lifecycle": [
                {"edge-1": {"release": "Latest"}},
                {"edge-2": {"release": "Latest"}},
            ],
        }
    )
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [
        _edge(hostname="edge-1", device_id=100, tt_conn_count=0),
        _edge(hostname="edge-2", device_id=200, tt_conn_count=2),
    ]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True

    r = mgr.schedule_upgrade("cfg.yaml", {"device": None})

    assert r["changed"] is True
    assert r["not_connected_devices"] == ["edge-1"]
    assert r["configured_devices"] == ["edge-2"]


def test_schedule_upgrade_skips_device_with_schedule_in_progress() -> None:
    """
    A device whose existing schedule hasn't reached Success/Failed yet is skipped
    (schedule_in_progress_devices) rather than attempted — submitting a new one now can race the
    upgrade backend's own dedup guard (which doesn't block on every non-terminal state — see
    _schedule_in_progress_state), confirmed live to cause a schedule to fail with
    FailureReason "Internal error".
    """
    mgr = _make_manager()
    upgrade_summary = MagicMock()
    upgrade_summary.schedule = _schedule("Downloading")
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [
        _edge(hostname="edge-1", device_id=100, upgrade_summary=upgrade_summary)
    ]

    r = mgr.schedule_upgrade(None, {"device": "edge-1", "release": "Latest"})

    assert r["changed"] is False
    assert r["schedule_in_progress_devices"] == ["edge-1"]
    assert r["configured_devices"] == []
    assert r["skipped_devices"] == []
    mgr.gsdk.put_devices_upgrade_schedule.assert_not_called()


def test_schedule_upgrade_not_connected_wins_over_schedule_in_progress() -> None:
    """
    A device that is both unreachable (ttConnCount 0) and has a schedule already in progress must
    land in not_connected_devices, not schedule_in_progress_devices — the connectivity check runs
    first (see schedule_upgrade's device loop), since there's no portal connection to deliver
    anything over regardless of what its existing schedule is doing.
    """
    mgr = _make_manager()
    upgrade_summary = MagicMock()
    upgrade_summary.schedule = _schedule("Downloading")
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [
        _edge(hostname="edge-1", device_id=100, upgrade_summary=upgrade_summary, tt_conn_count=0)
    ]

    r = mgr.schedule_upgrade(None, {"device": "edge-1", "release": "Latest"})

    assert r["not_connected_devices"] == ["edge-1"]
    assert r["schedule_in_progress_devices"] == []
    mgr.gsdk.put_devices_upgrade_schedule.assert_not_called()


def test_schedule_upgrade_schedule_in_progress_wins_over_already_on_release() -> None:
    """
    A device that is both busy (schedule in progress) and already resolved to be running the
    requested release's current build must land in schedule_in_progress_devices, not
    skipped_devices — the busy check runs before the already-on-release check (see
    schedule_upgrade's device loop), so the (possibly stale, since its own schedule is still
    executing) already-on-release reading doesn't mask the real reason it wasn't touched.
    """
    mgr = _make_manager()
    upgrade_summary = MagicMock()
    upgrade_summary.schedule = _schedule("Downloading")
    edge = _edge(hostname="edge-1", device_id=100, upgrade_summary=upgrade_summary)
    edge.sw_version = "2512.202608290526"
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [edge]
    mgr.gsdk.get_software_releases_summary.return_value = [_release_summary("2512.202608290526", "Stable", "25.12.8")]

    r = mgr.schedule_upgrade(None, {"device": "edge-1", "release": "Stable"})

    assert r["schedule_in_progress_devices"] == ["edge-1"]
    assert r["skipped_devices"] == []
    mgr.gsdk.put_devices_upgrade_schedule.assert_not_called()


def test_schedule_upgrade_treats_idle_schedule_as_in_progress() -> None:
    """
    Idle is deliberately treated as busy here even though the upgrade backend's own dedup guard
    does not block on it (see _schedule_in_progress_state) — a device can sit in Idle briefly
    right after being scheduled, before the backend scheduler has picked it up, and submitting a
    second request in that window is exactly the race this guard exists to rule out.
    """
    mgr = _make_manager()
    upgrade_summary = MagicMock()
    upgrade_summary.schedule = _schedule("Idle")
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [
        _edge(hostname="edge-1", device_id=100, upgrade_summary=upgrade_summary)
    ]

    r = mgr.schedule_upgrade(None, {"device": "edge-1", "release": "Latest"})

    assert r["schedule_in_progress_devices"] == ["edge-1"]
    mgr.gsdk.put_devices_upgrade_schedule.assert_not_called()


@pytest.mark.parametrize("state", ["Success", "Failed"])
def test_schedule_upgrade_proceeds_when_prior_schedule_is_terminal(state) -> None:
    mgr = _make_manager()
    upgrade_summary = MagicMock()
    upgrade_summary.schedule = _schedule(state)
    edge = _edge(hostname="edge-1", device_id=100, upgrade_summary=upgrade_summary)
    edge.sw_version = "2512.202608290526"
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [edge]
    mgr.gsdk.get_software_releases_summary.return_value = []
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True

    r = mgr.schedule_upgrade(None, {"device": "edge-1", "release": "Latest"})

    assert r["schedule_in_progress_devices"] == []
    assert r["configured_devices"] == ["edge-1"]
    mgr.gsdk.put_devices_upgrade_schedule.assert_called_once()


def test_schedule_upgrade_proceeds_when_no_prior_schedule() -> None:
    """No schedule object at all (device never had one) is unambiguously safe to proceed."""
    mgr = _make_manager()
    upgrade_summary = MagicMock()
    upgrade_summary.schedule = None
    edge = _edge(hostname="edge-1", device_id=100, upgrade_summary=upgrade_summary)
    edge.sw_version = "2512.202608290526"
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [edge]
    mgr.gsdk.get_software_releases_summary.return_value = []
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True

    r = mgr.schedule_upgrade(None, {"device": "edge-1", "release": "Latest"})

    assert r["schedule_in_progress_devices"] == []
    assert r["configured_devices"] == ["edge-1"]


def test_schedule_upgrade_proceeds_when_release_channel_unresolvable() -> None:
    """
    When the requested release channel can't be resolved to a build (e.g. not in the catalog, or
    the catalog fetch failed) the module must not guess it's already current — it proceeds with
    scheduling rather than silently skipping something it can't actually verify.
    """
    mgr = _make_manager()
    edge = _edge(hostname="edge-1", device_id=100)
    edge.sw_version = "2512.202608290526"
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [edge]
    mgr.gsdk.get_software_releases_summary.return_value = []  # "Stable" not found anywhere
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True

    r = mgr.schedule_upgrade(None, {"device": "edge-1", "release": "Stable"})

    assert r["changed"] is True
    assert r["configured_devices"] == ["edge-1"]
    assert r["skipped_devices"] == []
    mgr.gsdk.put_devices_upgrade_schedule.assert_called_once()


def test_schedule_upgrade_mixed_batch_skips_one_schedules_the_other() -> None:
    mgr = _make_manager()
    edge_already_current = _edge(hostname="edge-1", device_id=100)
    edge_already_current.sw_version = "2512.202608290526"
    edge_needs_upgrade = _edge(hostname="edge-2", device_id=200)
    edge_needs_upgrade.sw_version = "2606.202608261524"
    mgr.config_utils.render_config_file = MagicMock(
        return_value={
            "device_lifecycle": [
                {"edge-1": {"release": "Stable"}},
                {"edge-2": {"release": "Stable"}},
            ]
        }
    )
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [edge_already_current, edge_needs_upgrade]
    mgr.gsdk.get_software_releases_summary.return_value = [_release_summary("2512.202608290526", "Stable", "25.12.8")]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True

    r = mgr.schedule_upgrade("cfg.yaml", {"device": None})

    assert r["skipped_devices"] == ["edge-1"]
    assert r["configured_devices"] == ["edge-2"]
    call_kwargs = mgr.gsdk.put_devices_upgrade_schedule.call_args.kwargs
    assert call_kwargs["device_versions"] == [{"deviceId": 200, "version": {"release": "Stable"}}]


# ---------------------------------------------------------------------------
# rollback
# ---------------------------------------------------------------------------


def test_rollback_uses_last_running_version() -> None:
    mgr = _make_manager()
    upgrade_summary = MagicMock()
    upgrade_summary.last_running_version = _sw_version("Stable", "2512.1", "25.12.8")
    upgrade_summary.running_version = _sw_version("Latest", "2609.1", "26.9.1")
    upgrade_summary.schedule = None
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [
        _edge(hostname="edge-1", device_id=100, upgrade_summary=upgrade_summary)
    ]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True

    r = mgr.rollback(None, {"device": "edge-1", "release": None})

    assert r["changed"] is True
    assert r["configured_devices"] == ["edge-1"]
    call_kwargs = mgr.gsdk.put_devices_upgrade_schedule.call_args.kwargs
    assert call_kwargs["action"] == "Activate"
    assert call_kwargs["device_versions"] == [
        {"deviceId": 100, "version": {"release": "Stable", "version": "2512.1", "name": "25.12.8"}}
    ]


def test_rollback_reports_changed_again_after_last_running_version_flips() -> None:
    """
    rollback has no "already on this version" skip — lastRunningVersion always differs from
    what's currently running, so a repeat rollback right after a previous one (confirmed live:
    lastRunningVersion flips to point at whichever build the device just rolled back from) must
    still report changed=True and schedule a new PUT, not be silently treated as a no-op.
    """
    mgr = _make_manager()
    # Simulates the device's state immediately after a real rollback completed: currently running
    # the old build, lastRunningVersion now flipped to point at the build it just came from.
    upgrade_summary = MagicMock()
    upgrade_summary.last_running_version = _sw_version("Latest", "2610.1", "26.10.1")
    upgrade_summary.running_version = _sw_version("Stable", "2512.1", "25.12.8")
    upgrade_summary.schedule = None
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [
        _edge(hostname="edge-1", device_id=100, upgrade_summary=upgrade_summary)
    ]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True

    r = mgr.rollback(None, {"device": "edge-1", "release": None})

    assert r["changed"] is True
    assert r["configured_devices"] == ["edge-1"]
    assert r["skipped_devices"] == []
    call_kwargs = mgr.gsdk.put_devices_upgrade_schedule.call_args.kwargs
    assert call_kwargs["device_versions"] == [
        {"deviceId": 100, "version": {"release": "Latest", "version": "2610.1", "name": "26.10.1"}}
    ]


def test_rollback_ts_default_when_omitted_ignores_yaml_top_level() -> None:
    """
    ts applies to the whole batch (one PUT, one time) and so is module-parameter only: a
    top-level 'ts' key in config_file is never read, even when present.
    """
    mgr = _make_manager()
    upgrade_summary = MagicMock()
    upgrade_summary.last_running_version = _sw_version("Stable", "2512.1", "25.12.8")
    upgrade_summary.schedule = None
    mgr.config_utils.render_config_file = MagicMock(
        return_value={"ts": {"seconds": 5, "nanos": 6}, "device_lifecycle": [{"edge-1": {}}]}
    )
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [
        _edge(hostname="edge-1", device_id=100, upgrade_summary=upgrade_summary)
    ]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True

    mgr.rollback("cfg.yaml", {"device": None})

    call_kwargs = mgr.gsdk.put_devices_upgrade_schedule.call_args.kwargs
    assert call_kwargs["ts"] is None


def test_rollback_without_last_running_version_is_skipped_not_raised() -> None:
    """
    A device with no lastRunningVersion has nothing to roll back to — that's a no-op skip (like
    change_state's idempotent skips), not an error. There is no override: rollback always targets
    the device's own lastRunningVersion.
    """
    mgr = _make_manager()
    upgrade_summary = MagicMock()
    upgrade_summary.last_running_version = None
    upgrade_summary.schedule = None
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [
        _edge(hostname="edge-1", device_id=100, upgrade_summary=upgrade_summary)
    ]

    r = mgr.rollback(None, {"device": "edge-1", "release": None})

    assert r["changed"] is False
    assert r["skipped_devices"] == ["edge-1"]
    assert r["configured_devices"] == []
    mgr.gsdk.put_devices_upgrade_schedule.assert_not_called()


def test_rollback_mixed_batch_skips_one_rolls_back_the_other() -> None:
    """
    In a multi-device rollback, a device with no lastRunningVersion must be skipped without
    blocking the rest of the batch — the other device still gets rolled back normally.
    """
    mgr = _make_manager()
    mgr.config_utils.render_config_file = MagicMock(
        return_value={
            "device_lifecycle": [
                {"edge-1": {}},
                {"edge-2": {}},
            ]
        }
    )
    no_history = MagicMock()
    no_history.last_running_version = None
    no_history.schedule = None
    has_history = MagicMock()
    has_history.last_running_version = _sw_version("Stable", "2512.1", "25.12.8")
    has_history.running_version = _sw_version("Latest", "2609.1", "26.9.1")
    has_history.schedule = None
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [
        _edge(hostname="edge-1", device_id=100, upgrade_summary=no_history),
        _edge(hostname="edge-2", device_id=200, upgrade_summary=has_history),
    ]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True

    r = mgr.rollback("cfg.yaml", {"device": None})

    assert r["changed"] is True
    assert r["configured_devices"] == ["edge-2"]
    assert r["skipped_devices"] == ["edge-1"]
    call_kwargs = mgr.gsdk.put_devices_upgrade_schedule.call_args.kwargs
    assert call_kwargs["device_versions"] == [
        {"deviceId": 200, "version": {"release": "Stable", "version": "2512.1", "name": "25.12.8"}}
    ]


def test_rollback_logs_table_before_mutation(caplog) -> None:
    import logging as _logging

    mgr = _make_manager()
    upgrade_summary = MagicMock()
    upgrade_summary.last_running_version = _sw_version("Stable", "2512.1", "25.12.8")
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [
        _edge(hostname="edge-1", device_id=100, upgrade_summary=upgrade_summary)
    ]
    mgr.gsdk.get_software_releases_summary.return_value = [_release_summary("2512.1", "Stable", "25.12.8")]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True

    with caplog.at_level(_logging.INFO, logger="Graphiant_playbook"):
        mgr.rollback(None, {"device": "edge-1", "release": None})

    table_message = next(r.message for r in caplog.records if "Current state before rollback" in r.message)
    assert "edge-1" in table_message
    assert any("Release catalog" in r.message for r in caplog.records)


def test_rollback_unknown_device_raises_not_found() -> None:
    mgr = _make_manager()
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = []
    with pytest.raises(DeviceNotFoundError):
        mgr.rollback(None, {"device": "ghost", "release": None})


def test_rollback_multiple_missing_devices_reported_together() -> None:
    """Several bad device names in one config file must all surface in a single failure (see
    test_change_state_multiple_missing_devices_reported_together)."""
    mgr = _make_manager()
    mgr.config_utils.render_config_file = MagicMock(
        return_value={
            "device_lifecycle": [
                {"edge-1": {}},
                {"ghost-1": {}},
                {"ghost-2": {}},
            ],
        }
    )
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [_edge(hostname="edge-1", device_id=100)]

    with pytest.raises(DeviceNotFoundError, match="ghost-1") as exc_info:
        mgr.rollback("cfg.yaml", {"device": None})
    assert "ghost-2" in str(exc_info.value)
    assert "edge-1" not in str(exc_info.value)
    mgr.gsdk.put_devices_upgrade_schedule.assert_not_called()


def test_rollback_polls_and_reports_failed_device(caplog) -> None:
    import logging as _logging

    mgr = _make_manager()
    last_running = _sw_version("Stable", "2512.1", "25.12.8")
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [
        _edge(
            hostname="edge-1",
            device_id=100,
            upgrade_summary=MagicMock(last_running_version=last_running, schedule=None),
        )
    ]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True
    mgr.gsdk.poll_upgrade_schedule_completion_batch.side_effect = None
    mgr.gsdk.poll_upgrade_schedule_completion_batch.return_value = {100: ("Failed", "Internal error")}

    with caplog.at_level(_logging.WARNING, logger="Graphiant_playbook"):
        r = mgr.rollback(None, {"device": "edge-1", "release": None})

    assert r["changed"] is True
    assert r["failed_devices"] == ["edge-1"]
    messages = [rec.message for rec in caplog.records]
    assert any("edge-1" in m and "Internal error" in m for m in messages)


def test_rollback_polls_for_ready_after_success_and_reports_not_insync_on_timeout() -> None:
    """Same post-Success Ready poll as schedule_upgrade (see that test) — rollback's schedule
    reaching Success doesn't mean portalStatus is Ready yet either."""
    mgr = _make_manager()
    last_running = _sw_version("Stable", "2512.1", "25.12.8")
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [
        _edge(
            hostname="edge-1",
            device_id=100,
            upgrade_summary=MagicMock(last_running_version=last_running, schedule=None),
        )
    ]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True
    mgr.gsdk.poll_upgrade_schedule_completion_batch.side_effect = None
    mgr.gsdk.poll_upgrade_schedule_completion_batch.return_value = {100: ("Success", None)}
    mgr.gsdk.verify_device_portal_status.side_effect = Exception("timed out")

    r = mgr.rollback(None, {"device": "edge-1", "release": None})

    assert r["completed_devices"] == ["edge-1"]
    assert r["not_insync_devices"] == ["edge-1"]
    assert r["insync_devices"] == []


def test_rollback_ready_poll_skipped_when_verify_for_insync_false() -> None:
    mgr = _make_manager()
    last_running = _sw_version("Stable", "2512.1", "25.12.8")
    mgr.config_utils.render_config_file = MagicMock(
        return_value={
            "device_lifecycle": [{"edge-1": {"verify_for_insync": False}}],
        }
    )
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [
        _edge(
            hostname="edge-1",
            device_id=100,
            upgrade_summary=MagicMock(last_running_version=last_running, schedule=None),
        )
    ]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True
    mgr.gsdk.poll_upgrade_schedule_completion_batch.side_effect = None
    mgr.gsdk.poll_upgrade_schedule_completion_batch.return_value = {100: ("Success", None)}

    r = mgr.rollback("cfg.yaml", {"device": None})

    assert r["completed_devices"] == ["edge-1"]
    assert r["insync_devices"] == []
    assert r["not_insync_devices"] == []
    mgr.gsdk.verify_device_portal_status.assert_not_called()


def test_rollback_wait_for_completion_false_skips_poll() -> None:
    mgr = _make_manager()
    last_running = _sw_version("Stable", "2512.1", "25.12.8")
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [
        _edge(
            hostname="edge-1",
            device_id=100,
            upgrade_summary=MagicMock(last_running_version=last_running, schedule=None),
        )
    ]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True

    r = mgr.rollback(
        None,
        {"device": "edge-1", "release": None},
        wait_for_completion=False,
    )

    assert r["changed"] is True
    assert r["completed_devices"] == []
    mgr.gsdk.poll_upgrade_schedule_completion_batch.assert_not_called()


def test_rollback_per_device_wait_for_completion_override() -> None:
    """Same per-device wait_for_completion override as schedule_upgrade (see that test)."""
    mgr = _make_manager()
    last_running = _sw_version("Stable", "2512.1", "25.12.8")
    upgrade_summary_1 = MagicMock(last_running_version=last_running, schedule=None)
    upgrade_summary_2 = MagicMock(last_running_version=last_running, schedule=None)
    mgr.config_utils.render_config_file = MagicMock(
        return_value={
            "device_lifecycle": [
                {"edge-1": {"wait_for_completion": False}},
                {"edge-2": {}},
            ],
        }
    )
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [
        _edge(hostname="edge-1", device_id=100, upgrade_summary=upgrade_summary_1),
        _edge(hostname="edge-2", device_id=200, upgrade_summary=upgrade_summary_2),
    ]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True

    r = mgr.rollback("cfg.yaml", {"device": None})

    assert r["changed"] is True
    assert sorted(r["configured_devices"]) == ["edge-1", "edge-2"]
    assert r["completed_devices"] == ["edge-2"]
    mgr.gsdk.poll_upgrade_schedule_completion_batch.assert_called_once_with([200])


def test_rollback_check_mode_skips_poll() -> None:
    mgr = _make_manager()
    mgr.gsdk.check_mode = True
    last_running = _sw_version("Stable", "2512.1", "25.12.8")
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [
        _edge(
            hostname="edge-1",
            device_id=100,
            upgrade_summary=MagicMock(last_running_version=last_running, schedule=None),
        )
    ]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True

    r = mgr.rollback(None, {"device": "edge-1", "release": None})

    assert r["changed"] is True
    mgr.gsdk.poll_upgrade_schedule_completion_batch.assert_not_called()


def test_rollback_skips_device_with_schedule_in_progress() -> None:
    """
    Same guard as schedule_upgrade (see test_schedule_upgrade_skips_device_with_schedule_in_
    progress) — a device whose existing schedule hasn't reached Success/Failed yet is skipped
    (schedule_in_progress_devices), not resubmitted, to avoid racing a still-in-flight prior
    rollback/upgrade for the same device. Confirmed live: two Activate-only rollback requests for
    the same device within seconds of each other caused one to fail with FailureReason "Internal
    error" ("expected image ... not installed during activation").
    """
    mgr = _make_manager()
    upgrade_summary = MagicMock()
    upgrade_summary.last_running_version = _sw_version("Stable", "2512.1", "25.12.8")
    upgrade_summary.schedule = _schedule("Activating")
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [
        _edge(hostname="edge-1", device_id=100, upgrade_summary=upgrade_summary)
    ]

    r = mgr.rollback(None, {"device": "edge-1", "release": None})

    assert r["changed"] is False
    assert r["schedule_in_progress_devices"] == ["edge-1"]
    assert r["configured_devices"] == []
    assert r["skipped_devices"] == []
    mgr.gsdk.put_devices_upgrade_schedule.assert_not_called()


def test_rollback_treats_idle_schedule_as_in_progress() -> None:
    """Idle is deliberately treated as busy here too (see the schedule_upgrade equivalent test)."""
    mgr = _make_manager()
    upgrade_summary = MagicMock()
    upgrade_summary.last_running_version = _sw_version("Stable", "2512.1", "25.12.8")
    upgrade_summary.schedule = _schedule("Idle")
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [
        _edge(hostname="edge-1", device_id=100, upgrade_summary=upgrade_summary)
    ]

    r = mgr.rollback(None, {"device": "edge-1", "release": None})

    assert r["schedule_in_progress_devices"] == ["edge-1"]
    mgr.gsdk.put_devices_upgrade_schedule.assert_not_called()


@pytest.mark.parametrize("state", ["Success", "Failed"])
def test_rollback_proceeds_when_prior_schedule_is_terminal(state) -> None:
    mgr = _make_manager()
    upgrade_summary = MagicMock()
    upgrade_summary.last_running_version = _sw_version("Stable", "2512.1", "25.12.8")
    upgrade_summary.schedule = _schedule(state)
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [
        _edge(hostname="edge-1", device_id=100, upgrade_summary=upgrade_summary)
    ]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True

    r = mgr.rollback(None, {"device": "edge-1", "release": None})

    assert r["schedule_in_progress_devices"] == []
    assert r["configured_devices"] == ["edge-1"]
    mgr.gsdk.put_devices_upgrade_schedule.assert_called_once()


def test_rollback_mixed_batch_busy_device_skipped_other_rolls_back() -> None:
    """A busy device must not block the rest of the batch, same as the no-lastRunningVersion skip
    (test_rollback_mixed_batch_skips_one_rolls_back_the_other)."""
    mgr = _make_manager()
    mgr.config_utils.render_config_file = MagicMock(
        return_value={
            "device_lifecycle": [
                {"edge-1": {}},
                {"edge-2": {}},
            ]
        }
    )
    busy = MagicMock()
    busy.last_running_version = _sw_version("Stable", "2512.1", "25.12.8")
    busy.schedule = _schedule("Downloading")
    free = MagicMock()
    free.last_running_version = _sw_version("Stable", "2512.1", "25.12.8")
    free.running_version = _sw_version("Latest", "2609.1", "26.9.1")
    free.schedule = None
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [
        _edge(hostname="edge-1", device_id=100, upgrade_summary=busy),
        _edge(hostname="edge-2", device_id=200, upgrade_summary=free),
    ]
    mgr.gsdk.put_devices_upgrade_schedule.return_value = True

    r = mgr.rollback("cfg.yaml", {"device": None})

    assert r["schedule_in_progress_devices"] == ["edge-1"]
    assert r["configured_devices"] == ["edge-2"]


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------


def test_get_status_logs_enterprise_info_and_tabulated_edges() -> None:
    # Ensures the enterprise/edges logging (added to help diagnose "0 edges returned" cases)
    # runs without error against a real-shaped list of edges, tabulate included.
    mgr = _make_manager()
    mgr.gsdk.enterprise_info = {"company_name": "Acme", "enterprise_id": 10000000335}
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [
        _edge(hostname="edge-1", device_id=100, status="active"),
        _edge(hostname="edge-2", device_id=101, status="active"),
    ]
    r = mgr.get_status(None, {"device": None})
    assert set(r["devices"]) == {"edge-1", "edge-2"}


def test_get_status_tabulate_does_not_truncate_version_like_strings(caplog) -> None:
    # tabulate auto-parses dotted numeric-looking strings as floats by default, which silently
    # truncated a real sw_version like "2604.202604110216" down to "2604.2" in the logged table.
    import logging as _logging

    mgr = _make_manager()
    edge = _edge(hostname="edge-1", device_id=100, status="active")
    edge.sw_version = "2604.202604110216"
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [edge]

    with caplog.at_level(_logging.INFO, logger="Graphiant_playbook"):
        mgr.get_status(None, {"device": None})

    combined = "\n".join(r.message for r in caplog.records)
    assert "2604.202604110216" in combined
    assert "2604.2" not in combined.replace("2604.202604110216", "")


def _release_summary(version, release, name):
    key = MagicMock()
    key.version = version
    summary = MagicMock()
    summary.key = key
    summary.release = release
    summary.name = name
    return summary


def test_get_status_table_release_from_catalog_and_release_name_from_sw_name(caplog) -> None:
    # Release Name is the edge's own swName (reliably populated); Release is resolved from the
    # GET /v1/software/releases/summary catalog by matching swVersion — more reliable than the
    # edge's own upgradeSummary.runningVersion.release for currently-named releases.
    import logging as _logging

    mgr = _make_manager()
    edge = _edge(hostname="edge-1", device_id=100, status="active")
    edge.sw_version = "2606.202608261524"
    edge.sw_name = "26.6.3"
    edge.upgrade_summary = MagicMock()
    edge.upgrade_summary.running_version = _sw_version("Custom", "2606.202608261524", None)
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [edge]
    mgr.gsdk.get_software_releases_summary.return_value = [
        _release_summary("2606.202608261524", "Recommended", "26.6.3"),
    ]

    with caplog.at_level(_logging.INFO, logger="Graphiant_playbook"):
        mgr.get_status(None, {"device": None})

    table_message = next(r.message for r in caplog.records if "Reported devices" in r.message)
    assert "Release" in table_message and "Release Name" in table_message and "Software Version" in table_message
    assert "Portal Sync" in table_message
    # From the catalog (Recommended), not the edge's own runningVersion.release (Custom).
    assert "Recommended" in table_message
    assert "26.6.3" in table_message
    assert "2606.202608261524" in table_message


def test_get_status_table_release_name_falls_back_to_catalog_when_sw_name_empty(caplog) -> None:
    # swName (like the top-level Software column before it) is frequently unset by the real API
    # even for a currently-named release — fall back to the releases-summary catalog's own name.
    import logging as _logging

    mgr = _make_manager()
    edge = _edge(hostname="edge-1", device_id=100, status="active")
    edge.sw_version = "2606.202608261524"
    edge.sw_name = None
    edge.upgrade_summary = MagicMock()
    edge.upgrade_summary.running_version = _sw_version("Latest", "2606.202608261524", None)
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [edge]
    mgr.gsdk.get_software_releases_summary.return_value = [
        _release_summary("2606.202608261524", "Recommended", "26.6.3"),
    ]

    with caplog.at_level(_logging.INFO, logger="Graphiant_playbook"):
        mgr.get_status(None, {"device": None})

    table_message = next(r.message for r in caplog.records if "Reported devices" in r.message)
    assert "26.6.3" in table_message


def test_get_status_table_release_falls_back_to_running_version_when_not_in_catalog(caplog) -> None:
    # A build no longer tracked in the releases-summary catalog (e.g. superseded) falls back to
    # the edge's own upgradeSummary.runningVersion.release instead of showing a blank Release.
    import logging as _logging

    mgr = _make_manager()
    edge = _edge(hostname="edge-1", device_id=100, status="active")
    edge.sw_version = "2602.202602022035"
    edge.upgrade_summary = MagicMock()
    edge.upgrade_summary.running_version = _sw_version("Custom", "2602.202602022035", None)
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [edge]
    mgr.gsdk.get_software_releases_summary.return_value = [
        _release_summary("2606.202608261524", "Recommended", "26.6.3"),
    ]

    with caplog.at_level(_logging.INFO, logger="Graphiant_playbook"):
        mgr.get_status(None, {"device": None})

    table_message = next(r.message for r in caplog.records if "Reported devices" in r.message)
    assert "Custom" in table_message


def test_get_status_table_release_resolution_survives_catalog_fetch_failure(caplog) -> None:
    # The releases-summary fetch is enrichment only; a failure there must not break get_status.
    import logging as _logging

    mgr = _make_manager()
    edge = _edge(hostname="edge-1", device_id=100, status="active")
    edge.sw_version = "2602.202602022035"
    edge.upgrade_summary = MagicMock()
    edge.upgrade_summary.running_version = _sw_version("Custom", "2602.202602022035", None)
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [edge]
    mgr.gsdk.get_software_releases_summary.side_effect = Exception("boom")

    with caplog.at_level(_logging.INFO, logger="Graphiant_playbook"):
        r = mgr.get_status(None, {"device": None})

    assert "edge-1" in r["devices"]
    table_message = next(r.message for r in caplog.records if "Reported devices" in r.message)
    assert "Custom" in table_message


def test_get_status_single_device() -> None:
    mgr = _make_manager()
    upgrade_summary = MagicMock()
    upgrade_summary.status = "UpToDate"
    upgrade_summary.running_version = _sw_version("Stable", "2512.1", "25.12.8")
    upgrade_summary.last_running_version = None
    upgrade_summary.ready_for_activation_version = None
    upgrade_summary.schedule = None
    edge = _edge(hostname="edge-1", device_id=100, status="active", upgrade_summary=upgrade_summary)
    edge.portal_status = "Ready"
    edge.sw_version = "2512.1"
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [edge]

    r = mgr.get_status(None, {"device": "edge-1"})

    assert r["changed"] is False
    assert r["failed_devices"] == []
    dev = r["devices"]["edge-1"]
    assert dev["status"] == "active"
    assert dev["portal_status"] == "Ready"
    assert dev["upgrade_status"] == "UpToDate"
    assert dev["running_version"] == {"release": "Stable", "version": "2512.1", "name": "25.12.8"}


def test_get_status_device_not_found_recorded_in_failed_devices() -> None:
    mgr = _make_manager()
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = []
    r = mgr.get_status(None, {"device": "ghost"})
    assert r["devices"] == {}
    assert r["failed_devices"] == [{"device_name": "ghost", "error": "Device 'ghost' not found in edges summary"}]


def test_get_status_all_devices_by_role() -> None:
    mgr = _make_manager()
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [
        _edge(hostname="edge-1", device_id=100),
        _edge(hostname="edge-2", device_id=101),
    ]
    r = mgr.get_status(None, {"device": None}, role="cpe")
    mgr.gsdk.get_edges_summary_with_upgrade.assert_called_once_with(role="cpe")
    assert set(r["devices"]) == {"edge-1", "edge-2"}


def test_get_status_table_only_includes_requested_devices(caplog) -> None:
    # A specific device (or config_file device_lifecycle list) narrows what get_status reports;
    # the logged table must match that, not every edge the underlying GET happened to return.
    import logging as _logging

    mgr = _make_manager()
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [
        _edge(hostname="edge-1", device_id=100, status="active"),
        _edge(hostname="edge-2", device_id=101, status="active"),
    ]

    with caplog.at_level(_logging.INFO, logger="Graphiant_playbook"):
        mgr.get_status(None, {"device": "edge-1"})

    # The "fetched N edge(s) ... hostnames=[...]" diagnostic line legitimately lists every edge
    # the GET returned (useful for diagnosing enterprise/credential mismatches) — only the
    # rendered table itself should be scoped to the requested device(s).
    table_message = next(r.message for r in caplog.records if "Reported devices" in r.message)
    assert "edge-1" in table_message
    assert "edge-2" not in table_message


def test_get_status_no_role_lists_every_device_no_filter() -> None:
    # role is not a real device value and the API has no server-side role filter (the portal's
    # own "filter[role]=UnknownDeviceRole" is inert there too) — with no role given anywhere,
    # get_status must pass role=None through (list everything), not filter on a literal
    # "UnknownDeviceRole" string that no device actually has.
    mgr = _make_manager()
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [
        _edge(hostname="edge-1", device_id=100),
        _edge(hostname="edge-2", device_id=101),
    ]
    r = mgr.get_status(None, {"device": None})
    mgr.gsdk.get_edges_summary_with_upgrade.assert_called_once_with(role=None)
    assert set(r["devices"]) == {"edge-1", "edge-2"}


def test_get_status_role_from_yaml_when_no_device() -> None:
    mgr = _make_manager()
    mgr.config_utils.render_config_file = MagicMock(return_value={"role": "cpe"})
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = [_edge(hostname="edge-1", device_id=100)]

    r = mgr.get_status("cfg.yaml", {"device": None})

    mgr.gsdk.get_edges_summary_with_upgrade.assert_called_once_with(role="cpe")
    assert "edge-1" in r["devices"]


def test_get_status_explicit_role_overrides_yaml() -> None:
    mgr = _make_manager()
    mgr.config_utils.render_config_file = MagicMock(return_value={"role": "cpe"})
    mgr.gsdk.get_edges_summary_with_upgrade.return_value = []

    mgr.get_status("cfg.yaml", {"device": None}, role="gateway")

    mgr.gsdk.get_edges_summary_with_upgrade.assert_called_once_with(role="gateway")
