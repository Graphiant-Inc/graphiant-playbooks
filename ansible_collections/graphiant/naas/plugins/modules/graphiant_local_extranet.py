#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2025, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for managing Graphiant Local Extranet policies.

This module provides Local Extranet management capabilities including:
- Local Extranet policy creation, update, and deletion
- Automatic device rollout (apply) after create/update
"""

DOCUMENTATION = r"""
---
module: graphiant_local_extranet
short_description: Manage Graphiant Local Extranet policies
description:
  - Manages Local Extranet policies, which share a LAN segment (the provider/shared-service side)
    with other LAN segments (the consumer/branch side) across sites within the same enterprise.
  - Unlike M(graphiant.naas.graphiant_data_exchange) (cross-enterprise B2B peering), Local Extranet
    is single-tenant with no counterpart enterprise involved.
  - Supports creating, updating, and deleting policies. After a successful create or update, the
    policy is automatically pushed to devices — there is no separate "apply" step.
version_added: "26.7.0"
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
notes:
  - "Configuration files support Jinja2 templating syntax for dynamic configuration generation."
  - "The module automatically resolves names to IDs for LAN segments, sites, and devices."
  - "All operations are idempotent and safe to run multiple times without creating duplicates."
  - "Check mode (C(--check)) is supported: config load, validation, and name-to-ID resolution run"
  - "normally, but write operations are skipped and payloads are logged with a C([check_mode]) prefix."
  - "Use M(graphiant.naas.graphiant_local_extranet_info) to query policy summaries and device status."
options:
  operation:
    description:
      - "The specific Local Extranet operation to perform."
      - >-
        V(create_policies)/V(update_policies): Create or update policies from a YAML config file
        containing an I(local_extranet_policies) list. Each policy needs a I(name), a
        I(sharedSegment) (the provider LAN segment being shared), and I(targetSegments) (the
        consumer LAN segments allowed to access it). Optional I(source)/I(branches) blocks scope
        the provider and consumer sides respectively, each supporting I(sites) and I(prefixSet).
      - >-
        I(prefixSet) restricts which subnets are advertised{{ ":" }} omit it to share/allow all
        prefixes, or provide I(entries) (each with an I(ipPrefix) and optional I(maskLower)/
        I(maskUpper)) to restrict shared prefixes to specific subnets.
      - >-
        Optional I(targetDevices) limits which devices a policy is pushed to (defaults to all
        applicable devices). V(update_policies) requires the policy to already exist and supports
        C(--check)/C(--diff) to preview changes.
      - "V(delete_policies): Delete Local Extranet policies from a YAML configuration file."
      - >-
        For query operations (policies_summary, policy_device_status, lan_segments_usage, nat_usage),
        use M(graphiant.naas.graphiant_local_extranet_info) instead.
    type: str
    choices:
      - create_policies
      - update_policies
      - delete_policies
    required: true
  state:
    description:
      - "The desired state of the Local Extranet policies."
      - "V(present): Maps to V(create_policies) when O(operation) not specified."
      - "V(absent): Maps to V(delete_policies) when O(operation) not specified."
    type: str
    choices:
      - present
      - absent
    default: present
  config_file:
    description:
      - Path to the YAML configuration file for the operation.
      - Required for V(create_policies), V(update_policies), and V(delete_policies) operations.
      - Can be an absolute path or relative path. Relative paths are resolved using the configured config_path.
      - Configuration files support Jinja2 templating syntax for dynamic generation.
      - File must contain I(local_extranet_policies) list.
    type: str
  detailed_logs:
    description:
      - Enable detailed logging output for troubleshooting and monitoring.
      - When enabled, provides comprehensive logs of all Local Extranet operations.
      - Logs are captured and included in the RV(msg) return value for display using M(ansible.builtin.debug) module.
    type: bool
    default: false

attributes:
  check_mode:
    description: >
      Supported. In check mode, no API writes are performed; payloads that would be sent
      are logged with a C([check_mode]) prefix.
    support: full

requirements:
  - python >= 3.7
  - graphiant-sdk >= 26.8.0
  - tabulate

seealso:
  - module: graphiant.naas.graphiant_global_config
    description: Configure global objects (LAN segments) required for Local Extranet
  - module: graphiant.naas.graphiant_sites
    description: Configure sites required for Local Extranet policies
  - module: graphiant.naas.graphiant_local_extranet_info
    description: Query Local Extranet policy summaries and device status
  - module: graphiant.naas.graphiant_data_exchange
    description: Manage cross-enterprise (B2B) Data Exchange services, customers, matches, and invitations

author:
  - Graphiant Team (@graphiant)

"""

EXAMPLES = r"""
- name: Create Local Extranet policies
  graphiant.naas.graphiant_local_extranet:
    operation: create_policies
    config_file: "sample_local_extranet_policies.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: create_result

- name: Display policy creation result
  ansible.builtin.debug:
    msg: "{{ create_result.msg }}"

- name: Preview Local Extranet policy updates (check + diff)
  graphiant.naas.graphiant_local_extranet:
    operation: update_policies
    config_file: "sample_local_extranet_policies_update.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: update_result
  # Run playbook with: ansible-playbook playbook.yml --check --diff

- name: Update Local Extranet policies
  graphiant.naas.graphiant_local_extranet:
    operation: update_policies
    config_file: "sample_local_extranet_policies_update.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: update_result

- name: Display policy update result
  ansible.builtin.debug:
    msg: "{{ update_result.msg }}"

- name: Delete Local Extranet policies
  graphiant.naas.graphiant_local_extranet:
    operation: delete_policies
    config_file: "sample_local_extranet_policies.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
"""

RETURN = r"""
msg:
  description:
    - Result message from the operation, including detailed logs when O(detailed_logs) is enabled.
  type: str
  returned: always
  sample: |
    Successfully created 1 Local Extranet policies

    Detailed logs:
    2025-11-19 23:08:05,315 - Graphiant_playbook - INFO - Creating policy 'le-policy-1'...
    2025-11-19 23:08:05,450 - Graphiant_playbook - INFO - Successfully created policy 'le-policy-1'
result_data:
  description:
    - Result data from the operation.
  type: dict
  returned: when applicable
  sample: {}
changed:
  description:
    - Whether the operation made changes to the system.
  type: bool
  returned: always
  sample: true
operation:
  description:
    - The operation that was performed.
    - One of V(create_policies), V(update_policies), or V(delete_policies).
  type: str
  returned: always
  sample: "create_policies"
config_file:
  description:
    - The configuration file used for the operation.
  type: str
  returned: when applicable
  sample: "sample_local_extranet_policies.yaml"
diff:
  description:
    - Ansible C(--diff) output showing before/after state for each changed item.
    - Returned for V(create_policies) and V(update_policies) when the playbook is run with C(--diff)
      and at least one item would change.
    - For new items, C(before) is empty and C(after) is the full target config.
    - For updates, C(before) shows current values and C(after) shows target values.
  type: dict
  returned: when playbook uses C(--diff) and V(create_policies) or V(update_policies) has changes
  sample:
    before: |
      === le-policy-1 (policy) ===
      {"source": {"prefixSet": {"entries": [{"ipPrefix": "10.1.1.0/24", "maskLower": 24, "maskUpper": 32}]}}}
    after: |
      === le-policy-1 (policy) ===
      {"source": {"prefixSet": {"entries": [{"ipPrefix": "10.1.1.0/24", "maskLower": 25, "maskUpper": 28}]}}}
"""

from ansible.module_utils.basic import AnsibleModule  # noqa: E402
from ansible_collections.graphiant.naas.plugins.module_utils.graphiant_utils import (  # noqa: E402
    graphiant_portal_auth_argument_spec,
    get_graphiant_connection,
    handle_graphiant_exception,
)
from ansible_collections.graphiant.naas.plugins.module_utils.libs.device_config_common import (  # noqa: E402
    apply_module_diff,
)
from ansible_collections.graphiant.naas.plugins.module_utils.logging_decorator import capture_library_logs  # noqa: E402


@capture_library_logs
def execute_with_logging(module, func, *args, **kwargs):
    """
    Execute a function with optional detailed logging.

    Args:
        module: Ansible module instance
        func: Function to execute
        *args: Arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function

    Returns:
        dict: Result with 'changed' and 'result_msg' keys
    """
    success_msg = kwargs.pop("success_msg", "Operation completed successfully")

    try:
        result = func(*args, **kwargs)
        if isinstance(result, dict) and "changed" in result:
            return {"changed": result["changed"], "result_msg": success_msg, "details": result}
        return {"changed": True, "result_msg": success_msg}
    except Exception as e:
        raise e


def main():
    """Main function for the Local Extranet module."""

    argument_spec = dict(
        **graphiant_portal_auth_argument_spec(),
        operation=dict(
            type="str",
            required=True,
            choices=["create_policies", "update_policies", "delete_policies"],
        ),
        state=dict(type="str", choices=["present", "absent"], default="present"),
        config_file=dict(type="str", required=False),
        detailed_logs=dict(type="bool", default=False),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
        mutually_exclusive=[("operation", "state")],
        required_one_of=[("operation", "state")],
    )

    params = module.params
    operation = params.get("operation")
    state = params.get("state")
    config_file = params.get("config_file")

    if not operation:
        if state == "present":
            operation = "create_policies"
        elif state == "absent":
            operation = "delete_policies"

    if operation in ["create_policies", "update_policies", "delete_policies"]:
        if not config_file:
            module.fail_json(msg=f"config_file parameter is required for operation '{operation}'")

    try:
        connection = get_graphiant_connection(params, check_mode=module.check_mode)
        graphiant_config = connection.graphiant_config

        changed = False
        result_msg = ""
        result_data = {}
        diff_plan = []

        if operation == "create_policies":
            result = execute_with_logging(
                module,
                graphiant_config.local_extranet.create_policies,
                config_file,
                success_msg=f"Successfully created Local Extranet policies from {config_file}",
                diff_mode=getattr(module, "_diff", False),
            )
            changed = result["changed"]
            result_msg = result["result_msg"]
            diff_plan = result.get("details", {}).get("diff_plan", [])

        elif operation == "update_policies":
            success_msg = f"Successfully updated Local Extranet policies from {config_file}"
            if module.check_mode:
                success_msg = (
                    f"Check mode: validated Local Extranet policy updates from {config_file} " "(API calls skipped)"
                )
            result = execute_with_logging(
                module,
                graphiant_config.local_extranet.update_policies,
                config_file,
                success_msg=success_msg,
            )
            changed = result["changed"]
            result_msg = result["result_msg"]
            diff_plan = result.get("details", {}).get("diff_plan", [])

        elif operation == "delete_policies":
            result = execute_with_logging(
                module,
                graphiant_config.local_extranet.delete_policies,
                config_file,
                success_msg=f"Successfully deleted Local Extranet policies from {config_file}",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        else:
            module.fail_json(
                msg=f"Unsupported operation: {operation}. "
                f"Supported operations are: create_policies, update_policies, delete_policies. "
                f"For query operations, use graphiant.naas.graphiant_local_extranet_info module."
            )

        exit_payload = dict(
            changed=changed,
            msg=result_msg,
            result_msg=result_msg,
            result_data=result_data,
            operation=operation or "unknown",
            config_file=config_file if config_file else None,
        )
        apply_module_diff(module, exit_payload, {"diff_plan": diff_plan})

        module.exit_json(**exit_payload)

    except Exception as e:
        error_msg = handle_graphiant_exception(e, operation or "unknown")
        module.fail_json(msg=error_msg, operation=operation or "unknown")


if __name__ == "__main__":
    main()
