#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2025, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for managing Graphiant site attachments and detachments.

This module provides site management capabilities including:
- Attaching global system objects to sites
- Detaching global system objects from sites
- Managing site-level configurations
"""

DOCUMENTATION = r'''
---
module: graphiant_sites
short_description: Manage Graphiant sites and object attachments
description:
  - This module provides comprehensive site management capabilities for Graphiant Edge devices.
  - Supports site creation and deletion.
  - Enables attachment and detachment of global system objects to/from sites.
  - Can perform site-only operations or object attachment operations independently.
  - All operations use Jinja2 templates for consistent configuration deployment.
  - Configuration files support Jinja2 templating for dynamic generation.
version_added: "25.11.0"
notes:
  - "Site Operations:"
  - "  - Configure: Create sites and attach global objects in one operation."
  - "  - Deconfigure: Detach global objects and delete sites in one operation."
  - "  - Configure Sites: Create sites only (without attaching objects)."
  - "  - Deconfigure Sites: Delete sites only (without detaching objects)."
  - "  - Attach Objects: Attach global objects to existing sites."
  - "  - Detach Objects: Detach global objects from sites (without deleting sites)."
  - "Configuration files support Jinja2 templating syntax for dynamic configuration generation."
  - "The module automatically resolves site names and global object names to IDs."
  - "All operations are idempotent and safe to run multiple times."
  - "Global objects must be created using C(graphiant_global_config) module before attaching to sites."
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
  site_config_file:
    description:
      - Path to the site configuration YAML file.
      - Required for all operations.
      - Can be an absolute path or relative path. Relative paths are resolved using the configured config_path.
      - Configuration files support Jinja2 templating syntax for dynamic generation.
      - File must contain site definitions with site names and global object attachments.
    type: str
    required: true
  operation:
    description:
      - "The specific site operation to perform."
      - "C(configure): Create sites and attach global objects in one operation."
      - "C(deconfigure): Detach global objects and delete sites in one operation."
      - "C(configure_sites): Create sites only (without attaching objects)."
      - "C(deconfigure_sites): Delete sites only (without detaching objects)."
      - "C(attach_objects): Attach global objects to existing sites."
      - "C(detach_objects): Detach global objects from sites (without deleting sites)."
    type: str
    choices:
      - configure
      - deconfigure
      - configure_sites
      - deconfigure_sites
      - attach_objects
      - detach_objects
  state:
    description:
      - "The desired state of the sites."
      - "C(present): Maps to C(configure) when operation not specified."
      - "C(absent): Maps to C(deconfigure) when operation not specified."
    type: str
    choices: [ present, absent ]
    default: present
  detailed_logs:
    description:
      - Enable detailed logging output for troubleshooting and monitoring.
      - When enabled, provides comprehensive logs of all site operations.
      - Logs are captured and included in the result_msg for display using debug module.
    type: bool
    default: false

requirements:
  - python >= 3.10
  - graphiant-sdk >= 25.12.1

seealso:
  - module: graphiant.naas.graphiant_global_config
    description: Configure global objects (LAN segments, prefix sets, etc.) that can be attached to sites
  - module: graphiant.naas.graphiant_data_exchange
    description: Use sites in Data Exchange service configurations

author:
  - Graphiant Team (@graphiant)

'''

EXAMPLES = r'''
- name: Configure sites (create sites and attach objects)
  graphiant.naas.graphiant_sites:
    operation: configure
    site_config_file: "sample_sites.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: sites_result

- name: Create sites only
  graphiant.naas.graphiant_sites:
    operation: configure_sites
    site_config_file: "sample_sites.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Attach global objects to existing sites
  graphiant.naas.graphiant_sites:
    operation: attach_objects
    site_config_file: "sample_site_attachments.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Detach global objects from sites
  graphiant.naas.graphiant_sites:
    operation: detach_objects
    site_config_file: "sample_site_attachments.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Delete sites only
  graphiant.naas.graphiant_sites:
    operation: deconfigure_sites
    site_config_file: "sample_sites.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Deconfigure sites (detach objects and delete sites)
  graphiant.naas.graphiant_sites:
    operation: deconfigure
    site_config_file: "sample_sites.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

- name: Configure sites using state parameter
  graphiant.naas.graphiant_sites:
    state: present
    site_config_file: "sample_sites.yaml"
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
  sample: "Successfully configured (created sites and attached objects)"
changed:
  description:
    - Whether the operation made changes to the system.
    - C(true) for all configure/deconfigure/attach/detach operations.
  type: bool
  returned: always
  sample: true
operation:
  description:
    - The operation that was performed.
    - One of configure, deconfigure, configure_sites, deconfigure_sites, attach_objects, or detach_objects.
  type: str
  returned: always
  sample: "configure"
site_config_file:
  description:
    - The site configuration file used for the operation.
  type: str
  returned: always
  sample: "sample_sites.yaml"
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
    Main function for the Graphiant sites module.
    """

    # Define module arguments
    argument_spec = dict(
        host=dict(type='str', required=True, aliases=['base_url']),
        username=dict(type='str', required=True),
        password=dict(type='str', required=True, no_log=True),
        site_config_file=dict(type='str', required=True),
        operation=dict(
            type='str',
            required=False,
            choices=[
                'configure',
                'deconfigure',
                'configure_sites',
                'deconfigure_sites',
                'attach_objects',
                'detach_objects'
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
    site_config_file = params['site_config_file']

    # Validate that at least one of operation or state is provided
    if not operation and not state:
        supported_operations = ['configure', 'deconfigure', 'configure_sites', 'deconfigure_sites',
                                'attach_objects', 'detach_objects']
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
            site_config_file=site_config_file
        )

    try:
        # Get Graphiant connection
        connection = get_graphiant_connection(params)
        graphiant_config = connection.graphiant_config

        # Execute the requested operation
        changed = False
        result_msg = ""

        if operation == 'configure':
            result = execute_with_logging(module, graphiant_config.sites.configure, site_config_file,
                                          success_msg="Successfully configured (created sites and attached objects)")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'deconfigure':
            result = execute_with_logging(module, graphiant_config.sites.deconfigure, site_config_file,
                                          success_msg="Successfully deconfigured (detached objects and deleted sites)")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'configure_sites':
            result = execute_with_logging(module, graphiant_config.sites.configure_sites, site_config_file,
                                          success_msg="Successfully created sites")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation == 'deconfigure_sites':
            result = execute_with_logging(module, graphiant_config.sites.deconfigure_sites, site_config_file,
                                          success_msg="Successfully deleted sites")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation.lower().startswith('attach'):
            result = execute_with_logging(module, graphiant_config.sites.attach_objects, site_config_file,
                                          success_msg="Successfully attached global system objects to sites")
            changed = result['changed']
            result_msg = result['result_msg']

        elif operation.lower().startswith('detach'):
            result = execute_with_logging(module, graphiant_config.sites.detach_objects, site_config_file,
                                          success_msg="Successfully detached global system objects from sites")
            changed = result['changed']
            result_msg = result['result_msg']

        # Return success
        module.exit_json(
            changed=changed,
            msg=result_msg,
            operation=operation,
            site_config_file=site_config_file
        )

    except Exception as e:
        error_msg = handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == '__main__':
    main()
