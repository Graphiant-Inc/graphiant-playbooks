#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2025, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for managing Graphiant BGP peering, routing policies, and route aggregations.

This module provides BGP management capabilities including:
- BGP peering configuration and deconfiguration
- BGP route aggregation configuration and deconfiguration
- Policy attachment and detachment
- Routing policy management
"""

DOCUMENTATION = r"""
---
module: graphiant_bgp
short_description: Manage Graphiant BGP peering, routing policies, and route aggregations
description:
  - This module provides comprehensive BGP peering and routing policy management for Graphiant Edge devices.
  - Supports BGP peering neighbor configuration and deconfiguration.
  - Enables attachment and detachment of global BGP routing policies (filters) to BGP peers.
  - Supports BGP route aggregation configuration per LAN segment.
  - Neighbors and aggregations are independent — a segment can define either or both.
  - Supports enabling/disabling eBGP multipath per LAN segment via a segment C(ebgpMultipath) field.
  - Configuration files support Jinja2 templating for dynamic generation.
version_added: "25.12.0"
notes:
  - "BGP Operations:"
  - "  - Configure (state: present): Create BGP peering neighbors, route aggregations, and attach routing policies."
  - "  - Deconfigure (state: absent): Remove BGP peering neighbors and route aggregations. Policies are detached."
  - "  - Detach Policies: Detach global BGP routing policies from BGP peers without removing the peers or aggregations."
  - "Per-entry removal: within V(configure), an individual neighbor or aggregation marked with"
  - "  C(state: absent) in the config file is removed while all other entries are configured normally,"
  - "  so a single peer/aggregation can be deleted without a full deconfigure."
  - "Per-policy detach: within V(configure), set a neighbor filter field"
  - "  (C(ipv4InboundFilter), C(ipv4OutboundFilter), C(ipv6InboundFilter), C(ipv6OutboundFilter))"
  - "  to C(absent) to detach just that routing policy while keeping the neighbor and its other settings."
  - "  Omitting a filter field leaves the currently attached policy unchanged."
  - "Config-file fields use camelCase (e.g. C(remoteIpv4Address), C(peerAs), C(lanSegment), C(bgpAggregations))."
  - "  The original snake_case field names (C(remote_ipv4_address), C(peer_as), ...) are still accepted as"
  - "  aliases for backward compatibility; when both forms are given the camelCase value wins."
  - "Configuration files support Jinja2 templating syntax for dynamic configuration generation."
  - "The module automatically resolves device names, site names, and policy names to IDs."
  - "All operations are idempotent and safe to run multiple times."
  - "Global BGP filters must be created using M(graphiant.naas.graphiant_global_config) module"
  - "before attaching to BGP peers."
  - "BGP Aggregation config file fields per segment entry:"
  - "  bgpAggregations: list of aggregation entries, each with:"
  - "    prefix (required): The network prefix to aggregate, e.g. 1.1.1.0/27."
  - "    asSet (optional, default false): Include AS set information in the aggregated route."
  - "    summaryOnly (optional, default false): Suppress advertisement of more-specific routes."
  - "    state (optional): Set to 'absent' to remove just this aggregation under V(configure)."
  - "  Neighbor entries likewise accept state: absent to remove a single peer under V(configure)."
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
options:
  bgp_config_file:
    description:
      - Path to the BGP configuration YAML file.
      - Required for all operations.
      - Can be an absolute path or relative path. Relative paths are resolved using the configured config_path.
      - Configuration files support Jinja2 templating syntax for dynamic generation.
      - File must contain either BGP peering neighbor definitions or route aggregation definitions, or both.
    type: str
    required: true
  operation:
    description:
      - "The specific BGP operation to perform."
      - "V(configure): Configure BGP peering neighbors and/or route aggregations; attach global BGP routing policies."
      - "V(deconfigure): Remove BGP peering neighbors and/or route aggregations. Policies are automatically detached."
      - "V(detach_policies): Detach global BGP routing policies from BGP peers without removing peers or aggregations."
    type: str
    choices:
      - configure
      - deconfigure
      - detach_policies
  state:
    description:
      - "The desired state of the BGP configuration."
      - "V(present): Maps to V(configure) when O(operation) not specified."
      - "V(absent): Maps to V(deconfigure) when O(operation) not specified."
      - "Removes all neighbors and aggregations listed in the config file."
    type: str
    choices: [ present, absent ]
    default: present
  detailed_logs:
    description:
      - Enable detailed logging output for troubleshooting and monitoring.
      - When enabled, provides comprehensive logs of all BGP operations.
      - Logs are captured and included in the result_msg for display using M(ansible.builtin.debug) module.
    type: bool
    default: false
  vault_bgp_peering_md5_passwords:
    description:
      - Dict of device name to BGP neighbor address to MD5 password (configure only).
      - Fills a neighbor's MD5 password from Ansible Vault only when C(md5Password) is null/absent
        in the config file; a non-null value in the config always wins.
      - Pass from playbook vars loaded from an encrypted I(vault_secrets.yml); secrets stay in memory.
      - Keys must match the device name and the neighbor C(remoteIpv4Address) in the BGP config.
    type: dict
    default: {}
    required: false

attributes:
  check_mode:
    description: Full check mode support with per-device state comparison.
    support: full
    details: >
      The module fetches each device's current BGP state and compares it against the desired
      configuration. In check mode the same comparison runs, but the config push is skipped;
      V(changed) reflects whether a push would have occurred. Devices already in the desired
      state are reported under RV(skipped_devices) and do not count as changes.
  diff_mode:
    description: Supports diff mode; shows per-device before/after BGP state when run with C(--diff).
    support: full

requirements:
  - python >= 3.7
  - graphiant-sdk >= 26.9.0

seealso:
  - module: graphiant.naas.graphiant_interfaces
    description: Configure interfaces before setting up BGP peering
  - module: graphiant.naas.graphiant_global_config
    description: Configure global BGP filters (routing policies) that can be attached to BGP peers

author:
  - Graphiant Team (@graphiant)

"""

EXAMPLES = r"""
- name: Configure BGP peering, route aggregations and attach policies
  graphiant.naas.graphiant_bgp:
    operation: configure
    bgp_config_file: "sample_bgp_peering.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: bgp_result

# Load MD5 passwords from an encrypted vault file (secrets stay in memory only).
- name: Load BGP MD5 passwords from Ansible Vault
  ansible.builtin.include_vars: "configs/vault_secrets.yml"
  no_log: true

- name: Configure BGP peering with neighbor MD5 passwords from Ansible Vault
  graphiant.naas.graphiant_bgp:
    operation: configure
    bgp_config_file: "sample_bgp_peering.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    # Leave md5Password null/absent in the config; vault fills it per device -> neighbor address.
    vault_bgp_peering_md5_passwords: "{{ vault_bgp_peering_md5_passwords | default({}) }}"
  register: bgp_result

# Remove a single neighbor/aggregation without a full deconfigure by marking
# the entry with `state: absent` in the config file, e.g.:
#   bgpPeering:
#     - edge-1-sdktest:
#         segments:
#           - lanSegment: lan-7-test
#             neighbors:
#               - remoteIpv4Address: 10.1.17.11   # kept, configured normally
#                 peerAs: 60011
#               - remoteIpv4Address: 10.1.17.12   # removed
#                 peerAs: 60012
#                 state: absent
- name: Configure BGP peering (per-entry state:absent removes just that neighbor/aggregation)
  graphiant.naas.graphiant_bgp:
    operation: configure
    bgp_config_file: "sample_bgp_peering.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Detach policies from BGP peers
  graphiant.naas.graphiant_bgp:
    operation: detach_policies
    bgp_config_file: "sample_bgp_peering.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Deconfigure BGP peering and aggregations
  graphiant.naas.graphiant_bgp:
    operation: deconfigure
    bgp_config_file: "sample_bgp_peering.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Configure BGP peering using state parameter
  graphiant.naas.graphiant_bgp:
    state: present
    bgp_config_file: "sample_bgp_peering.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Deconfigure BGP peering and aggregations using state parameter
  graphiant.naas.graphiant_bgp:
    state: absent
    bgp_config_file: "sample_bgp_peering.yaml"
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
  sample: "Successfully configured BGP peering and attached policies"
changed:
  description:
    - Whether the operation made changes to the system.
    - V(true) only when at least one device required a config push.
    - V(false) when every device already matched the desired state (idempotent no-op).
  type: bool
  returned: always
  sample: true
operation:
  description:
    - The operation that was performed.
    - One of V(configure), V(deconfigure), or V(detach_policies).
  type: str
  returned: always
  sample: "configure"
bgp_config_file:
  description:
    - The BGP configuration file used for the operation.
  type: str
  returned: always
  sample: "sample_bgp_peering.yaml"
configured_devices:
  description:
    - Names of devices whose BGP configuration was pushed (differed from desired state).
  type: list
  elements: str
  returned: always
  sample: ["edge-1-sdktest"]
skipped_devices:
  description:
    - Names of devices skipped because they already matched the desired state.
  type: list
  elements: str
  returned: always
  sample: ["edge-2-sdktest"]
details:
  description:
    - Manager result, including the per-device C(diff_plan) with before/after BGP state.
  type: dict
  returned: always
"""

from ansible.module_utils.basic import AnsibleModule  # noqa: E402
from ansible_collections.graphiant.naas.plugins.module_utils.graphiant_utils import (  # noqa: E402
    get_graphiant_connection,
    graphiant_portal_auth_argument_spec,
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
        dict: Result with 'changed', 'result_msg', 'details', 'configured_devices',
        and 'skipped_devices' keys.
    """
    # Extract messaging kwargs before passing to func
    success_msg = kwargs.pop("success_msg", "Operation completed successfully")
    no_change_msg = kwargs.pop("no_change_msg", "No changes needed; device(s) already in desired state")

    result = func(*args, **kwargs)

    # If the function returns a dict with 'changed' key, use it
    if isinstance(result, dict) and "changed" in result:
        changed = bool(result.get("changed"))
        configured = result.get("configured_devices") or []
        skipped = result.get("skipped_devices") or []

        if changed:
            msg = success_msg
        else:
            msg = no_change_msg
            if skipped:
                msg += f" (skipped {len(skipped)} device(s))"

        return {
            "changed": changed,
            "result_msg": msg,
            "details": result,
            "configured_devices": configured,
            "skipped_devices": skipped,
        }

    # Fallback for functions that don't return change status
    return {"changed": True, "result_msg": success_msg, "details": {}, "configured_devices": [], "skipped_devices": []}


def main():
    """
    Main function for the Graphiant BGP module.
    """

    # Define module arguments
    argument_spec = dict(
        **graphiant_portal_auth_argument_spec(),
        bgp_config_file=dict(type="str", required=True),
        operation=dict(type="str", required=False, choices=["configure", "deconfigure", "detach_policies"]),
        state=dict(type="str", required=False, default="present", choices=["present", "absent"]),
        detailed_logs=dict(type="bool", required=False, default=False),
        vault_bgp_peering_md5_passwords=dict(type="dict", required=False, default={}, no_log=True),
    )

    # Create Ansible module
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    # Get parameters
    params = module.params
    operation = params.get("operation")
    state = params.get("state", "present")
    bgp_config_file = params["bgp_config_file"]

    # Validate that at least one of operation or state is provided
    if not operation and not state:
        supported_operations = ["configure", "deconfigure", "detach_policies"]
        module.fail_json(
            msg="Either 'operation' or 'state' parameter must be provided. "
            f"Supported operations: {', '.join(supported_operations)}"
        )

    # If operation is not specified, use state to determine operation
    if not operation:
        if state == "present":
            operation = "configure"
        elif state == "absent":
            operation = "deconfigure"

    # If operation is specified, it takes precedence over state
    # No additional mapping needed as operation is explicit

    # In check_mode, connection runs all logic but gsdk skips API writes and logs payloads only.

    try:
        # Get Graphiant connection
        connection = get_graphiant_connection(params, check_mode=module.check_mode)
        graphiant_config = connection.graphiant_config

        # Execute the requested operation
        if operation == "configure":
            vault_bgp_peering_md5_passwords = params.get("vault_bgp_peering_md5_passwords") or {}
            result = execute_with_logging(
                module,
                graphiant_config.bgp.configure,
                bgp_config_file,
                vault_bgp_peering_md5_passwords,
                success_msg="Successfully configured BGP peering and attached policies",
                no_change_msg="BGP peering already matches desired state; no changes needed",
            )

        elif operation == "detach_policies":
            result = execute_with_logging(
                module,
                graphiant_config.bgp.detach_policies,
                bgp_config_file,
                success_msg="Successfully detached policies from BGP peers",
                no_change_msg="BGP policies already detached; no changes needed",
            )

        elif operation == "deconfigure":
            result = execute_with_logging(
                module,
                graphiant_config.bgp.deconfigure,
                bgp_config_file,
                success_msg="Successfully deconfigured BGP peering",
                no_change_msg="BGP peering already absent; no changes needed",
            )

        else:
            supported_operations = ["configure", "deconfigure", "detach_policies"]
            module.fail_json(
                msg=f"Unsupported operation '{operation}'. "
                f"Supported operations: {', '.join(supported_operations)}.",
                operation=operation,
            )
            return

        # Return success
        details = result.get("details") or {}
        exit_payload = dict(
            changed=result["changed"],
            msg=result["result_msg"],
            operation=operation,
            bgp_config_file=bgp_config_file,
            configured_devices=result.get("configured_devices", []),
            skipped_devices=result.get("skipped_devices", []),
            details=details,
        )
        apply_module_diff(module, exit_payload, details)
        module.exit_json(**exit_payload)

    except Exception as e:
        error_msg = handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == "__main__":
    main()
