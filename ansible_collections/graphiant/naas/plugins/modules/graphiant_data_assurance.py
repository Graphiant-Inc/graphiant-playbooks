#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for managing Graphiant Data Assurance policies via the portal API:
  POST/PUT/DELETE /v1/data/assurance/assurances/global
"""

DOCUMENTATION = r"""
---
module: graphiant_data_assurance
short_description: Manage Graphiant Data Assurance policies
description:
  - Create, update, or delete Graphiant Data Assurance policies via the portal API.
  - Reads a structured YAML config file and applies the desired state to the Graphiant portal.
  - >-
    Both assurance policies (with C(flexAlgo)) and block-by-URL/app policies (without
    C(flexAlgo)) are entries in the C(DataAssurancePolicies) list and are sent to the
    C(/v1/data/assurance/assurances/global) endpoint.
  - >-
    Block-by-category policies are entries in the C(ContentFilterPolicies) list and are sent to
    the C(/v1/global/content-filters) endpoint. Each blocks one or more domain C(categories)
    (by name, resolved to a domain category ID) with an optional C(allowedUrlList) ("Allowed URL
    List") applied as per-category exception wildcards. Both lists are managed by the same module
    and operations from a single config file.
  - "Configure is idempotent: compares the intended config against live portal state and"
  - "skips the update when already matched."
  - "Deconfigure is idempotent: policies not found are silently skipped."
  - >-
    Deleting a policy is a two-step flow: the portal requires a policy to be unassigned from all
    sites before deletion, so the module first updates it to a detached config (no sites, empty
    apps/rules) and then deletes it.
  - >-
    With C(ansible-playbook --check), writes are skipped but C(changed) reflects whether
    an apply would modify at least one policy. Use C(--diff) to preview C(details.diff_plan).
notes:
  - >-
    Site scoping: use C(useAllSites: true) to apply a policy to all enterprise sites, or
    C(siteListName: "<name>") to scope it to a named site list. The module resolves the
    name to the portal site list ID and raises an error if it is not found.
  - >-
    C(flexAlgo) is the flex-algo name that defines the SLA metric for path selection
    (e.g. C(test-all-cores), C(hestia-all-cores)). Use
    V(/v1/data/assurance/flex-algos) to list available values. Omit for block/protection
    policies. When specified, the name is validated against the flex-algos that exist in
    the enterprise; the module fails with an error listing the available values if it is
    not found.
  - >-
    C(lanNames) is a list of LAN segment names (strings) that scope which segments
    the assurance policy applies to. Omit or leave empty to apply to all LAN segments.
    When specified, each name is validated against the LAN segments that exist in the
    enterprise; the module fails with an error listing the available values if any is
    not found.
  - >-
    Under C(apps), each entry represents one application to assure or block. Use
    C(profileName) (human-readable string such as V(Graphiant_Assured) or V(Threat_Blocked))
    to specify the assurance profile — the module resolves it to the corresponding integer
    C(bucketId). Use C(builtinAppId) (Graphiant built-in application ID) or C(customAppId)
    (enterprise custom application ID) to identify the application. C(useAllServers) (bool)
    and C(servers) (list of C({ip, port, protocol})) further scope to specific back-end servers.
  - >-
    App name validation and auto-fill: for each app the module looks up the app C(name) in its
    profile's bucket (bucket-apps API, keyed by C(profileName)/C(bucketId) over a ~30-day
    window). It validates the C(name) exists in that bucket and auto-fills C(isDomain),
    C(builtinAppId), and C(customAppId) from the matched bucket app when they are not provided
    (values you supply always take precedence). It also auto-fills C(servers)
    (C({ip, port, protocol})) from the bucket-app-servers telemetry when you do not provide any.
    If the bucket returns no apps for the window, the module fails with an error since the app
    name cannot be validated.
  - >-
    Validation and telemetry auto-fill apply to new apps. When updating an existing policy, an
    app already present in it reuses its currently stored servers/hints for any field you did not
    set, and the telemetry lookup is skipped — so re-running C(configure) with an unchanged config
    stays idempotent even though telemetry is time-windowed and can drift.
version_added: "26.8.0"
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
options:
  data_assurance_config_file:
    description:
      - Path to the Data Assurance YAML config file.
      - Can be an absolute path or relative to the configured config_path.
      - >-
        Supported top-level keys are C(DataAssurancePolicies) (assurance and block-by-URL/app
        policies) and C(ContentFilterPolicies) (block-by-category policies). Both are optional
        lists; either or both may be present.
      - >-
        Each C(DataAssurancePolicies) entry is either an assurance policy (includes C(flexAlgo))
        or a block/protection policy (omits C(flexAlgo)), sent to the assurances endpoint. Each
        C(ContentFilterPolicies) entry blocks domain C(categories) and is sent to the
        content-filters endpoint.
      - Each entry must have at minimum a C(name) field.
      - Configuration files support Jinja2 templating syntax.
    type: str
    required: true
  operation:
    description:
      - Specific operation to perform.
      - C(configure) creates or updates policies listed under C(DataAssurancePolicies).
        Idempotent — skips policies whose live config already matches the desired state.
      - >-
        C(deconfigure) deletes listed policies (detaches sites and clears apps/rules via an
        update, then deletes). Idempotent — skips policies not found.
    type: str
    required: false
    choices: [ configure, deconfigure ]
  state:
    description:
      - Desired state for Data Assurance policies.
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
      In check mode, no writes are sent to the portal, but the module still reads current
      policy state to determine whether changes would be made. Payloads that would be sent
      are logged with a C([check_mode]) prefix when O(detailed_logs) is enabled.
  diff_mode:
    description: Supports Ansible's C(--diff) for pending Data Assurance policy updates.
    support: full
    details: >
      When run with C(--diff) and at least one policy would change, the module returns a
      C(diff) dictionary (C(before) / C(after) strings). Structured entries are also in
      C(details.diff_plan), each with C(policy), C(action), C(before), and C(after).
requirements:
  - python >= 3.7
  - graphiant-sdk >= 26.8.0
author:
  - Graphiant Team (@graphiant)
"""

EXAMPLES = r"""
# Configure Data Assurance policies from a YAML file.
- name: Configure Data Assurance policies
  graphiant.naas.graphiant_data_assurance:
    operation: configure
    data_assurance_config_file: "sample_data_assurance_policies.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: da_result
  no_log: true

# Deconfigure (delete) Data Assurance policies.
- name: Deconfigure Data Assurance policies
  graphiant.naas.graphiant_data_assurance:
    operation: deconfigure
    data_assurance_config_file: "sample_data_assurance_policies.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  no_log: true

# Preview changes without pushing (check mode).
- name: Preview Data Assurance configure (dry run)
  graphiant.naas.graphiant_data_assurance:
    operation: configure
    data_assurance_config_file: "sample_data_assurance_policies.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
  check_mode: true
  register: da_preview

# Preview per-policy diffs (run playbook with --diff or set diff: true on the task).
- name: Preview Data Assurance policy changes
  graphiant.naas.graphiant_data_assurance:
    operation: configure
    data_assurance_config_file: "sample_data_assurance_policies.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
  diff: true
  register: da_diff
"""

RETURN = r"""
msg:
  description: Result message (includes detailed logs when enabled).
  type: str
  returned: always
changed:
  description:
    - Whether the operation modified at least one policy.
    - In check mode (C(--check)), no writes are sent, but V(changed) reflects whether
      changes would be made.
  type: bool
  returned: always
operation:
  description: The operation performed.
  type: str
  returned: always
data_assurance_config_file:
  description: The config file used for the operation.
  type: str
  returned: always
configured:
  description: Policy names that were created or updated (when changed=true).
  type: list
  elements: str
  returned: when supported
skipped_policies:
  description: Policy names that were skipped because desired state already matched.
  type: list
  elements: str
  returned: when supported
deleted:
  description: Policy names that were deleted (when deconfigure and changed=true).
  type: list
  elements: str
  returned: when supported
details:
  description:
    - Raw manager result details (includes C(diff_plan), configured/skipped/deleted lists).
    - Each C(diff_plan) entry has C(policy), C(action) (create/update), C(before), and
      C(after) normalized config snapshots.
  type: dict
  returned: when supported
diff:
  description:
    - Ansible diff output when run with C(--diff) and at least one policy would change.
    - Built from C(details.diff_plan) as JSON C(before) / C(after) strings per policy.
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
                f"graphiant_data_assurance: manager {name!s} failed: {type(e).__name__}: {e!s}",
            )
        raise
    if isinstance(result, dict) and "changed" in result:
        changed = bool(result.get("changed"))
        configured = result.get("configured") or []
        skipped = result.get("skipped") or []
        deleted = result.get("deleted") or []
        msg = success_msg if changed else no_change_msg
        if not changed and skipped:
            msg += f" (skipped {len(skipped)} polic{'y' if len(skipped) == 1 else 'ies'})"
        return {
            "changed": changed,
            "result_msg": msg,
            "details": result,
            "configured": configured,
            "skipped": skipped,
            "deleted": deleted,
        }
    return {"changed": True, "result_msg": success_msg, "details": result}


def main():
    argument_spec = dict(
        **graphiant_portal_auth_argument_spec(),
        data_assurance_config_file=dict(type="str", required=True),
        operation=dict(
            type="str",
            required=False,
            choices=["configure", "deconfigure"],
        ),
        state=dict(type="str", required=False, default="present", choices=["present", "absent"]),
        detailed_logs=dict(type="bool", required=False, default=False),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    params = module.params
    operation = params.get("operation")
    state = params.get("state", "present")
    cfg_file = params["data_assurance_config_file"]

    if not operation:
        operation = "configure" if state == "present" else "deconfigure"

    try:
        if params.get("detailed_logs"):
            ansible_module_log(
                module,
                (
                    f"graphiant_data_assurance: start operation={operation!r} "
                    f"data_assurance_config_file={cfg_file!r} check_mode={module.check_mode!r}"
                ),
            )
        connection = get_graphiant_connection(params, check_mode=module.check_mode)
        graphiant_config = connection.graphiant_config
        if params.get("detailed_logs"):
            ansible_module_log(
                module,
                "graphiant_data_assurance: GraphiantConfig obtained; dispatching to data assurance manager",
            )

        if operation == "configure":
            result = execute_with_logging(
                module,
                graphiant_config.data_assurance.configure,
                cfg_file,
                success_msg="Successfully configured Data Assurance policies",
                no_change_msg="Data Assurance policies already match desired state; no changes needed",
            )
        elif operation == "deconfigure":
            result = execute_with_logging(
                module,
                graphiant_config.data_assurance.deconfigure,
                cfg_file,
                success_msg="Successfully deconfigured Data Assurance policies",
                no_change_msg="Data Assurance policies already absent; no changes needed",
            )
        else:
            module.fail_json(
                msg=f"Unsupported operation '{operation}'. Supported operations: configure, deconfigure.",
                operation=operation,
            )
            return

        changed = result["changed"]
        result_msg = result["result_msg"]

        if params.get("detailed_logs"):
            preview = result_msg if len(result_msg) <= 200 else (result_msg[:200] + "…")
            ansible_module_log(
                module,
                f"graphiant_data_assurance: success changed={changed!r} result_msg_preview={preview!r}",
            )

        details = result.get("details") or {}
        exit_payload = dict(
            changed=changed,
            msg=result_msg,
            operation=operation,
            data_assurance_config_file=cfg_file,
            configured=result.get("configured", []),
            skipped_policies=result.get("skipped", []),
            deleted=result.get("deleted", []),
            details=details,
        )
        apply_module_diff(module, exit_payload, details)
        module.exit_json(**exit_payload)

    except Exception as e:
        if module.params.get("detailed_logs"):
            import traceback

            ansible_module_log(
                module,
                f"graphiant_data_assurance: {type(e).__name__}: {e!s}\n{traceback.format_exc()}",
            )
        else:
            ansible_module_log(
                module,
                f"graphiant_data_assurance: failed {type(e).__name__}: {e!s}",
            )
        error_msg = handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == "__main__":
    main()
