#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for managing Graphiant device lifecycle state and software upgrades.
"""

DOCUMENTATION = r"""
---
module: graphiant_device_lifecycle
short_description: Manage device lifecycle state and software upgrades/rollback
description:
  - >-
    Changes device lifecycle state with C(PUT /v1/devices/bringup) and schedules or rolls back
    software upgrades with C(PUT /v1/devices/upgrade/schedule). Matches the portal's
    Maintain > Device Lifecycle page. Use M(graphiant.naas.graphiant_device_lifecycle_info) to
    query current status instead.
  - >-
    O(operation=change_state) sets O(lifecycle_state) to V(activated), V(staging),
    V(maintenance), V(deactivated), or V(decommissioned). Idempotent against live
    C(GET /v1/edges-summary) C(status) — only devices that differ are pushed. V(decommissioned)
    is only accepted when the device's current state is V(deactivated) (matches the portal UI);
    the module fails the task otherwise rather than sending a request the device isn't in a
    valid state for.
  - >-
    O(operation=schedule_upgrade) schedules a software update to a release channel
    (O(release): V(Stable)/V(Recommended)/V(Latest)/V(Custom) — matches the portal's own
    "Change Release" dropdown exactly; V(Custom) only resolves to anything for an enterprise
    that has a custom image enabled, and is otherwise rejected by the API) via O(upgrade_action)
    (V(InstallActivate)/V(Install)/V(Activate), optional O(ts) to run later); O(operation=rollback)
    schedules C(action=Activate) back to each device's C(upgradeSummary.lastRunningVersion) — the
    only target either operation supports; neither can be pinned to an arbitrary exact build
    string, matching what the portal UI itself allows. Both are actions rather than fully
    declarative state, so a device that does need the change always reports C(changed=true) on
    success — except one idempotency-style skip each: C(schedule_upgrade) skips a device already
    resolved to be running the requested O(release) channel's current build
    (RV(skipped_devices)); C(rollback) skips a device with no C(lastRunningVersion) — its *only*
    skip, since C(lastRunningVersion) always differs from what's currently running, so there's no
    "already on this version" case; a repeat C(rollback) right after a previous one simply
    targets whichever build the device just came from, reporting C(changed=true) again.
    C(schedule_upgrade) additionally does not schedule a device whose portal Connectivity Status
    is Down (C(ttConnCount) below V(1)/Impaired) rather than attempting a push with nothing to
    deliver it over — unlike the other two skips, this one (RV(not_connected_devices)) fails the
    task, even when other devices in the same batch were scheduled successfully (RV(msg) is
    replaced with a summary; see notes). Both C(schedule_upgrade) and C(rollback) also skip
    (RV(schedule_in_progress_devices)) a device whose existing schedule hasn't reached a terminal
    state yet, to avoid racing a still-in-flight prior schedule for the same device — a soft skip
    like RV(skipped_devices), not a failure (see notes).
  - >-
    Supply O(config_file) for a C(device_lifecycle) list, and/or O(device) with
    O(lifecycle_state) / O(release) to run a single device or override one device from the file.
  - >-
    Precedence is NOT the same for every option: O(operation), O(upgrade_action), and O(ts)
    apply to the whole run and are module-parameter only (no O(config_file) equivalent).
    O(lifecycle_state) and O(release) follow the usual rule — a module parameter set via
    O(device) overrides that one device's entry in the file. O(verify_for_insync) and
    O(wait_for_completion) work the OPPOSITE way: the module parameter only sets the whole-run
    default, and a device's own value in O(config_file) always wins over it for itself — see
    notes.
version_added: "26.10.0"
notes:
  - >-
    After O(operation=change_state) succeeds for V(activated)/V(staging)/V(maintenance) (skipped
    for V(deactivated)/V(decommissioned)), the module polls C(GET /v1/edges-summary) until
    C(portalStatus=Ready) and the device has at least 2 tunnel-terminator connections, or a
    timeout is reached (reuses the same C(verify_device_portal_status) helper as
    M(graphiant.naas.graphiant_device_config)). Devices that don't reach Ready in time land in
    RV(not_insync_devices) and fail the task (RV(msg) is replaced with a summary naming them; the
    state change itself was still applied — see RV(configured_devices)); devices that did reach
    Ready land in RV(insync_devices). Set O(verify_for_insync=false) to skip this for every
    device, or set C(verify_for_insync) per device in O(config_file). Devices sharing the same
    desired O(lifecycle_state) are applied via a single batched C(PUT) call (matching the portal
    UI's own behavior), not one call per device; the readiness poll afterward still runs
    concurrently per device, not one at a time, and each retry logged while polling names the
    device by hostname (not just its numeric ID) so concurrent devices' log lines can be told
    apart.
  - >-
    After O(operation=schedule_upgrade) / O(operation=rollback) succeeds, the module polls each
    scheduled device's C(upgradeSummary.schedule.state) until it reaches C(Success) or C(Failed)
    (every other value, including any new one the API might add, means still in progress — not a
    failure, since downloads/installs can take minutes), landing in RV(completed_devices) /
    RV(failed_devices) / RV(in_progress_devices). A device whose schedule reaches C(Success) is
    then also polled for C(portalStatus=Ready) the same way O(operation=change_state) is (same
    O(verify_for_insync) toggle, same RV(insync_devices)/RV(not_insync_devices) result fields) —
    C(Success) doesn't mean the portal has settled back to C(Ready) yet. A C(Failed) schedule, or
    a non-empty RV(not_insync_devices), fails the task even though the schedule/rollback was still
    applied. Set O(wait_for_completion=false) to skip the schedule-state poll (and, since there's
    then no C(Success) to follow, the Ready poll too) for every device, or override either toggle
    per device in O(config_file).
  - >-
    With O(detailed_logs=true) and C(tabulate) installed, every operation logs the targeted
    devices' current state as a table before any C(PUT) (see
    M(graphiant.naas.graphiant_device_lifecycle_info)'s O(detailed_logs) note for column details).
    O(operation=change_state) (outside check mode) logs the same table again afterward, re-fetched
    to show each device's resulting state. O(operation=schedule_upgrade) and O(operation=rollback)
    additionally log the release channel -> current build table (from the same software releases
    catalog used to resolve RV(skipped_devices) and the diff C(after) value) right before the
    devices table, so the skip/schedule decision for every device is auditable from the log alone.
  - >-
    A O(device) or O(config_file) C(device_lifecycle) entry naming a device not found in
    C(GET /v1/edges-summary) fails the task before any C(PUT) is sent; every such unresolved
    device is collected and named together in one failure, not just the first one encountered,
    so a config file with several bad names surfaces all of them in a single run.
  - >-
    O(operation=schedule_upgrade) / O(operation=rollback) skip (RV(schedule_in_progress_devices))
    a device whose existing C(upgradeSummary.schedule.state) hasn't reached C(Success)/C(Failed)
    yet, including C(Idle) — submitting a new schedule while a prior one is still in progress can
    race the upgrade backend's own duplicate-request guard and has been observed to fail with
    C(FailureReason: "Internal error"). Not a failure here; this is reported the same way as
    RV(skipped_devices) (counted in the "N device(s) skipped" summary) rather than failing the
    task, since the device's prior schedule is itself still making progress toward the same goal.
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
options:
  operation:
    description:
      - >-
        The device lifecycle operation to perform. Module-parameter only (not settable in
        O(config_file)) — one invocation runs exactly one operation for every device in the
        batch, so there is no per-device or per-file notion of it; pass it with C(-e
        operation=...) or set it directly on the task (this collection's
        C(device_lifecycle_management.yml) playbook does this via its per-operation tags).
    type: str
    required: true
    choices: [ change_state, schedule_upgrade, rollback ]
  config_file:
    description:
      - >-
        Path to YAML that can drive the whole task by itself (only O(host) / O(username) /
        O(password) / O(access_token) and O(operation) still need to be set on the task) —
        optional only if O(device) is set instead.
      - Relative paths resolve using the collection config path (see C(GRAPHIANT_CONFIGS_PATH)).
      - >-
        Top-level key C(device_lifecycle) is a list of single-key dicts keyed by portal device
        name. For O(operation=change_state), the value has C(lifecycle_state) and optionally
        C(verify_for_insync) (overrides the module option, per device). For
        O(operation=schedule_upgrade), the value has C(release) and optionally
        C(wait_for_completion) and/or C(verify_for_insync) (each overrides its matching module
        option, per device). For O(operation=rollback), the value only needs
        C(wait_for_completion) / C(verify_for_insync) if overriding those (the rollback target is
        always the device's own last running version — an empty dict is enough otherwise).
      - >-
        O(upgrade_action) and O(ts) apply to the whole batch (one C(PUT) schedules every
        device's upgrade under a single action/time) and so, like O(operation), are
        module-parameter only — they cannot be set in this file.
    type: str
    required: false
  device:
    description:
      - Portal device name. With O(config_file), optional override for this one device.
      - Required when O(config_file) is omitted.
    type: str
    required: false
  lifecycle_state:
    description:
      - Target lifecycle state (O(operation=change_state) with O(device)).
    type: str
    required: false
    choices: [ activated, staging, maintenance, deactivated, decommissioned ]
  release:
    description:
      - >-
        Target software release channel (O(operation=schedule_upgrade) with O(device)) —
        matches the portal's own "Change Release" dropdown exactly. V(Custom) only resolves to
        anything for an enterprise that has a custom image enabled; offered here unconditionally
        and otherwise rejected by the API. There is no way to target an arbitrary exact build
        string instead of a channel, matching what the portal UI itself allows.
      - Ignored for O(operation=rollback) (the rollback target is always the device's own
        C(upgradeSummary.lastRunningVersion) — there is no override).
    type: str
    required: false
    choices: [ Stable, Recommended, Latest, Custom ]
  upgrade_action:
    description:
      - How to apply the upgrade (O(operation=schedule_upgrade)).
      - "V(InstallActivate): download and install/activate immediately (portal \"Download & Install\")."
      - "V(Install): download only, do not activate (portal \"Download Only\")."
      - "V(Activate): activate a version already downloaded to the device (portal \"Install Only\")."
      - >-
        Applies to every device in the batch (one C(PUT) call, one action) — module-parameter
        only, not settable in O(config_file); defaults to V(InstallActivate) when not given.
    type: str
    required: false
    default: null
    choices: [ InstallActivate, Install, Activate ]
  ts:
    description:
      - >-
        Optional schedule time for O(operation=schedule_upgrade) / O(operation=rollback):
        C({"seconds": <int>, "nanos": <int>}). Applies to every device in the batch (one C(PUT)
        call, one time) — module-parameter only, not settable in O(config_file); omit to run now.
    type: dict
    required: false
  verify_for_insync:
    description:
      - >-
        Poll for the device to reach C(portalStatus=Ready). For O(operation=change_state), after
        V(activated) / V(staging) / V(maintenance) changes (no effect on V(deactivated) /
        V(decommissioned)). For O(operation=schedule_upgrade) / O(operation=rollback), after that
        device's schedule reaches C(Success) — only consulted for a device that is also being
        watched by O(wait_for_completion) (see notes); has no effect on a device whose schedule
        reached C(Failed) or timed out, or one with O(wait_for_completion=false).
      - >-
        Sets the whole-run default; a device's own C(verify_for_insync) key in O(config_file)
        overrides this default for that device only. Defaults to V(true) when neither is given.
    type: bool
    default: null
  wait_for_completion:
    description:
      - >-
        For O(operation=schedule_upgrade) / O(operation=rollback), poll each scheduled device's
        C(upgradeSummary.schedule.state) after the C(PUT) until it reaches a terminal value
        (C(Success) or C(Failed)) or a timeout is reached (see notes); V(false) also disables the
        O(verify_for_insync) Ready poll that would otherwise follow a C(Success) for that device,
        since without this poll there's no C(Success) to follow. Has no effect on
        O(operation=change_state).
      - >-
        Sets the whole-run default; a device's own C(wait_for_completion) key in O(config_file)
        (alongside its C(release)) overrides this default for that device only. Defaults to
        V(true) when neither is given.
    type: bool
    default: null
  state:
    description:
      - Only C(present) is supported; use O(operation) to select the action.
    type: str
    required: false
    default: present
    choices: [ present ]
  detailed_logs:
    description: Enable detailed logging in the task result message.
    type: bool
    default: false

attributes:
  check_mode:
    description: Full support for C(change_state); partial for C(schedule_upgrade)/C(rollback).
    support: partial
    details: >
      C(change_state) reads current device state in check mode and sets C(changed) from whether
      a push would be needed, without sending the C(PUT) (same convention as
      M(graphiant.naas.graphiant_device_system)); the readiness poll is skipped in check mode.
      C(schedule_upgrade) and C(rollback) skip the mutating C(PUT) in check mode but, for a
      device that isn't skipped (see RV(skipped_devices)), always report C(changed=true) when
      resolved successfully — there's no live state to compare a one-off scheduled action
      against the way O(operation=change_state) can. In check mode, RV(msg) is prefixed with
      C([check_mode]) and says what would happen (e.g. "Would change device lifecycle state")
      rather than "Successfully changed ...", so a check-mode run cannot be mistaken for one
      that actually applied changes just by reading the message.
  diff_mode:
    description: Supports Ansible's C(--diff) for C(change_state), C(schedule_upgrade), and C(rollback).
    support: partial
    details: >
      C(change_state) shows before/after C(lifecycle_state); C(rollback) shows before/after
      C(version). C(schedule_upgrade) shows before/after C(version) too, where C(after) is the
      release channel's current build resolved from the software releases catalog (see
      RV(skipped_devices)) when resolvable, otherwise just the requested release channel name.
requirements:
  - python >= 3.7
  - graphiant-sdk >= 26.10.0
  - >-
    tabulate (optional; logs a pre-change device table with C(detailed_logs=true) when installed)
seealso:
  - module: graphiant.naas.graphiant_device_system
    description: Configure device hostname, region, and site.
  - module: graphiant.naas.graphiant_device_lifecycle_info
    description: Query device lifecycle state and software upgrade status.
author:
  - Graphiant Team (@graphiant)
"""

EXAMPLES = r"""
- name: Change lifecycle state for devices from a config file
  graphiant.naas.graphiant_device_lifecycle:
    operation: change_state
    config_file: "sample_device_lifecycle.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: lifecycle_result

- name: Move a single device to staging
  graphiant.naas.graphiant_device_lifecycle:
    operation: change_state
    device: "edge-1-sdktest"
    lifecycle_state: staging
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Deactivate then decommission a device
  graphiant.naas.graphiant_device_lifecycle:
    operation: change_state
    device: "edge-1-sdktest"
    lifecycle_state: deactivated
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Now safe to decommission (device is Deactivated)
  graphiant.naas.graphiant_device_lifecycle:
    operation: change_state
    device: "edge-1-sdktest"
    lifecycle_state: decommissioned
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Download and install the Latest release now
  graphiant.naas.graphiant_device_lifecycle:
    operation: schedule_upgrade
    device: "edge-1-sdktest"
    release: "Latest"
    upgrade_action: "InstallActivate"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Download the Stable release only, for later activation
  graphiant.naas.graphiant_device_lifecycle:
    operation: schedule_upgrade
    device: "edge-1-sdktest"
    release: "Stable"
    upgrade_action: "Install"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Schedule an upgrade for several devices, from a config file
  graphiant.naas.graphiant_device_lifecycle:
    operation: schedule_upgrade
    config_file: "sample_device_lifecycle.yaml"  # devices + release, from the file
    upgrade_action: "InstallActivate"  # applies to the whole batch; module param only
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Roll back a device to its previous running version
  graphiant.naas.graphiant_device_lifecycle:
    operation: rollback
    device: "edge-1-sdktest"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Override verify_for_insync for just one device in the batch
  graphiant.naas.graphiant_device_lifecycle:
    operation: change_state
    config_file: "sample_device_lifecycle.yaml"  # one device's own entry sets verify_for_insync: false
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
"""

RETURN = r"""
msg:
  description: Result message from the operation, including detailed logs when O(detailed_logs) is enabled.
  type: str
  returned: always
changed:
  description: Whether the operation made (or, in check mode, would make) changes.
  type: bool
  returned: always
operation:
  description: The operation that was performed.
  type: str
  returned: always
configured_devices:
  description: Device names updated (C(change_state)) or scheduled (C(schedule_upgrade)/C(rollback)).
  type: list
  elements: str
  returned: when applicable
skipped_devices:
  description: >-
    Device names skipped — for C(change_state), because they already matched O(lifecycle_state);
    for C(schedule_upgrade), because the device already resolved to be running the requested
    target (only when that target could actually be resolved to a build — see RV(msg)/notes);
    for C(rollback), because the device has no C(lastRunningVersion) to roll back to.
  type: list
  elements: str
  returned: when applicable
not_connected_devices:
  description: >-
    C(schedule_upgrade) only — device names not scheduled because the device's portal
    Connectivity Status is Down (C(ttConnCount) C(0) or missing): less than Impaired
    (C(ttConnCount>=1)), so there's no tunnel-terminator connection to actually deliver the
    upgrade over. Not attempted rather than sent and left to fail at the API; the rest of the
    batch is still scheduled normally, but a non-empty list here fails the task (RV(msg) replaced
    with a summary naming them, worded as "No devices were scheduled" instead of "Upgrade
    scheduled, but ..." when this is the only reason C(changed) is false).
  type: list
  elements: str
  returned: when applicable
schedule_in_progress_devices:
  description: >-
    C(schedule_upgrade) / C(rollback) only — device names not (re-)scheduled because their
    existing C(upgradeSummary.schedule.state) hadn't reached C(Success)/C(Failed) yet (including
    C(Idle)): submitting a new schedule here could race the upgrade backend's own duplicate-request
    guard. Not a failure — reported the same way as RV(skipped_devices) (counted in the "N
    device(s) skipped" summary), since the device's prior schedule is itself still progressing
    toward the same goal.
  type: list
  elements: str
  returned: when applicable
insync_devices:
  description: >-
    Device names that were polled for readiness and reached C(portalStatus=Ready) — the
    complement of RV(not_insync_devices) among the devices actually polled. For C(change_state),
    a subset of RV(configured_devices) polled after a V(activated)/V(staging)/V(maintenance)
    change with O(verify_for_insync) enabled. For C(schedule_upgrade)/C(rollback), a subset of
    RV(completed_devices) (schedule reached C(Success)) also polled because O(verify_for_insync)
    was enabled for that device. Neither RV(configured_devices) nor RV(completed_devices) alone
    distinguishes devices that reached Ready from ones that didn't, or from devices never polled
    at all (V(deactivated)/V(decommissioned) changes, O(verify_for_insync=false), or — for
    C(schedule_upgrade)/C(rollback) — a schedule that reached C(Failed)/timed out, or
    O(wait_for_completion=false)).
  type: list
  elements: str
  returned: when applicable
not_insync_devices:
  description: >-
    Device names that did not reach C(portalStatus=Ready) within the readiness poll timeout.
    Non-empty fails the task — the underlying change was still applied (C(change_state)'s state
    change, or C(schedule_upgrade)/C(rollback)'s already-C(Success) schedule; see
    RV(configured_devices)/RV(completed_devices)). Set O(verify_for_insync=false) to skip the
    poll and this check entirely.
  type: list
  elements: str
  returned: when applicable
completed_devices:
  description: >-
    For C(schedule_upgrade) / C(rollback), device names (a subset of RV(configured_devices))
    whose C(upgradeSummary.schedule.state) reached C(Success).
  type: list
  elements: str
  returned: when applicable
failed_devices:
  description: >-
    For C(schedule_upgrade) / C(rollback), device names whose C(upgradeSummary.schedule.state)
    reached C(Failed) (see the detailed logs for each device's C(failureReason)). Non-empty fails
    the task (the schedule/rollback itself was still applied; see RV(configured_devices)). Set
    O(wait_for_completion=false) to skip the poll and this check entirely.
  type: list
  elements: str
  returned: when applicable
in_progress_devices:
  description: >-
    For C(schedule_upgrade) / C(rollback), device names whose C(upgradeSummary.schedule.state)
    did not reach C(Success) or C(Failed) within the poll timeout — still in progress, not a
    failure (downloads/installs can take minutes). Use
    M(graphiant.naas.graphiant_device_lifecycle_info) in a follow-up task to keep watching these.
  type: list
  elements: str
  returned: when applicable
diff:
  description: Ansible C(--diff) payload (before/after) for C(change_state) and C(rollback).
  type: dict
  returned: when playbook uses C(--diff) and at least one device would change
details:
  description: Raw manager result payload.
  type: dict
  returned: always
"""

from typing import Any, Dict  # noqa: E402

from ansible.module_utils.basic import AnsibleModule  # noqa: E402

from ansible_collections.graphiant.naas.plugins.module_utils.graphiant_utils import (  # noqa: E402
    graphiant_portal_auth_argument_spec,
    get_graphiant_connection,
    handle_graphiant_exception,
)
from ansible_collections.graphiant.naas.plugins.module_utils.libs.device_config_common import (  # noqa: E402
    apply_module_diff,
)
from ansible_collections.graphiant.naas.plugins.module_utils.logging_decorator import (  # noqa: E402
    capture_library_logs,
)


@capture_library_logs
def execute_with_logging(module, func, *args, **kwargs):
    success_msg = kwargs.pop("success_msg", "Operation completed successfully")
    no_change_msg = kwargs.pop("no_change_msg", "No changes needed")
    result = func(*args, **kwargs)
    if isinstance(result, dict) and "changed" in result:
        changed = bool(result.get("changed"))
        msg = success_msg if changed else no_change_msg
        skipped = (
            (result.get("skipped_devices") or [])
            + (result.get("not_connected_devices") or [])
            + (result.get("schedule_in_progress_devices") or [])
        )
        if not changed and skipped:
            # Generic across operations: change_state skips devices already in the desired
            # lifecycle_state, rollback skips devices with no lastRunningVersion to roll back to,
            # schedule_upgrade also skips devices with no portal connectivity to schedule to
            # (not_connected_devices); both schedule_upgrade and rollback also skip devices with a
            # schedule already in progress (schedule_in_progress_devices) — "skipped" covers all of
            # these without claiming a specific reason the caller's own no_change_msg didn't
            # already state.
            msg += f" ({len(skipped)} device(s) skipped)"
        return {"changed": changed, "result_msg": msg, "details": result}
    return {"changed": True, "result_msg": success_msg, "details": result}


def main():
    argument_spec = dict(
        **graphiant_portal_auth_argument_spec(),
        operation=dict(
            type="str",
            required=True,
            choices=["change_state", "schedule_upgrade", "rollback"],
        ),
        config_file=dict(type="str", required=False, default=None),
        device=dict(type="str", required=False, default=None),
        lifecycle_state=dict(
            type="str",
            required=False,
            default=None,
            choices=["activated", "staging", "maintenance", "deactivated", "decommissioned"],
        ),
        release=dict(type="str", required=False, default=None, choices=["Stable", "Recommended", "Latest", "Custom"]),
        upgrade_action=dict(
            type="str", required=False, default=None, choices=["InstallActivate", "Install", "Activate"]
        ),
        ts=dict(type="dict", required=False, default=None),
        verify_for_insync=dict(type="bool", required=False, default=None),
        wait_for_completion=dict(type="bool", required=False, default=None),
        state=dict(type="str", required=False, default="present", choices=["present"]),
        detailed_logs=dict(type="bool", required=False, default=False),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)
    # After each module.exit_json() / module.fail_json() below, an explicit return is used so that
    # when the module is unit-tested with a MagicMock (which does not call sys.exit()), control flow
    # does not fall through. In a real Ansible process, exit_json/fail_json terminate the module;
    # the return is unreachable and does not change runtime behavior.

    params = module.params
    operation = params.get("operation")
    cfg_file = params.get("config_file")
    device = (params.get("device") or "").strip()

    if not cfg_file and not device:
        module.fail_json(
            msg="Provide config_file and/or device (portal device name).",
            operation=operation,
        )
        return

    try:
        connection = get_graphiant_connection(params, check_mode=module.check_mode)
        graphiant_config = connection.graphiant_config
        manager = graphiant_config.device_lifecycle

        if operation not in ("change_state", "schedule_upgrade", "rollback"):
            module.fail_json(
                msg=(
                    f"Provide operation (module param); got {operation!r}. Choices: "
                    "change_state, schedule_upgrade, rollback."
                ),
                operation=operation,
            )
            return

        module_params: Dict[str, Any] = {"device": device or None}
        if operation == "change_state":
            module_params["lifecycle_state"] = params.get("lifecycle_state")
        elif operation in ("schedule_upgrade", "rollback"):
            module_params["release"] = params.get("release")

        if operation == "change_state":
            if module.check_mode:
                cs_success_msg = "[check_mode] Would change device lifecycle state (no changes applied)"
                cs_no_change_msg = "[check_mode] Device(s) already in the desired lifecycle state; no changes needed"
            else:
                cs_success_msg = "Successfully changed device lifecycle state"
                cs_no_change_msg = "Device(s) already in the desired lifecycle state; no changes needed"
            result = execute_with_logging(
                module,
                manager.change_state,
                config_yaml_file=cfg_file,
                module_params=module_params,
                verify_for_insync=params.get("verify_for_insync"),
                success_msg=cs_success_msg,
                no_change_msg=cs_no_change_msg,
            )
            details = result.get("details") or {}
            if details.get("no_input"):
                module.exit_json(
                    changed=False,
                    msg="No device_lifecycle entries in YAML; nothing to do.",
                    operation=operation,
                    details=details,
                )
                return
            not_insync_devices = details.get("not_insync_devices", [])
            insync_devices = details.get("insync_devices", [])
            msg = result["result_msg"]
            if not_insync_devices:
                # The state change itself was applied (see configured_devices); portalStatus
                # never reached Ready within the poll timeout though, and that's required, not
                # informational — fail so a playbook doesn't treat this run as fully successful.
                # Replace (not append to) the success summary so the top-level msg doesn't read
                # as "Successfully changed..." while the task is actually failing; splitting on
                # capture_library_logs' "Detailed logs:" marker keeps that suffix intact and
                # readable after the (now accurate) summary, instead of tacking the failure note
                # on at the very end, after a potentially long detailed-logs dump.
                marker = "\n\nDetailed logs:\n"
                logs_suffix = msg[msg.index(marker) :] if marker in msg else ""  # noqa: E203
                insync_note = f"; reached Ready: {', '.join(insync_devices)}" if insync_devices else ""
                msg = (
                    f"Device lifecycle state changed, but {len(not_insync_devices)} device(s) did "
                    f"not reach Ready: {', '.join(not_insync_devices)}{insync_note} (see "
                    f"configured_devices for what was actually applied){logs_suffix}"
                )
            exit_payload = dict(
                changed=result["changed"],
                msg=msg,
                operation=operation,
                configured_devices=details.get("configured_devices", []),
                skipped_devices=details.get("skipped_devices", []),
                insync_devices=insync_devices,
                not_insync_devices=not_insync_devices,
                details=details,
            )
            apply_module_diff(module, exit_payload, details)
            if not_insync_devices:
                module.fail_json(**exit_payload)
                return
            module.exit_json(**exit_payload)
            return

        if operation == "schedule_upgrade":
            upgrade_action_label = params.get("upgrade_action") or "InstallActivate (default)"
            if module.check_mode:
                su_success_msg = (
                    f"[check_mode] Would schedule upgrade (action={upgrade_action_label}) (no changes applied)"
                )
                su_no_change_msg = "[check_mode] Device(s) already on the requested release; no changes needed"
            else:
                su_success_msg = f"Successfully scheduled upgrade (action={upgrade_action_label})"
                su_no_change_msg = "Device(s) already on the requested release; no changes needed"
            result = execute_with_logging(
                module,
                manager.schedule_upgrade,
                config_yaml_file=cfg_file,
                module_params=module_params,
                action=params.get("upgrade_action"),
                ts=params.get("ts"),
                wait_for_completion=params.get("wait_for_completion"),
                verify_for_insync=params.get("verify_for_insync"),
                success_msg=su_success_msg,
                no_change_msg=su_no_change_msg,
            )
            details = result.get("details") or {}
            if details.get("no_input"):
                module.exit_json(
                    changed=False,
                    msg="No device_lifecycle entries in YAML; nothing to do.",
                    operation=operation,
                    details=details,
                )
                return
            failed_devices = details.get("failed_devices", [])
            completed_devices = details.get("completed_devices", [])
            in_progress_devices = details.get("in_progress_devices", [])
            insync_devices = details.get("insync_devices", [])
            not_insync_devices = details.get("not_insync_devices", [])
            not_connected_devices = details.get("not_connected_devices", [])
            schedule_in_progress_devices = details.get("schedule_in_progress_devices", [])
            msg = result["result_msg"]
            if failed_devices or not_insync_devices or not_connected_devices:
                # Same convention as change_state's not_insync_devices: replace (not append to)
                # the success summary so msg doesn't read as "Successfully scheduled..." while
                # the task is actually failing; keep any detailed_logs suffix after the summary.
                # Unlike failed_devices/not_insync_devices (which only ever come from a device
                # that was actually scheduled, so changed is always true alongside them),
                # not_connected_devices can be the ONLY problem and apply to every device in the
                # batch (changed=false, nothing scheduled at all) — the lead sentence reflects
                # that instead of claiming "Upgrade scheduled" when nothing was.
                marker = "\n\nDetailed logs:\n"
                logs_suffix = msg[msg.index(marker) :] if marker in msg else ""  # noqa: E203
                completed_note = f"; completed: {', '.join(completed_devices)}" if completed_devices else ""
                in_progress_note = (
                    f"; still in progress: {', '.join(in_progress_devices)}" if in_progress_devices else ""
                )
                insync_note = f"; reached Ready: {', '.join(insync_devices)}" if insync_devices else ""
                problems = []
                if failed_devices:
                    problems.append(f"{len(failed_devices)} device(s) failed: {', '.join(failed_devices)}")
                if not_insync_devices:
                    problems.append(
                        f"{len(not_insync_devices)} device(s) completed but did not reach Ready: "
                        f"{', '.join(not_insync_devices)}"
                    )
                if not_connected_devices:
                    problems.append(
                        f"{len(not_connected_devices)} device(s) have no portal connectivity (not "
                        f"scheduled): {', '.join(not_connected_devices)}"
                    )
                lead = "Upgrade scheduled, but" if result["changed"] else "No devices were scheduled;"
                msg = (
                    f"{lead} {'; '.join(problems)}{completed_note}{in_progress_note}"
                    f"{insync_note} (see configured_devices for what was actually applied){logs_suffix}"
                )
            exit_payload = dict(
                changed=result["changed"],
                msg=msg,
                operation=operation,
                configured_devices=details.get("configured_devices", []),
                skipped_devices=details.get("skipped_devices", []),
                not_connected_devices=not_connected_devices,
                schedule_in_progress_devices=schedule_in_progress_devices,
                completed_devices=completed_devices,
                failed_devices=failed_devices,
                in_progress_devices=in_progress_devices,
                insync_devices=insync_devices,
                not_insync_devices=not_insync_devices,
                details=details,
            )
            apply_module_diff(module, exit_payload, details)
            if failed_devices or not_insync_devices or not_connected_devices:
                module.fail_json(**exit_payload)
                return
            module.exit_json(**exit_payload)
            return

        if operation == "rollback":
            if module.check_mode:
                rb_success_msg = "[check_mode] Would schedule rollback (no changes applied)"
                rb_no_change_msg = "[check_mode] Device(s) have no previous version to roll back to; no changes needed"
            else:
                rb_success_msg = "Successfully scheduled rollback"
                rb_no_change_msg = "Device(s) have no previous version to roll back to; no changes needed"
            result = execute_with_logging(
                module,
                manager.rollback,
                config_yaml_file=cfg_file,
                module_params=module_params,
                ts=params.get("ts"),
                wait_for_completion=params.get("wait_for_completion"),
                verify_for_insync=params.get("verify_for_insync"),
                success_msg=rb_success_msg,
                no_change_msg=rb_no_change_msg,
            )
            details = result.get("details") or {}
            if details.get("no_input"):
                module.exit_json(
                    changed=False,
                    msg="No device_lifecycle entries in YAML; nothing to do.",
                    operation=operation,
                    details=details,
                )
                return
            failed_devices = details.get("failed_devices", [])
            completed_devices = details.get("completed_devices", [])
            in_progress_devices = details.get("in_progress_devices", [])
            insync_devices = details.get("insync_devices", [])
            not_insync_devices = details.get("not_insync_devices", [])
            schedule_in_progress_devices = details.get("schedule_in_progress_devices", [])
            msg = result["result_msg"]
            if failed_devices or not_insync_devices:
                marker = "\n\nDetailed logs:\n"
                logs_suffix = msg[msg.index(marker) :] if marker in msg else ""  # noqa: E203
                completed_note = f"; completed: {', '.join(completed_devices)}" if completed_devices else ""
                in_progress_note = (
                    f"; still in progress: {', '.join(in_progress_devices)}" if in_progress_devices else ""
                )
                insync_note = f"; reached Ready: {', '.join(insync_devices)}" if insync_devices else ""
                problems = []
                if failed_devices:
                    problems.append(f"{len(failed_devices)} device(s) failed: {', '.join(failed_devices)}")
                if not_insync_devices:
                    problems.append(
                        f"{len(not_insync_devices)} device(s) completed but did not reach Ready: "
                        f"{', '.join(not_insync_devices)}"
                    )
                msg = (
                    f"Rollback scheduled, but {'; '.join(problems)}{completed_note}{in_progress_note}"
                    f"{insync_note} (see configured_devices for what was actually applied){logs_suffix}"
                )
            exit_payload = dict(
                changed=result["changed"],
                msg=msg,
                operation=operation,
                configured_devices=details.get("configured_devices", []),
                skipped_devices=details.get("skipped_devices", []),
                schedule_in_progress_devices=schedule_in_progress_devices,
                completed_devices=completed_devices,
                failed_devices=failed_devices,
                in_progress_devices=in_progress_devices,
                insync_devices=insync_devices,
                not_insync_devices=not_insync_devices,
                details=details,
            )
            apply_module_diff(module, exit_payload, details)
            if failed_devices or not_insync_devices:
                module.fail_json(**exit_payload)
                return
            module.exit_json(**exit_payload)
            return

        module.fail_json(msg=f"Unsupported operation: {operation}", operation=operation)
        return

    except Exception as e:
        error_msg = handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == "__main__":
    main()
