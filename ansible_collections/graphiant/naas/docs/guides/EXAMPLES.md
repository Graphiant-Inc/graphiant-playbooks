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

`graphiant_device_system` only supports `present` (configure); `absent` is not valid.

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

Check `logs/log_<date>.log` for the actual path used during execution.


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
ansible-playbook ansible_collections/graphiant/naas/playbooks/circuit_management.yml --tag static_routes
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
  no_log: true

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
  no_log: true

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
  no_log: true

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
  no_log: true

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
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/02_dataex_create_customers.yml --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/02_dataex_create_customers.yml
```

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
```


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

### Step 5: Accept Invitations (in the proxy tenant)

```bash
export GRAPHIANT_USERNAME="proxy-tenant-username"
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/07_dataex_accept_invitation.yml --check
```

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/07_dataex_accept_invitation.yml
```


```yaml
- name: Accept Data Exchange service invitation
  graphiant.naas.graphiant_data_exchange:
    <<: *graphiant_client_params
    operation: accept_invitation
    config_file: "de_workflows_configs/sample_data_exchange_acceptance.yaml"
    # matches_file is optional - if provided, uses service_id to lookup match_id via API if missing
    # If not provided, attempts API lookup (works if service is visible to consumer tenant)
    matches_file: "de_workflows_configs/output/sample_data_exchange_matches_responses_latest.json"
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

### Cleanup - Delete Data Exchange Customers

```bash
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/04_dataex_delete_customers.yml --check
ansible-playbook ansible_collections/graphiant/naas/playbooks/de_workflows/04_dataex_delete_customers.yml
```

```yaml
- name: Delete Data Exchange customers
  graphiant.naas.graphiant_data_exchange:
    <<: *graphiant_client_params
    operation: delete_customers
    config_file: "de_workflows_configs/sample_data_exchange_customers.yaml"
    # config_file: "de_workflows_configs/sample_data_exchange_customers_scale.yaml" # Scale testing
    # config_file: "de_workflows_configs/sample_data_exchange_customers_scale2.yaml" # Scale testing2
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

Data Exchange configs are in `configs/de_workflows_configs/`.

## Python Library Examples

For Python library usage, see `tests/test.py` which demonstrates:
- GraphiantConfig initialization
- Interface management
- BGP configuration
- Global object management
- Site operations
- Device system settings
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

