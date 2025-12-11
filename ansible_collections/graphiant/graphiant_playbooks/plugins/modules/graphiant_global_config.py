#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2025, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for managing Graphiant global configuration objects.

This module provides global configuration management capabilities including:
- Prefix sets configuration and deconfiguration
- BGP filters (routing policies) management
- SNMP services management
- Syslog services management
- IPFIX services management
- VPN profiles management
- LAN segments management
"""

DOCUMENTATION = r'''
---
module: graphiant_global_config
short_description: Manage Graphiant global configuration objects
description:
  - This module provides comprehensive global configuration object management for Graphiant devices.
  - >
    Supports multiple global object types: prefix sets, BGP filters, SNMP services,
    syslog services, IPFIX services, VPN profiles, and LAN segments.
  - Can manage all object types together using general operations or specific object types individually.
  - All operations use Jinja2 templates for consistent configuration deployment.
version_added: "25.11.0"
notes:
  - "Global Configuration Operations:"
  - "  - General operations (C(configure), C(deconfigure)):
  - Automatically detect and process all configuration types in the YAML file."
  - "  - Specific operations (C(configure_*), C(deconfigure_*)):
  - Process only the specific configuration type."
  - "Configuration files support Jinja2 templating syntax for dynamic configuration generation."
  - "The module automatically resolves names to IDs for sites, LAN segments, and other referenced objects."
  - "All operations are idempotent and safe to run multiple times."
  - "Global objects can be referenced by other modules (BGP, Sites, Data Exchange) after creation."
options:
  host:
    description:
      - Graphiant portal host URL for API connectivity.
      - 'Example: "https://api.graphiant.com"'
    type: str
    required: true
    aliases: [ base_url ]
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
  config_file:
    description:
      - Path to the global configuration YAML file.
      - Required for all operations.
      - Can be an absolute path or relative path. Relative paths are resolved using the configured config_path.
      - Configuration files support Jinja2 templating syntax for dynamic generation.
      - File must contain the appropriate global object definitions based on the operation type.
    type: str
    required: true
  operation:
    description:
      - "The specific global configuration operation to perform."
      - "C(configure): Configure all global objects (automatically detects all types in the file)."
      - "C(deconfigure): Deconfigure all global objects (automatically detects all types in the file)."
      - "C(configure_prefix_sets): Configure global prefix sets only."
      - "C(deconfigure_prefix_sets): Deconfigure global prefix sets only."
      - "C(configure_bgp_filters): Configure global BGP filters (routing policies) only."
      - "C(deconfigure_bgp_filters): Deconfigure global BGP filters only."
      - "C(configure_snmp_services): Configure global SNMP services only."
      - "C(deconfigure_snmp_services): Deconfigure global SNMP services only."
      - "C(configure_syslog_services): Configure global syslog services only."
      - "C(deconfigure_syslog_services): Deconfigure global syslog services only."
      - "C(configure_ipfix_services): Configure global IPFIX services only."
      - "C(deconfigure_ipfix_services): Deconfigure global IPFIX services only."
      - "C(configure_vpn_profiles): Configure global VPN profiles only."
      - "C(deconfigure_vpn_profiles): Deconfigure global VPN profiles only."
      - "C(configure_lan_segments): Configure global LAN segments only."
      - "C(deconfigure_lan_segments): Deconfigure global LAN segments only."
      - "C(configure_site_lists): Configure global site lists only."
      - "C(deconfigure_site_lists): Deconfigure global site lists only."
    type: str
    choices:
      - configure
      - deconfigure
      - configure_prefix_sets
      - deconfigure_prefix_sets
      - configure_bgp_filters
      - deconfigure_bgp_filters
      - configure_snmp_services
      - deconfigure_snmp_services
      - configure_syslog_services
      - deconfigure_syslog_services
      - configure_ipfix_services
      - deconfigure_ipfix_services
      - configure_vpn_profiles
      - deconfigure_vpn_profiles
      - configure_lan_segments
      - deconfigure_lan_segments
      - configure_site_lists
      - deconfigure_site_lists
  state:
    description:
      - "The desired state of the global configuration objects."
      - "C(present): Maps to C(configure) when operation not specified."
      - "C(absent): Maps to C(deconfigure) when operation not specified."
    type: str
    choices: [ present, absent ]
    default: present
  detailed_logs:
    description:
      - Enable detailed logging output for troubleshooting and monitoring.
      - When enabled, provides comprehensive logs of all global configuration operations.
      - Logs are captured and included in the result_msg for display using debug module.
    type: bool
    default: false

requirements:
  - python >= 3.10
  - graphiant-sdk >= 25.11.1

seealso:
  - module: graphiant.graphiant_playbooks.graphiant_bgp
    description: Attach global BGP filters to BGP peers
  - module: graphiant.graphiant_playbooks.graphiant_sites
    description: Attach global objects to sites
  - module: graphiant.graphiant_playbooks.graphiant_data_exchange
    description: Use global LAN segments and VPN profiles in Data Exchange workflows

author:
  - Graphiant Team (@graphiant)

'''

EXAMPLES = r'''
- name: Configure all global objects (general operation)
  graphiant.graphiant_playbooks.graphiant_global_config:
    operation: configure
    config_file: "sample_global_prefix_lists.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Configure global prefix sets (specific operation)
  graphiant.graphiant_playbooks.graphiant_global_config:
    operation: configure_prefix_sets
    config_file: "sample_global_prefix_lists.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Configure global BGP filters
  graphiant.graphiant_playbooks.graphiant_global_config:
    operation: configure_bgp_filters
    config_file: "sample_global_bgp_filters.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Configure global LAN segments
  graphiant.graphiant_playbooks.graphiant_global_config:
    operation: configure_lan_segments
    config_file: "sample_global_lan_segments.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Configure global VPN profiles
  graphiant.graphiant_playbooks.graphiant_global_config:
    operation: configure_vpn_profiles
    config_file: "sample_global_vpn_profiles.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Configure global site lists
  graphiant.graphiant_playbooks.graphiant_global_config:
    operation: configure_site_lists
    config_file: "sample_global_site_lists.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Deconfigure global prefix sets
  graphiant.graphiant_playbooks.graphiant_global_config:
    operation: deconfigure_prefix_sets
    config_file: "sample_global_prefix_lists.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Deconfigure all global objects using state parameter
  graphiant.graphiant_playbooks.graphiant_global_config:
    state: absent
    config_file: "sample_global_prefix_lists.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
'''

RETURN = r'''
msg:
  description:
    - Result message from the operation, including detailed logs when C(detailed_logs) is enabled.
  type: str
  returned: always
  sample: "Successfully configured all global objects"
changed:
  description:
    - Whether the operation made changes to the system.
    - C(true) for all configure/deconfigure operations.
  type: bool
  returned: always
  sample: true
operation:
  description:
    - The operation that was performed.
    - One of configure, deconfigure, or a specific configure_*/deconfigure_* operation.
  type: str
  returned: always
  sample: "configure_prefix_sets"
config_file:
  description:
    - The configuration file used for the operation.
  type: str
  returned: always
  sample: "sample_global_prefix_lists.yaml"
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.graphiant.graphiant_playbooks.plugins.module_utils.graphiant_utils import (
    get_graphiant_connection,
    handle_graphiant_exception
)
from ansible_collections.graphiant.graphiant_playbooks.plugins.module_utils.logging_decorator import (
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
        func(*args, **kwargs)
        return {
            'changed': True,
            'result_msg': success_msg
        }
    except Exception as e:
        raise e


def main():
    """
    Main function for the Graphiant global configuration module.
    """

    # Define module arguments
    argument_spec = dict(
        host=dict(type='str', required=True, aliases=['base_url']),
        username=dict(type='str', required=True),
        password=dict(type='str', required=True, no_log=True),
        config_file=dict(type='str', required=True),
        operation=dict(
            type='str',
            required=False,
            choices=[
                'configure',
                'deconfigure',
                'configure_prefix_sets',
                'deconfigure_prefix_sets',
                'configure_bgp_filters',
                'deconfigure_bgp_filters',
                'configure_snmp_services',
                'deconfigure_snmp_services',
                'configure_syslog_services',
                'deconfigure_syslog_services',
                'configure_ipfix_services',
                'deconfigure_ipfix_services',
                'configure_vpn_profiles',
                'deconfigure_vpn_profiles',
                'configure_lan_segments',
                'deconfigure_lan_segments',
                'configure_site_lists',
                'deconfigure_site_lists'
            ]
        ),
        state=dict(
            type='str',
            required=False,
            default='present',
            choices=['present', 'absent']
        ),
        detailed_logs=dict(
            type='bool',
            required=False,
            default=False
        )
    )

    # Create Ansible module
    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True
    )

    # Get parameters
    params = module.params
    operation = params.get('operation')
    state = params.get('state', 'present')
    config_file = params['config_file']

    # Validate that at least one of operation or state is provided
    if not operation and not state:
        supported_operations = [
            'configure', 'deconfigure', 'configure_prefix_sets', 'deconfigure_prefix_sets',
            'configure_bgp_filters', 'deconfigure_bgp_filters', 'configure_snmp_services',
            'deconfigure_snmp_services', 'configure_syslog_services', 'deconfigure_syslog_services',
            'configure_ipfix_services', 'deconfigure_ipfix_services', 'configure_vpn_profiles',
            'deconfigure_vpn_profiles', 'configure_lan_segments', 'deconfigure_lan_segments',
            'configure_site_lists', 'deconfigure_site_lists'
        ]
        module.fail_json(
            msg="Either 'operation' or 'state' parameter must be provided. "
                f"Supported operations: {', '.join(supported_operations)}"
        )

    # If operation is not specified, use state to determine operation
    if not operation:
        if state == 'present':
            operation = 'configure'
        elif state == 'absent':
            operation = 'deconfigure'

    # If operation is specified, it takes precedence over state
    # No additional mapping needed as operation is explicit

    # Handle check mode
    if module.check_mode:
        module.exit_json(
            changed=True,
            msg=f"Check mode: Would execute {operation}",
            operation=operation,
            config_file=config_file
        )

    try:
        # Get Graphiant connection
        connection = get_graphiant_connection(params)
        graphiant_config = connection.graphiant_config

        # Execute the requested operation
        changed = False
        result_msg = ""

        if operation == 'configure':
            result = execute_with_logging(module, graphiant_config.global_config.configure, config_file,
                                          success_msg="Successfully configured all global objects")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'deconfigure':
            result = execute_with_logging(module, graphiant_config.global_config.deconfigure, config_file,
                                          success_msg="Successfully deconfigured all global objects")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'configure_prefix_sets':
            result = execute_with_logging(module, graphiant_config.global_config.configure_prefix_sets,
                                          config_file,
                                          success_msg="Successfully configured global prefix sets")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'deconfigure_prefix_sets':
            result = execute_with_logging(module, graphiant_config.global_config.deconfigure_prefix_sets,
                                          config_file,
                                          success_msg="Successfully deconfigured global prefix sets")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'configure_bgp_filters':
            result = execute_with_logging(module, graphiant_config.global_config.configure_bgp_filters,
                                          config_file,
                                          success_msg="Successfully configured global BGP filters")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'deconfigure_bgp_filters':
            result = execute_with_logging(module, graphiant_config.global_config.deconfigure_bgp_filters,
                                          config_file,
                                          success_msg="Successfully deconfigured global BGP filters")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'configure_snmp_services':
            result = execute_with_logging(module, graphiant_config.global_config.configure_snmp_services,
                                          config_file,
                                          success_msg="Successfully configured global SNMP services")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'deconfigure_snmp_services':
            result = execute_with_logging(module, graphiant_config.global_config.deconfigure_snmp_services,
                                          config_file,
                                          success_msg="Successfully deconfigured global SNMP services")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'configure_syslog_services':
            result = execute_with_logging(module, graphiant_config.global_config.configure_syslog_services,
                                          config_file,
                                          success_msg="Successfully configured global syslog services")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'deconfigure_syslog_services':
            result = execute_with_logging(module, graphiant_config.global_config.deconfigure_syslog_services,
                                          config_file,
                                          success_msg="Successfully deconfigured global syslog services")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'configure_ipfix_services':
            result = execute_with_logging(module, graphiant_config.global_config.configure_ipfix_services,
                                          config_file,
                                          success_msg="Successfully configured global IPFIX services")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'deconfigure_ipfix_services':
            result = execute_with_logging(module, graphiant_config.global_config.deconfigure_ipfix_services,
                                          config_file,
                                          success_msg="Successfully deconfigured global IPFIX services")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'configure_vpn_profiles':
            result = execute_with_logging(module, graphiant_config.global_config.configure_vpn_profiles,
                                          config_file,
                                          success_msg="Successfully configured global VPN profiles")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'deconfigure_vpn_profiles':
            result = execute_with_logging(module, graphiant_config.global_config.deconfigure_vpn_profiles,
                                          config_file,
                                          success_msg="Successfully deconfigured global VPN profiles")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'configure_lan_segments':
            result = execute_with_logging(module, graphiant_config.global_config.configure_lan_segments,
                                          config_file,
                                          success_msg="Successfully configured global LAN segments")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'deconfigure_lan_segments':
            result = execute_with_logging(module, graphiant_config.global_config.deconfigure_lan_segments,
                                          config_file,
                                          success_msg="Successfully deconfigured global LAN segments")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'configure_site_lists':
            result = execute_with_logging(module, graphiant_config.global_config.configure_site_lists,
                                          config_file,
                                          success_msg="Successfully configured global site lists")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'deconfigure_site_lists':
            result = execute_with_logging(module, graphiant_config.global_config.deconfigure_site_lists,
                                          config_file,
                                          success_msg="Successfully deconfigured global site lists")
            changed = result['changed']
            result_msg = result['result_msg']

        # Return success
        module.exit_json(
            changed=changed,
            msg=result_msg,
            operation=operation,
            config_file=config_file
        )

    except Exception as e:
        error_msg = handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == '__main__':
    main()
