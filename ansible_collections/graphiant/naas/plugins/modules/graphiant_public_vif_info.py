#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for querying Graphiant gateway Public VIF information.

This module provides query capabilities for Public VIF:
- Services summary information
- Per-service detailed configuration
"""

DOCUMENTATION = r"""
---
module: graphiant_public_vif_info
short_description: Query Graphiant gateway Public VIF (local data exchange) service information
description:
  - This module provides query capabilities for Graphiant gateway Public VIF service information.
  - Returns summary information about Public VIF services.
  - Provides detailed configuration for a specific Public VIF service.
  - All operations return read-only information and never modify the system.
version_added: "26.8.0"
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
notes:
  - "This is a read-only module that queries information only."
  - "All operations return tabulated output for easy reading, where applicable."
options:
  query:
    description:
      - "The specific information to query."
      - "V(services_summary): Get summary of all Public VIF services with tabulated output."
      - "Returns service details including IDs, names, creator, and last-updated time."
      - "V(service_details): Get full configuration for a specific Public VIF service."
      - "Requires O(service_name)."
    type: str
    required: true
    choices:
      - services_summary
      - service_details
  service_name:
    description:
      - Public VIF service name.
      - Required for V(service_details) query.
    type: str
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
  - module: graphiant.naas.graphiant_public_vif
    description: Manage Public VIF services

author:
  - Graphiant Team (@graphiant)

"""

EXAMPLES = r"""
- name: Get Public VIF services summary
  graphiant.naas.graphiant_public_vif_info:
    query: services_summary
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
  register: services_summary

- name: Display services summary
  ansible.builtin.debug:
    msg: "{{ services_summary.msg }}"

- name: Get details for a specific service
  graphiant.naas.graphiant_public_vif_info:
    query: service_details
    service_name: "pvif-service-1"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: service_details

- name: Display service details
  ansible.builtin.debug:
    msg: "{{ service_details.result_data }}"
"""

RETURN = r"""
msg:
  description:
    - Result message from the query operation, including detailed logs when O(detailed_logs) is enabled.
  type: str
  returned: always
  sample: |
    Public VIF Services Summary:
    +------+-------------------+------------+---------------------------+
    |   ID | Service Name      | Created By |  Updated At               |
    +======+===================+============+===========================+
    | 8568 | pvif-service-1    | jdoe       | 2026-08-14T23:08:05Z      |
    +------+-------------------+------------+---------------------------+
result_data:
  description:
    - Result data from the query operation, including structured data for the requested query.
  type: dict
  returned: always
  sample:
    services:
      - id: 8568
        serviceName: "pvif-service-1"
        userName: "jdoe"
        updatedAt: "2026-08-14T23:08:05Z"
query:
  description:
    - The query that was performed.
    - One of V(services_summary) or V(service_details).
  type: str
  returned: always
  sample: "services_summary"
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
    """Main function for the Public VIF info module."""

    argument_spec = dict(
        **graphiant_portal_auth_argument_spec(),
        query=dict(
            type="str",
            required=True,
            choices=["services_summary", "service_details"],
        ),
        service_name=dict(type="str", required=False),
        detailed_logs=dict(type="bool", default=False),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
        required_if=[
            ("query", "service_details", ["service_name"]),
        ],
    )

    params = module.params
    query = params.get("query")
    service_name = params.get("service_name")

    try:
        connection = get_graphiant_connection(params, check_mode=module.check_mode)
        graphiant_config = connection.graphiant_config

        result_msg = ""
        result_data = {}

        if query == "services_summary":
            result = execute_with_logging(
                module,
                graphiant_config.public_vif.get_services_summary,
                success_msg="Successfully retrieved Public VIF services summary",
            )
            result_msg = result["result_msg"]
            result_data = result.get("result_data", {})

        elif query == "service_details":
            result = execute_with_logging(
                module,
                graphiant_config.public_vif.get_service_details,
                service_name,
                success_msg=f"Successfully retrieved details for service {service_name}",
            )
            result_msg = result["result_msg"]
            result_data = result.get("result_data", {})

        else:
            module.fail_json(
                msg=f"Unsupported query: {query}. Supported queries are: services_summary, service_details"
            )

        module.exit_json(changed=False, msg=result_msg, query=query, result_data=result_data)

    except Exception as e:
        module.fail_json(msg=f"Error executing query: {str(e)}")


if __name__ == "__main__":
    main()
