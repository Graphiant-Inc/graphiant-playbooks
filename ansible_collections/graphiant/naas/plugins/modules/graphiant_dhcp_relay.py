#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Graphiant Team <support@graphiant.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Ansible module for managing Graphiant DHCP relay on interfaces.
"""

DOCUMENTATION = r"""
---
module: graphiant_dhcp_relay
short_description: Manage Graphiant DHCP relay on interfaces and subinterfaces
description:
  - >-
    Configures DHCP relay (IPv4 and/or IPv6) on main interfaces and VLAN subinterfaces
    via C(PUT /v1/devices/{device_id}/config) under
    C(edge.interfaces.{name}.interface.ipv4.dhcp.dhcpRelay) and the IPv6 equivalent.
  - >-
    Supports configure and deconfigure operations. Deconfigure sets C(relayServers: [])
    for the address families listed in the config file (idempotent when relay is already removed).
  - Configuration files support Jinja2 templating for dynamic generation.
  - >-
    Configure idempotency: compares intended relay servers to existing device state per
    interface and address family; skips push when already matched (V(changed)=V(false)).
  - >-
    Validates that each referenced main interface or VLAN subinterface exists on the device
    before pushing; fails with a list of known interfaces when not found.
  - >-
    Mutual exclusion: an interface supports either DHCP relay or a DHCP subnet (server), not both.
    Configure fails with a clear error if the target interface already has a DHCP subnet configured.
    Remove the DHCP subnet first using M(graphiant.naas.graphiant_edge_services) with C(state: absent)
    before enabling DHCP relay on that interface.
version_added: "26.7.0"
notes:
  - >-
    Check mode (C(--check)): No config is pushed; payloads that would be pushed are logged
    with C([check_mode]). V(changed) reflects whether an apply would update at least one device.
  - >-
    Interfaces must be configured first using M(graphiant.naas.graphiant_interfaces) before
    applying DHCP relay.
  - >-
    Multiple relay entries for the same parent interface (different VLAN subinterfaces) are
    merged into a single device PUT payload.
extends_documentation_fragment:
  - graphiant.naas.graphiant_portal_auth
options:
  dhcp_relay_config_file:
    description:
      - Path to the DHCP relay configuration YAML file.
      - Optional when O(device) is set with at least O(name) or O(interfaces).
      - Can be an absolute path or relative path. Relative paths are resolved using the configured config_path.
      - >-
        File must contain a C(dhcp_relay_config) list; each entry maps a device name to a dict with
        an C(interfaces) key (list of interface entries with C(name), C(vlan), C(dhcpRelayIpv4),
        C(dhcpRelayIpv6)).
    type: str
    required: false
    aliases:
      - dhcp_relay_file
  device:
    description:
      - Portal device hostname for single-device or loop execution.
      - When combined with O(dhcp_relay_config_file), overrides that device's interface list in the file.
      - Required when O(dhcp_relay_config_file) is omitted.
    type: str
  name:
    description:
      - Interface name for single-interface module-param mode (e.g. C(GigabitEthernet4/0/0)).
      - Required when O(dhcp_relay_config_file) is omitted and O(interfaces) is not set.
    type: str
    aliases:
      - interface_name
  vlan:
    description:
      - VLAN ID for subinterface relay. Omit for main interface.
      - Used together with O(name) in single-interface mode.
    type: raw
  dhcpRelayIpv4:
    description:
      - List of IPv4 DHCP relay server addresses for the interface named by O(name).
      - Ignored when O(interfaces) is set.
    type: list
    elements: str
    aliases:
      - dhcp_relay_ipv4
  dhcpRelayIpv6:
    description:
      - List of IPv6 DHCP relay server addresses for the interface named by O(name).
      - Ignored when O(interfaces) is set.
    type: list
    elements: str
    aliases:
      - dhcp_relay_ipv6
  interfaces:
    description:
      - List of interface entries for multi-interface module-param mode.
      - Each entry may contain C(name), C(vlan), C(dhcpRelayIpv4), and C(dhcpRelayIpv6).
      - When set, takes precedence over O(name) / O(vlan) / O(dhcpRelayIpv4) / O(dhcpRelayIpv6).
    type: list
    elements: dict
  operation:
    description:
      - "The specific DHCP relay operation to perform."
      - "V(configure): Configure DHCP relay on interfaces and subinterfaces."
      - "V(deconfigure): Remove DHCP relay from interfaces and subinterfaces."
    type: str
    choices:
      - configure
      - deconfigure
  state:
    description:
      - "The desired state of the DHCP relay configuration."
      - "V(present): Maps to V(configure) when O(operation) is not specified."
      - "V(absent): Maps to V(deconfigure) when O(operation) is not specified."
    type: str
    choices: [ present, absent ]
    default: present
  detailed_logs:
    description:
      - Enable detailed logging output for troubleshooting and monitoring.
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
  diff_mode:
    description: Supports diff mode.
    support: full
    details: >
      With C(--diff), the module shows per-device before/after relay server lists for interfaces
      that would change (under C(edge.interfaces)).
requirements:
  - python >= 3.7
  - graphiant-sdk >= 26.5.0
seealso:
  - module: graphiant.naas.graphiant_interfaces
    description: Configure interfaces before setting up DHCP relay
author:
  - Graphiant Team (@graphiant)
"""

EXAMPLES = r"""
# --- From YAML config file ---

- name: Configure DHCP relay on interfaces (from YAML)
  graphiant.naas.graphiant_dhcp_relay:
    operation: configure
    dhcp_relay_config_file: "sample_dhcp_relay_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    detailed_logs: true

- name: Deconfigure DHCP relay from interfaces (from YAML)
  graphiant.naas.graphiant_dhcp_relay:
    operation: deconfigure
    dhcp_relay_config_file: "sample_dhcp_relay_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

# --- Single device, single interface from module parameters ---

- name: Configure DHCP relay on a single interface (module params)
  graphiant.naas.graphiant_dhcp_relay:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    operation: configure
    device: "edge-1-sdktest"
    name: "GigabitEthernet4/0/0"
    vlan: 1
    dhcpRelayIpv4:
      - 10.1.1.1
      - 10.2.1.1
    dhcpRelayIpv6:
      - 2001:10:1:1::1

- name: Deconfigure DHCP relay on a single interface (module params)
  graphiant.naas.graphiant_dhcp_relay:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    operation: deconfigure
    device: "edge-1-sdktest"
    name: "GigabitEthernet4/0/0"
    vlan: 1
    dhcpRelayIpv4:
      - 10.1.1.1

# --- Single device, multiple interfaces from module parameters ---

- name: Configure DHCP relay on multiple interfaces (module params)
  graphiant.naas.graphiant_dhcp_relay:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    operation: configure
    device: "edge-1-sdktest"
    interfaces:
      - name: GigabitEthernet4/0/0
        vlan: 1
        dhcpRelayIpv4:
          - 10.1.1.1
          - 10.2.1.1
        dhcpRelayIpv6:
          - 2001:10:1:1::1
      - name: GigabitEthernet8/0/0
        dhcpRelayIpv4:
          - 10.1.11.1
          - 10.2.11.1

# --- Loop over multiple devices (one interface per iteration) ---

- name: Configure DHCP relay on multiple devices (loop)
  graphiant.naas.graphiant_dhcp_relay:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    operation: configure
    device: "{{ item.device }}"
    name: "{{ item.name }}"
    vlan: "{{ item.vlan | default(omit) }}"
    dhcpRelayIpv4: "{{ item.dhcpRelayIpv4 | default(omit) }}"
    dhcpRelayIpv6: "{{ item.dhcpRelayIpv6 | default(omit) }}"
  loop:
    - device: edge-1-sdktest
      name: GigabitEthernet4/0/0
      vlan: 1
      dhcpRelayIpv4: ["10.1.1.1", "10.2.1.1"]
      dhcpRelayIpv6: ["2001:10:1:1::1"]
    - device: edge-2-sdktest
      name: GigabitEthernet8/0/0
      dhcpRelayIpv4: ["10.1.11.1"]

# --- Override one device from a YAML file ---

- name: Override DHCP relay for one device from file
  graphiant.naas.graphiant_dhcp_relay:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    operation: configure
    dhcp_relay_config_file: "sample_dhcp_relay_config.yaml"
    device: "edge-1-sdktest"
    name: "GigabitEthernet4/0/0"
    dhcpRelayIpv4:
      - 192.168.1.1

# --- Per-interface state: absent (remove all relay on one interface, configure others) ---

- name: Remove relay from one subinterface while configuring others
  graphiant.naas.graphiant_dhcp_relay:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    operation: configure
    device: "edge-3-sdktest"
    interfaces:
      - name: GigabitEthernet7/0/0
        dhcpRelayIpv4:
          - 10.2.1.2
      - name: GigabitEthernet8/0/0
        vlan: 30
        state: absent

# --- Per-AF state: absent (remove only IPv4 relay, keep IPv6) ---

- name: Remove IPv4 relay only, keep IPv6 on subinterface
  graphiant.naas.graphiant_dhcp_relay:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    operation: configure
    device: "edge-3-sdktest"
    interfaces:
      - name: GigabitEthernet8/0/0
        vlan: 30
        dhcpRelayIpv4:
          state: absent
        dhcpRelayIpv6:
          relayServers:
            - 2001:10:2:1::2

# --- Check / diff mode ---

- name: Preview DHCP relay changes (check + diff)
  graphiant.naas.graphiant_dhcp_relay:
    operation: configure
    dhcp_relay_config_file: "sample_dhcp_relay_config.yaml"
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
  check_mode: true
  diff: true
"""

RETURN = r"""
msg:
  description: Result message from the operation.
  type: str
  returned: always
changed:
  description:
    - Whether the operation made changes.
    - V(true) when config would be pushed to at least one device; V(false) when intended state already matched.
    - In check mode (C(--check)), no configuration is pushed, but V(changed) reflects whether changes would be made.
  type: bool
  returned: always
operation:
  description: The operation that was performed.
  type: str
  returned: always
dhcp_relay_config_file:
  description: The DHCP relay configuration file used for the operation, if provided.
  type: str
  returned: when provided
configured_devices:
  description: Device names where configuration would be or was pushed.
  type: list
  elements: str
  returned: when supported
skipped_devices:
  description: Device names where no DHCP relay changes were needed.
  type: list
  elements: str
  returned: when supported
details:
  description: Raw manager result (includes C(diff_plan), configured/skipped device and interface lists).
  type: dict
  returned: when supported
diff:
  description: Ansible C(--diff) payload showing per-device before/after DHCP relay state.
  type: dict
  returned: when playbook uses C(--diff) and at least one device would be updated
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
    success_msg = kwargs.pop("success_msg", "Operation completed successfully")
    no_change_msg = kwargs.pop("no_change_msg", "No changes needed")
    result = func(*args, **kwargs)
    if isinstance(result, dict) and "changed" in result:
        msg = no_change_msg if not result["changed"] else success_msg
        return {"changed": result["changed"], "result_msg": msg, "details": result}
    return {"changed": True, "result_msg": success_msg}


def main():
    argument_spec = dict(
        **graphiant_portal_auth_argument_spec(),
        dhcp_relay_config_file=dict(type="str", required=False, default=None, aliases=["dhcp_relay_file"]),
        device=dict(type="str", required=False, default=None),
        name=dict(type="str", required=False, default=None, aliases=["interface_name"]),
        vlan=dict(type="raw", required=False, default=None),
        dhcpRelayIpv4=dict(type="list", required=False, default=None, elements="str", aliases=["dhcp_relay_ipv4"]),
        dhcpRelayIpv6=dict(type="list", required=False, default=None, elements="str", aliases=["dhcp_relay_ipv6"]),
        interfaces=dict(type="list", required=False, default=None, elements="dict"),
        operation=dict(type="str", required=False, choices=["configure", "deconfigure"]),
        state=dict(type="str", required=False, default="present", choices=["present", "absent"]),
        detailed_logs=dict(type="bool", required=False, default=False),
    )

    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=True)

    params = module.params
    operation = params.get("operation")
    state = params.get("state", "present")
    dhcp_relay_config_file = params.get("dhcp_relay_config_file")
    device = (params.get("device") or "").strip()

    if not operation:
        operation = "configure" if state == "present" else "deconfigure"

    if not dhcp_relay_config_file and not device:
        module.fail_json(
            msg="Provide dhcp_relay_config_file and/or device (portal device name).",
            operation=operation,
        )
        return

    if not dhcp_relay_config_file and device:
        if not params.get("name") and not params.get("interfaces"):
            module.fail_json(
                msg="When dhcp_relay_config_file is omitted, provide name (interface name) or interfaces list.",
                operation=operation,
            )
            return

    module_params = {"device": device or None}
    for key in ("name", "vlan", "dhcpRelayIpv4", "dhcpRelayIpv6", "interfaces"):
        if params.get(key) is not None:
            module_params[key] = params[key]

    try:
        connection = get_graphiant_connection(params, check_mode=module.check_mode)
        graphiant_config = connection.graphiant_config

        if operation == "configure":
            result = execute_with_logging(
                module,
                graphiant_config.dhcp_relay_interfaces.configure_dhcp_relay_interfaces,
                dhcp_relay_config_file,
                module_params,
                success_msg="Successfully configured DHCP relay on interfaces",
                no_change_msg="DHCP relay already matches desired state; no changes needed",
            )
        else:
            result = execute_with_logging(
                module,
                graphiant_config.dhcp_relay_interfaces.deconfigure_dhcp_relay_interfaces,
                dhcp_relay_config_file,
                module_params,
                success_msg="Successfully deconfigured DHCP relay from interfaces",
                no_change_msg="DHCP relay already removed or not configured; no changes needed",
            )

        details = result.get("details") or {}
        exit_payload = dict(
            changed=result["changed"],
            msg=result["result_msg"],
            operation=operation,
            configured_devices=details.get("configured_devices", []),
            skipped_devices=details.get("skipped_devices", []),
            details=details,
        )
        if dhcp_relay_config_file:
            exit_payload["dhcp_relay_config_file"] = dhcp_relay_config_file
        apply_module_diff(module, exit_payload, details)
        module.exit_json(**exit_payload)

    except Exception as e:
        error_msg = handle_graphiant_exception(e, operation)
        module.fail_json(msg=error_msg, operation=operation)


if __name__ == "__main__":
    main()
