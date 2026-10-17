"""
Device Lifecycle Manager for Graphiant Playbooks.

Manages device lifecycle state (``PUT /v1/devices/bringup``) and software upgrade
scheduling/rollback (``PUT /v1/devices/upgrade/schedule``), plus a read-only
upgrade/lifecycle status query (``GET /v1/edges-summary?upgradeSummary=true``).

YAML uses the same list-of-single-key-dicts pattern as ``device_system`` (see
``device_config_common.load_device_list_yaml_config``).

Idempotency: ``change_state`` compares the device's current ``status`` (mapped to the same
friendly vocabulary as ``lifecycle_state``) against the desired value and only pushes devices
that differ; ``decommissioned`` is only accepted when the device is currently ``deactivated``
(matches the portal UI). ``schedule_upgrade``/``rollback`` are actions, not fully declarative
state, so a device that does need the change always reports ``changed`` — each has one
idempotency-style skip instead: ``schedule_upgrade`` skips a device already resolved (via
``_resolve_schedule_target_version``/``_release_catalog``) to be running the requested
``release`` channel's current build; ``rollback`` skips a device with no
``upgradeSummary.lastRunningVersion`` — its only skip, since ``lastRunningVersion`` always differs
from what's currently running (no "already there" case to detect); a repeat ``rollback`` right
after a previous one simply targets whichever build the device just came from, so it reports
``changed`` again. Both skips land in ``skipped_devices``, never forced or errored. There's no way
to pin ``schedule_upgrade``/``rollback`` to an arbitrary exact build string — ``release``
(``Stable``/``Recommended``/``Latest``/``Custom``) is the only target either accepts, matching the
portal's own "Change Release" dropdown exactly (``Custom`` only actually resolves to anything for
an enterprise that has a custom image enabled; offered here unconditionally and left for the API
to reject otherwise).
``schedule_upgrade`` additionally skips (``not_connected_devices``) a device whose portal
Connectivity Status is Down (``ttConnCount`` below 1/Impaired) rather than attempting a push with
no tunnel-terminator connection to deliver it over. Both ``schedule_upgrade`` and ``rollback``
also skip (``schedule_in_progress_devices``) a device whose existing
``upgradeSummary.schedule.state`` hasn't reached ``Success``/``Failed`` yet, including ``Idle`` —
submitting a new schedule while one is still in progress can race the upgrade backend's own dedup
guard (which doesn't block on every non-terminal state), confirmed live to cause a schedule to
fail with ``FailureReason: "Internal error"`` when it raced a still-in-flight prior
rollback/upgrade for the same device (see ``_schedule_in_progress_state``). A
named device not found in the live edge list fails the task before any mutating call, with every
unresolved device in the batch collected and named together (``missing_devices_message``) rather
than stopping at the first one hit.

Device resolution: every resolution pass in this manager (``change_state``'s pre-op and post-op
fetches, ``schedule_upgrade``/``rollback``'s post-op table) fetches the full enterprise edge list
once per round (``_fetch_edges_by_hostname`` — the API has no server-side filter by device name
or id) and resolves every device in the batch from that one shared result, so a batch of any size
costs one ``GET /v1/edges-summary`` per round, not one per device.

Polling: after a mutating call, ``change_state`` polls ``portalStatus=Ready``
(``verify_for_insync``); ``schedule_upgrade``/``rollback`` first poll
``upgradeSummary.schedule.state`` to a terminal ``Success``/``Failed`` value
(``wait_for_completion``, via ``_poll_schedule_completions``/
``GraphiantPortalClient.poll_upgrade_schedule_completion_batch`` — one shared
``GET /v1/edges-summary`` per round covers every watched device), then also poll
``portalStatus=Ready`` for any device whose schedule reached ``Success`` (a ``Success``
schedule doesn't mean the portal has settled back to ``Ready`` yet). All PUT calls and polls
for a batch run concurrently (``BaseManager.execute_concurrent_tasks``), not one device at a
time. Results land in ``completed_devices``/``failed_devices``/``in_progress_devices`` and
``insync_devices``/``not_insync_devices``; a timeout before Success/Failed is not a failure,
but a ``Failed`` schedule or a Ready-poll timeout is.

``operation``/``upgrade_action``/``ts`` apply to the whole call and are module-parameter only
(no config-file equivalent) — one invocation is exactly one operation, and one
``put_devices_upgrade_schedule`` PUT batches every device under a single ``action``/``ts``.
``verify_for_insync``/``wait_for_completion`` are the opposite: genuinely per-device, settable
as a key alongside ``lifecycle_state``/``release`` in that device's own ``device_lifecycle``
entry, which overrides the module-parameter default (itself ``True`` when unset) for just that
device.

With ``detailed_logs: true`` (and ``tabulate`` installed), every operation logs the current
state of its targeted devices as a table before any mutating call; ``change_state`` also logs
it again afterward (real runs only) to show a before/after snapshot, and logs each device's
actual transition line by line.
"""

from typing import Any, Dict, List, Optional

try:
    from tabulate import tabulate

    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False

from .base_manager import BaseManager
from .device_config_common import (
    coerce_str,
    load_device_list_yaml_config,
    missing_devices_message,
    new_apply_result,
)
from .exceptions import APIError, ConfigurationError, DeviceNotFoundError
from .logger import setup_logger

LOG = setup_logger()

_LOG_PREFIX = "[device-lifecycle]"
_YAML_KEY = "device_lifecycle"

# lifecycle_state (module-facing, matches the portal UI's dropdown wording) -> API `status`.
_FRIENDLY_TO_API = {
    "activated": "Allowed",
    "staging": "Pending",
    "maintenance": "Maintenance",
    "deactivated": "Denied",
    "decommissioned": "Removed",
}

# GET /v1/edges-summary `status` (lowercase, as observed on the portal) -> the same
# friendly vocabulary as `lifecycle_state`, for idempotency comparison. A decommissioned
# device is normally removed from edges-summary entirely (see change_state's handling of
# DeviceNotFoundError below), but "removed" is mapped defensively in case the API ever
# surfaces that status on the device before it disappears from the list.
_API_STATUS_TO_FRIENDLY = {
    "active": "activated",
    "staging": "staging",
    "maintenance": "maintenance",
    "inactive": "deactivated",
    "removed": "decommissioned",
}

# `lifecycle_state` values expected to leave the device connected; only these are
# followed up with a readiness poll after the change.
_READY_AFTER = frozenset({"activated", "staging", "maintenance"})

# Matches the portal's "Change Release" dropdown exactly — Custom only actually appears there
# (and only works via the API) for an enterprise that has a custom image enabled; offered here
# unconditionally and left for the API itself to reject when it isn't.
_RELEASES = frozenset({"Stable", "Recommended", "Latest", "Custom"})


class DeviceLifecycleManager(BaseManager):
    """Manage device lifecycle state and software upgrade scheduling/rollback."""

    def __init__(self, config_utils):
        super().__init__(config_utils)
        # Per-instance cache so a single operation call (which reads config_yaml_file once for
        # the device_lifecycle list and again for top-level settings) only parses/templates the
        # file once. Managers are constructed once per module invocation (see graphiant_config.py),
        # so instance lifetime matches a single operation call.
        self._config_file_cache: Dict[str, Any] = {}

    def _render_config_file_cached(self, path: str) -> Any:
        if path not in self._config_file_cache:
            self._config_file_cache[path] = self.render_config_file(path)
        return self._config_file_cache[path]

    def _release_catalog(self) -> Dict[str, Dict[str, Optional[str]]]:
        """
        Build a ``{swVersion: {"release": ..., "name": ...}}`` lookup from
        ``GET /v1/software/releases/summary``, for resolving the pre-op/status table's Release
        and Release Name columns. Display enrichment only — never let a failure here break the
        caller's actual operation.
        """
        try:
            summaries = self.gsdk.get_software_releases_summary()
        except Exception as e:  # noqa: BLE001 - enrichment only, must never fail the run
            LOG.warning("%s Failed to fetch software releases summary for Release column: %s", _LOG_PREFIX, e)
            return {}
        catalog: Dict[str, Dict[str, Optional[str]]] = {}
        for summary in summaries or []:
            key = getattr(summary, "key", None)
            version = getattr(key, "version", None) if key else None
            if version:
                catalog[version] = {
                    "release": getattr(summary, "release", None),
                    "name": getattr(summary, "name", None),
                }
        return catalog

    @staticmethod
    def _resolve_schedule_target_version(
        cfg: Dict[str, Any], release_catalog: Dict[str, Dict[str, Optional[str]]]
    ) -> Optional[str]:
        """
        Resolve the exact target ``swVersion`` for a ``schedule_upgrade`` entry's release
        *channel*, for idempotency comparison against the device's current ``swVersion`` —
        reverse-looked-up in ``release_catalog`` (keyed by version, not channel name) to
        whatever build that channel currently points to. Returns ``None`` when unresolvable
        (channel not in the catalog, or the catalog fetch failed) — callers must treat that as
        "can't tell, don't skip", not assume a match, since a channel can point to a different
        build over time.
        """
        release = cfg.get("release")
        if not release:
            return None
        for version, entry in release_catalog.items():
            if entry.get("release") == release:
                return version
        return None

    def _schedule_in_progress_state(self, edge: Any) -> Optional[str]:
        """
        Return the device's current ``upgradeSummary.schedule.state`` if it represents a prior
        schedule that hasn't reached a terminal value yet (``None`` if there's no schedule at all,
        or it's already ``Success``/``Failed`` — either way, safe to submit a new one).

        Submitting a new ``schedule_upgrade``/``rollback`` while a device's previous one is still
        in progress can race the backend's own dedup guard (upgrade service's
        ``ScheduleUpgrade()`` only blocks on a narrower set of states — notably excluding
        ``Idle``/``InMaintenance`` — so two requests close together for the same device can both
        land); confirmed live to actually cause one request's ``Activate`` to fail with
        ``FailureReason: "Internal error"`` ("expected image ... not installed during
        activation") when it raced a still-in-flight prior rollback for the same device/version.
        Deliberately stricter than the backend's own guard — treats any non-terminal state,
        including ``Idle``, as still busy, to fully rule out that race rather than narrow this to
        exactly the backend's own (narrower, and here untrusted) definition of "in progress".
        """
        upgrade_summary = getattr(edge, "upgrade_summary", None)
        schedule = getattr(upgrade_summary, "schedule", None) if upgrade_summary else None
        if schedule is None:
            return None
        state = getattr(schedule, "state", None)
        if state is None or state in self.gsdk.UPGRADE_SCHEDULE_TERMINAL_STATES:
            return None
        return state

    def _read_top_level_yaml(self, config_yaml_file: Optional[str]) -> Dict[str, Any]:
        """
        Return the top-level keys of ``config_yaml_file`` (currently only ``role``, read by
        ``get_status``), or ``{}`` when no file is given. ``operation``/``upgrade_action``/``ts``
        are whole-run, single-API-call settings and are module-param-only (see ``main()`` in
        ``graphiant_device_lifecycle.py``); ``verify_for_insync``/``wait_for_completion`` are
        genuinely per-device and are read from each device's own entry instead (see
        ``_validate_state_cfg``/``_validate_upgrade_cfg``), with the module param as the
        whole-run default a device falls back to when it doesn't specify its own.
        """
        path = coerce_str(config_yaml_file)
        if not path:
            return {}
        cfg = self._render_config_file_cached(path) or {}
        return cfg if isinstance(cfg, dict) else {}

    # ------------------------------------------------------------------
    # change_state
    # ------------------------------------------------------------------

    @staticmethod
    def _row_from_state_params(mp: Dict[str, Any]) -> Dict[str, Any]:
        lifecycle_state = mp.get("lifecycle_state")
        return {"lifecycle_state": lifecycle_state} if lifecycle_state else {}

    @staticmethod
    def _validate_state_cfg(device_name: str, cfg: Any) -> Dict[str, Any]:
        if not isinstance(cfg, dict):
            raise ConfigurationError(f"Device '{device_name}' config must be a dict")
        lifecycle_state = coerce_str(cfg.get("lifecycle_state")).lower()
        if not lifecycle_state:
            raise ConfigurationError(f"Device '{device_name}' is missing required 'lifecycle_state'")
        if lifecycle_state not in _FRIENDLY_TO_API:
            raise ConfigurationError(
                f"Device '{device_name}' has invalid lifecycle_state {lifecycle_state!r}. "
                f"Allowed: {sorted(_FRIENDLY_TO_API)}"
            )
        out: Dict[str, Any] = {"lifecycle_state": lifecycle_state}
        # Optional per-device override of the verify_for_insync default (module param, or True):
        # a readiness poll is a per-device operation to begin with (see poll_eligible in
        # change_state), so unlike upgrade_action/ts below it's a genuine per-device setting, not
        # a single-call-wide one.
        if "verify_for_insync" in cfg:
            out["verify_for_insync"] = bool(cfg["verify_for_insync"])
        return out

    def _load_device_states(
        self, config_yaml_file: Optional[str], module_params: Optional[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        return load_device_list_yaml_config(
            _YAML_KEY,
            config_yaml_file,
            module_params,
            self._render_config_file_cached,
            missing_input_error="Provide config_file and/or device (portal device name) with lifecycle_state.",
            build_row_from_params=self._row_from_state_params,
            validate_device_cfg=self._validate_state_cfg,
        )

    def _poll_device_ready(self, device_id: int, device_name: Optional[str] = None) -> Optional[str]:
        """
        Poll ``device_id`` for readiness, returning ``None`` on success or the error message on
        failure/timeout — never raises, so one device's timeout doesn't abort the whole
        ``execute_concurrent_tasks`` batch (via ``wait_checked``) and hide whether *other* devices
        reached Ready. Submitted directly to that batch by both ``change_state``'s readiness-poll
        phase and ``_poll_schedule_completions`` (``schedule_upgrade``/``rollback``). The manager
        still records every timeout in the result's ``not_insync_devices`` list; the module
        (``graphiant_device_lifecycle.py``) is what fails the overall task on a non-empty list —
        portalStatus reaching Ready is a requirement, not merely informational, but each device's
        poll must still run to completion independently.

        ``device_name``, when given, is passed through to ``verify_device_portal_status`` so its
        retry log lines name the device, not just its ID (see that method's docstring).
        """
        try:
            self.gsdk.verify_device_portal_status(device_id, device_name=device_name)
            return None
        except Exception as e:  # noqa: BLE001 - collected into not_insync_devices, not raised here
            return str(e)

    def _poll_schedule_completions(
        self, device_id_by_name: Dict[str, int], verify_for_insync_by_name: Dict[str, bool]
    ) -> Dict[str, List[str]]:
        """
        Poll every device in ``device_id_by_name`` (name -> device_id) for upgrade schedule
        completion — used by both ``schedule_upgrade`` and ``rollback`` after their
        ``put_devices_upgrade_schedule`` call succeeds. One shared ``GET /v1/edges-summary`` per
        round (see ``GraphiantPortalClient.poll_upgrade_schedule_completion_batch``) covers every
        device at once instead of each polling independently.

        A device whose schedule reaches ``Success`` isn't necessarily settled from the portal's
        perspective yet, so (when its own ``verify_for_insync_by_name`` entry is enabled) it's
        then also polled for ``portalStatus=Ready`` via ``_poll_device_ready``, concurrently
        across all such devices; a device whose schedule reached ``Failed`` or timed out is never
        Ready-polled.

        Returns ``{"completed_devices", "failed_devices", "in_progress_devices",
        "insync_devices", "not_insync_devices"}`` (each a list); empty immediately when
        ``device_id_by_name`` is empty.
        """
        outcome: Dict[str, List[str]] = {
            "completed_devices": [],
            "failed_devices": [],
            "in_progress_devices": [],
            "insync_devices": [],
            "not_insync_devices": [],
        }
        if not device_id_by_name:
            return outcome

        name_by_device_id = {device_id: name for name, device_id in device_id_by_name.items()}
        results = self.gsdk.poll_upgrade_schedule_completion_batch(list(device_id_by_name.values()))
        ready_poll_tasks: Dict[str, Dict[str, Any]] = {}
        for device_id, (state, failure_reason) in results.items():
            device_name = name_by_device_id[device_id]
            if state == "Success":
                outcome["completed_devices"].append(device_name)
                if verify_for_insync_by_name.get(device_name, True):
                    ready_poll_tasks[device_name] = {"device_id": device_id, "device_name": device_name}
            elif state == "Failed":
                LOG.warning(
                    "%s Device '%s' upgrade schedule failed: %s",
                    _LOG_PREFIX,
                    device_name,
                    failure_reason,
                )
                outcome["failed_devices"].append(device_name)
            else:
                # Timed out before reaching Success or Failed — downloads/installs can take
                # minutes, so this is reported as still in progress, not treated as a failure.
                LOG.warning(
                    "%s Device '%s' upgrade schedule did not reach Success/Failed within the "
                    "poll timeout; still in progress",
                    _LOG_PREFIX,
                    device_name,
                )
                outcome["in_progress_devices"].append(device_name)

        if ready_poll_tasks:
            poll_outcomes = self.execute_concurrent_tasks(self._poll_device_ready, ready_poll_tasks)
            for device_name in ready_poll_tasks:
                not_ready_error = poll_outcomes[device_name].result()
                if not_ready_error:
                    LOG.warning(
                        "%s Device '%s' upgrade succeeded but did not reach portalStatus=Ready afterward: %s",
                        _LOG_PREFIX,
                        device_name,
                        not_ready_error,
                    )
                    outcome["not_insync_devices"].append(device_name)
                else:
                    outcome["insync_devices"].append(device_name)

        return outcome

    def _log_post_schedule_table(self, device_names: List[str], label: str, release_catalog) -> None:
        """Re-fetch and log ``device_names``' resulting state after a schedule_upgrade/rollback
        poll — same before/after pattern as change_state's post-op table (see ``change_state``),
        one shared fetch for the whole batch (see ``_fetch_edges_by_hostname``). A device that
        disappears from edges-summary in the meantime is skipped, not an error."""
        by_hostname = self._fetch_edges_by_hostname()
        post_op_edges = []
        for device_name in device_names:
            edge = by_hostname.get(device_name)
            if edge is None:
                LOG.info("%s '%s' no longer resolvable for the post-op table", _LOG_PREFIX, device_name)
                continue
            post_op_edges.append(edge)
        _log_edges_table(post_op_edges, self.gsdk.enterprise_info, label=label, release_catalog=release_catalog)

    def _apply_status_group(
        self,
        desired: str,
        device_entries: List[Dict[str, Any]],
        check_mode: bool,
    ) -> None:
        """
        Apply one ``PUT /v1/devices/bringup`` call covering every device in ``device_entries``
        that shares the same ``desired`` lifecycle state, instead of one call per device —
        matches the portal UI's own behavior (a single ``deviceIds`` list per status change) and
        avoids the backend load a large batch of concurrent single-device calls can cause.
        Submitted to ``execute_concurrent_tasks`` once per distinct ``desired`` value in a batch
        (see ``change_state`` — almost always exactly one group).

        Readiness polling is a separate, per-device phase run after every group's PUT succeeds
        (see ``change_state``); it's a read-only GET, unaffected by the batching here.
        """
        for entry in device_entries:
            LOG.info(
                "%s%s %s %s: %s -> %s",
                _LOG_PREFIX,
                " [check_mode]" if check_mode else "",
                "Would change" if check_mode else "Changing",
                entry["device_name"],
                entry["before_label"],
                desired,
            )
        try:
            self.gsdk.put_devices_bringup([entry["device_id"] for entry in device_entries], _FRIENDLY_TO_API[desired])
        except APIError as e:
            names = ", ".join(entry["device_name"] for entry in device_entries)
            raise APIError(f"Failed to change lifecycle state to '{desired}' for device(s) {names}: {e}") from e

        for entry in device_entries:
            LOG.info(
                "%s%s ✓ %s %s to %s%s",
                _LOG_PREFIX,
                " [check_mode]" if check_mode else "",
                "Would change" if check_mode else "Changed",
                entry["device_name"],
                desired,
                " (no changes applied)" if check_mode else "",
            )

    def _fetch_edges_by_hostname(self) -> Dict[str, Any]:
        """
        Fetch the full enterprise edge list with a single ``GET /v1/edges-summary`` call and
        index it by hostname (``_index_by_hostname``) — the API has no server-side filter by
        device name or id for this endpoint, so resolving N devices one at a time (each its own
        full-list GET) costs N times the work for no benefit over fetching the list once per
        round and doing local dict lookups afterward. Used by every device-resolution loop in
        this manager (``change_state``'s pre-op and post-op passes, ``_log_post_schedule_table``)
        so a batch of any size costs exactly one of these calls per round, not one per device.
        """
        return _index_by_hostname(self.gsdk.get_edges_summary())

    def change_state(
        self,
        config_yaml_file: Optional[str] = None,
        module_params: Optional[Dict[str, Any]] = None,
        verify_for_insync: Optional[bool] = None,
    ) -> dict:
        by_name = self._load_device_states(config_yaml_file, module_params)
        if not by_name:
            LOG.info("%s No '%s' entries to process", _LOG_PREFIX, _YAML_KEY)
            return new_apply_result(no_input=True, not_insync_devices=[], insync_devices=[])

        # Whole-run default; a device entry's own 'verify_for_insync' (see _validate_state_cfg)
        # overrides this default for that device only.
        default_verify_for_insync = True if verify_for_insync is None else verify_for_insync

        enterprise = self.gsdk.enterprise_info["company_name"]
        result = new_apply_result(not_insync_devices=[], insync_devices=[])

        # Resolve current state for every targeted device first, so the pre-op table (and any
        # decommission-guard/not-found error below) reflects the full target set, not just
        # whatever was resolved before an error on an earlier device in iteration order. One
        # shared fetch covers the whole batch (see _fetch_edges_by_hostname); every device below
        # is then a local dict lookup, not its own API call.
        by_hostname = self._fetch_edges_by_hostname()
        resolved: Dict[str, Any] = {}
        missing_devices: List[str] = []
        for device_name, cfg in by_name.items():
            desired = cfg["lifecycle_state"]
            edge = by_hostname.get(device_name)
            if edge is None:
                # A decommissioned device is removed from edges-summary entirely, so re-running
                # decommissioned against one that's already gone should be a no-op, not an error.
                if desired == "decommissioned":
                    resolved[device_name] = (None, None)
                    continue
                missing_devices.append(device_name)
                continue
            resolved[device_name] = (edge.device_id, edge)
        if missing_devices:
            # Collected across every device before failing, so a config file with several bad
            # names surfaces all of them here in one run rather than one fix-and-retry cycle
            # per name.
            raise DeviceNotFoundError(missing_devices_message(missing_devices, enterprise))

        # Computed once and reused for both the pre-op and post-op tables below — it's a live
        # GET /v1/software/releases/summary call, not something to repeat per table.
        release_catalog = self._release_catalog()

        _log_edges_table(
            [edge for _device_id, edge in resolved.values() if edge is not None],
            self.gsdk.enterprise_info,
            label="Current state before change_state",
            release_catalog=release_catalog,
        )

        # Devices that need a PUT (+ readiness poll if eligible), keyed by device name -> per-
        # device info used below to build _apply_status_group's groups and the poll phase.
        apply_tasks: Dict[str, Dict[str, Any]] = {}
        # Subset of apply_tasks whose desired state actually gets polled (insync_devices below is
        # only meaningful for these — a device never polled at all isn't "ready", it's just
        # untested, so it must not silently end up looking the same as one that passed).
        poll_eligible: set = set()
        check_mode = getattr(self.gsdk, "check_mode", False)
        # Collected across the whole batch (like missing_devices above) rather than raising on
        # just the first offender, so a config file with several premature decommission requests
        # surfaces all of them in one run instead of one fix-and-retry cycle per device — and so
        # an earlier offender in iteration order can't mask whether a later device's otherwise
        # valid change would have succeeded.
        decommission_violations: List[str] = []

        for device_name, cfg in by_name.items():
            desired = cfg["lifecycle_state"]
            device_verify_for_insync = cfg.get("verify_for_insync", default_verify_for_insync)
            device_id, edge = resolved[device_name]
            if edge is None:
                LOG.info(
                    "%s ✓ '%s' not found in edges summary (already decommissioned), skipping",
                    _LOG_PREFIX,
                    device_name,
                )
                result["skipped_devices"].append(device_name)
                continue
            current_status = getattr(edge, "status", None)
            current_friendly = _API_STATUS_TO_FRIENDLY.get(coerce_str(current_status).lower())

            if desired == "decommissioned" and current_friendly != "deactivated":
                decommission_violations.append(f"'{device_name}' (current status: {current_status!r})")
                continue

            if current_friendly == desired:
                LOG.info("%s ✓ No change needed for %s, already %s", _LOG_PREFIX, device_name, desired)
                result["skipped_devices"].append(device_name)
                continue

            result["diff_plan"].append(
                {
                    "device": device_name,
                    "branch": "lifecycle_state",
                    "before": current_friendly or current_status,
                    "after": desired,
                }
            )

            apply_tasks[device_name] = {
                "device_name": device_name,
                "device_id": device_id,
                "desired": desired,
                "before_label": current_friendly or current_status,
            }
            if device_verify_for_insync and desired in _READY_AFTER and not check_mode:
                poll_eligible.add(device_name)

        if decommission_violations:
            raise ConfigurationError(
                f"{len(decommission_violations)} device(s) must be Deactivated before they can be "
                f"Decommissioned: {', '.join(decommission_violations)}. Set lifecycle_state: "
                f"deactivated first, then decommission once each shows as deactivated."
            )

        if apply_tasks:
            # Group devices by desired lifecycle_state so each group gets one put_devices_bringup
            # call (see _apply_status_group) instead of one call per device — almost always
            # exactly one group per run. Submitted through execute_concurrent_tasks so distinct
            # groups apply concurrently; raises (APIError, via wait_checked) if any group's PUT
            # failed, only after every group has run to completion.
            groups: Dict[str, List[Dict[str, Any]]] = {}
            for device_name, task in apply_tasks.items():
                groups.setdefault(task["desired"], []).append(
                    {
                        "device_name": device_name,
                        "device_id": task["device_id"],
                        "before_label": task["before_label"],
                    }
                )
            group_tasks = {
                desired: {"desired": desired, "device_entries": entries, "check_mode": check_mode}
                for desired, entries in groups.items()
            }
            self.execute_concurrent_tasks(self._apply_status_group, group_tasks)

            for device_name in apply_tasks:
                result["configured_devices"].append(device_name)
                result["changed"] = True

            # Readiness polling is a separate per-device phase, run after every group's PUT
            # succeeds — a read-only GET, unaffected by the batching above.
            if poll_eligible:
                poll_tasks = {
                    device_name: {
                        "device_id": apply_tasks[device_name]["device_id"],
                        "device_name": device_name,
                    }
                    for device_name in poll_eligible
                }
                poll_outcomes = self.execute_concurrent_tasks(self._poll_device_ready, poll_tasks)
                for device_name in poll_eligible:
                    not_ready_error = poll_outcomes[device_name].result()
                    if not_ready_error:
                        LOG.warning(
                            "%s Device '%s' did not reach Ready after lifecycle change: %s",
                            _LOG_PREFIX,
                            device_name,
                            not_ready_error,
                        )
                        result["not_insync_devices"].append(device_name)
                    else:
                        result["insync_devices"].append(device_name)

            # Re-fetch and log the resulting state, the same way the pre-op table does, so the
            # log shows both a before and an after snapshot instead of making the reader infer
            # the outcome from configured_devices/insync_devices/not_insync_devices and the
            # transition log lines alone. Real runs only — in check_mode nothing was actually
            # applied, so a refetch would just repeat the pre-op table unchanged.
            if not check_mode:
                post_op_by_hostname = self._fetch_edges_by_hostname()
                post_op_edges = []
                for device_name in apply_tasks:
                    edge = post_op_by_hostname.get(device_name)
                    if edge is None:
                        # e.g. a device just decommissioned (Removed) disappears from
                        # edges-summary entirely — expected, not a reason to fail this display
                        # step or the operation itself.
                        LOG.info(
                            "%s '%s' no longer resolvable for the post-op table (likely decommissioned)",
                            _LOG_PREFIX,
                            device_name,
                        )
                        continue
                    post_op_edges.append(edge)
                _log_edges_table(
                    post_op_edges,
                    self.gsdk.enterprise_info,
                    label="Resulting state after change_state",
                    release_catalog=release_catalog,
                )

        return result

    # ------------------------------------------------------------------
    # schedule_upgrade / rollback
    # ------------------------------------------------------------------

    @staticmethod
    def _row_from_upgrade_params(mp: Dict[str, Any]) -> Dict[str, Any]:
        row: Dict[str, Any] = {}
        if mp.get("release") is not None:
            row["release"] = mp["release"]
        return row

    @staticmethod
    def _validate_upgrade_cfg(require_release: bool):
        def _validate(device_name: str, cfg: Any) -> Dict[str, Any]:
            if not isinstance(cfg, dict):
                raise ConfigurationError(f"Device '{device_name}' config must be a dict")
            out: Dict[str, Any] = {}
            release = cfg.get("release")
            if release is not None:
                release = coerce_str(release)
                if release not in _RELEASES:
                    raise ConfigurationError(
                        f"Device '{device_name}' has invalid release {release!r}. Allowed: {sorted(_RELEASES)}"
                    )
                out["release"] = release
            elif require_release:
                raise ConfigurationError(f"Device '{device_name}' is missing required 'release'")
            # Optional per-device override of the wait_for_completion default (module param, or
            # True): the completion poll already tracks devices individually under one shared
            # fetch (see _poll_schedule_completions), so opting a given device in/out of being
            # watched is a genuine per-device setting, not a single-call-wide one like
            # upgrade_action/ts (which apply to the one PUT covering every device in this batch).
            if "wait_for_completion" in cfg:
                out["wait_for_completion"] = bool(cfg["wait_for_completion"])
            # Optional per-device override of the verify_for_insync default (module param, or
            # True): only consulted for a device that is also being watched for schedule
            # completion (wait_for_completion) — once (and only once) its schedule reaches
            # Success, see _poll_schedule_completions.
            if "verify_for_insync" in cfg:
                out["verify_for_insync"] = bool(cfg["verify_for_insync"])
            return out

        return _validate

    def _load_upgrade_targets(
        self,
        config_yaml_file: Optional[str],
        module_params: Optional[Dict[str, Any]],
        *,
        require_release: bool,
    ) -> Dict[str, Dict[str, Any]]:
        return load_device_list_yaml_config(
            _YAML_KEY,
            config_yaml_file,
            module_params,
            self._render_config_file_cached,
            missing_input_error="Provide config_file and/or device (portal device name).",
            build_row_from_params=self._row_from_upgrade_params,
            validate_device_cfg=self._validate_upgrade_cfg(require_release),
        )

    def schedule_upgrade(
        self,
        config_yaml_file: Optional[str] = None,
        module_params: Optional[Dict[str, Any]] = None,
        action: Optional[str] = None,
        ts: Optional[Dict[str, int]] = None,
        wait_for_completion: Optional[bool] = None,
        verify_for_insync: Optional[bool] = None,
    ) -> dict:
        by_name = self._load_upgrade_targets(config_yaml_file, module_params, require_release=True)
        if not by_name:
            LOG.info("%s No '%s' entries to process", _LOG_PREFIX, _YAML_KEY)
            return new_apply_result(no_input=True)

        # action/ts apply to the whole batch (one PUT covers every scheduled device under a
        # single action/ts), so these are module-param-only, with no per-device or config-file
        # fallback. wait_for_completion/verify_for_insync's defaults here may still be overridden
        # per device (see _validate_upgrade_cfg) since both polls already track devices
        # individually.
        effective_action = action or "InstallActivate"
        effective_ts = ts
        default_wait_for_completion = True if wait_for_completion is None else wait_for_completion
        default_verify_for_insync = True if verify_for_insync is None else verify_for_insync
        check_mode = getattr(self.gsdk, "check_mode", False)
        enterprise = self.gsdk.enterprise_info["company_name"]

        release_catalog = self._release_catalog()
        by_hostname = _index_by_hostname(self.gsdk.get_edges_summary_with_upgrade())
        device_versions: List[Dict[str, Any]] = []
        configured: List[str] = []
        skipped: List[str] = []
        not_connected: List[str] = []
        busy: List[str] = []
        diff_plan: List[Dict[str, Any]] = []
        device_id_by_name: Dict[str, int] = {}
        verify_for_insync_by_name: Dict[str, bool] = {}
        matched_edges = []
        missing_devices: List[str] = []

        for device_name, cfg in by_name.items():
            edge = by_hostname.get(device_name)
            if edge is None:
                missing_devices.append(device_name)
                continue
            matched_edges.append(edge)

            # Portal Connectivity Status: Up (ttConnCount>=2) or Impaired (ttConnCount>=1) is
            # required to schedule an upgrade — a device with no tunnel-terminator connections at
            # all (ttConnCount 0/None) can't actually receive one, so trying would just fail at
            # the API. Skipped here rather than attempted and left to fail; not a "nothing to do"
            # skip like the already-on-target-version one below, so it lands in its own result
            # field (not_connected_devices).
            tt_conn_count = getattr(edge, "tt_conn_count", None) or 0
            if tt_conn_count < 1:
                LOG.info(
                    "%s ✓ '%s' has no portal connectivity (ttConnCount=%s; need >=1/Impaired to "
                    "schedule an upgrade), skipping",
                    _LOG_PREFIX,
                    device_name,
                    tt_conn_count,
                )
                not_connected.append(device_name)
                continue

            # A prior schedule that hasn't reached Success/Failed yet — submitting a new one now
            # can race the backend's own (narrower) dedup guard, see _schedule_in_progress_state.
            # Skipped rather than attempted, same as not_connected_devices above, so it lands in
            # its own result field (schedule_in_progress_devices).
            in_progress_state = self._schedule_in_progress_state(edge)
            if in_progress_state is not None:
                LOG.info(
                    "%s ✓ '%s' has a schedule already in progress (state=%s), skipping to avoid a duplicate request",
                    _LOG_PREFIX,
                    device_name,
                    in_progress_state,
                )
                busy.append(device_name)
                continue

            version = {"release": cfg["release"]}
            target_version = self._resolve_schedule_target_version(cfg, release_catalog)
            current_version = getattr(edge, "sw_version", None)
            if target_version and current_version and target_version == current_version:
                # Resolvable target (the release channel's current build found in
                # release_catalog) already matches what the device is running — a genuine
                # no-op, not just "we couldn't tell". An unresolvable channel (catalog fetch
                # failed, or the channel name isn't in it) always falls through to scheduling
                # rather than guessing it's already current.
                LOG.info(
                    "%s ✓ No change needed for %s, already running %s",
                    _LOG_PREFIX,
                    device_name,
                    target_version,
                )
                skipped.append(device_name)
                continue

            device_versions.append({"deviceId": edge.device_id, "version": version})
            configured.append(device_name)
            if cfg.get("wait_for_completion", default_wait_for_completion):
                device_id_by_name[device_name] = edge.device_id
                verify_for_insync_by_name[device_name] = cfg.get("verify_for_insync", default_verify_for_insync)
            # "after" shows the resolved target build when the catalog resolved one (same value
            # being compared against current_version above); falls back to just the release
            # channel name when unresolvable, since there's no specific build to show either.
            after = dict(version)
            if target_version:
                after["version"] = target_version
            prior_running = getattr(getattr(edge, "upgrade_summary", None), "running_version", None)
            diff_plan.append(
                {
                    "device": device_name,
                    "branch": "schedule_upgrade",
                    "before": _version_to_dict(prior_running),
                    "after": after,
                }
            )

        if missing_devices:
            # Collected across every device before failing, so a config file with several bad
            # names surfaces all of them here in one run rather than one fix-and-retry cycle
            # per name.
            raise DeviceNotFoundError(missing_devices_message(missing_devices, enterprise))

        _log_release_catalog_table(release_catalog, self.gsdk.enterprise_info)
        _log_edges_table(
            matched_edges,
            self.gsdk.enterprise_info,
            label="Current state before schedule_upgrade",
            release_catalog=release_catalog,
        )

        result = new_apply_result(
            completed_devices=[],
            failed_devices=[],
            in_progress_devices=[],
            insync_devices=[],
            not_insync_devices=[],
            not_connected_devices=[],
            schedule_in_progress_devices=[],
        )
        result["skipped_devices"] = skipped
        result["not_connected_devices"] = not_connected
        result["schedule_in_progress_devices"] = busy
        if not device_versions:
            return result

        try:
            self.gsdk.put_devices_upgrade_schedule(
                device_versions=device_versions, action=effective_action, ts=effective_ts
            )
        except APIError as e:
            raise APIError(
                f"Failed to schedule upgrade (action={effective_action}) for device(s) " f"{', '.join(configured)}: {e}"
            ) from e

        result["changed"] = True
        result["configured_devices"] = configured
        result["diff_plan"] = diff_plan

        if device_id_by_name and not check_mode:
            result.update(self._poll_schedule_completions(device_id_by_name, verify_for_insync_by_name))
            self._log_post_schedule_table(configured, "Resulting state after schedule_upgrade", release_catalog)

        return result

    def rollback(
        self,
        config_yaml_file: Optional[str] = None,
        module_params: Optional[Dict[str, Any]] = None,
        ts: Optional[Dict[str, int]] = None,
        wait_for_completion: Optional[bool] = None,
        verify_for_insync: Optional[bool] = None,
    ) -> dict:
        by_name = self._load_upgrade_targets(config_yaml_file, module_params, require_release=False)
        if not by_name:
            LOG.info("%s No '%s' entries to process", _LOG_PREFIX, _YAML_KEY)
            return new_apply_result(no_input=True)

        # ts applies to the whole batch (one PUT covers every scheduled device under a single
        # ts), so it's module-param-only, with no per-device or config-file fallback.
        # wait_for_completion/verify_for_insync's defaults here may still be overridden per
        # device (see _validate_upgrade_cfg) since both polls already track devices individually.
        effective_ts = ts
        default_wait_for_completion = True if wait_for_completion is None else wait_for_completion
        default_verify_for_insync = True if verify_for_insync is None else verify_for_insync
        check_mode = getattr(self.gsdk, "check_mode", False)
        enterprise = self.gsdk.enterprise_info["company_name"]

        by_hostname = _index_by_hostname(self.gsdk.get_edges_summary_with_upgrade())

        device_versions: List[Dict[str, Any]] = []
        configured: List[str] = []
        skipped: List[str] = []
        busy: List[str] = []
        diff_plan: List[Dict[str, Any]] = []
        device_id_by_name: Dict[str, int] = {}
        verify_for_insync_by_name: Dict[str, bool] = {}
        matched_edges = []
        missing_devices: List[str] = []

        for device_name, cfg in by_name.items():
            edge = by_hostname.get(device_name)
            if edge is None:
                missing_devices.append(device_name)
                continue
            matched_edges.append(edge)

            # A prior schedule that hasn't reached Success/Failed yet — submitting a new one now
            # can race the backend's own (narrower) dedup guard, see _schedule_in_progress_state.
            # Skipped rather than attempted, so it lands in its own result field
            # (schedule_in_progress_devices), same as schedule_upgrade's not_connected_devices.
            in_progress_state = self._schedule_in_progress_state(edge)
            if in_progress_state is not None:
                LOG.info(
                    "%s ✓ '%s' has a schedule already in progress (state=%s), skipping to avoid a duplicate request",
                    _LOG_PREFIX,
                    device_name,
                    in_progress_state,
                )
                busy.append(device_name)
                continue

            upgrade_summary = getattr(edge, "upgrade_summary", None)
            last_running = getattr(upgrade_summary, "last_running_version", None) if upgrade_summary else None
            if last_running is None:
                # No prior version recorded for this device (e.g. it's never been
                # upgraded/rolled back before) — there's genuinely nothing to roll back to, so
                # this is a no-op skip, not an error (matches the portal UI, which has no way to
                # target anything other than a device's own last running version either).
                LOG.info(
                    "%s ✓ '%s' has no lastRunningVersion to roll back to, skipping",
                    _LOG_PREFIX,
                    device_name,
                )
                skipped.append(device_name)
                continue
            target_version = _version_to_dict(last_running)

            device_versions.append({"deviceId": edge.device_id, "version": target_version})
            configured.append(device_name)
            if cfg.get("wait_for_completion", default_wait_for_completion):
                device_id_by_name[device_name] = edge.device_id
                verify_for_insync_by_name[device_name] = cfg.get("verify_for_insync", default_verify_for_insync)
            prior_running = getattr(getattr(edge, "upgrade_summary", None), "running_version", None)
            diff_plan.append(
                {
                    "device": device_name,
                    "branch": "rollback",
                    "before": _version_to_dict(prior_running),
                    "after": target_version,
                }
            )

        if missing_devices:
            # Collected across every device before failing, so a config file with several bad
            # names surfaces all of them here in one run rather than one fix-and-retry cycle
            # per name.
            raise DeviceNotFoundError(missing_devices_message(missing_devices, enterprise))

        release_catalog = self._release_catalog()
        _log_release_catalog_table(release_catalog, self.gsdk.enterprise_info)
        _log_edges_table(
            matched_edges,
            self.gsdk.enterprise_info,
            label="Current state before rollback",
            release_catalog=release_catalog,
        )

        result = new_apply_result(
            completed_devices=[],
            failed_devices=[],
            in_progress_devices=[],
            insync_devices=[],
            not_insync_devices=[],
            schedule_in_progress_devices=[],
        )
        result["skipped_devices"] = skipped
        result["schedule_in_progress_devices"] = busy
        if not device_versions:
            return result

        try:
            self.gsdk.put_devices_upgrade_schedule(device_versions=device_versions, action="Activate", ts=effective_ts)
        except APIError as e:
            raise APIError(f"Failed to schedule rollback for device(s) {', '.join(configured)}: {e}") from e

        result["changed"] = True
        result["configured_devices"] = configured
        result["diff_plan"] = diff_plan

        if device_id_by_name and not check_mode:
            result.update(self._poll_schedule_completions(device_id_by_name, verify_for_insync_by_name))
            self._log_post_schedule_table(configured, "Resulting state after rollback", release_catalog)

        return result

    # ------------------------------------------------------------------
    # get_status (read-only)
    # ------------------------------------------------------------------

    def _resolve_status_targets(
        self, config_yaml_file: Optional[str], module_params: Optional[Dict[str, Any]]
    ) -> Optional[List[str]]:
        mp = module_params or {}
        device = coerce_str(mp.get("device"))
        if device:
            return [device]
        path = coerce_str(config_yaml_file)
        if not path:
            return None
        cfg = self._render_config_file_cached(path) or {}
        raw = cfg.get(_YAML_KEY)
        if raw is None:
            return None
        if not isinstance(raw, list):
            raise ConfigurationError(f"'{_YAML_KEY}' must be a list of device entries")
        names: List[str] = []
        for entry in raw:
            if not isinstance(entry, dict) or not entry:
                raise ConfigurationError(
                    f"Each entry in '{_YAML_KEY}' must be a non-empty dict keyed by portal device name"
                )
            names.extend(entry.keys())
        return names

    def get_status(
        self,
        config_yaml_file: Optional[str] = None,
        module_params: Optional[Dict[str, Any]] = None,
        role: Optional[str] = None,
    ) -> dict:
        LOG.info("%s Current enterprise info: %s", _LOG_PREFIX, self.gsdk.enterprise_info)
        device_names = self._resolve_status_targets(config_yaml_file, module_params)
        top = self._read_top_level_yaml(config_yaml_file)
        # No default role filter: the portal's own "Device Lifecycle" page always queries with
        # filter[role]=UnknownDeviceRole regardless of the actual devices returned (they show
        # role "cpe", "gateway", etc.) — the API has no server-side role filter to apply
        # (confirmed against the SDK's v1_edges_summary_get signature), so that query param is
        # inert there. Filtering client-side on the literal string "UnknownDeviceRole" would
        # match nothing, since no device ever reports that as its actual role. Omit role (here
        # and in config_file/module params) to list every device, matching that real behavior;
        # pass an explicit role (e.g. "cpe") only when you want a genuine client-side filter.
        effective_role = role or top.get("role")
        LOG.info(
            "%s get_status: requested device_names=%s, role filter=%r",
            _LOG_PREFIX,
            device_names,
            None if device_names else effective_role,
        )
        edges = self.gsdk.get_edges_summary_with_upgrade(role=None if device_names else effective_role)
        by_hostname = _index_by_hostname(edges)
        LOG.info(
            "%s get_status: fetched %d edge(s) from GET /v1/edges-summary; hostnames=%s",
            _LOG_PREFIX,
            len(edges),
            sorted(by_hostname),
        )
        names_to_report = device_names if device_names else sorted(by_hostname)
        devices: Dict[str, Any] = {}
        failed_devices: List[Dict[str, str]] = []
        matched_edges = []

        for name in names_to_report:
            edge = by_hostname.get(name)
            if edge is None:
                failed_devices.append({"device_name": name, "error": f"Device '{name}' not found in edges summary"})
                continue
            devices[name] = _edge_status_dict(edge)
            matched_edges.append(edge)

        # Only the devices actually being reported (device_names when given, otherwise every
        # device the role filter returned) — not the full unfiltered edges-summary response.
        _log_edges_table(
            matched_edges,
            self.gsdk.enterprise_info,
            label="Reported devices",
            release_catalog=self._release_catalog(),
        )

        return {"changed": False, "devices": devices, "failed_devices": failed_devices}

    # ------------------------------------------------------------------
    # BaseManager
    # ------------------------------------------------------------------

    def configure(self, config_yaml_file: str) -> dict:
        raise ConfigurationError(
            "graphiant_device_lifecycle has no 'configure' workflow; use one of the "
            "change_state / schedule_upgrade / rollback / get_status operations."
        )

    def deconfigure(self, config_yaml_file: str) -> dict:
        raise ConfigurationError(
            "Deconfigure is not applicable to device lifecycle. Use change_state with "
            "lifecycle_state: deactivated (and decommissioned once deactivated) instead."
        )


def _index_by_hostname(edges: Any) -> Dict[str, Any]:
    """Index edge-summary objects by ``hostname`` (skipping any with no hostname)."""
    return {edge.hostname: edge for edge in edges if getattr(edge, "hostname", None)}


def _version_to_dict(version: Any) -> Optional[Dict[str, Any]]:
    if version is None:
        return None
    if isinstance(version, dict):
        return version
    out = {}
    for key in ("release", "version", "name"):
        val = getattr(version, key, None)
        if val is not None:
            out[key] = val
    return out or None


def _schedule_to_dict(schedule: Any) -> Optional[Dict[str, Any]]:
    if schedule is None:
        return None
    return {
        "action": getattr(schedule, "action", None),
        "state": getattr(schedule, "state", None),
        "download_progress": getattr(schedule, "download_progress", None),
        "failure_reason": getattr(schedule, "failure_reason", None),
        "version": _version_to_dict(getattr(schedule, "version", None)),
    }


def _friendly_lifecycle_state(edge: Any) -> Optional[str]:
    """Friendly label matching the portal's "Lifecycle State" column (same vocabulary as the
    lifecycle_state module option); falls back to the raw status when it's not one of the known
    values (e.g. a device mid-transition)."""
    status = getattr(edge, "status", None)
    return _API_STATUS_TO_FRIENDLY.get(coerce_str(status).lower(), status)


def _catalog_entry(
    edge: Any, release_catalog: Optional[Dict[str, Dict[str, Optional[str]]]]
) -> Dict[str, Optional[str]]:
    sw_version = getattr(edge, "sw_version", None)
    if not sw_version or not release_catalog:
        return {}
    return release_catalog.get(sw_version) or {}


def _resolve_release(edge: Any, release_catalog: Optional[Dict[str, Dict[str, Optional[str]]]]) -> Optional[str]:
    """
    Resolve the release channel (Stable/Recommended/Latest/Custom) for ``edge``.

    Primary source is ``release_catalog`` (``GET /v1/software/releases/summary``, see
    ``DeviceLifecycleManager._release_catalog``) matched against the device's own ``swVersion``
    — that catalog is authoritative for currently-named releases. Falls back to
    ``upgradeSummary.runningVersion.release`` (reliably present, including V(Custom)) for a build
    no longer tracked in that catalog (e.g. an old superseded version).
    """
    release = _catalog_entry(edge, release_catalog).get("release")
    if release:
        return release
    running_version = getattr(getattr(edge, "upgrade_summary", None), "running_version", None)
    return getattr(running_version, "release", None)


def _resolve_release_name(edge: Any, release_catalog: Optional[Dict[str, Dict[str, Optional[str]]]]) -> Optional[str]:
    """
    Resolve the friendly release name (e.g. "26.6.3") for ``edge``.

    Primary source is the edge's own ``swName``. Falls back to ``release_catalog`` (matched by
    ``swVersion``, same catalog as ``_resolve_release``) when that's empty — the API frequently
    leaves ``swName`` unset even when the version is a currently-named release — and finally to
    ``upgradeSummary.runningVersion.name``. All three can legitimately be empty for an
    unlisted/superseded build that was never given a friendly name.
    """
    sw_name = getattr(edge, "sw_name", None)
    if sw_name:
        return sw_name
    name = _catalog_entry(edge, release_catalog).get("name")
    if name:
        return name
    running_version = getattr(getattr(edge, "upgrade_summary", None), "running_version", None)
    return getattr(running_version, "name", None)


def _log_release_catalog_table(
    release_catalog: Optional[Dict[str, Dict[str, Optional[str]]]],
    enterprise_info: Optional[Dict[str, Any]],
) -> None:
    """
    Log the release channel -> current build table (``GET /v1/software/releases/summary``, see
    ``DeviceLifecycleManager._release_catalog``), so ``schedule_upgrade``'s skip-vs-schedule
    decision (``_resolve_schedule_target_version`` comparing a device's own ``swVersion`` against
    this table's ``Version`` column for its target ``Release``) is auditable directly from
    ``detailed_logs`` instead of needing a separate manual query.
    """
    if not HAS_TABULATE or not release_catalog:
        return
    rows = sorted(
        ([entry.get("release"), version, entry.get("name")] for version, entry in release_catalog.items()),
        key=lambda row: row[0] or "",
    )
    LOG.info(
        "%s Release catalog (enterprise=%s):\n%s",
        _LOG_PREFIX,
        (enterprise_info or {}).get("company_name"),
        tabulate(rows, headers=["Release", "Version", "Name"], tablefmt="grid", disable_numparse=True),
    )


def _log_edges_table(
    edges: List[Any],
    enterprise_info: Optional[Dict[str, Any]],
    *,
    label: str,
    release_catalog: Optional[Dict[str, Dict[str, Optional[str]]]] = None,
) -> None:
    """
    Log a table of ``edges`` (skipped when ``tabulate`` isn't installed or ``edges`` is empty).

    Used both by ``get_status`` (the devices it's reporting) and, before any mutating call, by
    ``change_state`` / ``schedule_upgrade`` / ``rollback`` (the current state of the devices
    about to be changed) — so a run with ``detailed_logs: true`` always shows what it's about to
    act on. Columns: Device ID (prepended — needed to target a device precisely), Host Name,
    Lifecycle State, Portal Sync (``portalStatus``, e.g. V(Ready)/V(Configuring)/V(ModeChanged) —
    the same status ``verify_device_portal_status`` polls after a ``change_state`` mutation),
    Release (see ``_resolve_release``), Release Name (see ``_resolve_release_name``), Software
    Version (``swVersion``), Upgrade Status, Rollout Name, Site, Connected Region, Location.
    """
    if not HAS_TABULATE or not edges:
        return
    edge_table = [
        [
            getattr(edge, "device_id", None),
            getattr(edge, "hostname", None),
            _friendly_lifecycle_state(edge),
            getattr(edge, "portal_status", None),
            _resolve_release(edge, release_catalog),
            _resolve_release_name(edge, release_catalog),
            getattr(edge, "sw_version", None),
            getattr(getattr(edge, "upgrade_summary", None), "status", None),
            getattr(getattr(edge, "upgrade_summary", None), "rollout_name", None),
            getattr(edge, "site", None),
            ", ".join(getattr(edge, "connected_regions", None) or []),
            getattr(edge, "discovered_location", None),
        ]
        for edge in edges
    ]
    LOG.info(
        "%s %s (enterprise=%s):\n%s",
        _LOG_PREFIX,
        label,
        (enterprise_info or {}).get("company_name"),
        tabulate(
            edge_table,
            headers=[
                "Device ID",
                "Host Name",
                "Lifecycle State",
                "Portal Sync",
                "Release",
                "Release Name",
                "Software Version",
                "Upgrade Status",
                "Rollout Name",
                "Site",
                "Connected Region",
                "Location",
            ],
            tablefmt="grid",
            # Device ID and Software Version look numeric (e.g. "2604.202604110216") but aren't
            # meant to be — tabulate's automatic float parsing would otherwise silently truncate
            # a version string like that to "2604.2".
            disable_numparse=True,
        ),
    )


def _edge_status_dict(edge: Any) -> Dict[str, Any]:
    upgrade_summary = getattr(edge, "upgrade_summary", None)
    return {
        "device_id": getattr(edge, "device_id", None),
        "status": getattr(edge, "status", None),
        "lifecycle_state": _friendly_lifecycle_state(edge),
        "portal_status": getattr(edge, "portal_status", None),
        "sw_name": getattr(edge, "sw_name", None),
        "sw_version": getattr(edge, "sw_version", None),
        "site": getattr(edge, "site", None),
        "connected_regions": getattr(edge, "connected_regions", None),
        "location": getattr(edge, "discovered_location", None),
        "upgrade_status": getattr(upgrade_summary, "status", None) if upgrade_summary else None,
        "rollout_name": getattr(upgrade_summary, "rollout_name", None) if upgrade_summary else None,
        "running_version": (
            _version_to_dict(getattr(upgrade_summary, "running_version", None)) if upgrade_summary else None
        ),
        "last_running_version": (
            _version_to_dict(getattr(upgrade_summary, "last_running_version", None)) if upgrade_summary else None
        ),
        "ready_for_activation_version": (
            _version_to_dict(getattr(upgrade_summary, "ready_for_activation_version", None))
            if upgrade_summary
            else None
        ),
        "schedule": _schedule_to_dict(getattr(upgrade_summary, "schedule", None)) if upgrade_summary else None,
    }
