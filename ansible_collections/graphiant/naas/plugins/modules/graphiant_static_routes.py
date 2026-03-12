#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for managing Graphiant static routes under:
  edge.segments.<segment>.staticRoutes
"""

DOCUMENTATION = r'''
---
module: graphiant_static_routes
short_description: Manage Graphiant static routes (edge.segments.*.staticRoutes)
description:
  - Configure or delete static routes under edge segments (edge.segments.<segment>.staticRoutes).
  - Reads a structured YAML config file and builds the raw device-config payload in Python.
  - All operations are idempotent and safe to run multiple times.
notes:
  - "Static Routes Operations:"
  - "  - Configure: Create/update static routes listed in the config."
  - "  - Deconfigure: Delete static routes listed in the config."
  - "Configuration files support Jinja2 templating syntax for dynamic configuration generation."
  - "The module automatically resolves device names to IDs."
  - "YAML schema uses camelCase keys (for example: C(staticRoutes), C(lanSegment), C(destinationPrefix), C(nextHops))."
  - "Configure idempotency: compares intended routes to existing device state per segment + prefix; skips push when already matched (V(changed)=V(false))."
  - "Deconfigure deletes only the prefixes listed in the YAML (per segment)."
  - "Deconfigure payload uses C(route: null) per prefix; this module preserves nulls in the final payload pushed to the API."
version_added: "26.2.0"
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
options:
  static_routes_config_file:
    description:
      - Path to the static routes YAML file.
      - Can be an absolute path or relative to the configured config_path.
      - Expected top-level key is C(staticRoutes) (list of devices).
    type: str
    required: true
    aliases: [ static_route_config_file ]
  operation:
    description:
      - Specific operation to perform.
      - C(configure) builds full route objects.
      - C(deconfigure) deletes listed routes by setting route=null for each prefix.
    type: str
    required: false
    choices: [ configure, deconfigure ]
  state:
    description:
      - Desired state for routes.
      - C(present) maps to C(configure); C(absent) maps to C(deconfigure) if operation not set.
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
      In check mode, no configuration is pushed to devices, but the module still reads current
      device state to determine whether changes would be made. Payloads that would be pushed are
      logged with a C([check_mode]) prefix.

requirements:
  - python >= 3.7
  - graphiant-sdk >= 26.2.1

seealso:
  - module: graphiant.naas.graphiant_global_config
    description: Configure LAN segments before applying routes (if needed)
  - module: graphiant.naas.graphiant_interfaces
    description: Configure interfaces before applying routes (if needed)
  - module: graphiant.naas.graphiant_device_config
    description: Alternative method for pushing full device config payloads

author:
  - Graphiant Team (@graphiant)
'''

EXAMPLES = r'''
- name: Configure static routes
  graphiant.naas.graphiant_static_routes:
    operation: configure
    static_routes_config_file: "sample_static_route.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: static_routes_result
  no_log: true

- name: Display result message (includes detailed logs)
  ansible.builtin.debug:
    msg: "{{ static_routes_result.msg }}"

- name: Deconfigure static routes (deletes only prefixes listed in YAML)
  graphiant.naas.graphiant_static_routes:
    operation: deconfigure
    static_routes_config_file: "sample_static_route.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

'''

RETURN = r'''
msg:
  description:
    - Result message from the operation, including detailed logs when O(detailed_logs) is enabled.
  type: str
  returned: always
  sample: "Static routes already match desired state; no changes needed"
changed:
  description:
    - Whether the operation made changes.
    - V(true) when config would be pushed to at least one device; V(false) when intended state already matched.
    - In check mode (C(--check)), no configuration is pushed, but V(changed) reflects whether changes would be made.
  type: bool
  returned: always
  sample: false
operation:
  description: The operation performed.
  type: str
  returned: always
  sample: "configure"
static_routes_config_file:
  description: The static routes config file used for the operation.
  type: str
  returned: always
  sample: "sample_static_route.yaml"
configured_devices:
  description: Device names where configuration was pushed (when changed=true).
  type: list
  elements: str
  returned: when supported
  sample: ["edge-1-sdktest"]
skipped_devices:
  description: Device names that were skipped because desired state already matched.
  type: list
  elements: str
  returned: when supported
  sample: ["edge-1-sdktest"]
details:
  description: Raw manager result details (includes changed/configured_devices/skipped_devices).
  type: dict
  returned: when supported
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.graphiant.naas.plugins.module_utils.graphiant_utils import (
    graphiant_portal_auth_argument_spec,
    get_graphiant_connection,
    handle_graphiant_exception,
)
from ansible_collections.graphiant.naas.plugins.module_utils.logging_decorator import (
    capture_library_logs,
)


@capture_library_logs
def execute_with_logging(module, func, *args, **kwargs):
    success_msg = kwargs.pop('success_msg', 'Operation completed successfully')
    no_change_msg = kwargs.pop('no_change_msg', 'No changes needed')
    result = func(*args, **kwargs)
    if isinstance(result, dict) and 'changed' in result:
        changed = bool(result.get('changed'))
        configured = result.get('configured_devices') or []
        skipped = result.get('skipped_devices') or []

        if changed:
            msg = success_msg
        else:
            # Make "ok/no-change" messaging explicit and useful.
            msg = no_change_msg
            if skipped:
                msg += f" (skipped {len(skipped)} device(s))"

        return {'changed': changed, 'result_msg': msg, 'details': result, 'configured_devices': configured, 'skipped_devices': skipped}
    return {'changed': True, 'result_msg': success_msg, 'details': result}


def main():
    argument_spec = dict(
        **graphiant_portal_auth_argument_spec(),
        static_routes_config_file=dict(type='str', required=True, aliases=['static_route_config_file']),
        operation=dict(type='str', required=False, choices=['configure', 'deconfigure']),
        state=dict(type='str', required=False, default='present', choices=['present', 'absent']),
        detailed_logs=dict(type='bool', required=False, default=False),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    params = module.params
    operation = params.get('operation')
    state = params.get('state', 'present')
    cfg_file = params['static_routes_config_file']

    if not operation:
        operation = 'configure' if state == 'present' else 'deconfigure'

    try:
        # In check_mode, connection runs all logic but gsdk skips API writes and logs payloads only.
        connection = get_graphiant_connection(params, check_mode=module.check_mode)
        graphiant_config = connection.graphiant_config

        if operation == 'configure':
            result = execute_with_logging(
                module,
                graphiant_config.static_routes.configure,
                cfg_file,
                success_msg="Successfully configured static routes",
                no_change_msg="Static routes already match desired state; no changes needed",
            )
        elif operation == 'deconfigure':
            result = execute_with_logging(
                module,
                graphiant_config.static_routes.deconfigure,
                cfg_file,
                success_msg="Successfully deconfigured static routes",
                no_change_msg="Static routes already absent (or already removed); no changes needed",
            )
        else:
            module.fail_json(
                msg=f"Unsupported operation '{operation}'. Supported operations: configure, deconfigure.",
                operation=operation,
            )

        module.exit_json(
            changed=result['changed'],
            msg=result['result_msg'],
            operation=operation,
            static_routes_config_file=cfg_file,
            configured_devices=result.get('configured_devices', []),
            skipped_devices=result.get('skipped_devices', []),
            details=result.get('details', {}),
        )

    except Exception as e:
        error_msg = handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == '__main__':
    main()
