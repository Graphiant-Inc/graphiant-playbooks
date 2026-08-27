#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for managing Graphiant gateway Public VIF services.

This module provides Public VIF ("local data exchange service") management capabilities
including:
- Public VIF service creation, update, and deletion
"""

DOCUMENTATION = r"""
---
module: graphiant_public_vif
short_description: Manage Graphiant gateway Public VIF (local data exchange) services
description:
  - Manages gateway Public VIF services — a producer LAN segment (VRF) exposed over BGP through
    one or more Graphiant-managed gateways, in a chosen cloud region/provider, to a cloud router
    and to one or more consumer LAN segments.
  - Supports creating, updating, and deleting services.
version_added: "26.8.0"
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
notes:
  - "Configuration files support Jinja2 templating syntax for dynamic configuration generation."
  - >-
    Names given for I(lanSegment), I(region), I(advertisement.sites), and
    I(advertisement.siteLists) are resolved to IDs.
  - >-
    I(gatewayBgpNeighbors) (per-gateway BGP peering) and I(natPrefixStrategy) (per-gateway NAT
    prefix) share the same key space — the gateway device name or ID — and every key in one
    should have a matching entry in the other. I(consumerLanSegments) is a separate key space,
    keyed by consumer LAN segment name. See C(sample_public_vif_services.yaml).
  - >-
    Before any write, each configured gateway is checked against what's actually provisioned
    for the resolved I(region)/I(storageProvider); each neighbor's I(localInterface) is checked
    against that gateway's real interfaces; and the resolved I(lanSegment) is checked against
    what's configured on those gateways. A bad reference fails fast with a clear error instead
    of a confusing API rejection or a silently wrong VRF.
  - >-
    Each I(gatewayBgpNeighbors) entry's C(enabled)/C(bfd) fields are not user-configurable —
    the module always enables the neighbor and disables BFD (not yet supported for Public VIF).
  - >-
    Vault (create_services/update_services only): O(vault_public_vif_bgp_md5_passwords), keyed
    by C(service name) -> C(gateway name), fills a neighbor's C(md5Password) when left null in
    YAML (YAML value wins if set). Load from an encrypted vault file with
    M(ansible.builtin.include_vars) (no_log true); see I(configs/vault_secrets.yml.example).
    C(md5Password), from either source, is always redacted as C(********) in logs and C(--diff).
  - "V(create_services)/V(delete_services) are idempotent, matched by I(serviceName)."
  - >-
    V(update_services) is a full replace, not a merge — the config must contain the complete
    desired service; anything omitted (a field, or a I(gatewayBgpNeighbors)/
    I(consumerLanSegments)/I(natPrefixStrategy) entry) is removed. It does not compare against
    live state first, so every run reports C(changed=true) — see
    C(sample_public_vif_services_update.yaml).
  - >-
    Check mode (C(--check)) validates and resolves everything normally; only the write is
    skipped, with the payload logged under a C([check_mode]) prefix.
  - "Use M(graphiant.naas.graphiant_public_vif_info) to query service summaries and details."
options:
  operation:
    description:
      - "The specific Public VIF operation to perform."
      - >-
        V(create_services)/V(update_services): Create or update services from a YAML file
        containing a I(public_vif_services) list. Each service needs a I(serviceName); the
        producer I(lanSegment), I(region), and I(storageProvider) (cloud provider) for the
        gateways; one or more I(gatewayBgpNeighbors) (peer IP/ASN, local interface, timers,
        route filters, MD5 password per gateway); a matching I(natPrefixStrategy) entry per
        gateway (the public NAT prefix advertised to the cloud); and I(consumerLanSegments)
        (which LAN segments may use this Public VIF, and what they advertise over it).
      - >-
        Optional I(coveringPrefixes) summarizes the LAN routes advertised, and
        I(advertisement) scopes which sites/site lists may consume the service (all symmetric
        sites if omitted). V(update_services) requires the service to already exist and
        supports C(--check)/C(--diff) to preview the payload that would be sent.
      - "V(delete_services): Delete Public VIF services from a YAML configuration file."
      - >-
        For query operations (services_summary, service_details), use
        M(graphiant.naas.graphiant_public_vif_info) instead.
    type: str
    choices:
      - create_services
      - update_services
      - delete_services
    required: true
  state:
    description:
      - "The desired state of the Public VIF services."
      - "V(present): Maps to V(create_services) when O(operation) not specified."
      - "V(absent): Maps to V(delete_services) when O(operation) not specified."
    type: str
    choices:
      - present
      - absent
    default: present
  config_file:
    description:
      - Path to the YAML configuration file for the operation.
      - Required for V(create_services), V(update_services), and V(delete_services) operations.
      - Can be an absolute path or relative path. Relative paths are resolved using the configured config_path.
      - Configuration files support Jinja2 templating syntax for dynamic generation.
      - File must contain I(public_vif_services) list.
    type: str
  detailed_logs:
    description:
      - Enable detailed logging output for troubleshooting and monitoring.
      - When enabled, provides comprehensive logs of all Public VIF operations.
      - Logs are captured and included in the RV(msg) return value for display using M(ansible.builtin.debug) module.
    type: bool
    default: false
  vault_public_vif_bgp_md5_passwords:
    description:
      - >-
        Dict of service name to device name to BGP MD5 password (create_services/
        update_services only). Pass from playbook vars loaded from encrypted
        I(vault_secrets.yml); secrets in memory only.
      - >-
        Keys must match the service C(name) and the device name/ID key used under that
        service's I(gatewayBgpNeighbors) in the config. Optional; used only when a
        neighbor's I(md5Password) is null/absent in YAML.
    type: dict
    default: {}
    required: false

attributes:
  check_mode:
    description: >
      Supported. In check mode, no API writes are performed; payloads that would be sent
      are logged with a C([check_mode]) prefix.
    support: full

requirements:
  - python >= 3.7
  - graphiant-sdk >= 26.8.0
  - tabulate

seealso:
  - module: graphiant.naas.graphiant_global_config
    description: Configure global objects (LAN segments) required for Public VIF
  - module: graphiant.naas.graphiant_sites
    description: Configure sites required for Public VIF advertisement scoping
  - module: graphiant.naas.graphiant_public_vif_info
    description: Query Public VIF service summaries and details
  - module: graphiant.naas.graphiant_local_extranet
    description: Manage intra-enterprise Local Extranet LAN segment sharing
  - module: graphiant.naas.graphiant_data_exchange
    description: Manage cross-enterprise (B2B) Data Exchange services, customers, matches, and invitations

author:
  - Graphiant Team (@graphiant)

"""

EXAMPLES = r"""
- name: Create Public VIF services
  graphiant.naas.graphiant_public_vif:
    operation: create_services
    config_file: "sample_public_vif_services.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: create_result

- name: Display service creation result
  ansible.builtin.debug:
    msg: "{{ create_result.msg }}"

- name: Create Public VIF services with BGP MD5 passwords from Ansible Vault (leave md5Password null in YAML)
  graphiant.naas.graphiant_public_vif:
    operation: create_services
    config_file: "sample_public_vif_services.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    vault_public_vif_bgp_md5_passwords: "{{ vault_public_vif_bgp_md5_passwords | default({}) }}"
  register: create_result

- name: Preview Public VIF service updates (check + diff)
  graphiant.naas.graphiant_public_vif:
    operation: update_services
    config_file: "sample_public_vif_services_update.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: update_result
  # Run playbook with: ansible-playbook playbook.yml --check --diff

- name: Update Public VIF services
  graphiant.naas.graphiant_public_vif:
    operation: update_services
    config_file: "sample_public_vif_services_update.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: update_result

- name: Display service update result
  ansible.builtin.debug:
    msg: "{{ update_result.msg }}"

- name: Delete Public VIF services
  graphiant.naas.graphiant_public_vif:
    operation: delete_services
    config_file: "sample_public_vif_services.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
"""

RETURN = r"""
msg:
  description:
    - Result message from the operation, including detailed logs when O(detailed_logs) is enabled.
  type: str
  returned: always
  sample: |
    Successfully created 1 Public VIF services

    Detailed logs:
    2026-08-14 23:08:05,315 - Graphiant_playbook - INFO - Creating service 'pvif-service-1'...
    2026-08-14 23:08:05,450 - Graphiant_playbook - INFO - Successfully created service 'pvif-service-1'
result_data:
  description:
    - Result data from the operation.
  type: dict
  returned: when applicable
  sample: {}
changed:
  description:
    - Whether the operation made changes to the system.
  type: bool
  returned: always
  sample: true
operation:
  description:
    - The operation that was performed.
    - One of V(create_services), V(update_services), or V(delete_services).
  type: str
  returned: always
  sample: "create_services"
config_file:
  description:
    - The configuration file used for the operation.
  type: str
  returned: when applicable
  sample: "sample_public_vif_services.yaml"
diff:
  description:
    - Ansible C(--diff) output showing before/after state for each changed item.
    - Returned for V(create_services) and V(update_services) when the playbook is run with
      C(--diff) and at least one item would change.
    - For new services, C(before) is empty and C(after) is the full target config.
    - For updates, C(before) is empty (no live-state comparison is performed — see the module
      notes) and C(after) is the full payload that was sent.
    - C(gatewayBgpNeighbors[].md5Password) (and any other known secret field) is shown as
      C(********) in this output, same as log lines — it is never printed in plaintext.
  type: dict
  returned: when playbook uses C(--diff) and V(create_services) or V(update_services) has changes
  sample:
    before: |
      === pvif-service-1 (create) ===
      {}
    after: |
      === pvif-service-1 (create) ===
      {"serviceName": "pvif-service-1", "lanSegmentId": 8568, "regionId": 12}
"""

from ansible.module_utils.basic import AnsibleModule  # noqa: E402
from ansible_collections.graphiant.naas.plugins.module_utils.graphiant_utils import (  # noqa: E402
    graphiant_portal_auth_argument_spec,
    get_graphiant_connection,
    handle_graphiant_exception,
)
from ansible_collections.graphiant.naas.plugins.module_utils.libs.device_config_common import (  # noqa: E402
    apply_module_diff,
)
from ansible_collections.graphiant.naas.plugins.module_utils.logging_decorator import capture_library_logs  # noqa: E402


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
    success_msg = kwargs.pop("success_msg", "Operation completed successfully")

    try:
        result = func(*args, **kwargs)
        if isinstance(result, dict) and "changed" in result:
            return {"changed": result["changed"], "result_msg": success_msg, "details": result}
        return {"changed": True, "result_msg": success_msg}
    except Exception as e:
        raise e


def main():
    """Main function for the Public VIF module."""

    argument_spec = dict(
        **graphiant_portal_auth_argument_spec(),
        operation=dict(
            type="str",
            required=True,
            choices=["create_services", "update_services", "delete_services"],
        ),
        state=dict(type="str", choices=["present", "absent"], default="present"),
        config_file=dict(type="str", required=False),
        detailed_logs=dict(type="bool", default=False),
        vault_public_vif_bgp_md5_passwords=dict(type="dict", required=False, default={}, no_log=True),
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
        mutually_exclusive=[("operation", "state")],
        required_one_of=[("operation", "state")],
    )

    params = module.params
    operation = params.get("operation")
    state = params.get("state")
    config_file = params.get("config_file")

    if not operation:
        if state == "present":
            operation = "create_services"
        elif state == "absent":
            operation = "delete_services"

    if operation in ["create_services", "update_services", "delete_services"]:
        if not config_file:
            module.fail_json(msg=f"config_file parameter is required for operation '{operation}'")

    try:
        connection = get_graphiant_connection(params, check_mode=module.check_mode)
        graphiant_config = connection.graphiant_config

        changed = False
        result_msg = ""
        result_data = {}
        diff_plan = []

        vault_public_vif_bgp_md5_passwords = params.get("vault_public_vif_bgp_md5_passwords") or {}

        if operation == "create_services":
            result = execute_with_logging(
                module,
                graphiant_config.public_vif.create_services,
                config_file,
                success_msg=f"Successfully created Public VIF services from {config_file}",
                diff_mode=getattr(module, "_diff", False),
                vault_public_vif_bgp_md5_passwords=vault_public_vif_bgp_md5_passwords,
            )
            changed = result["changed"]
            result_msg = result["result_msg"]
            diff_plan = result.get("details", {}).get("diff_plan", [])

        elif operation == "update_services":
            success_msg = f"Successfully updated Public VIF services from {config_file}"
            if module.check_mode:
                success_msg = (
                    f"Check mode: validated Public VIF service updates from {config_file} " "(API calls skipped)"
                )
            result = execute_with_logging(
                module,
                graphiant_config.public_vif.update_services,
                config_file,
                success_msg=success_msg,
                vault_public_vif_bgp_md5_passwords=vault_public_vif_bgp_md5_passwords,
            )
            changed = result["changed"]
            result_msg = result["result_msg"]
            diff_plan = result.get("details", {}).get("diff_plan", [])

        elif operation == "delete_services":
            result = execute_with_logging(
                module,
                graphiant_config.public_vif.delete_services,
                config_file,
                success_msg=f"Successfully deleted Public VIF services from {config_file}",
            )
            changed = result["changed"]
            result_msg = result["result_msg"]

        else:
            module.fail_json(
                msg=f"Unsupported operation: {operation}. "
                f"Supported operations are: create_services, update_services, delete_services. "
                f"For query operations, use graphiant.naas.graphiant_public_vif_info module."
            )

        exit_payload = dict(
            changed=changed,
            msg=result_msg,
            result_msg=result_msg,
            result_data=result_data,
            operation=operation or "unknown",
            config_file=config_file if config_file else None,
        )
        apply_module_diff(module, exit_payload, {"diff_plan": diff_plan})

        module.exit_json(**exit_payload)

    except Exception as e:
        error_msg = handle_graphiant_exception(e, operation or "unknown")
        module.fail_json(msg=error_msg, operation=operation or "unknown")


if __name__ == "__main__":
    main()
