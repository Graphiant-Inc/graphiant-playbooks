# Example Playbooks

This guide provides detailed examples for using the Graphiant Playbooks collection.

For module reference, see the [Modules documentation](https://github.com/Graphiant-Inc/graphiant-playbooks/tree/main/ansible_collections/graphiant/naas#modules).

## Quick Start

Set up environment variables before running playbooks:

```bash
export GRAPHIANT_HOST="https://api.graphiant.com"
export GRAPHIANT_USERNAME="your_username"
export GRAPHIANT_PASSWORD="your_password"

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

## Interface Management

### Configure LAN Interfaces

```yaml
# playbooks/interface_management.yml
- name: Configure LAN interfaces
  graphiant.naas.graphiant_interfaces:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    interface_config_file: "sample_interface_config.yaml"
    operation: "configure_lan_interfaces"
    detailed_logs: true
```

Run:
```bash
ansible-playbook playbooks/interface_management.yml
```

### Configure WAN Circuits

```yaml
- name: Configure WAN circuits and interfaces
  graphiant.naas.graphiant_interfaces:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    interface_config_file: "sample_interface_config.yaml"
    circuit_config_file: "sample_circuit_config.yaml"
    operation: "configure_wan_circuits_interfaces"
    detailed_logs: true
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

### LAN Segments

```yaml
# playbooks/lan_segments_management.yml
- name: Configure LAN segments
  graphiant.naas.graphiant_global_config:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    config_file: "sample_global_lan_segments.yaml"
    operation: "configure_lan_segments"
    detailed_logs: true
```

### Site Lists

```yaml
# playbooks/site_lists_management.yml
- name: Configure site lists
  graphiant.naas.graphiant_global_config:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    config_file: "sample_global_site_lists.yaml"
    operation: "configure_site_lists"
    detailed_logs: true
```

## Site Management

```yaml
# playbooks/site_management.yml
- name: Configure sites and attachments
  graphiant.naas.graphiant_sites:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    site_config_file: "sample_sites.yaml"
    operation: "configure"
    detailed_logs: true
```

## Site-to-Site VPN

Site-to-Site VPN supports static and BGP routing. Preshared keys and BGP MD5 passwords are supplied via Ansible Vault when using the playbook; the vault key must match the VPN `name` in the config. See `configs/vault_secrets.yml.example` and `configs/sample_site_to_site_vpn.yaml`.

### Create Site-to-Site VPN

```yaml
# playbooks/site_to_site_vpn.yml (create)
- name: Create Site-to-Site VPN
  graphiant.naas.graphiant_site_to_site_vpn:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    operation: create
    site_to_site_vpn_config_file: "sample_site_to_site_vpn.yaml"
    detailed_logs: true
```

Run with vault (required for create):
```bash
ansible-playbook playbooks/site_to_site_vpn.yml --tags create --ask-vault-pass
# or: --vault-password-file ~/.vault_pass
```

### Delete Site-to-Site VPN

```yaml
- name: Delete Site-to-Site VPN
  graphiant.naas.graphiant_site_to_site_vpn:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    operation: delete
    site_to_site_vpn_config_file: "sample_site_to_site_vpn.yaml"
```

## Data Exchange Workflows

The Data Exchange module supports multi-step workflows. Run playbooks in order:

### Step 1: Prerequisites

```bash
# Set up LAN interfaces
ansible-playbook playbooks/de_workflows/00_dataex_lan_interface_prerequisites.yml

# Set up LAN segments
ansible-playbook playbooks/de_workflows/00_dataex_lan_segments_prerequisites.yml

# Set up VPN profiles
ansible-playbook playbooks/de_workflows/00_dataex_vpn_profile_prerequisites.yml
```

### Step 2: Create Services

```yaml
# playbooks/de_workflows/01_dataex_create_services.yml
- name: Create Data Exchange services
  graphiant.naas.graphiant_data_exchange:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    operation: "create_services"
    config_file: "de_workflows_configs/sample_data_exchange_services.yaml"
    detailed_logs: true
```

### Step 3: Create Customers

```yaml
# playbooks/de_workflows/02_dataex_create_customers.yml
- name: Create Data Exchange customers
  graphiant.naas.graphiant_data_exchange:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    operation: "create_customers"
    config_file: "de_workflows_configs/sample_data_exchange_customers.yaml"
    detailed_logs: true
```

### Step 4: Match Services to Customers

```yaml
# playbooks/de_workflows/03_dataex_match_services_to_customers.yml
- name: Match services to customers
  graphiant.naas.graphiant_data_exchange:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    operation: "match_service_to_customers"
    config_file: "de_workflows_configs/sample_data_exchange_matches.yaml"
    detailed_logs: true
```

### Step 5: Accept Invitations

```yaml
# playbooks/de_workflows/07_dataex_accept_invitation.yml
- name: Accept service invitation
  graphiant.naas.graphiant_data_exchange:
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"
    operation: "accept_invitation"
    config_file: "de_workflows_configs/sample_data_exchange_acceptance.yaml"
    matches_file: "de_workflows_configs/output/sample_data_exchange_matches_responses_latest.json"
    detailed_logs: true
```

### Cleanup

```bash
# Delete customers first
ansible-playbook playbooks/de_workflows/04_dataex_delete_customers.yml

# Then delete services
ansible-playbook playbooks/de_workflows/05_dataex_delete_services.yml
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
| `sample_interface_config.yaml` | Interface configurations |
| `sample_circuit_config.yaml` | Circuit configurations |
| `sample_bgp_peering.yaml` | BGP peering settings |
| `sample_global_prefix_lists.yaml` | Prefix set definitions |
| `sample_global_bgp_filters.yaml` | BGP filter definitions |
| `sample_global_lan_segments.yaml` | LAN segment definitions |
| `sample_global_vpn_profiles.yaml` | VPN profile definitions |
| `sample_sites.yaml` | Site definitions |
| `sample_site_attachments.yaml` | Site attachment configurations |

Data Exchange configs are in `configs/de_workflows_configs/`.

## Python Library Examples

For Python library usage, see `tests/test.py` which demonstrates:
- GraphiantConfig initialization
- Interface management
- BGP configuration
- Global object management
- Site operations
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

