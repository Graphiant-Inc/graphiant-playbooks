#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for managing Graphiant OSPFv2 configuration under:
  edge.segment.*.ospfv2
"""

DOCUMENTATION = r"""
---
module: graphiant_ospfv2
short_description: >-
  Manage Graphiant OSPFv2 configuration (edge.segments.*.ospfv2)
description:
  - Configure or delete OSPFv2 processes under edge segments (edge.segments.<segment>.ospfv2).
  - Reads a structured YAML config file and builds the raw device-config payload in Python.
  - All operations are idempotent and safe to run multiple times.
notes:
  - "OSPF Operations:"
  - "  - Configure: Create/update OSPFv2 processes listed in the config."
  - "  - Deconfigure: Delete OSPFv2 processes listed in the config."
  - "Configuration files support Jinja2 templating syntax for dynamic configuration generation."
  - "The module automatically resolves device names to IDs."
  - "YAML schema uses camelCase keys (for example: C(staticRoutes), C(lanSegment), C(destinationPrefix), C(nextHops))."
  - "Vault (configure only): O(vault_ospf_md5_passwords)."
  - "Use encrypted I(configs/vault_secrets.yml), I(configs/vault-password-file.sh); no plaintext."
  - "Load with M(ansible.builtin.include_vars) (no_log true); pass the dict so secrets stay in memory."
  - >-
    Vault keys are C(device name) -> C(interfaceName). Leave C(authentication.key) null in YAML
    to fill it from vault. See I(configs/vault_secrets.yml.example).
  - >-
    Configure idempotency: compares intended routes to existing device state per segment + prefix;
    skips push when already matched (V(changed)=V(false)).
  - "Deconfigure deletes only the prefixes listed in the YAML (per segment)."
  - >-
    Deconfigure payload uses C(route: null) per prefix; this module preserves nulls in the final
    payload pushed to the API.
version_added: "26.5.0"
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
options:
  ospfv2_config_file:
    description:
      - Path to the ospf YAML file.
      - Can be an absolute path or relative to the configured config_path.
      - Expected top-level key is C(networkLists) and C(portLists) (list of devices).
    type: str
    required: true
    aliases: [ ospf_config_file ]
  operation:
    description:
      - Specific operation to perform.
      - C(configure) builds full OSPF process objects.
      - C(deconfigure) deletes OSPF processes for listed segments.

    type: str
    required: false
    choices: [configure, deconfigure]
  state:
    description:
      - Desired state for OSPF processes.
      - >-
        C(present) maps to C(configure); C(absent) maps to C(deconfigure) if operation not set
    type: str
    required: false
    default: present
    choices: [ present, absent ]

  detailed_logs:
    description:
      - Enable detailed logging.
    type: bool
    default: false
  vault_ospf_md5_passwords:
    description:
      - >-
        Dict of device name to interface name to OSPF MD5 authentication key (configure only).
        Pass from playbook vars loaded from encrypted I(vault_secrets.yml); secrets in memory only.
      - >-
        Keys must match the device name and C(interfaceName) under that device's areas/interfaces in
        the OSPF config. Optional; used only when an interface's C(authentication.key) is null in YAML.
    type: dict
    default: {}
    required: false
attributes:
  check_mode:
    description: Supports check mode.
    support: full
    details: >
      In check mode, no configuration is pushed to devices, but the module still reads current
      device state to determine whether changes would be made. Payloads that would be pushed are
      logged with a C([check_mode]) prefix.
  diff_mode:
    description: Supports Ansible's C(--diff) for pending traffic policy list updates.
    support: full
    details: >
      When the playbook runs with C(--diff) and a device would change, the module returns a C(diff)
      dictionary (C(before) / C(after) strings). Structured entries are also in C(details.diff_plan).

requirements:
  - python >= 3.7
  - graphiant-sdk >= 26.7.0 (required for OSPFv2 interface MD5 authentication support)

author:
  - Graphiant Team (@graphiant)
"""

EXAMPLES = r"""
- name: Configure OSPF
  graphiant.naas.graphiant_ospfv2:
    operation: configure
    ospfv2_config_file: "sample_ospfv2_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
    state: present
  register: ospfv2_result
  no_log: true

- name: Display result message (includes detailed logs)
  ansible.builtin.debug:
    msg: "{{ ospfv2_result.msg }}"

- name: Configure OSPF with MD5 auth keys from Ansible Vault (leave authentication.key null in YAML)
  graphiant.naas.graphiant_ospfv2:
    operation: configure
    ospfv2_config_file: "sample_ospfv2_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    vault_ospf_md5_passwords: "{{ vault_ospf_md5_passwords | default({}) }}"
    state: present
  register: ospfv2_result

- name: Deconfigure OSPF (deletes only OSPF processes listed in YAML)
  graphiant.naas.graphiant_ospfv2:
    operation: deconfigure
    ospfv2_config_file: "sample_ospfv2_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
    state: absent
  no_log: true
"""

RETURN = r"""
msg:
  description:
    - Result message from the operation, including detailed logs when O(detailed_logs) is enabled.
  type: str
  returned: always
  sample: "OSPF processes already match desired state; no changes needed"
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
ospfv2_config_file:
  description: The OSPFv2 config file used for the operation.
  type: str
  returned: always
  sample: "sample_ospfv2_config.yaml"
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
  description: Raw manager result details (includes changed/configured/skipped device lists).
  type: dict
  returned: when supported
diff:
  description: Ansible C(--diff) payload showing per-device before/after OSPF state.
  type: dict
  returned: when playbook uses C(--diff) and at least one device would be updated
"""

from ansible.module_utils.basic import AnsibleModule  # noqa: E402

from ansible_collections.graphiant.naas.plugins.module_utils.graphiant_utils import (  # noqa: E402
    ansible_module_log,
    get_graphiant_connection,
    graphiant_portal_auth_argument_spec,
    handle_graphiant_exception,
)
from ansible_collections.graphiant.naas.plugins.module_utils.libs.device_config_common import (  # noqa: E402
    apply_module_diff,
)
from ansible_collections.graphiant.naas.plugins.module_utils.logging_decorator import (  # noqa: E402
    capture_library_logs,
)


@capture_library_logs
def execute_with_logging(module, func, *args, **kwargs):
    success_msg = kwargs.pop("success_msg", "Operation completed successfully")
    no_change_msg = kwargs.pop("no_change_msg", "No changes needed")
    try:
        result = func(*args, **kwargs)
    except Exception as e:
        if module.params.get("detailed_logs"):
            name = getattr(func, "__name__", str(func))
            ansible_module_log(
                module,
                f"graphiant_ospfv2: manager {name!s} failed: {type(e).__name__}: {e!s}",
            )
        raise
    if isinstance(result, dict) and "changed" in result:
        changed = bool(result.get("changed"))
        configured = result.get("configured_devices") or []
        skipped = result.get("skipped_devices") or []

        if changed:
            msg = success_msg
        else:
            # Make "ok/no-change" messaging explicit and useful.
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
    return {"changed": True, "result_msg": success_msg, "details": result}


def main():
    argument_spec = dict(
        **graphiant_portal_auth_argument_spec(),
        ospfv2_config_file=dict(type="str", required=True, aliases=["ospf_config_file"]),
        operation=dict(type="str", required=False, choices=["configure", "deconfigure"]),
        state=dict(type="str", required=False, default="present", choices=["present", "absent"]),
        detailed_logs=dict(type="bool", required=False, default=False),
        vault_ospf_md5_passwords=dict(type="dict", required=False, default={}, no_log=True),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    params = module.params
    operation = params.get("operation")
    state = params.get("state", "present")
    cfg_file = params["ospfv2_config_file"]

    if not operation:
        operation = "configure" if state == "present" else "deconfigure"

    try:
        if params.get("detailed_logs"):
            ansible_module_log(
                module,
                (
                    f"graphiant_ospfv2: start operation={operation!r} "
                    f"ospfv2_config_file={cfg_file!r} check_mode={module.check_mode!r}"
                ),
            )
        # In check_mode, connection runs all logic but gsdk skips API writes and logs payloads only.
        connection = get_graphiant_connection(params, check_mode=module.check_mode)
        graphiant_config = connection.graphiant_config
        if params.get("detailed_logs"):
            ansible_module_log(
                module,
                "graphiant_ospfv2: GraphiantConfig obtained; dispatching to ospfv2 manager",
            )

        # Execute the requested operation
        changed = False
        result_msg = ""

        if operation == "configure":
            vault_ospf_md5_passwords = params.get("vault_ospf_md5_passwords") or {}
            result = execute_with_logging(
                module,
                graphiant_config.ospfv2.configure,
                cfg_file,
                vault_ospf_md5_passwords,
                success_msg="Successfully configured ospfv2",
                no_change_msg="ospfv2 already match desired state; no changes needed",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]
        elif operation == "deconfigure":
            result = execute_with_logging(
                module,
                graphiant_config.ospfv2.deconfigure,
                cfg_file,
                success_msg="Successfully deconfigured ospfv2 process",
                no_change_msg="ospfv2 process already absent (or already removed); no changes needed",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]
        else:
            module.fail_json(
                msg=f"Unsupported operation '{operation}'. Supported operations: configure, deconfigure.",
                operation=operation,
            )
            return

        if params.get("detailed_logs"):
            preview = result_msg if len(result_msg) <= 200 else (result_msg[:200] + "…")
            ansible_module_log(
                module,
                f"graphiant_ospfv2: success changed={changed!r} result_msg_preview={preview!r}",
            )
        details = result.get("details") or {}
        exit_payload = dict(
            changed=changed,
            msg=result_msg,
            operation=operation,
            ospfv2_config_file=cfg_file,
            configured_devices=result.get("configured_devices", []),
            skipped_devices=result.get("skipped_devices", []),
            details=details,
        )
        apply_module_diff(module, exit_payload, details)
        module.exit_json(**exit_payload)

    except Exception as e:
        if module.params.get("detailed_logs"):
            import traceback

            ansible_module_log(
                module,
                f"graphiant_ospfv2: {type(e).__name__}: {e!s}\n{traceback.format_exc()}",
            )
        else:
            ansible_module_log(
                module,
                f"graphiant_ospfv2: failed {type(e).__name__}: {e!s}",
            )
        error_msg = handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == "__main__":
    main()
