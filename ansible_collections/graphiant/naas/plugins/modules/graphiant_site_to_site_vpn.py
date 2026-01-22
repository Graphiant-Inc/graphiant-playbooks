#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2025, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for managing Graphiant Site-to-Site VPN configuration.

This module provides Site-to-Site VPN management capabilities including:
- Site-to-Site VPN configuration on edge devices
- Site-to-Site VPN deconfiguration
"""

DOCUMENTATION = r'''
---
module: graphiant_site_to_site_vpn
short_description: Manage Graphiant Site-to-Site VPN configuration
description:
  - This module provides comprehensive Site-to-Site VPN management for Graphiant Edge devices.
  - Supports Site-to-Site VPN configuration and deconfiguration with static or BGP routing.
  - All operations use Jinja2 templates for consistent configuration deployment.
  - Configuration files support Jinja2 templating for dynamic generation.
version_added: "25.13.0"
notes:
  - "Site-to-Site VPN Operations:"
  - "  - Configure: Configure Site-to-Site VPN connections on edge devices."
  - "  - Deconfigure: Remove Site-to-Site VPN connections from edge devices."
  - "Configuration files support Jinja2 templating syntax for dynamic configuration generation."
  - "The module automatically resolves device names to IDs."
  - "All operations are idempotent and safe to run multiple times."
  - "Circuits and interfaces must be configured first before applying Site-to-Site VPN."
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
  site_to_site_vpn_config_file:
    description:
      - Path to the Site-to-Site VPN configuration YAML file.
      - Required for all operations.
      - Can be an absolute path or relative path. Relative paths are resolved using the configured config_path.
      - Configuration files support Jinja2 templating syntax for dynamic generation.
      - File must contain Site-to-Site VPN definitions with device names and VPN configurations.
    type: str
    required: true
  operation:
    description:
      - "The specific Site-to-Site VPN operation to perform."
      - "V(configure): Configure Site-to-Site VPN connections on edge devices."
      - "V(deconfigure): Deconfigure Site-to-Site VPN connections from edge devices."
    type: str
    choices:
      - configure
      - deconfigure
  state:
    description:
      - "The desired state of the Site-to-Site VPN configuration."
      - "V(present): Maps to V(configure) when O(operation) not specified."
      - "V(absent): Maps to V(deconfigure) when O(operation) not specified."
    type: str
    choices: [ present, absent ]
    default: present
  detailed_logs:
    description:
      - Enable detailed logging output for troubleshooting and monitoring.
      - When enabled, provides comprehensive logs of all Site-to-Site VPN operations.
      - Logs are captured and included in the result_msg for display using M(ansible.builtin.debug) module.
    type: bool
    default: false

attributes:
  check_mode:
    description: Supports check mode with partial support.
    support: partial
    details: >
      The module cannot accurately determine whether changes would actually be made without
      querying the current state via API calls. In check mode, the module assumes that changes
      would be made and returns V(changed=True) for all operations (V(configure), V(deconfigure)).
      This means that check mode may report changes even when the configuration is already
      applied. The module does not perform state comparison in check mode due to API limitations.

requirements:
  - python >= 3.7
  - graphiant-sdk >= 25.12.1

seealso:
  - module: graphiant.naas.graphiant_interfaces
    description: Configure interfaces before setting up Site-to-Site VPN
  - module: graphiant.naas.graphiant_device_config
    description: Alternative method for device configuration

author:
  - Graphiant Team (@graphiant)

'''

EXAMPLES = r'''
- name: Configure Site-to-Site VPN
  graphiant.naas.graphiant_site_to_site_vpn:
    operation: configure
    site_to_site_vpn_config_file: "sample_site_to_site_vpn.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: vpn_result

- name: Deconfigure Site-to-Site VPN
  graphiant.naas.graphiant_site_to_site_vpn:
    operation: deconfigure
    site_to_site_vpn_config_file: "sample_site_to_site_vpn.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Configure Site-to-Site VPN using state parameter
  graphiant.naas.graphiant_site_to_site_vpn:
    state: present
    site_to_site_vpn_config_file: "sample_site_to_site_vpn.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Deconfigure Site-to-Site VPN using state parameter
  graphiant.naas.graphiant_site_to_site_vpn:
    state: absent
    site_to_site_vpn_config_file: "sample_site_to_site_vpn.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
'''

RETURN = r'''
msg:
  description:
    - Result message from the operation, including detailed logs when O(detailed_logs) is enabled.
  type: str
  returned: always
  sample: "Successfully configured Site-to-Site VPN"
changed:
  description:
    - Whether the operation made changes to the system.
    - V(true) for all configure/deconfigure operations.
  type: bool
  returned: always
  sample: true
operation:
  description:
    - The operation that was performed.
    - One of V(configure) or V(deconfigure).
  type: str
  returned: always
  sample: "configure"
site_to_site_vpn_config_file:
  description:
    - The Site-to-Site VPN configuration file used for the operation.
  type: str
  returned: always
  sample: "sample_site_to_site_vpn.yaml"
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
    """
    Main function for the Graphiant Site-to-Site VPN module.
    """

    # Define module arguments
    argument_spec = dict(
        host=dict(type='str', required=True, aliases=['base_url']),
        username=dict(type='str', required=True),
        password=dict(type='str', required=True, no_log=True),
        site_to_site_vpn_config_file=dict(type='str', required=True),
        operation=dict(
            type='str',
            required=False,
            choices=[
                'configure',
                'deconfigure'
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
    site_to_site_vpn_config_file = params['site_to_site_vpn_config_file']

    # Validate that at least one of operation or state is provided
    if not operation and not state:
        supported_operations = ['configure', 'deconfigure']
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
        # All Site-to-Site VPN operations make changes
        # Note: Check mode assumes changes would be made as we cannot determine
        # current state without making API calls. In practice, these operations
        # typically result in changes unless the configuration is already applied.
        module.exit_json(
            changed=True,
            msg=f"Check mode: Would execute {operation} (assumes changes would be made)",
            operation=operation,
            site_to_site_vpn_config_file=site_to_site_vpn_config_file
        )

    try:
        # Get Graphiant connection
        connection = get_graphiant_connection(params)
        graphiant_config = connection.graphiant_config

        # Execute the requested operation
        changed = False
        result_msg = ""

        if operation == 'configure':
            result = execute_with_logging(
                module,
                graphiant_config.site_to_site_vpn.configure_site_to_site_vpn,
                site_to_site_vpn_config_file,
                success_msg="Successfully configured Site-to-Site VPN"
            )
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'deconfigure':
            result = execute_with_logging(
                module,
                graphiant_config.site_to_site_vpn.deconfigure_site_to_site_vpn,
                site_to_site_vpn_config_file,
                success_msg="Successfully deconfigured Site-to-Site VPN"
            )
            changed = result['changed']
            result_msg = result['result_msg']

        # Return success
        module.exit_json(
            changed=changed,
            msg=result_msg,
            operation=operation,
            site_to_site_vpn_config_file=site_to_site_vpn_config_file
        )

    except Exception as e:
        error_msg = handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == '__main__':
    main()
