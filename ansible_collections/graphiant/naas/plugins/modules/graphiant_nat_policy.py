#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for managing Graphiant device-level NAT policy objects under:
  edge.natPolicy.natRulesets
  edge.segments.<segment>.natRuleset (LAN segment association)
"""

DOCUMENTATION = r"""
---
module: graphiant_nat_policy
short_description: Manage device NAT policy rulesets and LAN segment attachments
description:
  - Configure or delete device-level NAT policy rulesets under C(edge.natPolicy.natRulesets).
  - Attach or detach a named ruleset on LAN segments under C(edge.segments.<name>.natRuleset.ruleset).
  - Reads a structured YAML config file and/or inline module params and builds the raw device-config payload.
  - >-
    The configure workflow applies rulesets (C(operation=configure)) and attaches them to LAN segments
    (C(operation=attach_to_lan_segments)). The deconfigure workflow clears segment references
    (C(operation=detach_from_lan_segments)) and deletes listed rulesets (C(operation=deconfigure)).
  - "Configure is idempotent: compares intended rulesets to existing device state and skips push when already matched."
  - "Deconfigure deletes only the rulesets listed in the YAML/params by setting C(ruleset: null) per ruleset key."
  - >-
    Under C(configure), set C(state: absent) on a ruleset entry to delete that ruleset (sends
    C(ruleset: null)), or set C(state: absent) on an individual rule to delete only that rule (sends
    C(rule: null)). Omitted C(state) means C(present).
  - >-
    Under C(attach_to_lan_segments), set C(state: absent) on a segment entry to detach that segment
    from its current NAT ruleset. Equivalent to running C(operation=detach_from_lan_segments) for
    that individual segment.
  - >-
    Safety check: deleting a ruleset that is still referenced by LAN segments raises an error.
    Detach the affected segments first using C(operation=detach_from_lan_segments) or
    C(operation=attach_to_lan_segments) with C(state: absent) on those segments, then delete the ruleset.
  - "Attach/detach operations compare each listed segment's ruleset reference to the device and skip when unchanged."
  - >-
    With C(ansible-playbook --check), writes are skipped but C(changed) reflects whether an apply would update
    at least one device. Use C(--diff) to preview C(details.diff_plan) and Ansible C(diff).
notes:
  - >-
    One YAML file may define both C(natRulesets) and C(segments). C(configure)/C(deconfigure) read
    C(natRulesets) only; C(attach_to_lan_segments)/C(detach_from_lan_segments) read C(segments) only.
    Run both steps for a full NAT policy lifecycle, or use the sample playbook tags C(configure) and
    C(deconfigure).
  - >-
    O(nat_policy_config_file) and O(device) are mutually complementary: either may be omitted, but at
    least one must be provided. When both are set, O(device) overrides that device's C(natRulesets) and
    C(segments) in the file with O(natRulesets) / O(segments) from module params.
  - "Configuration files support Jinja2 templating syntax for dynamic configuration generation."
  - >-
    Check mode (C(--check)) reads live device state, skips writes, sets C(changed) from whether an apply
    would update at least one device, and logs would-be payloads with a C([check_mode]) prefix when
    O(detailed_logs) is enabled. The segment attachment safety check and absent no-op pruning are skipped
    in check mode so that a full deconfigure workflow can be previewed with C(--check --diff) without
    running the real detach step first.
  - >-
    Diff mode (C(--diff)) adds Ansible C(diff) (C(before) / C(after) strings) and C(details.diff_plan).
    Ruleset entries list only changed rules under C(rules) (plus C(_meta) when ruleset metadata changes).
    Segment attach/detach diffs show per-segment ruleset references under C(segments).
  - >-
    Supported NAT rule types are C(OneToOne) and C(PAT). Each rule requires C(seq), C(type),
    C(originalSrcIpPrefix), and C(translatedSrcIpPrefix). C(name), C(originalDstIpPrefix),
    C(translatedDstIpPrefix), and C(advertisePreNatPrefixes) are optional.
    C(advertisePreNatPrefixes) defaults to C(false).
  - >-
    Deconfigure workflow ordering is enforced: a ruleset still attached to LAN segments cannot be deleted.
    Detach first using C(detach_from_lan_segments) or C(attach_to_lan_segments) with C(state: absent),
    then deconfigure.
version_added: "26.7.0"
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
options:
  nat_policy_config_file:
    description:
      - Path to the NAT policy YAML file.
      - Can be an absolute path or relative to the configured config_path.
      - Expected top-level key is C(natPolicyObject) (list of devices).
      - Each device may define C(natRulesets) and/or C(segments) in the same file.
      - C(configure)/C(deconfigure) use C(natRulesets); attach/detach operations use C(segments).
      - Optional when O(device) is set with at least O(natRulesets) or O(segments).
    type: str
    required: false
    aliases:
      - nat_policy_file
  device:
    description:
      - Portal device hostname for single-device or loop execution.
      - When combined with O(nat_policy_config_file), overrides that device's C(natRulesets) and/or
        C(segments) in the file with the values supplied via O(natRulesets) / O(segments).
      - Required when O(nat_policy_config_file) is omitted.
    type: str
  natRulesets:
    description:
      - >-
        NAT ruleset definitions for the device named by O(device) (C(configure) and C(deconfigure) operations).
      - >-
        Dict keyed by ruleset name. Each value is either a ruleset body dict (containing C(rules) list/dict
        and optional C(name)) or C({state: absent}) to delete that ruleset. Within a ruleset body, individual
        rules in the C(rules) list may include C(state: absent) to delete only that rule.
      - >-
        Deleting a ruleset that is still attached to LAN segments raises an error. Detach the segments first
        (C(detach_from_lan_segments) or C(attach_to_lan_segments) with C(state: absent)), then delete.
      - Ignored for C(attach_to_lan_segments) and C(detach_from_lan_segments) operations.
      - When combined with O(nat_policy_config_file) and O(device), overrides that device's ruleset map.
    type: dict
    aliases:
      - nat_rulesets
  segments:
    description:
      - >-
        LAN segment to NAT ruleset mapping for the device named by O(device)
        (C(attach_to_lan_segments) and C(detach_from_lan_segments) operations).
      - >-
        Dict keyed by segment name. For C(attach_to_lan_segments), each value may be one of:
        a ruleset name string, a dict with C(natRuleset) or C(ruleset) keys, or
        C({state: absent}) to detach that segment from its current ruleset reference.
        For C(detach_from_lan_segments), values are not used — all listed segments are detached.
      - When combined with O(nat_policy_config_file) and O(device), overrides that device's segments map.
    type: dict
  operation:
    description:
      - Specific operation to perform.
      - >-
        C(configure) creates/updates rulesets listed under C(natRulesets). Use C(state: absent) on a
        ruleset entry or an individual rule to delete only that object. Pair with C(attach_to_lan_segments)
        (or the playbook C(configure) tag) to attach rulesets to LAN segments.
      - >-
        C(deconfigure) deletes all listed rulesets by setting C(ruleset: null). A ruleset still attached
        to LAN segments raises an error — use C(detach_from_lan_segments) or C(attach_to_lan_segments)
        with C(state: absent) to detach first. Pair with the playbook C(deconfigure) tag to clear segment
        references before deleting.
      - >-
        C(attach_to_lan_segments) sets C(edge.segments.<segment>.natRuleset.ruleset) from the C(segments)
        map. Use C(state: absent) on a segment entry to detach that segment from its current ruleset.
      - C(detach_from_lan_segments) clears the ruleset reference on each segment listed under C(segments).
    type: str
    required: false
    choices: [ configure, deconfigure, attach_to_lan_segments, detach_from_lan_segments ]
  state:
    description:
      - Desired state for NAT policy rulesets.
      - C(present) maps to C(configure) when C(operation) is omitted.
      - C(absent) maps to C(deconfigure) when C(operation) is omitted.
    type: str
    required: false
    default: present
    choices: [ present, absent ]
  detailed_logs:
    description:
      - Enable detailed logging.
    type: bool
    default: false
attributes:
  check_mode:
    description: Supports check mode.
    support: full
    details: >
      In check mode, no configuration is pushed to devices, but the module still reads current
      device state to determine whether changes would be made. Payloads that would be pushed are
      logged with a C([check_mode]) prefix. The segment attachment safety check and absent no-op
      pruning are skipped in check mode so that a full deconfigure workflow (detach + deconfigure)
      can be previewed with C(--check --diff) without running the real detach step first.
  diff_mode:
    description: Supports Ansible's C(--diff) for pending NAT policy updates.
    support: full
    details: >
      When the playbook runs with C(--diff) and a device would change, the module returns a C(diff)
      dictionary (C(before) / C(after) strings). Structured entries are also in C(details.diff_plan).
      Ruleset diffs list only changed rules under C(rules) (plus C(_meta) when ruleset metadata changes).
requirements:
  - python >= 3.7
  - graphiant-sdk >= 25.12.1
author:
  - Graphiant Team (@graphiant)
"""

EXAMPLES = r"""
# =============================================================================
# CONFIGURE WORKFLOW: create/update rulesets, then attach to LAN segments
# =============================================================================

# Step 1 — configure NAT rulesets from a YAML file.
- name: Configure device-level NAT policy rulesets
  graphiant.naas.graphiant_nat_policy:
    operation: configure
    nat_policy_config_file: "sample_device_nat_policies.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

# Step 2 — attach rulesets to LAN segments (reads 'segments' key from the same YAML file).
- name: Attach NAT ruleset to LAN segments
  graphiant.naas.graphiant_nat_policy:
    operation: attach_to_lan_segments
    nat_policy_config_file: "sample_device_nat_policies.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

# =============================================================================
# DECONFIGURE WORKFLOW: detach from LAN segments first, then delete rulesets
#
# Order matters: deleting a ruleset that is still attached to LAN segments
# raises an error. Always detach before deconfiguring.
# =============================================================================

# Step 1 — detach each listed segment from its ruleset reference.
- name: Detach NAT ruleset from LAN segments
  graphiant.naas.graphiant_nat_policy:
    operation: detach_from_lan_segments
    nat_policy_config_file: "sample_device_nat_policies.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

# Step 2 — delete listed rulesets (raises error if any are still attached).
- name: Deconfigure device-level NAT policy rulesets
  graphiant.naas.graphiant_nat_policy:
    operation: deconfigure
    nat_policy_config_file: "sample_device_nat_policies.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

# =============================================================================
# STATE: ABSENT — delete a single ruleset or rule without deconfigure
# =============================================================================

# Delete one ruleset (state: absent on the ruleset entry under configure).
# Detach the segment first if it still references this ruleset.
- name: Delete a single NAT ruleset via state absent
  graphiant.naas.graphiant_nat_policy:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    operation: configure
    device: "edge-1-sdktest"
    natRulesets:
      NAT-Ruleset-1:
        state: absent

# Delete one rule within a ruleset (state: absent on the rule entry).
- name: Delete rule seq 20 from NAT-Ruleset-1
  graphiant.naas.graphiant_nat_policy:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    operation: configure
    device: "edge-1-sdktest"
    natRulesets:
      NAT-Ruleset-1:
        rules:
          - seq: 20
            state: absent

# =============================================================================
# STATE: ABSENT ON SEGMENTS — detach a segment via attach_to_lan_segments
# =============================================================================

# Detach a single segment from its ruleset using state: absent on that segment.
# Equivalent to detach_from_lan_segments for only that segment.
- name: Detach LAN-Segment-1 from its NAT ruleset (state absent)
  graphiant.naas.graphiant_nat_policy:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    operation: attach_to_lan_segments
    device: "edge-1-sdktest"
    segments:
      LAN-Segment-1:
        state: absent
      LAN-Segment-2: NAT-Ruleset-2   # attach/update another segment in the same call

# =============================================================================
# SINGLE DEVICE — inline module params (no YAML file required)
# =============================================================================

- name: Configure NAT rulesets on a single device
  graphiant.naas.graphiant_nat_policy:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    operation: configure
    device: "edge-1-sdktest"
    natRulesets:
      NAT-Ruleset-1:
        rules:
          - seq: 10
            type: OneToOne
            name: host-mapping
            originalSrcIpPrefix: 192.168.1.0/24
            translatedSrcIpPrefix: 10.0.1.0/24
          - seq: 20
            type: PAT
            originalSrcIpPrefix: 10.1.0.0/16
            translatedSrcIpPrefix: 203.0.113.1/32
            advertisePreNatPrefixes: true

- name: Attach NAT ruleset to LAN segments (module params)
  graphiant.naas.graphiant_nat_policy:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    operation: attach_to_lan_segments
    device: "edge-1-sdktest"
    segments:
      LAN-Segment-1: NAT-Ruleset-1

- name: Detach NAT ruleset from LAN segments (module params)
  graphiant.naas.graphiant_nat_policy:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    operation: detach_from_lan_segments
    device: "edge-1-sdktest"
    segments:
      LAN-Segment-1: NAT-Ruleset-1

- name: Deconfigure NAT rulesets on a single device (module params)
  graphiant.naas.graphiant_nat_policy:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    operation: deconfigure
    device: "edge-1-sdktest"
    natRulesets:
      NAT-Ruleset-1: {}

# =============================================================================
# LOOP — configure multiple devices
# =============================================================================

- name: Configure NAT rulesets on multiple devices
  graphiant.naas.graphiant_nat_policy:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    operation: configure
    device: "{{ item.device }}"
    natRulesets: "{{ item.natRulesets }}"
  loop:
    - device: edge-1-sdktest
      natRulesets:
        NAT-Ruleset-1:
          rules:
            - seq: 10
              type: OneToOne
              originalSrcIpPrefix: 192.168.1.0/24
              translatedSrcIpPrefix: 10.0.1.0/24
    - device: edge-2-sdktest
      natRulesets:
        NAT-Ruleset-2:
          rules:
            - seq: 10
              type: PAT
              originalSrcIpPrefix: 10.1.0.0/16
              translatedSrcIpPrefix: 203.0.113.1/32

# =============================================================================
# OVERRIDE — combine YAML file with inline params for one device
# =============================================================================

- name: Override NAT ruleset for one device from file
  graphiant.naas.graphiant_nat_policy:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    operation: configure
    nat_policy_config_file: "sample_device_nat_policies.yaml"
    device: "edge-1-sdktest"
    natRulesets:
      NAT-Ruleset-Override:
        rules:
          - seq: 10
            type: OneToOne
            originalSrcIpPrefix: 172.16.0.0/24
            translatedSrcIpPrefix: 10.0.2.0/24

# =============================================================================
# CHECK / DIFF MODE — preview changes without pushing
# =============================================================================

# Dry-run: reads live device state, skips writes, sets changed=true when changes
# would be made. The segment safety check and absent no-op pruning are skipped in
# check mode, so a full deconfigure workflow can be previewed without a prior detach.
- name: Preview NAT policy configure (dry run)
  graphiant.naas.graphiant_nat_policy:
    operation: configure
    nat_policy_config_file: "sample_device_nat_policies.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  check_mode: true
  register: nat_policy_preview

# Diff mode: shows before/after per device and branch.
# details.diff_plan[].before/after.natRulesets.<name>.rules.<seq> — changed rules only.
# details.diff_plan[].before/after.segments.<name> — segment ruleset reference.
- name: Preview NAT policy rule changes (diff mode)
  graphiant.naas.graphiant_nat_policy:
    operation: configure
    nat_policy_config_file: "sample_device_nat_policies.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
  diff: true
  register: nat_policy_diff
"""

RETURN = r"""
msg:
  description: Human-readable result message.
  type: str
  returned: always
changed:
  description:
    - Whether the operation pushed (or would push in check mode) config to at least one device.
    - In check mode (C(--check)), no configuration is pushed, but V(changed) is true when changes would be made.
  type: bool
  returned: always
operation:
  description: The operation that was performed.
  type: str
  returned: always
nat_policy_config_file:
  description: The NAT policy config file used for the operation, if one was provided.
  type: str
  returned: when provided
configured_devices:
  description: Device names where configuration was pushed (or would be pushed in check mode).
  type: list
  elements: str
  returned: always
skipped_devices:
  description: Device names skipped because the desired state already matched the device.
  type: list
  elements: str
  returned: always
details:
  description:
    - Raw manager result dict containing C(diff_plan), C(configured_devices), and C(skipped_devices).
    - >-
      C(diff_plan) is a list of per-device change entries. Each entry has C(device) (hostname),
      C(branch) (e.g. C(edge.natPolicy.natRulesets) or C(edge.segments)), and normalized
      C(before) / C(after) snapshots showing the state before and after the intended change.
      For ruleset branches, only changed rules appear under C(rules); ruleset-level metadata
      changes appear under C(_meta). For segment branches, each changed segment appears under
      C(segments) with its before/after ruleset reference.
  type: dict
  returned: always
diff:
  description:
    - Ansible diff output when the playbook runs with C(--diff) and at least one device would change.
    - Built from C(details.diff_plan) as formatted JSON C(before) / C(after) strings per device and branch.
    - C(before) shows the current device state; C(after) shows the intended state.
  type: dict
  returned: when diff mode is enabled and C(details.diff_plan) is non-empty
"""

from ansible.module_utils.basic import AnsibleModule  # noqa: E402

from ansible_collections.graphiant.naas.plugins.module_utils.graphiant_utils import (  # noqa: E402
    ansible_module_log,
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
    try:
        result = func(*args, **kwargs)
    except Exception as e:
        if module.params.get("detailed_logs"):
            name = getattr(func, "__name__", str(func))
            ansible_module_log(
                module,
                f"graphiant_nat_policy: manager {name!s} failed: {type(e).__name__}: {e!s}",
            )
        raise
    if isinstance(result, dict) and "changed" in result:
        changed = bool(result.get("changed"))
        configured = result.get("configured_devices") or []
        skipped = result.get("skipped_devices") or []
        msg = success_msg if changed else no_change_msg
        if not changed and skipped:
            msg += f" (skipped {len(skipped)} device(s))"
        return {
            "changed": changed,
            "result_msg": msg,
            "details": result,
            "configured_devices": configured,
            "skipped_devices": skipped,
        }
    return {"changed": True, "result_msg": success_msg, "details": result}


def main():
    argument_spec = dict(
        **graphiant_portal_auth_argument_spec(),
        nat_policy_config_file=dict(type="str", required=False, default=None, aliases=["nat_policy_file"]),
        device=dict(type="str", required=False, default=None),
        natRulesets=dict(type="dict", required=False, default=None, aliases=["nat_rulesets"]),
        segments=dict(type="dict", required=False, default=None),
        operation=dict(
            type="str",
            required=False,
            choices=["configure", "deconfigure", "attach_to_lan_segments", "detach_from_lan_segments"],
        ),
        state=dict(type="str", required=False, default="present", choices=["present", "absent"]),
        detailed_logs=dict(type="bool", required=False, default=False),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    params = module.params
    operation = params.get("operation")
    state = params.get("state", "present")
    cfg_file = params.get("nat_policy_config_file")
    device = (params.get("device") or "").strip() or None

    if not operation:
        operation = "configure" if state == "present" else "deconfigure"

    if not cfg_file and not device:
        module.fail_json(
            msg="Provide nat_policy_config_file and/or device (portal device name).",
            operation=operation,
        )
        return

    module_params = {"device": device}
    for key in ("natRulesets", "segments"):
        if params.get(key) is not None:
            module_params[key] = params[key]

    try:
        if params.get("detailed_logs"):
            ansible_module_log(
                module,
                (
                    f"graphiant_nat_policy: start operation={operation!r} "
                    f"nat_policy_config_file={cfg_file!r} device={device!r} "
                    f"check_mode={module.check_mode!r}"
                ),
            )
        connection = get_graphiant_connection(params, check_mode=module.check_mode)
        graphiant_config = connection.graphiant_config

        if operation == "configure":
            result = execute_with_logging(
                module,
                graphiant_config.nat_policy.configure,
                cfg_file,
                module_params=module_params,
                success_msg="Successfully configured device-level NAT policy rulesets",
                no_change_msg="Device-level NAT policy already matches desired state; no changes needed",
            )
        elif operation == "deconfigure":
            result = execute_with_logging(
                module,
                graphiant_config.nat_policy.deconfigure,
                cfg_file,
                module_params=module_params,
                success_msg="Successfully deconfigured device-level NAT policy rulesets",
                no_change_msg="Device-level NAT policy rulesets already absent; no changes needed",
            )
        elif operation == "attach_to_lan_segments":
            result = execute_with_logging(
                module,
                graphiant_config.nat_policy.attach_to_lan_segments,
                cfg_file,
                module_params=module_params,
                success_msg="Successfully attached NAT ruleset(s) to LAN segment(s)",
                no_change_msg="LAN segment NAT ruleset references already match desired state",
            )
        elif operation == "detach_from_lan_segments":
            result = execute_with_logging(
                module,
                graphiant_config.nat_policy.detach_from_lan_segments,
                cfg_file,
                module_params=module_params,
                success_msg="Successfully detached NAT ruleset(s) from LAN segment(s)",
                no_change_msg="LAN segment NAT ruleset references already cleared",
            )
        else:
            module.fail_json(
                msg=(
                    f"Unsupported operation '{operation}'. Supported operations: configure, deconfigure, "
                    f"attach_to_lan_segments, detach_from_lan_segments."
                ),
                operation=operation,
            )
            return

        if params.get("detailed_logs"):
            preview = result["result_msg"]
            if len(preview) > 200:
                preview = preview[:200] + "…"
            ansible_module_log(
                module,
                f"graphiant_nat_policy: success changed={result['changed']!r} result_msg_preview={preview!r}",
            )
        details = result.get("details") or {}
        exit_payload = dict(
            changed=result["changed"],
            msg=result["result_msg"],
            operation=operation,
            configured_devices=result.get("configured_devices", []),
            skipped_devices=result.get("skipped_devices", []),
            details=details,
        )
        if cfg_file:
            exit_payload["nat_policy_config_file"] = cfg_file
        apply_module_diff(module, exit_payload, details)
        module.exit_json(**exit_payload)

    except Exception as e:
        if module.params.get("detailed_logs"):
            import traceback

            ansible_module_log(
                module,
                f"graphiant_nat_policy: {type(e).__name__}: {e!s}\n{traceback.format_exc()}",
            )
        else:
            ansible_module_log(
                module,
                f"graphiant_nat_policy: failed {type(e).__name__}: {e!s}",
            )
        error_msg = handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == "__main__":
    main()
