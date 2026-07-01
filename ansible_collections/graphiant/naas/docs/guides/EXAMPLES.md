# Example Playbooks

This guide provides detailed examples for using the Graphiant Playbooks collection.

For module reference, see the [Modules documentation](https://github.com/Graphiant-Inc/graphiant-playbooks/tree/main/ansible_collections/graphiant/naas#modules).

## Quick Start

Set up environment variables before running playbooks:

```bash
export GRAPHIANT_HOST="https://api.graphiant.com"
export GRAPHIANT_USERNAME="your_username"
export GRAPHIANT_PASSWORD="your_password"

# Alternative (SSO): graphiant login, then source ~/.graphiant/env.sh for GRAPHIANT_ACCESS_TOKEN

# Optional: Enable debug callback for readable detailed_logs output (removes `\n` characters)
export ANSIBLE_STDOUT_CALLBACK=debug
```

All modules support `detailed_logs` parameter:
- `true`: Show detailed library logs in task output
- `false`: Show only basic success/error messages (default)

All modules support `state` parameter:
- `present`: Configure/create resources (maps to `configure` operation)
- `absent`: Deconfigure/remove resources (maps to `deconfigure` operation)
- When both `operation` and `state` are provided, `operation` takes precedence

`graphiant_device_system`, `graphiant_edge_services`, and `graphiant_macsec` only support `present` (configure); `absent` is not valid at module level (MACsec PSK removal uses `state: absent` on individual `presharedKeys` entries).

### Config File Path Resolution

Config file paths are resolved in the following order:

1. **Absolute path**: If an absolute path is provided, it is used directly
2. **GRAPHIANT_CONFIGS_PATH**: If set, uses this path directly as the configs directory
3. **Collection's configs folder**: By default, looks in the collection's `configs/` folder. Find the collection location with:
   ```bash
   ansible-galaxy collection list graphiant.naas
   ```
4. **Fallback**: If configs folder cannot be located, falls back to `configs/` in current working directory

Similarly, template paths use `GRAPHIANT_TEMPLATES_PATH` environment variable.

Check `logs/log_<date>.log` under the playbook working directory (for example `playbooks/logs/`). Secrets are already masked in Ansible output (`no_log` on modules and tasks, plus vault). Outside Ansible, collection logs mask API keys in `_SENSITIVE_LOG_KEYS` (`device_config_common.py`)—see [CREDENTIAL_MANAGEMENT_GUIDE.md](CREDENTIAL_MANAGEMENT_GUIDE.md#logging). Do not commit log files.


## Device system settings (name, region, site)

### Module: graphiant.naas.graphiant_device_system

`graphiant_device_system` sets the edge, gateway, or core system fields on `PUT /v1/devices/{id}/config` (`name`, `regionName`, `site`). **Configure-only**: `state: present` only—no deconfigure (see **Quick Start**). Missing `site` in both the portal and YAML **fails** the task and leaves other devices in the run untouched.

With `--check`, nothing is pushed; state is still read and would-be payloads are logged under `[check_mode]`. With `--diff`, pending branch edits surface as Ansible `diff` (`before` / `after`) and `details.diff_plan`.

Use `configs/sample_device_system.yaml`; optional top-level `sites` creates sites devices reference by name.

### Playbook

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/device_system_management.yml --tag configure -e config_file=sample_device_system.yaml --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/device_system_management.yml --tag configure -e config_file=sample_device_system.yaml --check --diff
ansible-playbook ansible_collections/graphiant/naas/playbooks/device_system_management.yml --tag configure -e config_file=sample_device_system.yaml
ansible-playbook ansible_collections/graphiant/naas/playbooks/device_system_management.yml --tag configure -e config_file=sample_device_system.yaml --diff
```

### Module task

Apply device system settings from a config file.

```yaml
- name: Configure device system settings from YAML
  graphiant.naas.graphiant_device_system:
    <<: *graphiant_client_params
    operation: configure
    system_config_file: "{{ config_file }}"
    detailed_logs: true
    state: present
  register: configure_result
  tags: ['configure']

- name: Display configure result (from YAML)
  ansible.builtin.debug:
    msg: |
      {{ configure_result.msg | trim }}
      configured_devices={{ configure_result.configured_devices | default([]) }}
      skipped_devices={{ configure_result.skipped_devices | default([]) }}
  when: configure_result is defined and configure_result.msg is defined
  tags: ['configure']
```

Apply device system settings from module parameters instead of a config file. 

```yaml
- name: Apply device system settings from module parameters
  graphiant.naas.graphiant_device_system:
    <<: *graphiant_client_params
    operation: configure
    device: "edge-3-sdktest"
    name: "edge-3-sdktest"
    regionName: "us-east-2 (Atlanta)"
    site:
      name: "New York-sdktest"
    detailed_logs: true
    state: present
```

## Edge services (DHCP, DNS, LLDP, LWS password)

### Module: graphiant.naas.graphiant_edge_services

`graphiant_edge_services` configures edge service on the Edge/Gateway devices using `PUT /v1/devices/{id}/config`:

- **LAN segment DHCP subnets** — pools, ranges, static leases; use `state: absent` to remove a subnet
- **LAN interface LLDP** — enable or disable per interface (LAN only)
- **Device local web server password** — from the config YAML file, Ansible Vault (`vault_devices_lws_password`), or module parameters
- **Edge DNS mode** — `DNSModeStatic`, `DNSModeCloudflare`, or `DNSModeDynamic`

Configure-only (`state: present`); core devices are rejected.

Other edge-related settings use different modules: **syslog**, **IPFIX**, and **SNMP** (and global NTP objects) via `graphiant_global_config`; **device-level NTP** via `graphiant_ntp`. Any unstructured device JSON can be pushed with `graphiant_device_config`.

**Prerequisite:** LAN segments and interfaces must exist first (e.g. `interface_management.yml --tag lan`).

With `--check`, nothing is pushed; would-be payloads are logged under `[check_mode]`. With `--diff`, pending updates appear in Ansible `diff` and `details.diff_plan`. LWS plaintext is never shown in diffs—only `localWebServerPasswordConfigured`.

Use `configs/sample_edge_services.yaml`. DHCP subnet API keys combine interface name and `ipPrefix` with a hyphen. LLDP applies to **LAN interfaces only**; the task **fails** if `lldp` references a WAN/circuit interface or an interface that does not exist on the device.

**Local web server password** — precedence: YAML `localWebServerPassword` → `vault_devices_lws_password` → module params. Load vault with `include_vars` and pass `vault_devices_lws_password` to the module ([CREDENTIAL_MANAGEMENT_GUIDE.md](CREDENTIAL_MANAGEMENT_GUIDE.md)); do not reference playbook variables in the config file (Jinja render has no playbook context). Self-contained Jinja (`{% set %}`, loops) is fine — see `configs/de_workflows_configs/`.

- **Default (no force):** password is pushed only when the device has none; if the portal already has a hash, LWS is skipped (DNS/LLDP/DHCP still apply).
- **Vault (recommended):** keys = portal hostnames (e.g. `edge-3-sdktest` in `vault_secrets.yml` and YAML).
- **`localWebServerPasswordForce: true`:** always push when a password is available; task **fails** if no password from YAML, vault, or module params. Clear force after a successful rotate—the portal stores a hash, so force re-pushes every run.

Use `no_log: true` on tasks that pass passwords.

#### Vault setup

Required when you configure local web server passwords via Ansible Vault (`vault_devices_lws_password` in `vault_secrets.yml`). Use the `configure` playbook tag and pass `--vault-password-file` on every run (including `--check`). For DNS, LLDP, and DHCP only—or LWS via plaintext in the config YAML or module params—vault is not required; use `configure_without_vault` instead.

```bash
cp ansible_collections/graphiant/naas/configs/vault_secrets.yml.example ansible_collections/graphiant/naas/configs/vault_secrets.yml
# Edit vault_devices_lws_password (keys = portal device hostnames), then:
export ANSIBLE_VAULT_PASSPHRASE="*************"
ansible-vault encrypt ansible_collections/graphiant/naas/configs/vault_secrets.yml --vault-password-file ansible_collections/graphiant/naas/configs/vault-password-file.sh
```

### Playbook

Tags: `configure` (YAML + vault for LWS), `configure_without_vault` (YAML only, no vault load), `configure_params_examples`, `configure_params_lws`, `info`.

**With vault** (`configure`) — **required** for LWS passwords supplied via Ansible Vault. Loads `vault_secrets.yml`, passes `vault_devices_lws_password` to the module, and requires `--vault-password-file` (e.g. when YAML sets `localWebServerPasswordForce: true` and the password is in vault, not in the config file):

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/edge_services_management.yml --tags configure -e config_file=sample_edge_services.yaml --check --diff --vault-password-file ansible_collections/graphiant/naas/configs/vault-password-file.sh
ansible-playbook ansible_collections/graphiant/naas/playbooks/edge_services_management.yml --tags configure -e config_file=sample_edge_services.yaml --vault-password-file ansible_collections/graphiant/naas/configs/vault-password-file.sh
```

**Without vault** (`configure_without_vault`) — use when LWS is **not** sourced from Ansible Vault. Skips vault `include_vars`; `vault_devices_lws_password` stays empty. Suitable for DNS, LLDP, and DHCP only. For LWS without vault, set `localWebServerPassword` literally in YAML or pass it as a module parameter; omit `localWebServerPasswordForce` or set it to `false` (force without YAML, vault, or module params **fails**):

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/edge_services_management.yml --tags configure_without_vault -e config_file=sample_edge_services.yaml --check --diff
ansible-playbook ansible_collections/graphiant/naas/playbooks/edge_services_management.yml --tags configure_without_vault -e config_file=sample_edge_services.yaml
```

**Module-parameter examples** (`configure_params_lws` requires vault when the password comes from `vault_devices_lws_password`):

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/edge_services_management.yml --tags configure_params_examples
ansible-playbook ansible_collections/graphiant/naas/playbooks/edge_services_management.yml --tags configure_params_lws -e edge_lws_device=edge-3-sdktest --vault-password-file ansible_collections/graphiant/naas/configs/vault-password-file.sh
```

### Module task

From YAML **with vault** (`configure` tag — vault loaded by playbook):

```yaml
- name: Configure edge services from YAML
  graphiant.naas.graphiant_edge_services:
    <<: *graphiant_client_params
    operation: configure
    edge_services_config_file: "{{ config_file }}"
    vault_devices_lws_password: "{{ vault_devices_lws_password | default({}) }}"
    detailed_logs: true
    state: present
  register: configure_result
  tags: ['configure']

- name: Display configure result (from YAML)
  ansible.builtin.debug:
    msg: |
      {{ configure_result.msg | trim }}
      configured_devices={{ configure_result.configured_devices | default([]) }}
      skipped_devices={{ configure_result.skipped_devices | default([]) }}
  when: configure_result is defined and configure_result.msg is defined
  tags: ['configure']
```

From YAML **without vault** (`configure_without_vault` tag — omit `vault_devices_lws_password` or pass `{}`; LWS only via `localWebServerPassword` in the config file):

```yaml
- name: Configure edge services from YAML (no vault)
  graphiant.naas.graphiant_edge_services:
    <<: *graphiant_client_params
    operation: configure
    edge_services_config_file: "{{ config_file }}"
    detailed_logs: true
    state: present
  register: configure_result
  tags: ['configure_without_vault']
```

For a **single device**, use module parameters (camelCase API names; snake_case aliases such as `dhcp_subnets` accepted):

```yaml
- name: Apply edge services from module parameters
  graphiant.naas.graphiant_edge_services:
    <<: *graphiant_client_params
    operation: configure
    device: "edge-2-sdktest"
    dns:
      mode: DNSModeStatic
      static:
        primaryIpv4: "8.8.8.8"
        secondaryIpv4: "8.8.4.4"
    lldp:
      GigabitEthernet4/0/0: true
      GigabitEthernet8/0/0: true
    dhcpSubnets:
      - segment: lan-1-test
        interface: GigabitEthernet8/0/0
        ipPrefix: "10.2.11.0/24"
        state: present
        subnet:
          name: Edge-2-lan-1-test-DHCP
          ipGateway: "10.2.11.1"
          ipRangesV2:
            ipRange:
              - start: "10.2.11.100"
                end: "10.2.11.200"
          domainName: example.com
          domainNameServer:
            primary: "8.8.8.8"
            secondary: "8.8.4.4"
    detailed_logs: true
    state: present
```

#### DHCP subnets (`dhcpSubnets`)

Each entry targets one pool on a LAN segment. `segment` must match the device LAN segment name; `interface` and `ipPrefix` must match an existing LAN interface/subinterface and its prefix (from `interface_management.yml --tags lan`). The API key is `{interface}-{ipPrefix}`. Use `state: absent` to remove a pool.

**YAML** (`configs/sample_edge_services.yaml`):

```yaml
edge_services:
  - edge-1-sdktest:
      dhcpSubnets:
        - segment: lan-1-test
          interface: GigabitEthernet7/0/0
          ipPrefix: "10.1.11.0/24"
          state: present
          subnet:
            name: Edge-1-lan-1-test-DHCP
            ipGateway: "10.1.11.1"
            ipRangesV2:
              ipRange:
                - start: "10.1.11.100"
                  end: "10.1.11.200"
            domainName: example.com
            domainNameServer:
              primary: "8.8.8.8"
              secondary: "8.8.4.4"
        - segment: lan-7-test
          interface: GigabitEthernet7/0/0.18
          ipPrefix: "10.1.17.0/24"
          state: present
          subnet:
            name: Edge-1-lan-7-test-DHCP
            ipGateway: "10.1.17.1"
            ipRangesV2:
              ipRange:
                - start: "10.1.17.100"
                  end: "10.1.17.200"
  - edge-3-sdktest:
      dhcpSubnets:
        - segment: lan-7-test
          interface: GigabitEthernet8/0/0.28
          ipPrefix: "10.3.177.0/24"
          state: absent   # removes GigabitEthernet8/0/0.28-10.3.177.0/24
```

**Module params** — add a pool:

```yaml
- name: Add DHCP pool on edge-2
  graphiant.naas.graphiant_edge_services:
    <<: *graphiant_client_params
    operation: configure
    device: "edge-2-sdktest"
    dhcpSubnets:
      - segment: lan-1-test
        interface: GigabitEthernet8/0/0
        ipPrefix: "10.2.11.0/24"
        state: present
        subnet:
          name: Edge-2-lan-1-test-DHCP
          ipGateway: "10.2.11.1"
          ipRangesV2:
            ipRange:
              - start: "10.2.11.100"
                end: "10.2.11.200"
    state: present
```

**Module params** — remove a pool (`state: absent`; `subnet` not required):

```yaml
- name: Remove DHCP pool on edge-3
  graphiant.naas.graphiant_edge_services:
    <<: *graphiant_client_params
    operation: configure
    device: "edge-3-sdktest"
    dhcpSubnets:
      - segment: lan-7-test
        interface: GigabitEthernet8/0/0.28
        ipPrefix: "10.3.177.0/24"
        state: absent
    state: present
```

LWS via module params or vault (omit `localWebServerPasswordForce` for first-time set; use `true` only to rotate):

```yaml
- name: Set local web server password (single device)
  graphiant.naas.graphiant_edge_services:
    <<: *graphiant_client_params
    operation: configure
    device: "edge-3-sdktest"
    localWebServerPasswordForce: true  # remove or set false after successful rotate
    vault_devices_lws_password: "{{ vault_devices_lws_password | default({}) }}"
    state: present
  no_log: true
```

There is no `deconfigure` operation for the module as a whole. To revert settings, use module parameters per device: set `dns.mode` to `DNSModeDynamic`, set listed `lldp` interfaces to `false`, use `dhcpSubnets` with `state: absent` for each pool, and set each `dpiApplications` map key you want removed to `state: absent` (sends `application: null`). See `tests/test.py` `_edge_services_deconfigure_module_params` and `test_deconfigure_edge_services`.

## Interface Management

Check mode (`--check`) is supported for interface operations: no configuration is pushed, and the payloads that would be pushed are logged with a `[check_mode]` prefix so you can see exactly what would be applied.

### Module: graphiant.naas.graphiant_interfaces

#### Configure WAN interfaces and circuits (including WAN static routes)

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/interface_management.yml --tag wan --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/interface_management.yml --tag wan
```

```yaml
- name: Configure WAN circuits and interfaces
  graphiant.naas.graphiant_interfaces:
    <<: *graphiant_client_params
    interface_config_file: "sample_interface_config.yaml"
    circuit_config_file: "sample_circuit_config.yaml"
    operation: "configure_wan_circuits_interfaces"
    detailed_logs: true
    state: present
  tags: ['interfaces', 'wan', 'circuits']
  register: configure_result

- name: Display WAN Interface Configuration Results
  ansible.builtin.debug:
    msg: "{{ configure_result.msg }}"
  when: configure_result is defined and configure_result.msg is defined
  tags: ['interfaces', 'wan', 'circuits']
```

#### Update circuit configuration and add WAN circuit static routes

**Prerequisite:** Configure WAN circuits/interfaces first.

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/circuit_management.yml --tag static_routes --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/circuit_management.yml --tag static_routes
```

```yaml
- name: Configure circuits only (Circuit configuration and static routes)
  graphiant.naas.graphiant_interfaces:
    <<: *graphiant_client_params
    interface_config_file: "sample_interface_config.yaml"
    circuit_config_file: "sample_circuit_config.yaml"
    operation: "configure_circuits"
    detailed_logs: true
    state: present
  register: configure_result
  tags: ['configure', 'static_routes']

- name: Display circuits configuration results
  ansible.builtin.debug:
    msg: "{{ configure_result.msg }}"
  when: configure_result is defined and configure_result.msg is defined
  tags: ['configure', 'static_routes']
```

#### Deconfigure WAN circuit static routes

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/circuit_management.yml --tag deconfigure --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/circuit_management.yml --tag deconfigure
```

```yaml
- name: Deconfigure circuits (i.e removes static routes only)
  graphiant.naas.graphiant_interfaces:
    <<: *graphiant_client_params
    interface_config_file: "sample_interface_config.yaml"
    circuit_config_file: "sample_circuit_config.yaml"
    operation: "deconfigure_circuits"
    detailed_logs: true
    state: absent
  register: deconfigure_result
  tags: ['deconfigure']

- name: Display circuits static routes deconfiguration results
  ansible.builtin.debug:
    msg: "{{ deconfigure_result.msg }}"
  when: deconfigure_result is defined and deconfigure_result.msg is defined
  tags: ['deconfigure']
```

**Note:** Circuits cannot be deleted by this operation. A circuit is removed only when its WAN interface is deconfigured (i.e. set to default LAN).

#### Deconfigure WAN interfaces

The operation `deconfigure_wan_circuits_interfaces` is a two-step process:

1. **Stage 1:** Static routes (if any) on the circuit are removed.
2. **Stage 2:** WAN interfaces are deconfigured (set to default LAN). When a WAN interface is deconfigured, the associated circuit is automatically removed.

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/circuit_management.yml --tag deconfigure
ansible-playbook ansible_collections/graphiant/naas/playbooks/interface_management.yml --tag deconfigure_wan --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/interface_management.yml --tag deconfigure_wan
ansible-playbook ansible_collections/graphiant/naas/playbooks/interface_management.yml --tag deconfigure_wan --check
```

```yaml
- name: Deconfigure WAN circuits and interfaces
  graphiant.naas.graphiant_interfaces:
    <<: *graphiant_client_params
    interface_config_file: "sample_interface_config.yaml"
    circuit_config_file: "sample_circuit_config.yaml"
    operation: "deconfigure_wan_circuits_interfaces"
    detailed_logs: true
    state: absent
  tags: ['deconfigure_wan']
  register: deconfigure_wan_result

- name: Display WAN Deconfiguration Results
  ansible.builtin.debug:
    msg: "{{ deconfigure_wan_result.msg }}"
  when: deconfigure_wan_result is defined and deconfigure_wan_result.msg is defined
  tags: ['deconfigure_wan']
```

#### Configure LAN interfaces

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/interface_management.yml --tag lan --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/interface_management.yml --tag lan
```

```yaml
- name: Configure LAN interfaces only
  graphiant.naas.graphiant_interfaces:
    <<: *graphiant_client_params
    interface_config_file: "sample_interface_config.yaml"
    operation: "configure_lan_interfaces"
    detailed_logs: true
    state: present
  tags: ['interfaces', 'lan']
  register: configure_result

- name: Display LAN Interface Configuration Results
  ansible.builtin.debug:
    msg: "{{ configure_result.msg }}"
  when: configure_result is defined and configure_result.msg is defined
  tags: ['interfaces', 'lan']
```

#### Deconfigure LAN interfaces

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/interface_management.yml --tag deconfigure_lan --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/interface_management.yml --tag deconfigure_lan
ansible-playbook ansible_collections/graphiant/naas/playbooks/interface_management.yml --tag deconfigure_lan --check
```

```yaml
- name: Deconfigure LAN interfaces only
  graphiant.naas.graphiant_interfaces:
    <<: *graphiant_client_params
    interface_config_file: "sample_interface_config.yaml"
    operation: "deconfigure_lan_interfaces"
    detailed_logs: true
    state: absent
  tags: ['deconfigure_lan']
  register: deconfigure_lan_result

- name: Display LAN Interface Deconfiguration Results
  ansible.builtin.debug:
    msg: "{{ deconfigure_lan_result.msg }}"
  when: deconfigure_lan_result is defined and deconfigure_lan_result.msg is defined
  tags: ['deconfigure_lan']
```

#### Configure LAN and WAN interfaces together

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/interface_management.yml --tag configure --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/interface_management.yml --tag configure
```

```yaml
- name: Configure all interfaces (combined operation)
  graphiant.naas.graphiant_interfaces:
    <<: *graphiant_client_params
    interface_config_file: "sample_interface_config.yaml"
    circuit_config_file: "sample_circuit_config.yaml"
    operation: "configure_interfaces"
    detailed_logs: true
    state: present
  tags: ['interfaces', 'configure']
  register: configure_result

- name: Display All Interfaces Configuration Results
  ansible.builtin.debug:
    msg: "{{ configure_result.msg }}"
  when: configure_result is defined and configure_result.msg is defined
  tags: ['interfaces', 'configure']
```

## Core (Backbone) Management

Check mode (`--check`) is supported for all backbone operations: no configuration is pushed, and the payloads that would be pushed are logged with a `[check_mode]` prefix so you can see exactly what would be applied.

### Module: graphiant.naas.graphiant_backbone

`graphiant_backbone` manages Graphiant Core (backbone) device configuration via `PUT /v1/devices/{id}/config` on the `core` branch (counterpart to `graphiant_interfaces` on the `edge` branch). A single `config_yaml_file` holds the full Core configuration; each operation slices the appropriate section (interfaces filtered by type / circuit prefix, site block, `vrfs.syslogTargets`, …) and pushes only that slice.

Deconfigure operations are idempotent: parent and VLAN sub-interface existence is checked via `gsdk.get_device_info` before delete payloads are built, and per-VRF `syslogTargets` are checked against `device.segments[*].syslog_targets[*].name`.

| Operation | Purpose |
|---|---|
| `configure` / `deconfigure` | Full Core push or orchestrated teardown (WAN circuits → direct-peer → core-to-core tunnels → core-to-core ifaces → syslog targets) |
| `configure_core_to_core_interfaces` / `deconfigure_core_to_core_interfaces` | Core-to-core links (`loopback`, `core_to_core_link` with optional VLAN sub-interfaces, `disabled`) |
| `configure_core_to_core_tunnel_interfaces` / `deconfigure_core_to_core_tunnel_interfaces` | Core-to-core IPsec tunnels (`core_to_core_ipsec_tunnel`) |
| `configure_wan_circuits` / `deconfigure_wan_circuits` | ISP transit interfaces (circuit prefix `isp-`, plus paired `p2mp_tunnel` entries) |
| `configure_direct_peer_interfaces` / `deconfigure_direct_peer_interfaces` | Direct-peer interfaces (circuit prefix `direct-peer-`) |
| `configure_syslog_targets` / `deconfigure_syslog_targets` | Per-VRF `syslogTargets` under `core.vrfs.<vrf>` |

Sample configs: `configs/sample_backbone_config.yaml` (full Core config covering all interface flavors + sites + syslog) and `configs/sample_backbone_direct_peer_config.yaml` (direct-peer focused).

#### Full Core configure / deconfigure (orchestrated)

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/backbone_management.yml --tag configure --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/backbone_management.yml --tag configure
ansible-playbook ansible_collections/graphiant/naas/playbooks/backbone_management.yml --tag deconfigure
```

```yaml
- name: Push full Core (backbone) configuration
  graphiant.naas.graphiant_backbone:
    <<: *graphiant_client_params
    config_yaml_file: "sample_backbone_config.yaml"
    operation: "configure"
    detailed_logs: true
    state: present
  register: configure_result
  tags: ['backbone', 'configure']

- name: Deconfigure all backbone resources (orchestrated teardown)
  graphiant.naas.graphiant_backbone:
    <<: *graphiant_client_params
    config_yaml_file: "sample_backbone_config.yaml"
    operation: "deconfigure"
    detailed_logs: true
    state: absent
  register: deconfigure_result
  tags: ['backbone', 'deconfigure']
```

#### Core-to-core interfaces (loopback + core_to_core_link with optional VLANs)

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/backbone_management.yml --tag configure_core_to_core_interfaces
ansible-playbook ansible_collections/graphiant/naas/playbooks/backbone_management.yml --tag deconfigure_core_to_core_interfaces
```

```yaml
- name: Configure core-to-core interfaces
  graphiant.naas.graphiant_backbone:
    <<: *graphiant_client_params
    config_yaml_file: "sample_backbone_config.yaml"
    operation: "configure_core_to_core_interfaces"
    detailed_logs: true
    state: present
  register: configure_result
  tags: ['backbone', 'configure_core_to_core_interfaces']

- name: Deconfigure core-to-core interfaces (reset to enterprise default LAN)
  graphiant.naas.graphiant_backbone:
    <<: *graphiant_client_params
    config_yaml_file: "sample_backbone_config.yaml"
    operation: "deconfigure_core_to_core_interfaces"
    detailed_logs: true
    state: absent
  tags: ['backbone', 'deconfigure_core_to_core_interfaces']
```

#### Core-to-core IPsec tunnels

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/backbone_management.yml --tag configure_core_to_core_tunnel_interfaces
ansible-playbook ansible_collections/graphiant/naas/playbooks/backbone_management.yml --tag deconfigure_core_to_core_tunnel_interfaces
```

```yaml
- name: Configure core-to-core IPsec tunnel interfaces
  graphiant.naas.graphiant_backbone:
    <<: *graphiant_client_params
    config_yaml_file: "sample_backbone_config.yaml"
    operation: "configure_core_to_core_tunnel_interfaces"
    detailed_logs: true
    state: present
  tags: ['backbone', 'configure_core_to_core_tunnel_interfaces']

- name: Deconfigure core-to-core IPsec tunnel interfaces
  graphiant.naas.graphiant_backbone:
    <<: *graphiant_client_params
    config_yaml_file: "sample_backbone_config.yaml"
    operation: "deconfigure_core_to_core_tunnel_interfaces"
    detailed_logs: true
    state: absent
  tags: ['backbone', 'deconfigure_core_to_core_tunnel_interfaces']
```

The `tunnel_underlay` interface is pre-pushed into an ISP VRF before the tunnel is inserted; without this the SDK rejects the request with `interface_tunnel: provided local interface is the incorrect type or not in an ISP VRF`.

#### WAN ISP circuits

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/backbone_management.yml --tag configure_wan_circuits
ansible-playbook ansible_collections/graphiant/naas/playbooks/backbone_management.yml --tag deconfigure_wan_circuits
```

```yaml
- name: Configure backbone WAN ISP circuit interfaces
  graphiant.naas.graphiant_backbone:
    <<: *graphiant_client_params
    config_yaml_file: "sample_backbone_config.yaml"
    operation: "configure_wan_circuits"
    detailed_logs: true
    state: present
  tags: ['backbone', 'configure_wan_circuits']

- name: Deconfigure backbone WAN ISP circuit interfaces
  graphiant.naas.graphiant_backbone:
    <<: *graphiant_client_params
    config_yaml_file: "sample_backbone_config.yaml"
    operation: "deconfigure_wan_circuits"
    detailed_logs: true
    state: absent
  tags: ['backbone', 'deconfigure_wan_circuits']
```

`p2mp_tunnel` interfaces paired with an ISP circuit are lifecycle-coupled to the circuit: the SDK auto-deletes the tunnel when the circuit is deconfigured, so p2mp tunnels are configured alongside the WAN circuit and never explicitly deconfigured.

#### Direct-peer interfaces

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/backbone_management.yml --tag configure_direct_peer_interfaces
ansible-playbook ansible_collections/graphiant/naas/playbooks/backbone_management.yml --tag deconfigure_direct_peer_interfaces
```

```yaml
- name: Configure backbone direct-peer interfaces
  graphiant.naas.graphiant_backbone:
    <<: *graphiant_client_params
    config_yaml_file: "sample_backbone_direct_peer_config.yaml"
    operation: "configure_direct_peer_interfaces"
    detailed_logs: true
    state: present
  tags: ['backbone', 'configure_direct_peer_interfaces']

- name: Deconfigure backbone direct-peer interfaces
  graphiant.naas.graphiant_backbone:
    <<: *graphiant_client_params
    config_yaml_file: "sample_backbone_direct_peer_config.yaml"
    operation: "deconfigure_direct_peer_interfaces"
    detailed_logs: true
    state: absent
  tags: ['backbone', 'deconfigure_direct_peer_interfaces']
```

#### Per-VRF syslog targets

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/backbone_management.yml --tag configure_syslog_targets
ansible-playbook ansible_collections/graphiant/naas/playbooks/backbone_management.yml --tag deconfigure_syslog_targets
```

```yaml
- name: Configure per-VRF backbone syslog targets
  graphiant.naas.graphiant_backbone:
    <<: *graphiant_client_params
    config_yaml_file: "sample_backbone_config.yaml"
    operation: "configure_syslog_targets"
    detailed_logs: true
    state: present
  tags: ['backbone', 'configure_syslog_targets']

- name: Deconfigure per-VRF backbone syslog targets
  graphiant.naas.graphiant_backbone:
    <<: *graphiant_client_params
    config_yaml_file: "sample_backbone_config.yaml"
    operation: "deconfigure_syslog_targets"
    detailed_logs: true
    state: absent
  tags: ['backbone', 'deconfigure_syslog_targets']
```

### Module: graphiant.naas.graphiant_vrrp

#### Configure VRRP on interfaces

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/vrrp_interface_management.yml --tag configure --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/vrrp_interface_management.yml --tag configure
```

```yaml
- name: Configure VRRP on interfaces
  graphiant.naas.graphiant_vrrp:
    <<: *graphiant_client_params
    operation: configure
    vrrp_config_file: "sample_vrrp_config.yaml"
    detailed_logs: true
    state: present
  register: configure_result
  tags: ['vrrp_interfaces', 'configure']

- name: Display VRRP Configuration Results
  ansible.builtin.debug:
    msg: "{{ configure_result.msg }}"
  when: configure_result is defined and configure_result.msg is defined
  tags: ['vrrp_interfaces', 'configure']
```

#### Disable VRRP on interfaces

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/vrrp_interface_management.yml --tag deconfigure --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/vrrp_interface_management.yml --tag deconfigure
ansible-playbook ansible_collections/graphiant/naas/playbooks/vrrp_interface_management.yml --tag deconfigure --check
```

```yaml
- name: Deconfigure VRRP from interfaces (disable)
  graphiant.naas.graphiant_vrrp:
    <<: *graphiant_client_params
    operation: deconfigure
    vrrp_config_file: "sample_vrrp_config.yaml"
    detailed_logs: true
    state: absent
  register: deconfigure_result
  tags: ['vrrp_interfaces', 'deconfigure']

- name: Display VRRP Deconfiguration Results
  ansible.builtin.debug:
    msg: "{{ deconfigure_result.msg }}"
  when: deconfigure_result is defined and deconfigure_result.msg is defined
  tags: ['vrrp_interfaces', 'deconfigure']
```

#### Enable existing VRRP configuration on interfaces

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/vrrp_interface_management.yml --tag enable --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/vrrp_interface_management.yml --tag enable
ansible-playbook ansible_collections/graphiant/naas/playbooks/vrrp_interface_management.yml --tag enable --check
```

```yaml
- name: Enable existing VRRP configurations
  graphiant.naas.graphiant_vrrp:
    <<: *graphiant_client_params
    operation: enable
    vrrp_config_file: "sample_vrrp_config.yaml"
    detailed_logs: true
  register: enable_result
  tags: ['vrrp_interfaces', 'enable']

- name: Display VRRP Enable Results
  ansible.builtin.debug:
    msg: "{{ enable_result.msg }}"
  when: enable_result is defined and enable_result.msg is defined
  tags: ['vrrp_interfaces', 'enable']
```

### Module: graphiant.naas.graphiant_lag_interfaces

#### Configure LAG interfaces and subinterfaces

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/lag_interface_management.yml --tag configure --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/lag_interface_management.yml --tag configure
```

```yaml
- name: Configure LAG interfaces (LAG + optional subinterfaces)
  graphiant.naas.graphiant_lag_interfaces:
    <<: *graphiant_client_params
    operation: configure
    lag_config_file: "sample_lag_interface_config.yaml"
    detailed_logs: true
    state: present
  register: configure_result
  tags: ['configure']

- name: Display LAG Configuration Results
  ansible.builtin.debug:
    msg: "{{ configure_result.msg }}"
  when: configure_result is defined and configure_result.msg is defined
  tags: ['configure']
```

#### Add LAG members

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/lag_interface_management.yml --tag add_lag_members --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/lag_interface_management.yml --tag add_lag_members
ansible-playbook ansible_collections/graphiant/naas/playbooks/lag_interface_management.yml --tag add_lag_members --check
```

```yaml
- name: Add LAG members
  graphiant.naas.graphiant_lag_interfaces:
    <<: *graphiant_client_params
    operation: add_lag_members
    lag_config_file: "sample_lag_interface_config.yaml"
    detailed_logs: true
  register: add_members_result
  tags: ['add_lag_members']

- name: Display Add LAG Members Results
  ansible.builtin.debug:
    msg: "{{ add_members_result.msg }}"
  when: add_members_result is defined and add_members_result.msg is defined
  tags: ['add_lag_members']
```

#### Remove LAG members

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/lag_interface_management.yml --tag add_lag_members --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/lag_interface_management.yml --tag remove_lag_members --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/lag_interface_management.yml --tag remove_lag_members
ansible-playbook ansible_collections/graphiant/naas/playbooks/lag_interface_management.yml --tag remove_lag_members --check
```

```yaml
- name: Remove LAG members
  graphiant.naas.graphiant_lag_interfaces:
    <<: *graphiant_client_params
    operation: remove_lag_members
    lag_config_file: "sample_lag_interface_config.yaml"
    detailed_logs: true
  register: remove_members_result
  tags: ['remove_lag_members']

- name: Display Remove LAG Members Results
  ansible.builtin.debug:
    msg: "{{ remove_members_result.msg }}"
  when: remove_members_result is defined and remove_members_result.msg is defined
  tags: ['remove_lag_members']
```

#### Update LACP configuration on LAG interfaces

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/lag_interface_management.yml --tag update_lacp_configs --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/lag_interface_management.yml --tag update_lacp_configs
ansible-playbook ansible_collections/graphiant/naas/playbooks/lag_interface_management.yml --tag update_lacp_configs --check
```

```yaml
- name: Update LACP settings (mode/timer)
  graphiant.naas.graphiant_lag_interfaces:
    <<: *graphiant_client_params
    operation: update_lacp_configs
    lag_config_file: "sample_lag_interface_config.yaml"
    detailed_logs: true
  register: update_lacp_result
  tags: ['update_lacp_configs']

- name: Display Update LACP Results
  ansible.builtin.debug:
    msg: "{{ update_lacp_result.msg }}"
  when: update_lacp_result is defined and update_lacp_result.msg is defined
  tags: ['update_lacp_configs']
```

#### Delete LAG subinterfaces

Idempotent: skips if LAG or subinterface does not exist.

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/lag_interface_management.yml --tag delete_lag_subinterfaces --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/lag_interface_management.yml --tag delete_lag_subinterfaces
ansible-playbook ansible_collections/graphiant/naas/playbooks/lag_interface_management.yml --tag delete_lag_subinterfaces --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/lag_interface_management.yml --tag configure
ansible-playbook ansible_collections/graphiant/naas/playbooks/lag_interface_management.yml --tag delete_lag_subinterfaces --check
```

```yaml
- name: Delete LAG subinterfaces (VLANs)
  graphiant.naas.graphiant_lag_interfaces:
    <<: *graphiant_client_params
    operation: delete_lag_subinterfaces
    lag_config_file: "sample_lag_interface_config.yaml"
    detailed_logs: true
  register: delete_subif_result
  tags: ['delete_lag_subinterfaces']

- name: Display Delete LAG Subinterfaces Results
  ansible.builtin.debug:
    msg: "{{ delete_subif_result.msg }}"
  when: delete_subif_result is defined and delete_subif_result.msg is defined
  tags: ['delete_lag_subinterfaces']
```

#### Deconfigure LAG interfaces (delete subinterfaces, then delete LAG)

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/lag_interface_management.yml --tag deconfigure --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/lag_interface_management.yml --tag deconfigure
ansible-playbook ansible_collections/graphiant/naas/playbooks/lag_interface_management.yml --tag deconfigure --check
```

```yaml
- name: Deconfigure LAG interfaces (delete subinterfaces + delete LAG)
  graphiant.naas.graphiant_lag_interfaces:
    <<: *graphiant_client_params
    operation: deconfigure
    lag_config_file: "sample_lag_interface_config.yaml"
    detailed_logs: true
    state: absent
  register: deconfigure_result
  tags: ['deconfigure']

- name: Display LAG Deconfiguration Results
  ansible.builtin.debug:
    msg: "{{ deconfigure_result.msg }}"
  when: deconfigure_result is defined and deconfigure_result.msg is defined
  tags: ['deconfigure']
```

## MACsec (802.1AE)

### Module: graphiant.naas.graphiant_macsec

`graphiant_macsec` configures interface MACsec on Edge/Gateway devices using `PUT /v1/devices/{id}/config`:

- **Ethernet or LAG main interfaces** — `edge.interfaces.{name}.interface.macsec.macsec` or `edge.lagInterfaces.{name}.interface.macsec.macsec` (not subinterfaces)
- **Enable/disable**, encryption enforcement mode, key server priority
- **Pre-shared keys (PSK)** — up to 3 per interface; rotate with `state: absent` on a key entry (at least one must remain when enabled)
- **SAK profile** — replay protection window and rekey interval

Configure-only (`state: present` at module level). Requires a **software image with MACsec support** on the target device.

**Prerequisites:** main LAN interfaces must exist (`interface_management.yml --tags lan`). For MACsec on a LAG, configure the LAG first (`lag_interface_management.yml --tags configure`).

**CAK (recommended):** omit `cak` from YAML; set `ckn` on each key and pass `vault_devices_macsec_psk` (device → interface → ckn → cak) via Ansible Vault. Plaintext `cak` in YAML or module params is for dev/local only. Diffs redact CAK and show `cakConfigured` booleans. Use `no_log: true` on tasks that pass secrets.

Partial updates merge with portal state (disable with `enabled: false`, priority-only, PSK rotation, SAK-only). With `--check`, nothing is pushed; use `--diff` for `details.diff_plan` and Ansible `diff`.

Use `configs/sample_macsec.yaml` (top-level `macsec` list, same pattern as `edge_services`).

Query operational status with `graphiant_macsec_info` (`GET /v2/monitoring/macsec/{device_id}/status`).

#### Vault setup

Required when CAK is supplied via Ansible Vault (`vault_devices_macsec_psk` in `vault_secrets.yml`). Use the `configure` tag and pass `--vault-password-file` on every run (including `--check`). For dev-only plaintext `cak` in the config YAML, use `configure_without_vault` instead.

```bash
cp ansible_collections/graphiant/naas/configs/vault_secrets.yml.example ansible_collections/graphiant/naas/configs/vault_secrets.yml
# Edit vault_devices_macsec_psk (device → interface → ckn → cak), then:
export ANSIBLE_VAULT_PASSPHRASE="*************"
ansible-vault encrypt ansible_collections/graphiant/naas/configs/vault_secrets.yml --vault-password-file ansible_collections/graphiant/naas/configs/vault-password-file.sh
```

### Playbook

Tags: `configure` (YAML + vault for CAK), `configure_without_vault` (YAML only, no vault load), `configure_params_examples`, `status`, `info`.

**With vault** (`configure`):

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/macsec_management.yml --tags configure -e config_file=sample_macsec.yaml --check --diff --vault-password-file ansible_collections/graphiant/naas/configs/vault-password-file.sh
ansible-playbook ansible_collections/graphiant/naas/playbooks/macsec_management.yml --tags configure -e config_file=sample_macsec.yaml --vault-password-file ansible_collections/graphiant/naas/configs/vault-password-file.sh
```

**Without vault** (`configure_without_vault`) — only when each key has plaintext `cak` in the config YAML (dev/local):

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/macsec_management.yml --tags configure_without_vault -e config_file=sample_macsec.yaml --check --diff
ansible-playbook ansible_collections/graphiant/naas/playbooks/macsec_management.yml --tags configure_without_vault -e config_file=sample_macsec.yaml
```

**Module-parameter examples** and **monitoring status**:

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/macsec_management.yml --tags configure_params_examples --vault-password-file ansible_collections/graphiant/naas/configs/vault-password-file.sh
ansible-playbook ansible_collections/graphiant/naas/playbooks/macsec_management.yml --tags status -e macsec_device=edge-1-sdktest
```

### Module task

From YAML **with vault**:

```yaml
- name: Load vault secrets for MACsec
  ansible.builtin.include_vars:
    file: vault_secrets.yml
  no_log: true

- name: Configure MACsec from YAML
  graphiant.naas.graphiant_macsec:
    <<: *graphiant_client_params
    operation: configure
    macsec_config_file: "{{ config_file }}"
    vault_devices_macsec_psk: "{{ vault_devices_macsec_psk | default({}) }}"
    detailed_logs: true
    state: present
  register: configure_result
  no_log: true

- name: Display configure result
  ansible.builtin.debug:
    msg: |
      {{ configure_result.msg | trim }}
      configured_devices={{ configure_result.configured_devices | default([]) }}
      skipped_devices={{ configure_result.skipped_devices | default([]) }}
  when: configure_result is defined and configure_result.msg is defined
```

**Single device** via module parameters (LAG example):

```yaml
- name: Enable MACsec on LAG1
  graphiant.naas.graphiant_macsec:
    <<: *graphiant_client_params
    operation: configure
    device: "edge-1-sdktest"
    vault_devices_macsec_psk: "{{ vault_devices_macsec_psk | default({}) }}"
    interfaces:
      LAG1:
        enabled: true
        encryptionEnforcementMode: MACSEC_ENFORCEMENT_MODE_MUST_ENCRYPT
        keyServerPriority: 200
        presharedKeys:
          - nickname: macsec-key-1
            startTime: "2029-12-11 11:12:13"
            ckn: "853c6a4eb4f21c58a5bfeb9600dd26e8e045ded866b02a45f5f52cebadcd5956"
            cipherSuite: AES_256_CMAC
            useXpnForCipherSuite: true
        sakConfiguration:
          replayProtectionWindowSize: 64
          rekeyInterval: 3600
    state: present
  no_log: true
```

**Disable**, **rotate keys**, and **SAK-only** updates:

```yaml
- name: Disable MACsec on an interface
  graphiant.naas.graphiant_macsec:
    <<: *graphiant_client_params
    operation: configure
    device: "edge-1-sdktest"
    interfaces:
      LAG1:
        enabled: false
    state: present

- name: Rotate MACsec keys (remove key1, keep key2)
  graphiant.naas.graphiant_macsec:
    <<: *graphiant_client_params
    operation: configure
    device: "edge-1-sdktest"
    vault_devices_macsec_psk: "{{ vault_devices_macsec_psk | default({}) }}"
    interfaces:
      GigabitEthernet7/0/0:
        presharedKeys:
          - nickname: key1
            state: absent
    state: present
  no_log: true

- name: Update SAK replay window only
  graphiant.naas.graphiant_macsec:
    <<: *graphiant_client_params
    operation: configure
    device: "edge-1-sdktest"
    interfaces:
      LAG1:
        sakConfiguration:
          replayProtectionWindowSize: 62
    state: present
```

There is no module-level `deconfigure` or `state: absent`. To turn off MACsec, set `enabled: false` on the interface. To remove a PSK, use `state: absent` on that key entry (see `tests/test.py` MACsec tests).

**PSK rotation:** the API does not allow updating an existing nickname in place (same behavior as the portal UI). Add a new `presharedKeys` entry with a **unique nickname**, then delete the old key with `state: absent`. Listing an unchanged existing key in YAML is idempotent and does not re-push CAK. SAK-only or `enabled` changes push without touching existing PSKs. CAK is omitted from Ansible `--diff` output (`cakConfigured` is shown instead).

### Module: graphiant.naas.graphiant_macsec_info

Read-only monitoring status per interface (`MACSEC_STATUS_SECURE`, `MACSEC_STATUS_UNSECURE`).

```yaml
- name: Get MACsec status for all interfaces
  graphiant.naas.graphiant_macsec_info:
    <<: *graphiant_client_params
    device: "edge-1-sdktest"
    detailed_logs: true
  register: macsec_status

- name: Display MACsec statuses
  ansible.builtin.debug:
    var: macsec_status.macsec_statuses

- name: Get MACsec status for one interface
  graphiant.naas.graphiant_macsec_info:
    <<: *graphiant_client_params
    device: "edge-1-sdktest"
    interface: LAG1
  register: lag_macsec_status
```

## Prefix and Port Lists

### Module: graphiant.naas.graphiant_prefix_port_list

`graphiant_prefix_port_list` manages device-level prefix and port lists via `PUT /v1/devices/{id}/config`:

- **Prefix lists** — `edge.trafficPolicy.networkLists` (named CIDR collections)
- **Port lists** — `edge.trafficPolicy.portLists` (named port number collections)

Create operations compare intended lists to live device state and skip the push when already matched. Delete operations remove only the list names listed in the YAML for each device. Check mode (`--check`) and diff mode (`--diff`) are supported — use `--check --diff` to preview `details.diff_plan` and Ansible `diff`.

Use `configs/sample_prefix_and_port_list.yaml`. Top-level keys are `networkLists` and `portLists` (each a list of device entries). Under each device name, list entries use `name`, `networks` or `ports`, and optional `state: absent` on create operations to delete a single list (`list: null`) without removing other entries in the same file.

**Prerequisite for:** traffic policy and security policy rules that reference custom applications often depend on edge services (DPI); prefix/port lists are used directly in policy match criteria and edge services where network/port list objects are required. Configure prefix/port lists before traffic or security policy when your design references those names.

### Playbook

Playbook file: `playbooks/prefix_port_list_mangement.yml` (note spelling).

Tags: `create_prefix_port_lists`, `delete_prefix_port_lists`, `create_prefix_lists`, `delete_prefix_lists`, `create_port_lists`, `delete_port_lists`.

```bash
# Create prefix and port lists (dry run, then apply)
ansible-playbook ansible_collections/graphiant/naas/playbooks/prefix_port_list_mangement.yml --tags create_prefix_port_lists --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/prefix_port_list_mangement.yml --tags create_prefix_port_lists --check --diff
ansible-playbook ansible_collections/graphiant/naas/playbooks/prefix_port_list_mangement.yml --tags create_prefix_port_lists

# Delete prefix and port lists listed in the YAML
ansible-playbook ansible_collections/graphiant/naas/playbooks/prefix_port_list_mangement.yml --tags delete_prefix_port_lists --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/prefix_port_list_mangement.yml --tags delete_prefix_port_lists

# Prefix lists or port lists only
ansible-playbook ansible_collections/graphiant/naas/playbooks/prefix_port_list_mangement.yml --tags create_prefix_lists
ansible-playbook ansible_collections/graphiant/naas/playbooks/prefix_port_list_mangement.yml --tags delete_prefix_lists
ansible-playbook ansible_collections/graphiant/naas/playbooks/prefix_port_list_mangement.yml --tags create_port_lists
ansible-playbook ansible_collections/graphiant/naas/playbooks/prefix_port_list_mangement.yml --tags delete_port_lists
```

### Module task

**Create prefix and port lists:**

```yaml
- name: Create prefix and port lists
  graphiant.naas.graphiant_prefix_port_list:
    <<: *graphiant_client_params
    operation: create_prefix_port_lists
    prefix_port_list_config_file: "sample_prefix_and_port_list.yaml"
    detailed_logs: true
    state: present
  register: create_result
  tags: ['create_prefix_port_lists']

- name: Display create result
  ansible.builtin.debug:
    msg: |
      {{ create_result.msg | trim }}
      configured_devices={{ create_result.configured_devices | default([]) }}
      skipped_devices={{ create_result.skipped_devices | default([]) }}
  when: create_result is defined and create_result.msg is defined
  tags: ['create_prefix_port_lists']
```

**Delete prefix and port lists** (removes every list name listed under each device in the YAML):

```yaml
- name: Delete prefix and port lists
  graphiant.naas.graphiant_prefix_port_list:
    <<: *graphiant_client_params
    operation: delete_prefix_port_lists
    prefix_port_list_config_file: "sample_prefix_and_port_list.yaml"
    detailed_logs: true
    state: absent
  register: delete_result
  tags: ['delete_prefix_port_lists']

- name: Display delete result
  ansible.builtin.debug:
    msg: |
      {{ delete_result.msg | trim }}
      configured_devices={{ delete_result.configured_devices | default([]) }}
      skipped_devices={{ delete_result.skipped_devices | default([]) }}
  when: delete_result is defined and delete_result.msg is defined
  tags: ['delete_prefix_port_lists']
```

**Create or delete prefix lists only** (`create_prefix_lists` / `delete_prefix_lists`) or **port lists only** (`create_port_lists` / `delete_port_lists`) — same YAML file; set `operation` accordingly and omit the other list type from the payload.

### Config YAML (`configs/sample_prefix_and_port_list.yaml`)

```yaml
networkLists:
  - edge-1-sdktest:
    - name: graphiant_dia_prefix
      networks:
        - 1.1.1.1/32
        - 8.8.8.8/32
    - name: testing_prefix_list
      networks:
        - 10.1.1.0/24
        - 10.1.2.0/24
      state: absent          # on create_*: delete this list only (list: null)

portLists:
  - edge-1-sdktest:
    - name: web_ports
      ports:
        - 80
        - 443
    - name: testing_port_list
      ports:
        - 123
```

**Per-list deletion on create** (under `create_*` operations; default is present):

```yaml
- name: old_prefix_list
  networks:
    - 10.0.0.0/8
  state: absent
```

**Operations:**

| Operation | Description |
|-----------|-------------|
| `create_prefix_port_lists` | Create or update both prefix and port lists in the YAML |
| `delete_prefix_port_lists` | Delete all prefix and port list names listed per device |
| `create_prefix_lists` | Create or update prefix lists only (`networkLists`) |
| `delete_prefix_lists` | Delete listed prefix lists only |
| `create_port_lists` | Create or update port lists only (`portLists`) |
| `delete_port_lists` | Delete listed port lists only |

When `operation` is omitted, `state: present` maps to `create_prefix_port_lists` and `state: absent` maps to `delete_prefix_port_lists`.

## Traffic Policies

### Module: graphiant.naas.graphiant_traffic_policy

`graphiant_traffic_policy` manages device-level traffic policy rulesets and LAN segment attachments via `PUT /v1/devices/{id}/config` (`edge.trafficPolicy.trafficRulesets` and `edge.segments.<segment>.trafficRuleset`).

- **Traffic rulesets** — named collections of rules with sequence numbers, match criteria (application, network/L4, DSCP), SLA class, and egress action (overlay, DIA, or IPsec circuit selection)
- **LAN segment attachments** — map each segment name to a ruleset reference under `segments` in the YAML
- **Rule shorthand** — match fields (`applicationBuiltin`, `ipProtocol`, `destinationNetwork`, and so on) may be listed at rule top level; the manager normalizes them to API shape on push
- **Per-rule action** — optional `remarkCodePoint`, `primaryCircuitLabel`, and `backupCircuitLabel` (required for `dia` / `ipsec` egress when circuit labels apply)

Configure-only operations require LAN segments to be attached separately (or use the `configure` tag, which runs both steps). Check mode (`--check`) and diff mode (`--diff`) are supported — the module reads live device state, skips writes in check mode, and sets `changed` from whether an apply would update at least one device. Use `--check --diff` to preview `details.diff_plan` and Ansible `diff`. Ruleset diffs list only changed rules under `rules` (plus `_meta` when ruleset metadata changes); segment attach/detach diffs show per-segment ruleset references.

Use `configs/sample_device_traffic_policies.yaml`. Top-level key is `trafficPolicyObject` (list of devices). Each device entry contains `trafficRulesets` (list of rulesets) and `segments` (map of segment name to ruleset name).

**Prerequisites:** Configure prefix/port lists (`graphiant_prefix_port_list`) and edge services (DPI applications) before rules that reference `applicationCustom`. WAN circuits must exist before rules with `egress: dia` or `egress: ipsec` and circuit labels. Integration tests in `tests/test.py` run `test_configure_prefix_and_port_list` and `test_configure_edge_services` before traffic policy tests.

### Playbook

Tags: `configure` (configure rulesets + attach to LAN segments), `deconfigure` (detach from segments + delete rulesets), `attach_to_lan_segments`, `detach_from_lan_segments`.

```bash
# Configure (dry run, then apply)
ansible-playbook ansible_collections/graphiant/naas/playbooks/traffic_policies_management.yml --tags configure --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/traffic_policies_management.yml --tags configure --check --diff
ansible-playbook ansible_collections/graphiant/naas/playbooks/traffic_policies_management.yml --tags configure

# Deconfigure (dry run, then apply)
ansible-playbook ansible_collections/graphiant/naas/playbooks/traffic_policies_management.yml --tags deconfigure --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/traffic_policies_management.yml --tags deconfigure --check --diff
ansible-playbook ansible_collections/graphiant/naas/playbooks/traffic_policies_management.yml --tags deconfigure

# Attach / detach LAN segments only
ansible-playbook ansible_collections/graphiant/naas/playbooks/traffic_policies_management.yml --tags attach_to_lan_segments
ansible-playbook ansible_collections/graphiant/naas/playbooks/traffic_policies_management.yml --tags detach_from_lan_segments
```

### Module task

**Configure rulesets** (`configure` tag — runs configure then attach_to_lan_segments):

```yaml
- name: Configure device-level traffic policy rulesets
  graphiant.naas.graphiant_traffic_policy:
    <<: *graphiant_client_params
    operation: configure
    traffic_policy_config_file: "sample_device_traffic_policies.yaml"
    detailed_logs: true
    state: present
  register: configure_result
  tags: ['configure']

- name: Display configure result
  ansible.builtin.debug:
    msg: |
      {{ configure_result.msg | trim }}
      configured_devices={{ configure_result.configured_devices | default([]) }}
      skipped_devices={{ configure_result.skipped_devices | default([]) }}
  when: configure_result is defined and configure_result.msg is defined
  tags: ['configure']
```

**Attach rulesets to LAN segments** (run after `configure`, or standalone to update segment assignments):

```yaml
- name: Attach traffic ruleset to LAN segments
  graphiant.naas.graphiant_traffic_policy:
    <<: *graphiant_client_params
    operation: attach_to_lan_segments
    traffic_policy_config_file: "sample_device_traffic_policies.yaml"
    detailed_logs: true
  register: attach_result
  tags: ['configure', 'attach_to_lan_segments']

- name: Display attach-to-segments result
  ansible.builtin.debug:
    msg: |
      {{ attach_result.msg | trim }}
      configured_devices={{ attach_result.configured_devices | default([]) }}
      skipped_devices={{ attach_result.skipped_devices | default([]) }}
  when: attach_result is defined and attach_result.msg is defined
  tags: ['configure', 'attach_to_lan_segments']
```

**Detach rulesets from LAN segments** (run before `deconfigure` to clear segment references first):

```yaml
- name: Detach traffic ruleset from LAN segments
  graphiant.naas.graphiant_traffic_policy:
    <<: *graphiant_client_params
    operation: detach_from_lan_segments
    traffic_policy_config_file: "sample_device_traffic_policies.yaml"
    detailed_logs: true
  register: detach_result
  tags: ['deconfigure', 'detach_from_lan_segments']

- name: Display detach-from-segments result
  ansible.builtin.debug:
    msg: |
      {{ detach_result.msg | trim }}
      configured_devices={{ detach_result.configured_devices | default([]) }}
      skipped_devices={{ detach_result.skipped_devices | default([]) }}
  when: detach_result is defined and detach_result.msg is defined
  tags: ['deconfigure', 'detach_from_lan_segments']
```

**Deconfigure rulesets** (run after `detach_from_lan_segments` — removes rulesets listed in the YAML):

```yaml
- name: Deconfigure device-level traffic policy rulesets
  graphiant.naas.graphiant_traffic_policy:
    <<: *graphiant_client_params
    operation: deconfigure
    traffic_policy_config_file: "sample_device_traffic_policies.yaml"
    detailed_logs: true
    state: absent
  register: deconfigure_result
  tags: ['deconfigure']

- name: Display deconfigure result
  ansible.builtin.debug:
    msg: |
      {{ deconfigure_result.msg | trim }}
      configured_devices={{ deconfigure_result.configured_devices | default([]) }}
      skipped_devices={{ deconfigure_result.skipped_devices | default([]) }}
  when: deconfigure_result is defined and deconfigure_result.msg is defined
  tags: ['deconfigure']
```

### Config YAML (`configs/sample_device_traffic_policies.yaml`)

```yaml
trafficPolicyObject:
  - edge-1-sdktest:
      trafficRulesets:
        - name: Edge-1-Traffic-Policy
          description: Application and network steering
          rules:
            - seq: 1
              applicationBuiltin: Office 365
              logging: true
              slaClass: Gold                    # Default | Bronze | Silver | Gold
              egress: overlay                   # overlay | dia | ipsec

            - seq: 200
              ipProtocol: udp                   # any | icmp | igmp | tcp | udp | esp | ah
              destinationPort: 53
              destinationNetwork: 0.0.0.0/0
              logging: true
              slaClass: Silver
              egress: dia
              primaryCircuitLabel: internet_dia_2   # required for dia egress

            - seq: 300
              applicationCustom: graphiant_dia_ping   # requires DPI app from edge_services
              logging: true
              slaClass: Gold
              egress: ipsec
              primaryCircuitLabel:
                ipsecLabel: ipsec_label_1
              backupCircuitLabel:
                ipsecLabel: ipsec_label_2

        - name: Edge-2-Traffic-Policy
          description: Catch-all and remark example
          rules:
            - seq: 2000
              sourceNetwork: 10.10.10.0/24
              destinationNetwork: 20.20.20.0/24
              dscpCodePoint: 1                      # match DSCP 0-63
              logging: true
              slaClass: Default
              remarkCodePoint: 3                    # remark DSCP 0-63
              egress: dia
              primaryCircuitLabel: internet_dia_2

      segments:
        lan-1-test: Edge-2-Traffic-Policy          # segment name -> ruleset name
```

**Per-object deletion** (under `configure`; `state: absent` targets individual objects):

```yaml
# Delete one ruleset by name
- name: My-Ruleset
  state: absent

# Delete one rule by seq (only seq required)
- seq: 500
  state: absent
```

**Required rule fields:**

| Field | Description |
|-------|-------------|
| `seq` | Rule sequence number (unique within the ruleset) |
| `logging` | `true` or `false` |
| `slaClass` | `Default`, `Bronze`, `Silver`, or `Gold` |
| `egress` | `overlay`, `dia`, or `ipsec` |

**Optional match fields** (rule shorthand — may appear at rule top level):

| Key | Description |
|-----|-------------|
| `applicationBuiltin` | Portal built-in application name |
| `applicationCustom` | Custom DPI application name (configure via `graphiant_edge_services` first) |
| `ipProtocol` | `any`, `icmp`, `igmp`, `tcp`, `udp`, `esp`, `ah` |
| `sourceNetwork` / `destinationNetwork` | CIDR string |
| `sourcePort` / `destinationPort` | Port number 1–65535 (meaningful for `tcp` / `udp`) |
| `dscpCodePoint` | DSCP match value 0–63 |
| `icmpType` | ICMP type when `ipProtocol` is `icmp` (see sample YAML comments for values) |

**Optional action / egress fields:**

| Key | Description |
|-----|-------------|
| `primaryCircuitLabel` | DIA circuit label string, or `{ipsecLabel: ...}` for IPsec |
| `backupCircuitLabel` | Optional backup circuit (same shapes as primary) |
| `remarkCodePoint` | DSCP remark value 0–63 |

For `egress: overlay`, circuit labels are usually omitted. For `egress: dia`, set `primaryCircuitLabel` to an existing WAN circuit label. For `egress: ipsec`, use `ipsecLabel` objects under the circuit label fields.

**Check and diff mode**

With `--check`, nothing is pushed; the module reads live device state and sets `changed` from whether an apply would update at least one device. Would-be payloads are logged with a `[check_mode]` prefix when `detailed_logs: true`.

With `--diff`, pending changes appear in Ansible `diff` (`before` / `after`) and `details.diff_plan`. Each `diff_plan` entry includes `device`, `branch`, and normalized snapshots:

| Branch | Diff shape |
|--------|------------|
| `edge.trafficPolicy.trafficRulesets` | Per ruleset: changed rules only under `rules.<seq>`; metadata under `_meta` |
| `edge.segments` | Per segment: `ruleset` reference before and after |

Example `details.diff_plan` entry for a single rule update:

```yaml
- device: edge-1-sdktest
  branch: edge.trafficPolicy.trafficRulesets
  before:
    trafficRulesets:
      Edge-1-Traffic-Policy:
        rules:
          "200":
            seq: 200
            action:
              primaryCircuitLabel:
                label: internet_dia_1
  after:
    trafficRulesets:
      Edge-1-Traffic-Policy:
        rules:
          "200":
            seq: 200
            action:
              primaryCircuitLabel:
                label: internet_dia_2
```

Unchanged rules are omitted from the diff. Rule deletions show the existing rule in `before` and `null` in `after` for that sequence key.

## Security Policies

### Module: graphiant.naas.graphiant_security_policy

`graphiant_security_policy` manages device-level security policy rulesets and zone pair attachments via `PUT /v1/devices/{id}/config` (`edge.trafficPolicy.securityRulesets` and `edge.trafficPolicy.zones`).

- **Security rulesets** — named collections of rules with sequence numbers, actions (`accept`, `reject`, `inspect`, `drop`), and match criteria (application, network/L4, content filter, domain list)
- **Zone pair attachments** — directional pairs (fromZone → toZone) that reference a named ruleset; optional `tcpProtection` flag per pair
- **Meter rates** — per-rule uplink/downlink policing rates (`uplinkPolicerRate`, `uplinkBurstRate`, `downlinkPolicerRate`, `downlinkBurstRate`)
- **Implicit rule action** — `implicitRuleAction` on the ruleset controls the default action for unmatched traffic (`accept` or `reject`)

Configure-only operations require zone pairs to be attached separately (or use the `configure` tag which runs both steps). Check mode (`--check`) and diff mode (`--diff`) are supported — the module reads live device state, skips writes in check mode, and sets `changed` from whether an apply would update at least one device. Use `--check --diff` to preview `details.diff_plan` and Ansible `diff`. Ruleset diffs list only changed rules under `rules` (plus `_meta` when ruleset metadata changes); zone pair attach/detach diffs show `ruleset` and `tcpProtection` per pair.

**Match type constraint:** Each rule uses one primary match type — application **or** network/L4, not both. Combining `applicationBuiltin` / `applicationCustom` with `ipProtocol`, `sourceNetwork`, `destinationNetwork`, or ports in the same rule is rejected at validation. You also cannot switch match type on an existing rule; delete it (`state: absent`) and add a new rule with the desired match type.

Use `configs/sample_device_security_policies.yaml`. Top-level key is `SecurityPolicyObject` (list of devices). Each device entry contains `securityRulesets` (list of rulesets) and `zones` (list of zone pairs).

**Prerequisites:** Configure prefix/port lists (`graphiant_prefix_port_list`) and edge services (DPI applications) before rules that reference `applicationCustom`. Integration tests in `tests/test.py` run `test_configure_prefix_and_port_list` and `test_configure_edge_services` before security policy tests.

### Playbook

Tags: `configure` (configure rulesets + attach zone pairs), `deconfigure` (detach zone pairs + delete rulesets), `attach_to_zone_pairs`, `detach_from_zone_pairs`.

```bash
# Configure (dry run, then apply)
ansible-playbook ansible_collections/graphiant/naas/playbooks/security_policies_management.yml --tags configure --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/security_policies_management.yml --tags configure --check --diff
ansible-playbook ansible_collections/graphiant/naas/playbooks/security_policies_management.yml --tags configure

# Deconfigure (dry run, then apply)
ansible-playbook ansible_collections/graphiant/naas/playbooks/security_policies_management.yml --tags deconfigure --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/security_policies_management.yml --tags deconfigure --check --diff
ansible-playbook ansible_collections/graphiant/naas/playbooks/security_policies_management.yml --tags deconfigure

# Attach / detach zone pairs only
ansible-playbook ansible_collections/graphiant/naas/playbooks/security_policies_management.yml --tags attach_to_zone_pairs
ansible-playbook ansible_collections/graphiant/naas/playbooks/security_policies_management.yml --tags detach_from_zone_pairs
```

### Module task

**Configure rulesets** (`configure` tag — runs configure then attach_to_zone_pairs):

```yaml
- name: Configure device-level security policy rulesets
  graphiant.naas.graphiant_security_policy:
    <<: *graphiant_client_params
    operation: configure
    security_policy_config_file: "sample_device_security_policies.yaml"
    detailed_logs: true
    state: present
  register: configure_result
  tags: ['configure']

- name: Display configure result
  ansible.builtin.debug:
    msg: |
      {{ configure_result.msg | trim }}
      configured_devices={{ configure_result.configured_devices | default([]) }}
      skipped_devices={{ configure_result.skipped_devices | default([]) }}
  when: configure_result is defined and configure_result.msg is defined
  tags: ['configure']
```

**Attach rulesets to zone pairs** (run after `configure`, or standalone to update zone assignments):

```yaml
- name: Attach security ruleset to zone pairs
  graphiant.naas.graphiant_security_policy:
    <<: *graphiant_client_params
    operation: attach_to_zone_pairs
    security_policy_config_file: "sample_device_security_policies.yaml"
    detailed_logs: true
  register: attach_result
  tags: ['configure', 'attach_to_zone_pairs']

- name: Display attach-to-zone-pairs result
  ansible.builtin.debug:
    msg: |
      {{ attach_result.msg | trim }}
      configured_devices={{ attach_result.configured_devices | default([]) }}
      skipped_devices={{ attach_result.skipped_devices | default([]) }}
  when: attach_result is defined and attach_result.msg is defined
  tags: ['configure', 'attach_to_zone_pairs']
```

**Detach rulesets from zone pairs** (run before `deconfigure` to clear zone references first):

```yaml
- name: Detach security ruleset from zone pairs
  graphiant.naas.graphiant_security_policy:
    <<: *graphiant_client_params
    operation: detach_from_zone_pairs
    security_policy_config_file: "sample_device_security_policies.yaml"
    detailed_logs: true
  register: detach_result
  tags: ['deconfigure', 'detach_from_zone_pairs']

- name: Display detach-from-zone-pairs result
  ansible.builtin.debug:
    msg: |
      {{ detach_result.msg | trim }}
      configured_devices={{ detach_result.configured_devices | default([]) }}
      skipped_devices={{ detach_result.skipped_devices | default([]) }}
  when: detach_result is defined and detach_result.msg is defined
  tags: ['deconfigure', 'detach_from_zone_pairs']
```

**Deconfigure rulesets** (run after `detach_from_zone_pairs` — removes rulesets listed in the YAML):

```yaml
- name: Deconfigure device-level security policy rulesets
  graphiant.naas.graphiant_security_policy:
    <<: *graphiant_client_params
    operation: deconfigure
    security_policy_config_file: "sample_device_security_policies.yaml"
    detailed_logs: true
    state: absent
  register: deconfigure_result
  tags: ['deconfigure']

- name: Display deconfigure result
  ansible.builtin.debug:
    msg: |
      {{ deconfigure_result.msg | trim }}
      configured_devices={{ deconfigure_result.configured_devices | default([]) }}
      skipped_devices={{ deconfigure_result.skipped_devices | default([]) }}
  when: deconfigure_result is defined and deconfigure_result.msg is defined
  tags: ['deconfigure']
```

**Check and diff mode**

With `--check`, nothing is pushed; the module reads live device state and sets `changed` from whether an apply would update at least one device. Would-be payloads are logged with a `[check_mode]` prefix when `detailed_logs: true`.

With `--diff`, pending changes appear in Ansible `diff` and `details.diff_plan`:

| Branch | Diff shape |
|--------|------------|
| `edge.trafficPolicy.securityRulesets` | Per ruleset: changed rules only under `rules.<seq>`; metadata under `_meta` |
| `edge.trafficPolicy.zones` | Per zone pair (`inside->outside`): `ruleset` and `tcpProtection` before and after |

Example per-rule diff when changing a rule action:

```yaml
- device: edge-1-sdktest
  branch: edge.trafficPolicy.securityRulesets
  before:
    securityRulesets:
      Edge-1-Security-Policy-DIA-LAN-1:
        rules:
          "150":
            seq: 150
            action: reject
  after:
    securityRulesets:
      Edge-1-Security-Policy-DIA-LAN-1:
        rules:
          "150":
            seq: 150
            action: accept
```

### Config YAML (`configs/sample_device_security_policies.yaml`)

```yaml
SecurityPolicyObject:
  - edge-1-sdktest:
      securityRulesets:
        - name: Edge-1-Security-Policy-DIA-LAN-1
          description: Security policy for DIA to LAN-1 traffic
          implicitRuleAction: reject     # accept | reject (default for unmatched traffic)
          rules:
            - seq: 150
              logging: true
              match:
                applicationBuiltin: WhatsApp    # built-in application match
              action: accept                    # accept | reject | inspect | drop
              uplinkPolicerRate: 5000           # kbps; optional meter rates
              uplinkBurstRate: 10000

        - name: Edge-1-Security-Policy-LAN-1-DIA
          description: Security policy for LAN-1 to DIA traffic
          implicitRuleAction: reject
          rules:
            - seq: 150
              logging: true
              match:
                applicationCustom: graphiant_dia_ping   # custom application
              action: reject
            - seq: 160
              logging: true
              match:
                ipProtocol: tcp                          # any | icmp | igmp | tcp | udp | esp | ah
                destinationNetwork: 10.2.1.101/32        # CIDR string
              action: reject
              uplinkPolicerRate: 5000
              uplinkBurstRate: 10000
            - seq: 170
              logging: true
              match:
                applicationBuiltin: Facebook
              action: inspect                            # DPI / threat inspection
              uplinkPolicerRate: 5000
              uplinkBurstRate: 10000
              downlinkPolicerRate: 5000
              downlinkBurstRate: 10000

      zones:
        - fromZone: zone-DIA
          toZone: zone-lan-1
          ruleset: Edge-1-Security-Policy-DIA-LAN-1
          tcpProtection: false          # optional; defaults to false
        - fromZone: zone-lan-1
          toZone: zone-DIA
          ruleset: Edge-1-Security-Policy-LAN-1-DIA
          tcpProtection: false
```

**Per-object deletion** (under `configure`; `state: absent` targets individual objects):

```yaml
# Delete one ruleset by name
- name: My-Ruleset
  state: absent

# Delete one rule by seq
- seq: 500
  state: absent
```

**Rule actions** (per rule; normalized to lowercase on push):

| Value | Description |
|-------|-------------|
| `accept` | Allow matching traffic |
| `reject` | Deny matching traffic |
| `inspect` | Allow and inspect matching traffic (DPI / threat inspection) |
| `drop` | Silently deny matching traffic |

`implicitRuleAction` on the ruleset (catch-all for unmatched traffic) accepts only `accept` or `reject`.

**Match type reference:**

| Key | Description |
|-----|-------------|
| `applicationBuiltin` | Portal built-in application name |
| `applicationCustom` | Custom application name |
| `ipProtocol` | `any`, `icmp`, `igmp`, `tcp`, `udp`, `esp`, `ah` |
| `sourceNetwork` | CIDR string (e.g. `10.0.0.0/8`) |
| `destinationNetwork` | CIDR string |
| `sourcePort` | Port number 1–65535 |
| `destinationPort` | Port number 1–65535 |
| `contentFilter` | `domainCategoryIds` shorthand or full API shape |
| `domainList` | `domainWildcards` shorthand or full API shape |

Use exactly one primary match type per rule: **application** (`applicationBuiltin` / `applicationCustom`) **or** **network/L4** (`ipProtocol`, `sourceNetwork`, `destinationNetwork`, ports). Do not combine both in the same rule. You cannot switch match type on an existing rule — delete it (`state: absent`) and create a new rule with the desired type.

## BGP Configuration

```yaml
# Configure BGP peering
- name: Configure BGP peering
  graphiant.naas.graphiant_bgp:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    bgp_config_file: "sample_bgp_peering.yaml"
    operation: "configure"
    detailed_logs: true
```

Run:
```bash
ansible-playbook playbooks/complete_network_setup.yml
```

## Global Configuration Objects

When both `operation` and `state` are provided, `operation` takes precedence.

### Module: graphiant.naas.graphiant_global_config

#### Configure / deconfigure prefix lists

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag prefix_sets --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag prefix_sets
```

```yaml
- name: Configure global prefix sets
  graphiant.naas.graphiant_global_config:
    <<: *graphiant_client_params
    config_file: "sample_global_prefix_lists.yaml"
    operation: "configure"
    detailed_logs: true
    state: present
  register: prefix_sets_result
  tags: ['global_config', 'prefix_sets']

- name: Display prefix sets result
  ansible.builtin.debug:
    msg: "{{ prefix_sets_result.msg }}"
  tags: ['global_config', 'prefix_sets']
```

Deconfigure:

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag deconfigure_prefix_sets --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag deconfigure_prefix_sets
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag deconfigure_prefix_sets --check
```

```yaml
- name: Deconfigure global prefix sets
  graphiant.naas.graphiant_global_config:
    <<: *graphiant_client_params
    config_file: "sample_global_prefix_lists.yaml"
    operation: "deconfigure"
    detailed_logs: true
    state: present
  register: deconfigure_prefix_sets_result
  tags: ['deconfigure_prefix_sets']

- name: Display deconfigure prefix sets result
  ansible.builtin.debug:
    msg: "{{ deconfigure_prefix_sets_result.msg }}"
  tags: ['deconfigure_prefix_sets']
```

#### Configure BGP filters

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag bgp_filters --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag bgp_filters
```

```yaml
- name: Configure global BGP filters
  graphiant.naas.graphiant_global_config:
    <<: *graphiant_client_params
    config_file: "sample_global_bgp_filters.yaml"
    operation: "configure"
    detailed_logs: true
    state: present
  register: bgp_filters_result
  tags: ['global_config', 'bgp_filters']

- name: Display BGP filters result
  ansible.builtin.debug:
    msg: "{{ bgp_filters_result.msg }}"
  tags: ['global_config', 'bgp_filters']
```

#### Configure / deconfigure Graphiant filters

Graphiant filters use attach points GraphiantIn / GraphiantOut. Use `sample_global_graphiant_filters.yaml` with `graphiant_routing_policies` key.

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag graphiant_filters --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag graphiant_filters
```

```yaml
- name: Configure global Graphiant filters
  graphiant.naas.graphiant_global_config:
    <<: *graphiant_client_params
    config_file: "sample_global_graphiant_filters.yaml"
    operation: "configure_graphiant_filters"
    detailed_logs: true
    state: present
  register: graphiant_filters_result
  tags: ['global_config', 'graphiant_filters']

- name: Display Graphiant filters result
  ansible.builtin.debug:
    msg: "{{ graphiant_filters_result.msg }}"
  tags: ['global_config', 'graphiant_filters']
```

Deconfigure:

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag deconfigure_graphiant_filters --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag deconfigure_graphiant_filters
```

```yaml
- name: Deconfigure global Graphiant filters
  graphiant.naas.graphiant_global_config:
    <<: *graphiant_client_params
    config_file: "sample_global_graphiant_filters.yaml"
    operation: "deconfigure_graphiant_filters"
    detailed_logs: true
    state: absent
  register: deconfigure_graphiant_filters_result
  tags: ['deconfigure_graphiant_filters']

- name: Display deconfigure Graphiant filters result
  ansible.builtin.debug:
    msg: "{{ deconfigure_graphiant_filters_result.msg }}"
  tags: ['deconfigure_graphiant_filters']
```

#### Configure / deconfigure LAN segments

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/lan_segments_management.yml --tag configure --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/lan_segments_management.yml --tag configure
```

```yaml
- name: Configure Global LAN Segments
  graphiant.naas.graphiant_global_config:
    <<: *graphiant_client_params
    config_file: "sample_global_lan_segments.yaml"
    operation: "configure_lan_segments"
    detailed_logs: true
    state: present
  register: configure_result
  tags: ['configure']

- name: Display Configuration Results
  ansible.builtin.debug:
    msg: "{{ configure_result.msg }}"
  when: configure_result is defined and configure_result.msg is defined
  tags: ['configure']
```

Deconfigure:

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/lan_segments_management.yml --tag deconfigure --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/lan_segments_management.yml --tag deconfigure
```

```yaml
- name: Deconfigure Global LAN Segments
  graphiant.naas.graphiant_global_config:
    <<: *graphiant_client_params
    config_file: "sample_global_lan_segments.yaml"
    operation: "deconfigure_lan_segments"
    detailed_logs: true
    state: absent
  register: deconfigure_result
  tags: ['deconfigure']

- name: Display Deconfiguration Results
  ansible.builtin.debug:
    msg: "{{ deconfigure_result.msg }}"
  when: deconfigure_result is defined and deconfigure_result.msg is defined
  tags: ['deconfigure']
```

#### Configure SNMP system objects

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag snmp --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag snmp
```

```yaml
- name: Configure global SNMP system objects
  graphiant.naas.graphiant_global_config:
    <<: *graphiant_client_params
    config_file: "sample_global_snmp_services.yaml"
    operation: "configure"
    detailed_logs: true
    state: present
  register: snmp_result
  tags: ['global_config', 'snmp']

- name: Display SNMP result
  ansible.builtin.debug:
    msg: "{{ snmp_result.msg }}"
  tags: ['global_config', 'snmp']
```

#### Configure syslog servers

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag syslog --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag syslog
```

```yaml
- name: Configure global syslog servers
  graphiant.naas.graphiant_global_config:
    <<: *graphiant_client_params
    config_file: "sample_global_syslog_servers.yaml"
    operation: "configure"
    detailed_logs: true
    state: present
  register: syslog_result
  tags: ['global_config', 'syslog']

- name: Display syslog result
  ansible.builtin.debug:
    msg: "{{ syslog_result.msg }}"
  tags: ['global_config', 'syslog']
```

#### Configure / deconfigure NTP objects

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag ntp --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag ntp
```

```yaml
- name: Configure global NTP objects
  graphiant.naas.graphiant_global_config:
    <<: *graphiant_client_params
    config_file: "sample_global_ntp.yaml"
    operation: "configure_ntps"
    detailed_logs: true
    state: present
  register: ntp_result
  tags: ['global_config', 'ntp']

- name: Display NTP result
  ansible.builtin.debug:
    msg: "{{ ntp_result.msg }}"
  tags: ['global_config', 'ntp']
```

#### Configure IPFIX collectors

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag ipfix --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag ipfix
```

```yaml
- name: Configure global IPFIX collectors
  graphiant.naas.graphiant_global_config:
    <<: *graphiant_client_params
    config_file: "sample_global_ipfix_exporters.yaml"
    operation: "configure"
    detailed_logs: true
    state: present
  register: ipfix_result
  tags: ['global_config', 'ipfix']

- name: Display IPFIX result
  ansible.builtin.debug:
    msg: "{{ ipfix_result.msg }}"
  tags: ['global_config', 'ipfix']
```

#### Configure / deconfigure VPN profiles (3rd party IPsec)

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag vpn_profiles --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag vpn_profiles
```

```yaml
- name: Configure global VPN profiles
  graphiant.naas.graphiant_global_config:
    <<: *graphiant_client_params
    config_file: "sample_global_vpn_profiles.yaml"
    operation: "configure"
    detailed_logs: true
    state: present
  register: vpn_result
  tags: ['global_config', 'vpn_profiles']

- name: Display configure VPN profiles result
  ansible.builtin.debug:
    msg: "{{ vpn_result.msg }}"
  tags: ['global_config', 'vpn_profiles']
```

Deconfigure:

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag deconfigure_vpn_profiles --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag deconfigure_vpn_profiles
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag deconfigure_vpn_profiles --check
```

```yaml
- name: Deconfigure global VPN profiles
  graphiant.naas.graphiant_global_config:
    <<: *graphiant_client_params
    config_file: "sample_global_vpn_profiles.yaml"
    detailed_logs: true
    state: absent
  register: deconfigure_vpn_profiles_result
  tags: ['deconfigure_vpn_profiles']

- name: Display deconfigure VPN profiles result
  ansible.builtin.debug:
    msg: "{{ deconfigure_vpn_profiles_result.msg }}"
  tags: ['deconfigure_vpn_profiles']
```

### Site lists


```bash
# Configure (dry run, then apply)
ansible-playbook ansible_collections/graphiant/naas/playbooks/site_lists_management.yml --tag configure --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/site_lists_management.yml --tag configure
ansible-playbook ansible_collections/graphiant/naas/playbooks/site_lists_management.yml --tag configure --check

# Deconfigure (dry run, then apply)
ansible-playbook ansible_collections/graphiant/naas/playbooks/site_lists_management.yml --tag deconfigure --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/site_lists_management.yml --tag deconfigure
ansible-playbook ansible_collections/graphiant/naas/playbooks/site_lists_management.yml --tag deconfigure --check
```

**Configure site lists** (`playbooks/site_lists_management.yml`):

```yaml
- name: Configure Global Site Lists
  graphiant.naas.graphiant_global_config:
    <<: *graphiant_client_params
    config_file: "sample_global_site_lists.yaml"
    operation: "configure_site_lists"
    detailed_logs: true
    state: present
  register: configure_result
  tags: ['configure']

- name: Display Configuration Results
  ansible.builtin.debug:
    msg: "{{ configure_result.msg }}"
  when: configure_result is defined and configure_result.msg is defined
  tags: ['configure']
```

**Deconfigure site lists**:

```yaml
- name: Deconfigure Global Site Lists
  graphiant.naas.graphiant_global_config:
    <<: *graphiant_client_params
    config_file: "sample_global_site_lists.yaml"
    operation: "deconfigure_site_lists"
    detailed_logs: true
    state: absent
  register: deconfigure_result
  tags: ['deconfigure']

- name: Display Deconfiguration Results
  ansible.builtin.debug:
    msg: "{{ deconfigure_result.msg }}"
  when: deconfigure_result is defined and deconfigure_result.msg is defined
  tags: ['deconfigure']
```

## Site Management

**Module:** `graphiant.naas.graphiant_sites`

Create sites, delete sites, attach or detach global system objects (LAN segments, site lists, etc.) to/from sites. Check mode is supported. Use the site management playbook with the tags below.

### Create sites

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/site_management.yml --tag configure_sites --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/site_management.yml --tag configure_sites
ansible-playbook ansible_collections/graphiant/naas/playbooks/site_management.yml --tag configure_sites --check
```

```yaml
- name: Configure Sites (Create Sites)
  graphiant.naas.graphiant_sites:
    <<: *graphiant_client_params
    site_config_file: "sample_sites.yaml"
    operation: "configure_sites"
    detailed_logs: true
    state: present
  register: configure_sites_result
  tags: ['configure_sites']

- name: Display Configure Sites Result
  ansible.builtin.debug:
    msg: "{{ configure_sites_result.msg }}"
  when: configure_sites_result is defined and configure_sites_result.msg is defined
  tags: ['configure_sites']
```

### Delete sites

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/site_management.yml --tag deconfigure_sites --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/site_management.yml --tag deconfigure_sites
ansible-playbook ansible_collections/graphiant/naas/playbooks/site_management.yml --tag deconfigure_sites --check
```

```yaml
- name: Deconfigure Sites (Delete Sites Only)
  graphiant.naas.graphiant_sites:
    <<: *graphiant_client_params
    site_config_file: "sample_sites.yaml"
    operation: "deconfigure_sites"
    detailed_logs: true
    state: absent
  register: deconfigure_sites_result
  tags: ['deconfigure_sites']

- name: Display Deconfigure Sites Result
  ansible.builtin.debug:
    msg: "{{ deconfigure_sites_result.msg }}"
  when: deconfigure_sites_result is defined and deconfigure_sites_result.msg is defined
  tags: ['deconfigure_sites']
```

### Attach system objects to sites

Prerequisite: global objects (e.g. LAN segments, site lists) are already created.

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/site_management.yml --tag attach_objects --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/site_management.yml --tag attach_objects
```

```yaml
- name: Attach Objects to Sites
  graphiant.naas.graphiant_sites:
    <<: *graphiant_client_params
    site_config_file: "sample_sites.yaml"
    operation: "attach_objects"
    detailed_logs: true
    state: present
  register: attach_result
  tags: ['attach_objects']

- name: Display Attach Result
  ansible.builtin.debug:
    msg: "{{ attach_result.msg }}"
  when: attach_result is defined and attach_result.msg is defined
  tags: ['attach_objects']
```

### Detach system objects from sites

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/site_management.yml --tag detach_objects --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/site_management.yml --tag detach_objects
```

```yaml
- name: Detach Objects from Sites
  graphiant.naas.graphiant_sites:
    <<: *graphiant_client_params
    site_config_file: "sample_sites.yaml"
    operation: "detach_objects"
    detailed_logs: true
    state: present
  register: detach_result
  tags: ['detach_objects']

- name: Display Detach Result
  ansible.builtin.debug:
    msg: "{{ detach_result.msg }}"
  when: detach_result is defined and detach_result.msg is defined
  tags: ['detach_objects']
```

### Create sites and attach objects

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/site_management.yml --tag configure --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/site_management.yml --tag configure
```

```yaml
- name: Configure Sites (Create Sites + Attach Objects)
  graphiant.naas.graphiant_sites:
    <<: *graphiant_client_params
    site_config_file: "sample_sites.yaml"
    operation: "configure"
    detailed_logs: true
    state: present
  register: configure_result
  tags: ['configure']

- name: Display Configure Result
  ansible.builtin.debug:
    msg: "{{ configure_result.msg }}"
  when: configure_result is defined and configure_result.msg is defined
  tags: ['configure']
```

### Detach objects and delete sites

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/site_management.yml --tag deconfigure --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/site_management.yml --tag deconfigure
ansible-playbook ansible_collections/graphiant/naas/playbooks/site_management.yml --tag deconfigure --check
```

```yaml
- name: Deconfigure Sites (Detach Objects + Delete Sites)
  graphiant.naas.graphiant_sites:
    <<: *graphiant_client_params
    site_config_file: "sample_sites.yaml"
    operation: "deconfigure"
    detailed_logs: true
    state: absent
  register: deconfigure_result
  tags: ['deconfigure']

- name: Display Deconfigure Result
  ansible.builtin.debug:
    msg: "{{ deconfigure_result.msg }}"
  when: deconfigure_result is defined and deconfigure_result.msg is defined
  tags: ['deconfigure']
```

## Site-to-Site VPN

### Module: graphiant.naas.graphiant_site_to_site_vpn

Site-to-Site VPN supports static and BGP routing. Preshared keys and BGP MD5 passwords are supplied via Ansible Vault; the vault key must match the VPN `name` in the config. See `configs/vault_secrets.yml.example` and `configs/sample_site_to_site_vpn.yaml`.

#### Vault setup

```bash
cp ansible_collections/graphiant/naas/configs/vault_secrets.yml.example ansible_collections/graphiant/naas/configs/vault_secrets.yml
export ANSIBLE_VAULT_PASSPHRASE="*************"
ansible-vault encrypt ansible_collections/graphiant/naas/configs/vault_secrets.yml --vault-password-file ansible_collections/graphiant/naas/configs/vault-password-file.sh
```

#### Create Site-to-Site VPN

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/site_to_site_vpn.yml --tag create --check --vault-password-file ansible_collections/graphiant/naas/configs/vault-password-file.sh
ansible-playbook ansible_collections/graphiant/naas/playbooks/site_to_site_vpn.yml --tag create --vault-password-file ansible_collections/graphiant/naas/configs/vault-password-file.sh
ansible-playbook ansible_collections/graphiant/naas/playbooks/site_to_site_vpn.yml --tag create --check --vault-password-file ansible_collections/graphiant/naas/configs/vault-password-file.sh
```

The playbook configures VPN profiles, then creates the Site-to-Site VPN (see `site_to_site_vpn.yml`). Use `vault_site_to_site_vpn_keys` and `vault_bgp_md5_passwords` from vars loaded via `include_vars` from the encrypted `vault_secrets.yml`.

#### Delete Site-to-Site VPN

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/site_to_site_vpn.yml --tag delete --check --vault-password-file ansible_collections/graphiant/naas/configs/vault-password-file.sh
ansible-playbook ansible_collections/graphiant/naas/playbooks/site_to_site_vpn.yml --tag delete --vault-password-file ansible_collections/graphiant/naas/configs/vault-password-file.sh
```

```yaml
- name: Delete Site-to-Site VPN
  graphiant.naas.graphiant_site_to_site_vpn:
    <<: *graphiant_client_params
    operation: delete
    site_to_site_vpn_config_file: "sample_site_to_site_vpn.yaml"
    detailed_logs: true
    state: absent
```

## Edge NTP Configuration

NTP configuration is pushed directly to devices using the device config API (similar to static routes).
This is **different from** global NTP objects
managed by `graphiant_global_config` (portal-wide objects under `/v1/global/config`).

See `configs/sample_device_ntp.yaml`.

### Playbook

You can also use the bundled playbook:

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/ntp_management.yml --tags configure --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/ntp_management.yml --tags configure
ansible-playbook ansible_collections/graphiant/naas/playbooks/ntp_management.yml --tags deconfigure --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/ntp_management.yml --tags deconfigure
```

### Configure NTP Module task

```yaml
- name: Configure device-level NTP objects
  graphiant.naas.graphiant_ntp:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    operation: configure
    ntp_config_file: "sample_device_ntp.yaml"
    detailed_logs: true
  register: ntp_configure_result

- name: Display result message (includes detailed logs)
  ansible.builtin.debug:
    msg: "{{ ntp_configure_result.msg }}"
```

### Deconfigure NTP objects

Deconfigure deletes only the objects listed in the YAML (per device) by setting `config: null`.

```yaml
- name: Deconfigure device-level NTP objects
  graphiant.naas.graphiant_ntp:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    operation: deconfigure
    ntp_config_file: "sample_device_ntp.yaml"
    detailed_logs: true
  register: ntp_deconfigure_result

- name: Display result message (includes detailed logs)
  ansible.builtin.debug:
    msg: "{{ ntp_deconfigure_result.msg }}"
```

## Static Routes

Static routes are managed under `edge.segments.<segment>.staticRoutes`.
See `configs/sample_static_route.yaml`.

### Configure static routes

```yaml
- name: Configure static routes
  graphiant.naas.graphiant_static_routes:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    operation: configure
    static_routes_config_file: "sample_static_route.yaml"
    detailed_logs: true
  register: static_routes_configure_result

- name: Display result message (includes detailed logs)
  ansible.builtin.debug:
    msg: "{{ static_routes_configure_result.msg }}"
```

### Deconfigure static routes

Deconfigure deletes only the prefixes listed in the YAML (per segment).

```yaml
- name: Deconfigure static routes
  graphiant.naas.graphiant_static_routes:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    operation: deconfigure
    static_routes_config_file: "sample_static_route.yaml"
    detailed_logs: true
  register: static_routes_deconfigure_result

- name: Display result message (includes detailed logs)
  ansible.builtin.debug:
    msg: "{{ static_routes_deconfigure_result.msg }}"
```

## Data Exchange Workflows

### Step 1: Prerequisites

```bash
# Create LAN segments
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/00_dataex_lan_segments_prerequisites.yml --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/00_dataex_lan_segments_prerequisites.yml

# Configure interfaces
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/00_dataex_lan_interface_prerequisites.yml --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/00_dataex_lan_interface_prerequisites.yml

# Create Prefix Lists
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag prefix_sets --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag prefix_sets

# Create Graphiant filters to be in Data Exchange Services
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag graphiant_filters --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/complete_network_setup.yml --tag graphiant_filters

# Create VPN profiles in the proxy tenant
export GRAPHIANT_USERNAME="proxy-tenant-username"
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/00_dataex_vpn_profile_prerequisites.yml --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/00_dataex_vpn_profile_prerequisites.yml
```

### Step 2: Create Data Exchange Services


```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/01_dataex_create_services.yml --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/01_dataex_create_services.yml
```

To create Data Exchange services

```yaml
- name: Create Data Exchange Services
  graphiant.naas.graphiant_data_exchange:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    operation: create_services
    config_file: "de_workflows_configs/sample_data_exchange_services.yaml"
    # config_file: "de_workflows_configs/sample_data_exchange_services_scale.yaml" # Scale testing
    # config_file: "de_workflows_configs/sample_data_exchange_services_scale2.yaml" # Scale testing2
    detailed_logs: true
  register: create_services_result

- name: Display services creation detailed result
  ansible.builtin.debug:
    msg: "{{ create_services_result.msg }}"
```

To list Data Exchange services

```yaml
- name: Get Data Exchange services summary
  graphiant.naas.graphiant_data_exchange_info:
    <<: *graphiant_client_params
    query: services_summary
    detailed_logs: true
  register: services_summary

- name: Display services summary
  ansible.builtin.debug:
    msg: "{{ services_summary.msg }}"
```

### Step 3: Create Data Exchange Customers

```bash
# Dry-run (validates config)
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/02_dataex_create_customers.yml --check

# Dry-run with diff: shows which customers would be created, and detects adminEmail drift on existing customers
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/02_dataex_create_customers.yml --check --diff

# Apply
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/02_dataex_create_customers.yml

# Custom config file
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/02_dataex_create_customers.yml \
  -e config_file=de_workflows_configs/sample_data_exchange_customers.yaml
```

> **Drift detection**: running with `--check --diff` compares the desired `adminEmail` list against the current portal state for existing customers. If they differ, a diff is shown with a note to use `update_customers` to apply the change.

To create Data Exchange Customers

```yaml
- name: Create Data Exchange customers
  graphiant.naas.graphiant_data_exchange:
    <<: *graphiant_client_params
    operation: create_customers
    config_file: "de_workflows_configs/sample_data_exchange_customers.yaml"
    # config_file: "de_workflows_configs/sample_data_exchange_customers_scale.yaml" # Scale testing
    # config_file: "de_workflows_configs/sample_data_exchange_customers_scale2.yaml" # Scale testing2
    detailed_logs: true
  register: create_customers_result

- name: Display customers creation result
  ansible.builtin.debug:
    msg: "{{ create_customers_result.msg }}"
```

To list Data Exchange Customers

```yaml
- name: Get Data Exchange customers summary
  graphiant.naas.graphiant_data_exchange_info:
    <<: *graphiant_client_params
    query: customers_summary
    detailed_logs: true
  register: customers_summary

- name: Display customers summary
  ansible.builtin.debug:
    msg: "{{ customers_summary.msg }}"
```

### Step 4: Match Services to Customers

```bash
export GRAPHIANT_CONFIGS_PATH=$(pwd)/ansible_collections/graphiant/naas/configs/
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/03_dataex_match_services_to_customers.yml --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/03_dataex_match_services_to_customers.yml

# Custom config file
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/03_dataex_match_services_to_customers.yml \
  -e config_file=de_workflows_configs/sample_data_exchange_matches.yaml
```

> Match responses (including `match_id`) are automatically saved to `de_workflows_configs/output/sample_data_exchange_matches_responses_latest.json`. This file is used in Step 5 when the service is not yet visible via API in the consumer tenant.

```yaml
- name: Match Data Exchange services to customers
  graphiant.naas.graphiant_data_exchange:
    <<: *graphiant_client_params
    operation: match_service_to_customers
    config_file: "de_workflows_configs/sample_data_exchange_matches.yaml"
    # config_file: "de_workflows_configs/sample_data_exchange_matches_scale.yaml" # Scale testing
    # config_file: "de_workflows_configs/sample_data_exchange_matches_scale2.yaml" # Scale testing2
    detailed_logs: true
  register: match_result

- name: Display match result
  ansible.builtin.debug:
    msg: "{{ match_result.msg }}"
```

### Step 5: Accept Invitations (in the proxy/consumer tenant)

`matches_file` is **optional**:
- **Omit it** when the service is already visible in the consumer tenant via API (e.g. after a previous acceptance or if the producer has already shared it). This is the common case for idempotent re-runs.
- **Provide it** when the service is not yet visible via API — typically during a `--check` dry-run before the first acceptance, or in environments where the producer has not yet shared the service. The file is saved by Workflow 3 (Step 4) at `de_workflows_configs/output/<matches>_responses_latest.json`.

```bash
export GRAPHIANT_USERNAME="proxy-tenant-username"

# Dry-run without matches_file (works if service is already visible via API)
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/07_dataex_accept_invitation.yml --check

# Dry-run with matches_file (required when service is not yet visible via API)
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/07_dataex_accept_invitation.yml --check \
  -e matches_file=de_workflows_configs/output/sample_data_exchange_matches_responses_latest.json

# Apply (matches_file optional; omit to use API lookup, or provide explicitly)
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/07_dataex_accept_invitation.yml \
  -e matches_file=de_workflows_configs/output/sample_data_exchange_matches_responses_latest.json

# Custom config file
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/07_dataex_accept_invitation.yml \
  -e config_file=de_workflows_configs/sample_data_exchange_acceptance.yaml \
  -e matches_file=de_workflows_configs/output/sample_data_exchange_matches_responses_latest.json
```

> **Tip**: if the `--check` run fails with "Service not found via API", the error message shows the exact `-e matches_file=...` path to pass. The matches file is saved by Step 4 in the `output/` subdirectory next to your config file.

```yaml
- name: Accept Data Exchange service invitation
  graphiant.naas.graphiant_data_exchange:
    <<: *graphiant_client_params
    operation: accept_invitation
    config_file: "de_workflows_configs/sample_data_exchange_acceptance.yaml"
    # matches_file is optional. When provided, match_id is resolved from the file (with API
    # fallback if the entry is missing). When omitted, match_id is resolved entirely via API
    # (works as long as the service is visible to the consumer tenant).
    # Pass via: -e matches_file=de_workflows_configs/output/sample_data_exchange_matches_responses_latest.json
    matches_file: "{{ matches_file | default(omit) }}"
    # Scale testing
    # config_file: "de_workflows_configs/sample_data_exchange_acceptance_scale.yaml"
    # matches_file: "de_workflows_configs/output/sample_data_exchange_matches_scale_responses_latest.json"
    # Scale testing2
    # config_file: "de_workflows_configs/sample_data_exchange_acceptance_scale2.yaml"
    # matches_file: "de_workflows_configs/output/sample_data_exchange_matches_scale2_responses_latest.json"
    detailed_logs: true
  register: accept_result

- name: Display acceptance result
  ansible.builtin.debug:
    msg: "{{ accept_result.result_msg }}"
```

> **After acceptance**: Graphiant automatically emails the non-Graphiant end customer with a temporary password and a security profile download (their VPN tunnel credentials). No further action is needed from the proxy tenant.

#### Config file: Site-to-Site VPN with `ipsecGatewayPeers`

Use `ipsecGatewayPeers` for all new configs (requires `graphiant_sdk >= 26.6.0`); the legacy `ipsecGatewayDetails` key is still accepted for single-peer backward compatibility.

Each `remotePeers` entry is one customer VPN device. Graphiant provisions one IPSec interface per peer on **every** gateway device at the site (`tunnel1` → gw-device-1, `tunnel2` → gw-device-2). Interface naming: `{ipsecGatewayPeers.name}-{peer.name}`. Leave `insideIpv4Cidr`, `psk`, and `localIkePeerIdentity` as `null` — the playbook auto-fills them from the portal APIs.

```yaml
siteToSiteVpn:
  ipsecGatewayPeers:
    name: "s2s-FinanceInc"      # prefix for interface names: s2s-FinanceInc-peer-1, ...
    routing:
      bgp:                       # shared across all peers
        peerAsn: 65501
        # ... see sample_data_exchange_acceptance.yaml for full BGP config
    remotePeers:
      - name: "peer-1"
        destinationAddress: "0.0.0.0"   # customer WAN IP; 0.0.0.0 = wildcard
        mtu: 1400
        tcpMss: 1360
        remoteIkePeerIdentity: "0.0.0.0"
        ikeInitiator: false
        tunnel1: { insideIpv4Cidr: null, insideIpv6Cidr: null, psk: null, localIkePeerIdentity: null }
        tunnel2: { insideIpv4Cidr: null, insideIpv6Cidr: null, psk: null, localIkePeerIdentity: null }
        vpnProfile: "vpnprofile-global-test"
      - name: "peer-2"           # add peer-3, peer-4, ... as needed
        # ... same structure as peer-1
  region: "us-central-1 (Chicago)"
  emails: ["finance@financeinc.com"]
```

> **HTTP 500 "must include IPSec gateway details"** — two causes: (1) **Old SDK** (`<= 26.5.0`): `ipsecGatewayPeers` is silently dropped by `.to_dict()` — upgrade to `graphiant_sdk >= 26.6.0` and check the `SDK-serialized payload` log to confirm. (2) **Config missing both keys**: add `ipsecGatewayPeers` or `ipsecGatewayDetails` under `siteToSiteVpn`.

### Cleanup - Delete Data Exchange Customers

```bash
# Dry-run (validates config)
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/04_dataex_delete_customers.yml --check

# Apply
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/04_dataex_delete_customers.yml

# Custom config file
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/04_dataex_delete_customers.yml \
  -e config_file=de_workflows_configs/sample_data_exchange_customers.yaml
```

```yaml
- name: Delete Data Exchange customers
  graphiant.naas.graphiant_data_exchange:
    <<: *graphiant_client_params
    operation: delete_customers
    config_file: "{{ config_file | default('de_workflows_configs/sample_data_exchange_customers.yaml') }}"
    detailed_logs: true
  register: delete_customers_result

- name: Display delete customers result
  ansible.builtin.debug:
    msg: "{{ delete_customers_result.msg }}"
```

### Cleanup - Delete Data Exchange Services

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/05_dataex_delete_services.yml --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/05_dataex_delete_services.yml
```

```yaml
- name: Delete Data Exchange services
  graphiant.naas.graphiant_data_exchange:
    <<: *graphiant_client_params
    operation: delete_services
    config_file: "de_workflows_configs/sample_data_exchange_services.yaml"
    # config_file: "de_workflows_configs/sample_data_exchange_services_scale.yaml" # Scale testing
    # config_file: "de_workflows_configs/sample_data_exchange_services_scale2.yaml" # Scale testing2
    detailed_logs: true
  register: delete_services_result

- name: Display delete services result
  ansible.builtin.debug:
    msg: "{{ delete_services_result.msg }}"
```

## Complete Network Setup

The `complete_network_setup.yml` playbook demonstrates a full configuration workflow:

```bash
ansible-playbook playbooks/complete_network_setup.yml
```

This playbook:
1. Configures global prefix sets
2. Configures BGP filters
3. Sets up BGP peering
4. Configures interfaces and circuits
5. Attaches objects to sites

## Using YAML Anchors

See `playbooks/credential_examples.yml` for credential management patterns:

```yaml
vars:
  graphiant_client_params: &graphiant_client_params
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

tasks:
  - name: Task 1
    graphiant.naas.graphiant_interfaces:
      <<: *graphiant_client_params
      interface_config_file: "config.yaml"
      operation: "configure_lan_interfaces"
      detailed_logs: true

  - name: Task 2
    graphiant.naas.graphiant_bgp:
      <<: *graphiant_client_params
      bgp_config_file: "bgp.yaml"
      operation: "configure"
      detailed_logs: true
```

## Configuration File Examples

Sample configuration files are in the `configs/` directory:

| File | Description |
|------|-------------|
| `sample_device_system.yaml` | Device system configuration (hostname, region and site name) |
| `sample_interface_config.yaml` | Interface configurations |
| `sample_circuit_config.yaml` | Circuit configurations |
| `sample_bgp_peering.yaml` | BGP peering settings |
| `sample_global_prefix_lists.yaml` | Prefix set definitions |
| `sample_global_bgp_filters.yaml` | BGP filter definitions |
| `sample_global_graphiant_filters.yaml` | Graphiant filter definitions (GraphiantIn / GraphiantOut) |
| `sample_global_lan_segments.yaml` | LAN segment definitions |
| `sample_global_ntp.yaml` | NTP object definitions |
| `sample_global_vpn_profiles.yaml` | VPN profile definitions |
| `sample_sites.yaml` | Site definitions |
| `sample_site_attachments.yaml` | Site attachment configurations |
| `sample_device_ntp.yaml` | Device NTP configuration  |
| `sample_static_route.yaml` | Static routes under edge segments |
| `sample_macsec.yaml` | Interface MACsec (802.1AE) on ethernet or LAG main interfaces |
| `sample_edge_services.yaml` | Edge services (DHCP, DNS, LLDP, LWS password) |
| `sample_prefix_and_port_list.yaml` | Device-level prefix lists (`networkLists`) and port lists (`portLists`) under `edge.trafficPolicy` |
| `sample_device_traffic_policies.yaml` | Device-level traffic policy rulesets and LAN segment attachments |
| `sample_device_security_policies.yaml` | Device-level security policy rulesets and zone pair attachments |

Data Exchange configs are in `configs/de_workflows_configs/`.

## Python Library Examples

For Python library usage, see `tests/test.py` which demonstrates:
- GraphiantConfig initialization
- Interface management
- BGP configuration
- Global object management
- Site operations
- Device system settings
- Edge services and MACsec configuration
- Data Exchange workflows

```python
from libs.graphiant_config import GraphiantConfig

config = GraphiantConfig(
    base_url="https://api.graphiant.com",
    username="user",
    password="pass"
)

# Configure interfaces
config.interfaces.configure_lan_interfaces("interface_config.yaml")

# Configure BGP
config.bgp.configure("bgp_config.yaml")

# Configure global objects
config.global_config.configure("global_prefix_lists.yaml")
```

## Troubleshooting

Enable detailed logging:

```yaml
- name: Debug task
  graphiant.naas.graphiant_interfaces:
    <<: *graphiant_client_params
    interface_config_file: "config.yaml"
    operation: "configure_lan_interfaces"
    detailed_logs: true
```

Use debug callback for clean output:

```bash
export ANSIBLE_STDOUT_CALLBACK=debug
ansible-playbook playbook.yml -vvv
```

