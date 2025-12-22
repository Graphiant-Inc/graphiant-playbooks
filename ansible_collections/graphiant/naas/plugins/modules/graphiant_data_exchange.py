#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2025, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for managing Graphiant Data Exchange services, customers, and matches.

This module provides Data Exchange management capabilities including:
- Data Exchange services creation and deletion
- Data Exchange customers creation and deletion
- Service-to-customer matching operations
- Summary and query operations for services and customers
"""

DOCUMENTATION = r'''
---
module: graphiant_data_exchange
short_description: Manage Graphiant Data Exchange services, customers, matches, and invitations
description:
  - This module provides comprehensive Data Exchange management capabilities for Graphiant's B2B peering platform.
  - Enables creating, deleting, and querying Data Exchange services and customers.
  - Provides service-to-customer matching operations with automatic match response file management.
  - Supports invitation acceptance with gateway service deployment and VPN configuration.
version_added: "25.12.0"
notes:
  - "Data Exchange Workflows:"
  - "  - Workflow 1 (Create Services): Create Data Exchange services that can be shared with customers."
  - "  - Workflow 2 (Create Customers): Create Data Exchange customers (nonGraphiant peers)."
  - "  - Workflow 3 (Match Services): Match services to customers and establish peering relationships."
  - "  - Workflow 4 (Accept Invitation): Accept service invitations for non Graphiant customers."
  - "Configuration files support Jinja2 templating syntax for dynamic configuration generation."
  - "Match responses are automatically saved to JSON files in the output directory near the configuration file."
  - "The module automatically resolves names to IDs for sites, LAN segments, services, customers, and regions."
  - "All operations are idempotent and safe to run multiple times without creating duplicates."
  - "For accept_invitation operation, minimum 2 gateways per region are required for redundancy."
  - "Check mode (C(--check)) is not supported for this module. Data Exchange operations involve complex multi-step workflows with state changes that cannot be safely simulated. The C(accept_invitation) operation provides a C(dry_run) parameter for validation without API calls."
options:
  operation:
    description: "The specific Data Exchange operation to perform. C(create_services): Create Data Exchange services from YAML configuration (Workflow 1). Configuration file must contain C(data_exchange_services) list with service definitions. Services define peering services with LAN segments, sites, and service prefixes. C(delete_services): Delete Data Exchange services from YAML configuration. Services must be deleted after customers that depend on them. C(get_services_summary): Get summary of all Data Exchange services with tabulated output. Returns service details including IDs, names, status, role, and matched customers count. C(create_customers): Create Data Exchange customers from YAML configuration (Workflow 2). Configuration file must contain C(data_exchange_customers) list with customer definitions. Customers can be non-Graphiant peers that can be invited to connect to services. C(delete_customers): Delete Data Exchange customers from YAML configuration. Customers must be deleted before services they depend on. C(get_customers_summary): Get summary of all Data Exchange customers with tabulated output. Returns customer details including IDs, names, type, status, and matched services count. C(match_service_to_customers): Match services to customers from YAML configuration (Workflow 3). Configuration file must contain C(data_exchange_matches) list with match definitions. Automatically saves match responses to JSON file for use in Workflow 4. Updates existing match entries or appends new ones based on customer_name and service_name. C(accept_invitation): Accept Data Exchange service invitation (Workflow 4). Configuration file must contain C(data_exchange_acceptances) list with acceptance details. Requires matches_file from Workflow 3 for match ID lookup. Supports dry-run mode for validation without API calls. Configures full IPSec gateway deployment with dual tunnels, static routing, and VPN profiles. C(get_service_health): Get service health monitoring information for all matched customers. Returns tabulated health status including overall health, producer prefix health, and customer prefix health. Supports both consumer and provider views."
    type: str
    choices:
      - create_services
      - delete_services
      - get_services_summary
      - create_customers
      - delete_customers
      - get_customers_summary
      - match_service_to_customers
      - accept_invitation
      - get_service_health
    required: true
  state:
    description: "The desired state of the Data Exchange resources. C(present): Maps to C(create_services) when operation not specified. C(absent): Maps to C(delete_services) when operation not specified. C(query): Maps to C(get_services_summary) when operation not specified."
    type: str
    choices:
      - present
      - absent
      - query
    default: present
  config_file:
    description:
      - Path to the YAML configuration file for the operation.
      - Required for C(create_services), C(delete_services), C(create_customers), C(delete_customers), C(match_service_to_customers), and C(accept_invitation) operations.  # noqa: E501
      - Can be an absolute path or relative path. Relative paths are resolved using the configured config_path.
      - Configuration files support Jinja2 templating syntax for dynamic generation.
      - For C(create_services), file must contain C(data_exchange_services) list.
      - For C(create_customers) or C(delete_customers), file must contain C(data_exchange_customers) list.
      - For C(match_service_to_customers), file must contain C(data_exchange_matches) list.
      - For C(accept_invitation), file must contain C(data_exchange_acceptances) list.
      - Match responses are saved to C(output/) directory near the configuration file.
    type: str
  matches_file:
    description:
      - Path to the matches responses JSON file for match ID lookup.
      - Optional for C(accept_invitation) operation.
      - If not provided, default C(de_workflows_configs/output/sample_data_exchange_matches_responses_latest.json).
      - Can be an absolute path or relative path. Relative paths are resolved using the configured config_path.
      - This file is automatically generated by C(match_service_to_customers) operation (Workflow 3).
      - File contains match details including C(customer_id), C(service_id), C(match_id), and C(status).
      - Required for C(accept_invitation) to look up match IDs for customer-service combinations.
    type: str
  dry_run:
    description:
      - Enable dry-run mode for C(accept_invitation) operation.
      - When enabled, validates configuration without making actual API calls.
      - Performs all name-to-ID resolution and configuration validation.
      - Useful for testing and validation before actual execution.
      - Only applicable to C(accept_invitation) operation.
    type: bool
    default: false
  detailed_logs:
    description:
      - Enable detailed logging output for troubleshooting and monitoring.
      - When enabled, provides comprehensive logs of all Data Exchange operations.
      - Logs are captured and included in the C(msg) return value for display using debug module.
    type: bool
    default: false
  host:
    description:
      - Graphiant portal host URL for API connectivity.
      - 'Example: "https://api.graphiant.com"'
    type: str
    required: true
    aliases: [ base_url, host ]
  username:
    description:
      - Graphiant portal username for authentication.
    type: str
    required: true
  password:
    description:
      - Graphiant portal password for authentication.
    type: str
    required: true
  service_name:
    description:
      - Service name for health monitoring operations.
      - Required for C(get_service_health) operation.
      - Must be an existing Data Exchange service name.
    type: str
  is_provider:
    description:
      - Whether to get provider view for service health monitoring.
      - When C(false), returns health from consumer/customer perspective.
      - When C(true), returns health from service provider perspective.
      - Only applicable to C(get_service_health) operation.
    type: bool
    default: false

requirements:
  - python >= 3.10
  - graphiant-sdk >= 25.12.1
  - tabulate

seealso:
  - module: graphiant.naas.graphiant_interfaces
    description: Configure interfaces and circuits for Data Exchange prerequisites
  - module: graphiant.naas.graphiant_global_config
    description: Configure global objects (LAN segments, VPN profiles) required for Data Exchange
  - module: graphiant.naas.graphiant_sites
    description: Configure sites required for Data Exchange services

author:
  - Graphiant Team (@graphiant)

'''

EXAMPLES = r'''
- name: Workflow 1 - Create Data Exchange services
  graphiant.naas.graphiant_data_exchange:
    operation: create_services
    config_file: "de_workflows_configs/sample_data_exchange_services.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: create_services_result

- name: Display services creation result
  debug:
    msg: "{{ create_services_result.msg }}"

- name: Workflow 1 - Create services with Jinja2 template (scale testing)
  graphiant.naas.graphiant_data_exchange:
    operation: create_services
    config_file: "de_workflows_configs/sample_data_exchange_services_scale.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Workflow 2 - Create Data Exchange customers
  graphiant.naas.graphiant_data_exchange:
    operation: create_customers
    config_file: "de_workflows_configs/sample_data_exchange_customers.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: create_customers_result

- name: Display customers creation result
  debug:
    msg: "{{ create_customers_result.msg }}"

- name: Workflow 2 - Create customers with Jinja2 template (scale testing)
  graphiant.naas.graphiant_data_exchange:
    operation: create_customers
    config_file: "de_workflows_configs/sample_data_exchange_customers_scale2.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Workflow 3 - Match Data Exchange services to customers
  graphiant.naas.graphiant_data_exchange:
    operation: match_service_to_customers
    config_file: "de_workflows_configs/sample_data_exchange_matches.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: match_result

- name: Display match result
  debug:
    msg: "{{ match_result.msg }}"

- name: Workflow 4 - Accept Data Exchange service invitation (Dry Run)
  graphiant.naas.graphiant_data_exchange:
    operation: accept_invitation
    config_file: "de_workflows_configs/sample_data_exchange_acceptance.yaml"
    matches_file: "de_workflows_configs/output/sample_data_exchange_matches_responses_latest.json"
    dry_run: true
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: accept_result_dry_run

- name: Display dry run result
  debug:
    msg: "{{ accept_result_dry_run.msg }}"

- name: Workflow 4 - Accept Data Exchange service invitation
  graphiant.naas.graphiant_data_exchange:
    operation: accept_invitation
    config_file: "de_workflows_configs/sample_data_exchange_acceptance.yaml"
    matches_file: "de_workflows_configs/output/sample_data_exchange_matches_responses_latest.json"
    dry_run: false
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: accept_result

- name: Display acceptance result
  debug:
    msg: "{{ accept_result.msg }}"

- name: Delete Data Exchange customers (must be deleted before services)
  graphiant.naas.graphiant_data_exchange:
    operation: delete_customers
    config_file: "de_workflows_configs/sample_data_exchange_customers.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Delete Data Exchange services
  graphiant.naas.graphiant_data_exchange:
    operation: delete_services
    config_file: "de_workflows_configs/sample_data_exchange_services.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Get Data Exchange services summary
  graphiant.naas.graphiant_data_exchange:
    operation: get_services_summary
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
  register: services_summary

- name: Display services summary
  debug:
    msg: "{{ services_summary.msg }}"

- name: Get Data Exchange customers summary
  graphiant.naas.graphiant_data_exchange:
    operation: get_customers_summary
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
  register: customers_summary

- name: Display customers summary
  debug:
    msg: "{{ customers_summary.msg }}"

- name: Get service health (consumer view)
  graphiant.naas.graphiant_data_exchange:
    operation: get_service_health
    service_name: "de-service-1"
    is_provider: false
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: service_health

- name: Display service health
  debug:
    msg: "{{ service_health.msg }}"

- name: Get service health (provider view)
  graphiant.naas.graphiant_data_exchange:
    operation: get_service_health
    service_name: "de-service-1"
    is_provider: true
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: service_health_provider

- name: Display service health (provider view)
  debug:
    msg: "{{ service_health_provider.msg }}"

- name: Complete Data Exchange workflow (all four workflows)
  block:
    - name: Workflow 1 - Create services
      graphiant.naas.graphiant_data_exchange:
        operation: create_services
        config_file: "de_workflows_configs/sample_data_exchange_services.yaml"
        host: "{{ graphiant_host }}"
        username: "{{ graphiant_username }}"
        password: "{{ graphiant_password }}"
        detailed_logs: true
      register: create_services_result

    - name: Workflow 2 - Create customers
      graphiant.naas.graphiant_data_exchange:
        operation: create_customers
        config_file: "de_workflows_configs/sample_data_exchange_customers.yaml"
        host: "{{ graphiant_host }}"
        username: "{{ graphiant_username }}"
        password: "{{ graphiant_password }}"
        detailed_logs: true
      register: create_customers_result

    - name: Workflow 3 - Match services to customers
      graphiant.naas.graphiant_data_exchange:
        operation: match_service_to_customers
        config_file: "de_workflows_configs/sample_data_exchange_matches.yaml"
        host: "{{ graphiant_host }}"
        username: "{{ graphiant_username }}"
        password: "{{ graphiant_password }}"
        detailed_logs: true
      register: match_result

    - name: Workflow 4 - Accept invitations
      graphiant.naas.graphiant_data_exchange:
        operation: accept_invitation
        config_file: "de_workflows_configs/sample_data_exchange_acceptance.yaml"
        matches_file: "de_workflows_configs/output/sample_data_exchange_matches_responses_latest.json"
        dry_run: false
        host: "{{ graphiant_host }}"
        username: "{{ graphiant_username }}"
        password: "{{ graphiant_password }}"
        detailed_logs: true
      register: accept_result

    - name: Display workflow results
      debug:
        msg: "{{ item.msg }}"
      loop:
        - "{{ create_services_result }}"
        - "{{ create_customers_result }}"
        - "{{ match_result }}"
        - "{{ accept_result }}"
'''

RETURN = r'''
msg:
  description:
    - Result message from the operation, including detailed logs when C(detailed_logs) is enabled.
    - For summary operations, includes tabulated output for easy reading.
    - For health operations, includes tabulated health status for all matched customers.
  type: str
  returned: always
  sample: |
    Successfully created 3 Data Exchange services

    Detailed logs:
    2025-10-19 23:08:05,315 - Graphiant_playbook - INFO - Creating service 'de-service-1'...
    2025-10-19 23:08:05,450 - Graphiant_playbook - INFO - Successfully created service 'de-service-1'
result_data:
  description:
    - Result data from the operation, including structured data for summary and health operations.
    - For summary operations, contains service/customer details with IDs, names, status, and counts.
    - For health operations, contains health metrics for all matched customers.
  type: dict
  returned: when applicable
  sample:
    {
      "services": [
        {
          "name": "de-service-1",
          "status": "ACTIVE",
          "id": 123,
          "matched_customers": 2
        }
      ],
      "summary": {
        "total": 3,
        "created": 3
      }
    }
changed:
  description:
    - Whether the operation made changes to the system.
    - C(true) for create, delete, match, and accept operations.
    - C(false) for query operations (get_services_summary, get_customers_summary, get_service_health).
  type: bool
  returned: always
  sample: true
operation:
  description:
    - The operation that was performed.
    - One of create_services, delete_services, get_services_summary, create_customers, delete_customers,
      get_customers_summary, match_service_to_customers, accept_invitation, or get_service_health.
  type: str
  returned: always
  sample: "create_services"
config_file:
  description:
    - The configuration file used for the operation.
    - Only returned for operations that require a configuration file.
  type: str
  returned: when applicable
  sample: "de_workflows_configs/sample_data_exchange_services.yaml"
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.graphiant.naas.plugins.module_utils.graphiant_utils import (
    get_graphiant_connection,
    handle_graphiant_exception
)
from ansible_collections.graphiant.naas.plugins.module_utils.logging_decorator import (
    capture_library_logs
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
        dict: Result with 'changed' and 'result_msg' keys
    """
    # Extract success_msg from kwargs before passing to func
    success_msg = kwargs.pop('success_msg', 'Operation completed successfully')

    try:
        result = func(*args, **kwargs)

        # If the function returns a dict with 'changed' key, use it
        if isinstance(result, dict) and 'changed' in result:
            return {
                'changed': result['changed'],
                'result_msg': success_msg,
                'details': result
            }

        # Fallback for functions that don't return change status
        return {
            'changed': True,
            'result_msg': success_msg
        }
    except Exception as e:
        raise e


def main():
    """Main function for the Data Exchange module."""

    # Define module arguments
    argument_spec = dict(
        host=dict(type='str', required=True, aliases=['base_url']),
        username=dict(type='str', required=True),
        password=dict(type='str', required=True, no_log=True),
        operation=dict(
            type='str',
            required=True,
            choices=[
                'create_services',
                'delete_services',
                'get_services_summary',
                'create_customers',
                'delete_customers',
                'get_customers_summary',
                'match_service_to_customers',
                'accept_invitation',
                'get_service_health'
            ]
        ),
        state=dict(
            type='str',
            choices=['present', 'absent', 'query'],
            default='present'
        ),
        config_file=dict(type='str', required=False),
        matches_file=dict(type='str', required=False),
        detailed_logs=dict(type='bool', default=False),
        dry_run=dict(type='bool', default=False),
        service_name=dict(type='str', required=False),
        is_provider=dict(type='bool', default=False)
    )

    # Create module instance
    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=False,
        mutually_exclusive=[
            ('operation', 'state')
        ],
        required_one_of=[
            ('operation', 'state')
        ]
    )

    # Get parameters
    params = module.params
    operation = params.get('operation')
    state = params.get('state')
    config_file = params.get('config_file')

    # Determine operation based on state if operation not provided
    if not operation:
        if state == 'present':
            # Default to create_services for present state
            operation = 'create_services'
        elif state == 'absent':
            # Default to delete_services for absent state
            operation = 'delete_services'
        elif state == 'query':
            # Default to get_services_summary for query state
            operation = 'get_services_summary'

    # Validate required parameters
    if operation in ['create_services', 'delete_services', 'create_customers', 'delete_customers',
                     'match_service_to_customers']:
        if not config_file:
            module.fail_json(
                msg=f"config_file parameter is required for operation '{operation}'"
            )

    try:
        # Get Graphiant connection
        connection = get_graphiant_connection(params)
        graphiant_config = connection.graphiant_config

        # Execute the requested operation
        changed = False
        result_msg = ""
        result_data = {}

        if operation == 'create_services':
            result = execute_with_logging(module, graphiant_config.data_exchange.create_services,
                                          config_file,
                                          success_msg=f"Successfully created Data Exchange services from {config_file}")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'delete_services':
            result = execute_with_logging(module, graphiant_config.data_exchange.delete_services,
                                          config_file,
                                          success_msg=f"Successfully deleted Data Exchange services from {config_file}")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'get_services_summary':
            result = execute_with_logging(module, graphiant_config.data_exchange.get_services_summary,
                                          success_msg="Successfully retrieved Data Exchange services summary")
            result_msg = result['result_msg']
            result_data = result.get('result_data', {})

        elif operation == 'create_customers':
            result = execute_with_logging(module, graphiant_config.data_exchange.create_customers,
                                          config_file,
                                          success_msg=f"Successfully created Data Exchange customers {config_file}")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'delete_customers':
            result = execute_with_logging(module, graphiant_config.data_exchange.delete_customers,
                                          config_file,
                                          success_msg=f"Successfully deleted Data Exchange customers {config_file}")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'get_customers_summary':
            result = execute_with_logging(module, graphiant_config.data_exchange.get_customers_summary,
                                          success_msg="Successfully retrieved Data Exchange customers summary")
            result_msg = result['result_msg']
            result_data = result.get('result_data', {})

        elif operation == 'match_service_to_customers':
            result = execute_with_logging(module, graphiant_config.data_exchange.match_service_to_customers,
                                          config_file,
                                          success_msg="Successfully matched Data Exchange services to customers")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'accept_invitation':
            # accept_invitation operation supports config_file and optional matches_file, dry_run
            if not config_file:
                module.fail_json(msg="accept_invitation operation requires config_file parameter")

            matches_file = params.get('matches_file')
            dry_run = params.get('dry_run', False)

            success_msg = f"Successfully accepted Data Exchange service invitation from {config_file}"
            if dry_run:
                success_msg = f"DRY-RUN: Validated Data Exchange service invitation from {config_file} " \
                              "(API calls skipped)"

            result = execute_with_logging(module, graphiant_config.data_exchange.accept_invitation,
                                          config_file, matches_file, dry_run,
                                          success_msg=success_msg)

            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'get_service_health':
            service_name = params.get('service_name')
            is_provider = params.get('is_provider', False)

            if not service_name:
                module.fail_json(msg="get_service_health operation requires service_name parameter")

            result = execute_with_logging(
                module, graphiant_config.data_exchange.get_service_health, service_name, is_provider,
                success_msg=f"Successfully retrieved service health for service {service_name}")
            result_msg = result['result_msg']
            result_data = result.get('result_data', {})

        else:
            module.fail_json(
                msg=f"Unsupported operation: {operation}. "
                    f"Supported operations are: create_services, delete_services, get_services_summary, "
                    f"create_customers, delete_customers, get_customers_summary, match_service_to_customers, "
                    f"accept_invitation, get_service_health"
            )

        # Return success
        module.exit_json(
            changed=changed,
            msg=result_msg,
            result_msg=result_msg,
            result_data=result_data,
            operation=operation or 'unknown',
            config_file=config_file if config_file else None
        )

    except Exception as e:
        error_msg = handle_graphiant_exception(e, operation or 'unknown')
        module.fail_json(msg=error_msg, operation=operation or 'unknown')


if __name__ == '__main__':
    main()
