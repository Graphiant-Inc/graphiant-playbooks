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
      - This parameter is marked C(no_log) in the module to avoid leaking credentials.
    type: str
    required: true
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
      - C(show_validated_payload) shows the SDK-validated payload (dry-run).
    type: str
    required: false
    choices: [ configure, deconfigure, show_validated_payload ]
  validated_operation:
    description:
      - When I(operation=show_validated_payload), controls whether the module validates the C(configure) or C(deconfigure) payload shape.
      - "If omitted, defaults based on I(state): C(configure) for C(present) and C(deconfigure) for C(absent)."
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
    description: Supports check mode with partial support.
    support: partial
    details: >
      In check mode the module exits without making API calls, so it does not compare
      intended state to current device state. For C(configure) and C(deconfigure) it
      returns V(changed=True) (assumes changes would be made). For C(show_validated_payload)
      it returns V(changed=False).

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

- name: Show validated payload (dry-run)
  graphiant.naas.graphiant_static_routes:
    operation: show_validated_payload
    static_routes_config_file: "sample_static_route.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    # validate configure payload (default for state=present)
    state: present

- name: Show validated payload for deconfigure (dry-run)
  graphiant.naas.graphiant_static_routes:
    operation: show_validated_payload
    static_routes_config_file: "sample_static_route.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    validated_operation: deconfigure
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
    - V(true) when config was pushed to at least one device; V(false) when intended state already matched.
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
validated_payload:
  description: SDK-validated payload returned by I(operation=show_validated_payload).
  type: dict
  returned: when I(operation=show_validated_payload)
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.graphiant.naas.plugins.module_utils.graphiant_utils import (
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
        host=dict(type='str', required=True, aliases=['base_url']),
        username=dict(type='str', required=True),
        password=dict(type='str', required=True, no_log=True),
        static_routes_config_file=dict(type='str', required=True, aliases=['static_route_config_file']),
        operation=dict(type='str', required=False, choices=['configure', 'deconfigure', 'show_validated_payload']),
        validated_operation=dict(type='str', required=False, choices=['configure', 'deconfigure']),
        state=dict(type='str', required=False, default='present', choices=['present', 'absent']),
        detailed_logs=dict(type='bool', required=False, default=False),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    params = module.params
    operation = params.get('operation')
    state = params.get('state', 'present')
    cfg_file = params['static_routes_config_file']
    validated_operation = params.get('validated_operation')

    if not operation:
        operation = 'configure' if state == 'present' else 'deconfigure'

    if module.check_mode:
        if operation == 'show_validated_payload':
            validate_op = validated_operation or ('configure' if state == 'present' else 'deconfigure')
            module.exit_json(
                changed=False,
                msg=f"Check mode: Would validate {validate_op} payload from {cfg_file} (no changes made)",
                operation=operation,
                static_routes_config_file=cfg_file,
                validated_operation=validate_op,
            )
        module.exit_json(
            changed=True,
            msg=f"Check mode: Would execute {operation} (assumes changes would be made)",
            operation=operation,
            static_routes_config_file=cfg_file,
        )

    try:
        connection = get_graphiant_connection(params)
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
        else:  # show_validated_payload
            validate_op = validated_operation or ('configure' if state == 'present' else 'deconfigure')
            validated = graphiant_config.static_routes.show_validated_payload(cfg_file, operation=validate_op)
            module.exit_json(
                changed=False,
                msg="Successfully previewed validated payload for static routes",
                operation=operation,
                static_routes_config_file=cfg_file,
                validated_operation=validate_op,
                validated_payload=validated,
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
