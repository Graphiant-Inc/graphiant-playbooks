#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for managing Graphiant Gateway Services via the portal API:
  POST/PUT/DELETE /v1/gateways
"""

DOCUMENTATION = r"""
---
module: graphiant_gateway_services
short_description: Manage Graphiant Gateway Services (cloud gateway and connectivity)
description:
  - >-
    Manages Graphiant Gateway Services via C(POST/PUT/DELETE /v1/gateways). Two service
    types are supported under the top-level C(gatewayServices) key in the config file:
    C(cloudGateway) (cloud peering for AWS, Azure, GCP, and Oracle) and C(connectivity)
    (site-to-site IPSec VPN gateway, C(ipsecGatewayPeers)).
  - >-
    The C(create) operation is idempotent create-or-update. Services that do not exist are
    created; existing connectivity services are updated in place when the config changes, and
    services that already match are skipped. To change a service, edit the config file and
    re-run C(create).
  - >-
    Update is not supported for cloud gateway services (C(create)/C(delete) only). Only
    connectivity services can be updated; a re-run of C(create) against an unchanged cloud
    gateway is skipped rather than updated.
  - >-
    Region names, LAN segment names, and speeds in the config file are resolved to the API
    C(regionId)/C(vrfId) and the S-prefixed speed enum (e.g. C(1Gbps) -> C(S1Gbps)) before
    the request is sent. Region, LAN segment, and any connectivity C(vpnProfile) names are
    validated against the enterprise before any gateway is pushed, failing fast with the list
    of available values when a name is not found.
notes:
  - "Configuration files support Jinja2 templating syntax for dynamic value substitution."
  - >-
    With C(ansible-playbook --check), writes are skipped but C(changed) reflects whether an
    apply would create, update, or delete at least one service. Use C(--diff) to preview the
    pending changes.
version_added: "26.9.0"
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
options:
  gateway_services_config_file:
    description:
      - Path to the YAML configuration file containing the C(gatewayServices) definition.
      - Relative paths resolve using the collection config path (see C(GRAPHIANT_CONFIGS_PATH)).
    type: str
    required: true
  operation:
    description:
      - Operation to perform.
      - C(create) creates services that do not exist and updates existing connectivity services (idempotent).
      - C(delete) removes the services defined in the config file.
      - When omitted, it is derived from C(state) (C(present) -> C(create), C(absent) -> C(delete)).
    type: str
    required: false
    choices: [ create, delete ]
  state:
    description:
      - Desired state, used to derive C(operation) when C(operation) is not set.
    type: str
    required: false
    default: present
    choices: [ present, absent ]
  detailed_logs:
    description: Enable detailed logging in the task result message.
    type: bool
    required: false
    default: false
  force_update:
    description:
      - Re-push every matching C(connectivity) gateway (PUT) even when the idempotency comparison
        finds no change.
      - Tunnel C(psk), inside CIDRs, and BGP C(md5Password) are excluded from the comparison (they
        are auto-generated/auto-allocated per apply when left null), so a rotated secret is not
        otherwise detected. Set this to C(true) after changing a PSK/MD5 value to make it take effect.
      - Applies to C(create) only and to connectivity gateways only; cloud gateways are never
        updated (change one via delete + create).
    type: bool
    required: false
    default: false
  vault_gateway_ipsec_psks:
    description:
      - Connectivity tunnel pre-shared keys, keyed by gateway name then peer name then tunnel.
      - >-
        Each tunnel C(psk) is sourced by one of three modes, in precedence order:
        (1) DIRECT INPUT — a non-null C(psk) in the config file is used as-is;
        (2) VAULT — a C(psk) left C(null) in the config is filled from this dict when a matching
        C(gateway/peer/tunnel) entry exists;
        (3) API AUTO-FILL — a C(psk) left C(null) with no matching vault entry is auto-generated
        by the portal. Add entries here only for tunnels you want vault to supply.
      - 'Structure: C({<gateway name>: {peer-1: {tunnel1: <psk>, tunnel2: <psk>}, peer-2: {...}}}).
        The peer key is C(peer-<N>), 1-based over C(remotePeers).'
    type: dict
    required: false
    default: {}
  vault_gateway_bgp_md5_passwords:
    description:
      - Connectivity BGP MD5 passwords, keyed by gateway name (C(ipsecGatewayPeers.name)).
      - Used to fill C(routing.bgp.md5Password) when left C(null) in the config (BGP routing only);
        a non-null value in the config takes precedence. Optional — if unset, BGP runs without MD5.
      - 'Structure: C({<gateway name>: <md5 password>}).'
    type: dict
    required: false
    default: {}
attributes:
  check_mode:
    description: Supports check mode.
    support: full
    details: >
      In check mode, no configuration is pushed; the module still reads current state to
      determine whether changes would be made.
  diff_mode:
    description: Supports Ansible's C(--diff) for pending gateway service changes.
    support: full
    details: >
      When the playbook runs with C(--diff) and a service would change, the module returns a
      C(diff) dictionary (C(before) / C(after)). Structured entries are also in C(details).
requirements:
  - python >= 3.7
  - graphiant-sdk >= 26.8.0
seealso:
  - module: graphiant.naas.graphiant_site_to_site_vpn
    description: Per-edge site-to-site IPSec VPN (device-level, distinct from gateway connectivity).
  - module: graphiant.naas.graphiant_global_config
    description: Global routing policies (filters) referenced by cloud gateway C(routingPolicy).
author:
  - Graphiant Team (@graphiant)
"""

EXAMPLES = r"""
- name: Create or update gateway services from YAML
  graphiant.naas.graphiant_gateway_services:
    operation: create
    gateway_services_config_file: "sample_gateway_services_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true
  register: gateway_services_create_result

- name: Preview changes without applying (dry run)
  graphiant.naas.graphiant_gateway_services:
    operation: create
    gateway_services_config_file: "sample_gateway_services_config.yaml"
    access_token: "{{ graphiant_access_token }}"
  check_mode: true
  diff: true

- name: Delete gateway services defined in YAML
  graphiant.naas.graphiant_gateway_services:
    operation: delete
    gateway_services_config_file: "sample_gateway_services_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
  register: gateway_services_delete_result

# Connectivity tunnel PSK sourcing — three modes (see also sample_gateway_services_config.yaml):
#   1. DIRECT INPUT : set psk inline in the config file, e.g. tunnel1: { psk: "my-preshared-key" }
#   2. VAULT        : leave psk null in the config and provide it via vault_gateway_ipsec_psks below
#   3. API AUTO-FILL: leave psk null in the config with no vault entry; the portal generates one
- name: Create gateway services with vault-supplied PSK (mode 2)
  graphiant.naas.graphiant_gateway_services:
    operation: create
    gateway_services_config_file: "sample_gateway_services_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    vault_gateway_ipsec_psks:
      test:                 # gateway name (ipsecGatewayPeers.name)
        peer-1:             # peer-<N>, 1-based over remotePeers
          tunnel2: "{{ vault_gateway_test_peer1_tunnel2_psk }}"
  register: gateway_services_create_result
"""

RETURN = r"""
msg:
  description: Human-readable result (includes detailed logs when enabled).
  type: str
  returned: always
changed:
  description: Whether at least one gateway service was created, updated, or deleted.
  type: bool
  returned: always
operation:
  description: Operation performed (C(create) or C(delete)).
  type: str
  returned: always
gateway_services_config_file:
  description: Path to the YAML file used.
  type: str
  returned: always
created:
  description: Names of gateway services that were created.
  type: list
  elements: str
  returned: when operation is C(create)
updated:
  description: Names of connectivity gateway services that were updated in place.
  type: list
  elements: str
  returned: when operation is C(create)
skipped_services:
  description: Names of gateway services skipped because state already matched.
  type: list
  elements: str
  returned: always
deleted:
  description: Names of gateway services that were deleted.
  type: list
  elements: str
  returned: when operation is C(delete)
diff:
  description: Ansible C(--diff) payload when changes would be applied.
  type: dict
  returned: when playbook uses C(--diff) and at least one service would change
details:
  description: Structured payload from the manager (service lists, diff plan, etc.).
  type: dict
  returned: always
"""

from ansible.module_utils.basic import AnsibleModule  # noqa: E402

from ansible_collections.graphiant.naas.plugins.module_utils.graphiant_utils import (  # noqa: E402
    ansible_module_log,
    graphiant_portal_auth_argument_spec,
    get_graphiant_connection,
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
                f"graphiant_gateway_services: manager {name!s} failed: {type(e).__name__}: {e!s}",
            )
        raise
    if isinstance(result, dict) and "changed" in result:
        changed = bool(result.get("changed"))
        created = result.get("created") or []
        updated = result.get("updated") or []
        skipped = result.get("skipped") or []
        deleted = result.get("deleted") or []
        if changed:
            counts = [
                f"{len(names)} {label}"
                for label, names in (
                    ("created", created),
                    ("updated", updated),
                    ("deleted", deleted),
                )
                if names
            ]
            msg = f"{success_msg} ({', '.join(counts)})" if counts else success_msg
        else:
            msg = no_change_msg
            if skipped:
                msg += f" (skipped {len(skipped)} {'service' if len(skipped) == 1 else 'services'})"
        return {
            "changed": changed,
            "result_msg": msg,
            "details": result,
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "deleted": deleted,
        }
    return {"changed": True, "result_msg": success_msg, "details": result}


def main():
    argument_spec = dict(
        **graphiant_portal_auth_argument_spec(),
        gateway_services_config_file=dict(type="str", required=True),
        operation=dict(
            type="str",
            required=False,
            choices=["create", "delete"],
        ),
        state=dict(type="str", required=False, default="present", choices=["present", "absent"]),
        detailed_logs=dict(type="bool", required=False, default=False),
        force_update=dict(type="bool", required=False, default=False),
        vault_gateway_ipsec_psks=dict(type="dict", required=False, default={}, no_log=True),
        vault_gateway_bgp_md5_passwords=dict(type="dict", required=False, default={}, no_log=True),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    params = module.params
    operation = params.get("operation")
    state = params.get("state", "present")
    cfg_file = params["gateway_services_config_file"]

    if not operation:
        operation = "create" if state == "present" else "delete"

    try:
        if params.get("detailed_logs"):
            ansible_module_log(
                module,
                (
                    f"gateway_services: start operation={operation!r} "
                    f"gateway_services_config_file={cfg_file!r} check_mode={module.check_mode!r}"
                ),
            )
        connection = get_graphiant_connection(params, check_mode=module.check_mode)
        graphiant_config = connection.graphiant_config
        if params.get("detailed_logs"):
            ansible_module_log(
                module,
                "gateway_services: GraphiantConfig obtained; dispatching to gateway services manager",
            )

        if operation == "create":
            result = execute_with_logging(
                module,
                graphiant_config.gateway_services.create,
                cfg_file,
                params.get("vault_gateway_ipsec_psks") or {},
                params.get("vault_gateway_bgp_md5_passwords") or {},
                force_update=bool(params.get("force_update")),
                success_msg="Successfully created gateway services",
                no_change_msg="Gateway service(s) already match desired state; no changes needed",
            )
        elif operation == "delete":
            result = execute_with_logging(
                module,
                graphiant_config.gateway_services.delete,
                cfg_file,
                success_msg="Successfully deleted Gateway services",
                no_change_msg="Gateway service(s) already absent; no changes needed",
            )
        else:
            module.fail_json(
                msg=f"Unsupported operation '{operation}'. Supported operations: create, delete.",
                operation=operation,
            )
            return

        changed = result["changed"]
        result_msg = result["result_msg"]

        if params.get("detailed_logs"):
            preview = result_msg if len(result_msg) <= 200 else (result_msg[:200] + "…")
            ansible_module_log(
                module,
                f"graphiant_gateway_services: success changed={changed!r} result_msg_preview={preview!r}",
            )

        details = result.get("details") or {}
        exit_payload = dict(
            changed=changed,
            msg=result_msg,
            operation=operation,
            gateway_services_config_file=cfg_file,
            created=result.get("created", []),
            updated=result.get("updated", []),
            skipped_services=result.get("skipped", []),
            deleted=result.get("deleted", []),
            details=details,
        )
        apply_module_diff(module, exit_payload, details)
        module.exit_json(**exit_payload)

    except Exception as e:
        if module.params.get("detailed_logs"):
            import traceback

            ansible_module_log(
                module,
                f"graphiant_gateway_services: {type(e).__name__}: {e!s}\n{traceback.format_exc()}",
            )
        else:
            ansible_module_log(
                module,
                f"graphiant_gateway_services: failed {type(e).__name__}: {e!s}",
            )
        error_msg = handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == "__main__":
    main()
