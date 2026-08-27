#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2025, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for querying Graphiant Local Extranet information.

This module provides query capabilities for Local Extranet:
- Policies summary information
- Per-device policy rollout status
- LAN segment and NAT usage monitoring
"""

DOCUMENTATION = r"""
---
module: graphiant_local_extranet_info
short_description: Query Graphiant Local Extranet policies, device status, and usage information
description:
  - This module provides query capabilities for Graphiant Local Extranet information.
  - Returns summary information about Local Extranet policies.
  - Provides per-device policy rollout status.
  - Provides LAN segment and NAT pool usage monitoring information.
  - All operations return read-only information and never modify the system.
version_added: "26.7.0"
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
notes:
  - "This is a read-only module that queries information only."
  - "All operations return tabulated output for easy reading, where applicable."
options:
  query:
    description:
      - "The specific information to query."
      - "V(policies_summary): Get summary of all Local Extranet policies with tabulated output."
      - "Returns policy details including IDs, names, type, shared segment, and target segments count."
      - "V(policy_device_status): Get per-device push/rollout status for a Local Extranet policy."
      - "Requires O(policy_name)."
      - "V(lan_segments_usage): Get LAN segment usage/monitoring information."
      - "O(policy_name) is optional; when omitted, returns usage across all policies."
      - "V(nat_usage): Get NAT pool usage/monitoring information for a Local Extranet policy."
      - "Requires O(policy_name)."
    type: str
    required: true
    choices:
      - policies_summary
      - policy_device_status
      - lan_segments_usage
      - nat_usage
  policy_name:
    description:
      - Local Extranet policy name.
      - Required for V(policy_device_status) and V(nat_usage) queries.
      - Optional for V(lan_segments_usage).
    type: str
  is_provider:
    description:
      - Whether to get provider view for LAN segment usage monitoring.
      - Only applicable to V(lan_segments_usage) query.
    type: bool
  detailed_logs:
    description:
      - Enable detailed logging output for troubleshooting and monitoring.
      - When enabled, provides comprehensive logs of all query operations.
      - Logs are captured and included in the RV(msg) return value for display using M(ansible.builtin.debug) module.
    type: bool
    default: false

attributes:
  check_mode:
    description: Supports check mode (always read-only).
    support: full

requirements:
  - python >= 3.7
  - graphiant-sdk >= 26.8.0
  - tabulate

seealso:
  - module: graphiant.naas.graphiant_local_extranet
    description: Manage Local Extranet policies

author:
  - Graphiant Team (@graphiant)

"""

EXAMPLES = r"""
- name: Get Local Extranet policies summary
  graphiant.naas.graphiant_local_extranet_info:
    query: policies_summary
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
  register: policies_summary

- name: Display policies summary
  ansible.builtin.debug:
    msg: "{{ policies_summary.msg }}"

- name: Get device rollout status for a policy
  graphiant.naas.graphiant_local_extranet_info:
    query: policy_device_status
    policy_name: "le-policy-1"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: device_status

- name: Display device status
  ansible.builtin.debug:
    msg: "{{ device_status.msg }}"

- name: Get LAN segment usage
  graphiant.naas.graphiant_local_extranet_info:
    query: lan_segments_usage
    policy_name: "le-policy-1"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
  register: lan_segments_usage

- name: Get NAT pool usage
  graphiant.naas.graphiant_local_extranet_info:
    query: nat_usage
    policy_name: "le-policy-1"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
  register: nat_usage
"""

RETURN = r"""
msg:
  description:
    - Result message from the query operation, including detailed logs when O(detailed_logs) is enabled.
  type: str
  returned: always
  sample: |
    Local Extranet Policies Summary:
    +------+---------------+----------------+------------------+
    |   ID | Name          | Shared Segment |  Target Segments |
    +======+===============+================+==================+
    | 8568 | le-policy-1   | lan-1          |                2 |
    +------+---------------+----------------+------------------+
result_data:
  description:
    - Result data from the query operation, including structured data for the requested query.
  type: dict
  returned: always
  sample:
    policies:
      - id: 8568
        name: "le-policy-1"
        sharedSegment: "lan-1"
        targetSegmentsCount: 2
query:
  description:
    - The query that was performed.
    - One of V(policies_summary), V(policy_device_status), V(lan_segments_usage), or V(nat_usage).
  type: str
  returned: always
  sample: "policies_summary"
"""

from ansible.module_utils.basic import AnsibleModule  # noqa: E402
from ansible_collections.graphiant.naas.plugins.module_utils.graphiant_utils import (  # noqa: E402
    graphiant_portal_auth_argument_spec,
    get_graphiant_connection,
)
from ansible_collections.graphiant.naas.plugins.module_utils.logging_decorator import (  # noqa: E402
    capture_library_logs,
)


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
        dict: Result with 'result_msg' and 'result_data' keys
    """
    success_msg = kwargs.pop("success_msg", "Query completed successfully")

    try:
        result = func(*args, **kwargs)
        if isinstance(result, dict) and "result_msg" in result:
            return {"result_msg": result.get("result_msg", success_msg), "result_data": result.get("result_data", {})}
        return {"result_msg": success_msg, "result_data": result if isinstance(result, dict) else {}}
    except Exception as e:
        raise e


def main():
    """Main function for the Local Extranet info module."""

    argument_spec = dict(
        **graphiant_portal_auth_argument_spec(),
        query=dict(
            type="str",
            required=True,
            choices=["policies_summary", "policy_device_status", "lan_segments_usage", "nat_usage"],
        ),
        policy_name=dict(type="str", required=False),
        is_provider=dict(type="bool", required=False),
        detailed_logs=dict(type="bool", default=False),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
        required_if=[
            ("query", "policy_device_status", ["policy_name"]),
            ("query", "nat_usage", ["policy_name"]),
        ],
    )

    params = module.params
    query = params.get("query")
    policy_name = params.get("policy_name")

    try:
        connection = get_graphiant_connection(params, check_mode=module.check_mode)
        graphiant_config = connection.graphiant_config

        result_msg = ""
        result_data = {}

        if query == "policies_summary":
            result = execute_with_logging(
                module,
                graphiant_config.local_extranet.get_policies_summary,
                success_msg="Successfully retrieved Local Extranet policies summary",
            )
            result_msg = result["result_msg"]
            result_data = result.get("result_data", {})

        elif query == "policy_device_status":
            result = execute_with_logging(
                module,
                graphiant_config.local_extranet.get_device_status,
                policy_name,
                success_msg=f"Successfully retrieved device status for policy {policy_name}",
            )
            result_msg = result["result_msg"]
            result_data = result.get("result_data", {})

        elif query == "lan_segments_usage":
            is_provider = params.get("is_provider")
            result = execute_with_logging(
                module,
                graphiant_config.local_extranet.get_lan_segments_usage,
                policy_name,
                is_provider,
                success_msg="Successfully retrieved LAN segment usage",
            )
            result_msg = result["result_msg"]
            result_data = result.get("result_data", {})

        elif query == "nat_usage":
            result = execute_with_logging(
                module,
                graphiant_config.local_extranet.get_nat_usage,
                policy_name,
                success_msg=f"Successfully retrieved NAT usage for policy {policy_name}",
            )
            result_msg = result["result_msg"]
            result_data = result.get("result_data", {})

        else:
            module.fail_json(
                msg=f"Unsupported query: {query}. "
                f"Supported queries are: policies_summary, policy_device_status, lan_segments_usage, nat_usage"
            )

        module.exit_json(changed=False, msg=result_msg, query=query, result_data=result_data)

    except Exception as e:
        module.fail_json(msg=f"Error executing query: {str(e)}")


if __name__ == "__main__":
    main()
