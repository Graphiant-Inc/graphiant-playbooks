#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for querying Graphiant device lifecycle and software upgrade status.
"""

DOCUMENTATION = r"""
---
module: graphiant_device_lifecycle_info
short_description: Query device lifecycle state and software upgrade status
description:
  - >-
    Read-only query of C(GET /v1/edges-summary) (with C(upgradeSummary=true)); matches the
    portal's Maintain > Device Lifecycle page. Returns per-device C(status), C(portalStatus),
    and C(upgradeSummary) fields (running/last-running/ready-for-activation version, schedule
    state), plus C(lifecycle_state) (a friendly label for C(status): V(activated), V(staging),
    V(maintenance), or V(deactivated)).
  - >-
    With neither O(config_file) nor O(device) set, all devices matching O(role) are returned,
    and the task cannot fail on a missing device (there is no fixed target list to compare
    against). When O(device) or O(config_file)'s C(device_lifecycle) list names specific
    devices, the task fails if any of them are not found (returned in RV(failed_devices)), the
    same way a named M(graphiant.naas.graphiant_device_lifecycle) C(change_state) target that
    does not exist fails rather than being silently skipped.
  - >-
    Supply O(config_file) for a C(device_lifecycle) list (only the device names, i.e. the list
    keys, are used — other per-device fields in that file are ignored here), and/or O(device)
    to query a single device.
version_added: "26.10.0"
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
options:
  config_file:
    description:
      - >-
        Path to YAML with a top-level C(device_lifecycle) list (only the device names, i.e. the
        list keys, are used); optional if O(device) is set instead, or to list every device.
      - Relative paths resolve using the collection config path (see C(GRAPHIANT_CONFIGS_PATH)).
      - >-
        The file may also set a top-level C(role) key (same as the O(role) option); O(role) on
        the task always overrides the file's value.
    type: str
    required: false
  device:
    description:
      - Portal device name to query. With O(config_file), optional override for this one device.
      - Omit along with O(config_file) to query all devices matching O(role).
    type: str
    required: false
  role:
    description:
      - >-
        Client-side device role filter (e.g. V(cpe), V(gateway)) used only when neither
        O(config_file) nor O(device) is set.
      - >-
        If not set here, taken from a top-level C(role) key in O(config_file) when present, else
        all devices are returned (no filter). The portal's own Device Lifecycle page always
        sends C(filter[role]=UnknownDeviceRole) regardless of the actual devices shown — the API
        has no server-side role filter to apply, so that value has no effect there either; it is
        not a real device role and filtering on it here would incorrectly match no devices.
    type: str
    required: false
    default: null
  detailed_logs:
    description: >-
      Enable detailed logging in the task result message. When C(tabulate) is installed, this
      also logs a table of the reported devices (Device ID, Host Name, Lifecycle State, Portal
      Sync, Release, Release Name, Software Version, Upgrade Status, Rollout Name, Site,
      Connected Region, Location) and the enterprise the connection resolved to — useful for
      diagnosing an empty or unexpected result (e.g. credentials resolving to the wrong
      enterprise). C(Portal Sync) is the raw C(portalStatus) (e.g. C(Ready), C(Configuring),
      C(ModeChanged)) — the same status M(graphiant.naas.graphiant_device_lifecycle)'s
      C(change_state) polls for after a mutation. C(Software Version) is the device's own
      C(swVersion). C(Release) and C(Release Name) are resolved
      from multiple sources, in order, since any single one of them is frequently empty for a
      given device: for C(Release) — a C(GET /v1/software/releases/summary) catalog lookup by
      C(swVersion), then C(upgradeSummary.runningVersion.release); for C(Release Name) — the
      device's own C(swName), then that same catalog lookup, then
      C(upgradeSummary.runningVersion.name). All can legitimately end up empty for an
      unlisted/superseded build that was never given a friendly name.
    type: bool
    default: false

attributes:
  check_mode:
    description: Always read-only; check mode has no side effects.
    support: full
requirements:
  - python >= 3.7
  - graphiant-sdk >= 26.10.0
  - tabulate (optional; logs a tabulated device table with C(detailed_logs=true) when installed)
seealso:
  - module: graphiant.naas.graphiant_device_lifecycle
    description: Change device lifecycle state, schedule/roll back software upgrades.
author:
  - Graphiant Team (@graphiant)
"""

EXAMPLES = r"""
- name: Get upgrade/lifecycle status for all cpe devices
  graphiant.naas.graphiant_device_lifecycle_info:
    role: "cpe"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
  register: status_result

- name: Show status
  ansible.builtin.debug:
    var: status_result.devices

- name: Get status for a single device
  graphiant.naas.graphiant_device_lifecycle_info:
    device: "edge-1-sdktest"
    detailed_logs: true
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Get status for the devices listed in a config file
  graphiant.naas.graphiant_device_lifecycle_info:
    config_file: "sample_device_lifecycle.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
"""

RETURN = r"""
msg:
  description: Result message, including detailed logs when O(detailed_logs) is enabled.
  type: str
  returned: always
changed:
  description: Always C(false) (read-only).
  type: bool
  returned: always
devices:
  description: Per-device status, keyed by device name.
  type: dict
  returned: always
  contains:
    device_id:
      description: Portal device ID.
      type: int
    status:
      description: Raw portal status (e.g. C(active), C(inactive), C(staging), C(maintenance)).
      type: str
    lifecycle_state:
      description: Friendly label for C(status) (V(activated)/V(staging)/V(maintenance)/V(deactivated)).
      type: str
    portal_status:
      description: Portal sync status (e.g. C(Ready)).
      type: str
    sw_name:
      description: Software release name (e.g. C(26.6.3)).
      type: str
    sw_version:
      description: Software build version string.
      type: str
    site:
      description: Portal site name.
      type: str
    connected_regions:
      description: Regions the device has tunnel-terminator connections to.
      type: list
      elements: str
    location:
      description: Discovered location (city/state/country) as a single string.
      type: str
    upgrade_status:
      description: C(upgradeSummary.status) (e.g. C(UpToDate), C(UpgradeAvailable)).
      type: str
    rollout_name:
      description: C(upgradeSummary.rolloutName), when the device is part of a rollout.
      type: str
    running_version:
      description: C(upgradeSummary.runningVersion) (C(release)/C(version)/C(name)).
      type: dict
    last_running_version:
      description: C(upgradeSummary.lastRunningVersion).
      type: dict
    ready_for_activation_version:
      description: C(upgradeSummary.readyForActivationVersion), when a download is complete but not yet activated.
      type: dict
    schedule:
      description: C(upgradeSummary.schedule) (action/state/download progress/failure reason/target version).
      type: dict
failed_devices:
  description: >-
    Devices that could not be found. Only possible when specific devices were requested via
    O(device) or O(config_file); non-empty fails the task.
  type: list
  elements: dict
  returned: always
  contains:
    device_name:
      description: The device name that could not be found.
      type: str
    error:
      description: Error detail explaining the lookup failure.
      type: str
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
from ansible_collections.graphiant.naas.plugins.module_utils.logging_decorator import (  # noqa: E402
    capture_library_logs,
)


@capture_library_logs
def execute_with_logging(module, func, *args, **kwargs):
    success_msg = kwargs.pop("success_msg", "Query completed successfully")
    result = func(*args, **kwargs)
    return {"result_msg": success_msg, "details": result}


def main():
    argument_spec = dict(
        **graphiant_portal_auth_argument_spec(),
        config_file=dict(type="str", required=False, default=None),
        device=dict(type="str", required=False, default=None),
        role=dict(type="str", required=False, default=None),
        detailed_logs=dict(type="bool", required=False, default=False),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)
    # After each module.exit_json() / module.fail_json() below, an explicit return is used so that
    # when the module is unit-tested with a MagicMock (which does not call sys.exit()), control flow
    # does not fall through. In a real Ansible process, exit_json/fail_json terminate the module;
    # the return is unreachable and does not change runtime behavior.

    params = module.params
    cfg_file = params.get("config_file")
    device = (params.get("device") or "").strip()
    module_params: Dict[str, Any] = {"device": device or None}

    try:
        connection = get_graphiant_connection(params, check_mode=module.check_mode)
        graphiant_config = connection.graphiant_config
        manager = graphiant_config.device_lifecycle

        result = execute_with_logging(
            module,
            manager.get_status,
            config_yaml_file=cfg_file,
            module_params=module_params,
            role=params.get("role"),
            success_msg="Retrieved device lifecycle/upgrade status",
        )
        details = result.get("details") or {}
        devices = details.get("devices", {})
        failed = details.get("failed_devices", [])
        msg = f"Retrieved status for {len(devices)} device(s)"
        if failed:
            msg += f"; {len(failed)} device(s) not found"
        # capture_library_logs appends "Detailed logs:" onto result_msg (success_msg here) when
        # detailed_logs=true; keep that suffix on the recomputed device/failed-count summary.
        logged = result.get("result_msg") or ""
        marker = "\n\nDetailed logs:\n"
        if marker in logged:
            marker_idx = logged.index(marker)
            msg += logged[marker_idx:]

        result_payload = dict(changed=False, msg=msg, devices=devices, failed_devices=failed, details=details)
        if failed:
            # failed_devices is only ever non-empty when specific devices were requested (by
            # device or config_file device_lifecycle list) — listing every device with a role
            # filter or no filter can never produce one, since the reported names are built from
            # what was actually found in that case. A named target you asked about not existing
            # is a real failure, not just informational.
            module.fail_json(**result_payload)
            return
        module.exit_json(**result_payload)
        return

    except Exception as e:
        error_msg = handle_graphiant_exception(e, "get_status")
        module.fail_json(msg=error_msg)


if __name__ == "__main__":
    main()
