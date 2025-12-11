#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2025, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for managing Graphiant interfaces and circuits.

This module provides comprehensive interface management capabilities including:
- LAN interface configuration and deconfiguration
- WAN interface and circuit management
- Circuit-only operations (for static routes)
- Combined interface operations
"""

DOCUMENTATION = r'''
---
module: graphiant_interfaces
short_description: Manage Graphiant interfaces and circuits
description:
  - This module provides comprehensive interface and circuit management capabilities for Graphiant Edge devices.
  - Supports LAN interface configuration and deconfiguration for subinterfaces.
  - Enables WAN interface and circuit management with static routes.
  - Supports circuit-only operations for updating static routes without reconfiguring interfaces.
  - All operations use Jinja2 templates for consistent configuration deployment.
  - Configuration files support Jinja2 templating for dynamic generation.
version_added: "25.11.0"
notes:
  - "Interface Operations:"
  - "  - LAN interfaces: Configure/deconfigure subinterfaces for LAN connectivity."
  - "  - WAN interfaces: Configure/deconfigure WAN circuits and interfaces together."
  - "  - Circuits only: Update circuit configurations including static routes without touching interfaces."
  - "Configuration files support Jinja2 templating syntax for dynamic configuration generation."
  - "The module automatically resolves device names to IDs and validates configurations."
  - "All operations are idempotent and safe to run multiple times."
  - "For WAN operations, deconfigure_circuits should be run before deconfigure_wan_circuits_interfaces
  to remove static routes first."
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
  interface_config_file:
    description:
      - Path to the interface configuration YAML file.
      - Required for all operations.
      - Can be an absolute path or relative path. Relative paths are resolved using the configured config_path.
      - Configuration files support Jinja2 templating syntax for dynamic generation.
      - File must contain interface definitions with device names, interface names, and subinterface configurations.
    type: str
    required: true
  circuit_config_file:
    description:
      - Path to the circuit configuration YAML file.
      - Required for WAN and circuit operations (C(configure_wan_circuits_interfaces), C(deconfigure_wan_circuits_interfaces), C(configure_circuits), C(deconfigure_circuits)).  # noqa: E501
      - Optional for LAN-only operations.
      - Can be an absolute path or relative path. Relative paths are resolved using the configured config_path.
      - Configuration files support Jinja2 templating syntax for dynamic generation.
      - File must contain circuit definitions with static routes and circuit configurations.
    type: str
    required: false
  operation:
    description: "The specific interface operation to perform. C(configure_interfaces): Configure all interfaces (LAN and WAN) in one operation. C(deconfigure_interfaces): Deconfigure all interfaces. Resets parent interface to default LAN and deletes subinterfaces. C(configure_lan_interfaces): Configure LAN interfaces (subinterfaces) only. C(deconfigure_lan_interfaces): Deconfigure LAN interfaces (subinterfaces) only. C(configure_wan_circuits_interfaces): Configure WAN circuits and interfaces together. C(deconfigure_wan_circuits_interfaces): Deconfigure WAN circuits and interfaces together. C(configure_circuits): Configure circuits only. Can be called separately after interface is configured. C(deconfigure_circuits): Deconfigure circuits only. Removes static routes if any."
    type: str
    choices:
      - configure_interfaces
      - deconfigure_interfaces
      - configure_lan_interfaces
      - deconfigure_lan_interfaces
      - configure_wan_circuits_interfaces
      - deconfigure_wan_circuits_interfaces
      - configure_circuits
      - deconfigure_circuits
  state:
    description: "The desired state of the interfaces. C(present): Maps to C(configure_interfaces) when operation not specified. C(absent): Maps to C(deconfigure_interfaces) when operation not specified."
    type: str
    choices: [ present, absent ]
    default: present
  circuits_only:
    description:
      - If C(true), only circuits are affected in deconfigure operations.
      - Used with C(deconfigure_interfaces) and C(deconfigure_wan_circuits_interfaces) operations.
      - When C(true), static routes are removed but interfaces remain configured.
    type: bool
    default: false
  detailed_logs:
    description:
      - Enable detailed logging output for troubleshooting and monitoring.
      - When enabled, provides comprehensive logs of all interface operations.
      - Logs are captured and included in the result_msg for display using debug module.
    type: bool
    default: false

requirements:
  - python >= 3.10
  - graphiant-sdk >= 25.11.1

seealso:
  - module: graphiant.graphiant_playbooks.graphiant_global_config
    description: >
      Configure global objects (LAN segments, VPN profiles) that may be referenced
      in interface configurations.
  - module: graphiant.graphiant_playbooks.graphiant_bgp
    description: Configure BGP peering after interfaces are configured

author:
  - Graphiant Team (@graphiant)

'''

EXAMPLES = r'''
- name: Configure all interfaces (LAN and WAN)
  graphiant.graphiant_playbooks.graphiant_interfaces:
    operation: configure_interfaces
    interface_config_file: "sample_interface_config.yaml"
    circuit_config_file: "sample_circuit_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: configure_result

- name: Configure LAN interfaces only
  graphiant.graphiant_playbooks.graphiant_interfaces:
    operation: configure_lan_interfaces
    interface_config_file: "sample_interface_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Configure WAN circuits and interfaces
  graphiant.graphiant_playbooks.graphiant_interfaces:
    operation: configure_wan_circuits_interfaces
    interface_config_file: "sample_interface_config.yaml"
    circuit_config_file: "sample_circuit_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Configure circuits only (update static routes)
  graphiant.graphiant_playbooks.graphiant_interfaces:
    operation: configure_circuits
    interface_config_file: "sample_interface_config.yaml"
    circuit_config_file: "sample_circuit_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Deconfigure circuits (remove static routes)
  graphiant.graphiant_playbooks.graphiant_interfaces:
    operation: deconfigure_circuits
    interface_config_file: "sample_interface_config.yaml"
    circuit_config_file: "sample_circuit_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Deconfigure WAN circuits and interfaces
  graphiant.graphiant_playbooks.graphiant_interfaces:
    operation: deconfigure_wan_circuits_interfaces
    interface_config_file: "sample_interface_config.yaml"
    circuit_config_file: "sample_circuit_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Deconfigure all interfaces
  graphiant.graphiant_playbooks.graphiant_interfaces:
    operation: deconfigure_interfaces
    interface_config_file: "sample_interface_config.yaml"
    circuit_config_file: "sample_circuit_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Deconfigure interfaces using state parameter
  graphiant.graphiant_playbooks.graphiant_interfaces:
    state: absent
    interface_config_file: "sample_interface_config.yaml"
    circuit_config_file: "sample_circuit_config.yaml"
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
  sample: "Successfully configured all interfaces"
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
    - One of configure_interfaces, deconfigure_interfaces, configure_lan_interfaces, deconfigure_lan_interfaces,
      configure_wan_circuits_interfaces, deconfigure_wan_circuits_interfaces, configure_circuits,
      or deconfigure_circuits.
  type: str
  returned: always
  sample: "configure_interfaces"
interface_config_file:
  description:
    - The interface configuration file used for the operation.
  type: str
  returned: always
  sample: "sample_interface_config.yaml"
circuit_config_file:
  description:
    - The circuit configuration file used for the operation.
    - Only returned when circuit_config_file was provided.
  type: str
  returned: when applicable
  sample: "sample_circuit_config.yaml"
circuits_only:
  description:
    - Whether only circuits were affected in the operation.
  type: bool
  returned: always
  sample: false
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
    Main function for the Graphiant interfaces module.
    """

    # Define module arguments
    argument_spec = dict(
        host=dict(type='str', required=True, aliases=['base_url']),
        username=dict(type='str', required=True),
        password=dict(type='str', required=True, no_log=True),
        interface_config_file=dict(type='str', required=True),
        circuit_config_file=dict(type='str', required=False, default=None),
        operation=dict(
            type='str',
            required=False,
            choices=[
                'configure_interfaces',
                'deconfigure_interfaces',
                'configure_lan_interfaces',
                'deconfigure_lan_interfaces',
                'configure_wan_circuits_interfaces',
                'deconfigure_wan_circuits_interfaces',
                'configure_circuits',
                'deconfigure_circuits'
            ]
        ),
        circuits_only=dict(type='bool', required=False, default=False),
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
    interface_config_file = params['interface_config_file']
    circuit_config_file = params.get('circuit_config_file')
    circuits_only = params.get('circuits_only', False)

    # Validate that at least one of operation or state is provided
    if not operation and not state:
        supported_operations = [
            'configure_interfaces', 'deconfigure_interfaces', 'configure_lan_interfaces',
            'deconfigure_lan_interfaces', 'configure_wan_circuits_interfaces',
            'deconfigure_wan_circuits_interfaces', 'configure_circuits', 'deconfigure_circuits'
        ]
        module.fail_json(
            msg="Either 'operation' or 'state' parameter must be provided. "
                f"Supported operations: {', '.join(supported_operations)}"
        )

    # If operation is not specified, use state to determine operation
    if not operation:
        if state == 'present':
            operation = 'configure_interfaces'
        elif state == 'absent':
            operation = 'deconfigure_interfaces'

    # If operation is specified, it takes precedence over state
    # No additional mapping needed as operation is explicit

    # Validate operation-specific requirements
    circuit_operations = [
        'configure_wan_circuits_interfaces',
        'deconfigure_wan_circuits_interfaces',
        'configure_circuits',
        'deconfigure_circuits'
    ]

    if operation in circuit_operations and not circuit_config_file:
        module.fail_json(
            msg=f"Operation '{operation}' requires 'circuit_config_file' parameter"
        )

    # Handle check mode
    if module.check_mode:
        module.exit_json(
            changed=True,
            msg=f"Check mode: Would execute {operation}",
            operation=operation,
            interface_config_file=interface_config_file,
            circuit_config_file=circuit_config_file
        )

    try:
        # Get Graphiant connection
        connection = get_graphiant_connection(params)
        graphiant_config = connection.graphiant_config

        # Execute the requested operation
        changed = False
        result_msg = ""

        if operation == 'configure_interfaces':
            result = execute_with_logging(module, graphiant_config.interfaces.configure_interfaces,
                                          interface_config_file, circuit_config_file,
                                          success_msg="Successfully configured all interfaces")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'deconfigure_interfaces':
            result = execute_with_logging(module, graphiant_config.interfaces.deconfigure_interfaces,
                                          interface_config_file, circuit_config_file, circuits_only,
                                          success_msg="Successfully deconfigured all interfaces")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'configure_lan_interfaces':
            result = execute_with_logging(module, graphiant_config.interfaces.configure_lan_interfaces,
                                          interface_config_file,
                                          success_msg="Successfully configured LAN interfaces")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'deconfigure_lan_interfaces':
            result = execute_with_logging(module, graphiant_config.interfaces.deconfigure_lan_interfaces,
                                          interface_config_file,
                                          success_msg="Successfully deconfigured LAN interfaces")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'configure_wan_circuits_interfaces':
            result = execute_with_logging(module, graphiant_config.interfaces.configure_wan_circuits_interfaces,
                                          circuit_config_file, interface_config_file,
                                          success_msg="Successfully configured WAN circuits and interfaces")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'deconfigure_wan_circuits_interfaces':
            result = execute_with_logging(module, graphiant_config.interfaces.deconfigure_wan_circuits_interfaces,
                                          interface_config_file, circuit_config_file, circuits_only,
                                          success_msg="Successfully deconfigured WAN circuits and interfaces")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'configure_circuits':
            result = execute_with_logging(module, graphiant_config.interfaces.configure_circuits,
                                          circuit_config_file, interface_config_file,
                                          success_msg="Successfully configured circuits")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'deconfigure_circuits':
            result = execute_with_logging(module, graphiant_config.interfaces.deconfigure_circuits,
                                          circuit_config_file, interface_config_file,
                                          success_msg="Successfully deconfigured circuits")
            changed = result['changed']
            result_msg = result['result_msg']

        # Return success
        module.exit_json(
            changed=changed,
            msg=result_msg,
            operation=operation,
            interface_config_file=interface_config_file,
            circuit_config_file=circuit_config_file,
            circuits_only=circuits_only
        )

    except Exception as e:
        error_msg = handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == '__main__':
    main()
