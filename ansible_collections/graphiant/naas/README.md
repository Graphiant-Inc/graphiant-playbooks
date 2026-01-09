# Graphiant NaaS Ansible Collection

[![License: GPL v3+](https://img.shields.io/badge/License-GPLv3+-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/)
[![Ansible](https://img.shields.io/badge/ansible--core-2.17+-green.svg)](https://docs.ansible.com/)

The Ansible Graphiant NaaS collection includes modules for automating the management of Graphiant NaaS (Network as a Service) infrastructure.

## Description

This collection provides Ansible modules to automate:
- Interface and circuit configuration
- BGP peering management
- Global configuration objects (prefix sets, BGP filters, VPN profiles, LAN segments)
- Site management and object attachments
- Data Exchange workflows
- Raw device configuration deployment (Edge, Gateway, and Core devices)

### Key Features

- **Idempotent Operations**: All modules correctly report `changed: false` when no modifications occur
- **Structured Results**: Manager methods return detailed results with `changed`, `created`, `skipped`, and `deleted` fields
- **Graceful Error Handling**: Handles "object not found" errors gracefully in deconfigure operations
- **Jinja2 Template Support**: Configuration files support Jinja2 templating for dynamic generation
- **Comprehensive Logging**: Optional detailed logging for debugging and troubleshooting

## Ansible Version Compatibility

This collection requires **ansible-core >= 2.17.0**.

## Python Requirements

- Python >= 3.7 (compatible with ansible-core 2.17, 2.18, 2.19, and 2.20)
- Graphiant SDK >= 25.12.1

> **Note:** All dependency versions are managed centrally in `_version.py`. See [Version Management Guide](docs/guides/VERSION_MANAGEMENT.md) for details.

## Included Content

### [Modules](https://github.com/Graphiant-Inc/graphiant-playbooks/tree/main/ansible_collections/graphiant/naas#modules)

| Name | Description |
|------|-------------|
| `graphiant_interfaces` | Manage interfaces and circuits (LAN/WAN) |
| `graphiant_bgp` | Manage BGP peering and routing policies |
| `graphiant_global_config` | Manage global configuration objects |
| `graphiant_sites` | Manage sites and site attachments |
| `graphiant_data_exchange` | Manage Data Exchange workflows |
| `graphiant_device_config` | Push raw device configurations to Edge, Gateway, and Core devices |

## Installation

### From Source

```bash
git clone https://github.com/Graphiant-Inc/graphiant-playbooks.git
cd graphiant-playbooks

# Create virtual environment or activate an existing virtual environment
python3.7 -m venv venv
source venv/bin/activate

# Install collection dependencies
pip install -r ansible_collections/graphiant/naas/requirements-ee.txt

# Install collection from source
ansible-galaxy collection install ansible_collections/graphiant/naas/ --force
```

### From Ansible Galaxy

```bash
# Install collection dependencies in a virtual environment
pip install -r ansible_collections/graphiant/naas/requirements-ee.txt

# Install collection from Ansible Galaxy
ansible-galaxy collection install graphiant.naas
```

### Verify Installation

```bash
ansible-galaxy collection list graphiant.naas
```

### Test Installation (E2E Integration Test)

Test the installed collection by running the `hello_test.yml` playbook. This test is also run automatically in CI/CD as the E2E integration test when GRAPHIANT credentials are configured:

```bash
# Set environment variables
export GRAPHIANT_HOST="https://api.graphiant.com"
export GRAPHIANT_USERNAME="your_username"
export GRAPHIANT_PASSWORD="your_password"

# Optional: Enable pretty output for detailed_logs
export ANSIBLE_STDOUT_CALLBACK=debug

# Run test playbook
ansible-playbook ~/.ansible/collections/ansible_collections/graphiant/naas/playbooks/hello_test.yml
```

The `hello_test.yml` playbook:
- Tests module loading with check_mode (no API calls)
- Tests actual API connectivity and configuration
- Shows detailed logs when `detailed_logs: true`
- Warns if `ANSIBLE_STDOUT_CALLBACK` is not set to `debug`

### Validation and Linting

**Validate collection structure:**
```bash
# From repository root
python scripts/validate_collection.py

# Or from collection directory
python ../../scripts/validate_collection.py
```

**Build collection (for distribution):**
```bash
# Using ansible-galaxy
ansible-galaxy collection build ansible_collections/graphiant/naas/

# Or using build script (from repository root)
python scripts/build_collection.py
```
<｜tool▁calls▁begin｜><｜tool▁call▁begin｜>
read_file

**Linting tools (run locally):**
```bash
# Python linting with flake8 (local development only, not in CI)
flake8 ansible_collections/graphiant/naas/plugins/module_utils

# Python linting with pylint (errors only, local development only, not in CI)
export PYTHONPATH=$PYTHONPATH:$(pwd)/ansible_collections/graphiant/naas/plugins/module_utils/libs
pylint --errors-only ansible_collections/graphiant/naas/plugins/module_utils

# Ansible playbook linting (runs in CI, requires collection to be installed first)
ansible-galaxy collection install ansible_collections/graphiant/naas/ --force
ansible-lint --config-file ~/.ansible/collections/ansible_collections/graphiant/naas/.ansible-lint ~/.ansible/collections/ansible_collections/graphiant/naas/playbooks/

# YAML/Jinja template linting (runs in CI)
djlint ansible_collections/graphiant/naas/configs -e yaml
djlint ansible_collections/graphiant/naas/templates -e yaml
```

**Antsibull documentation validation (runs in CI):**
```bash
# Install antsibull-docs
pip install antsibull-docs

# Validate module documentation
antsibull-docs lint-collection-docs ansible_collections/graphiant/naas/
```

**Note:** CI/CD pipelines run `ansible-lint`, `djlint`, and `antsibull-docs` linting. `flake8` and `pylint` are available for local development but are not part of the CI pipeline. See `.github/workflows/README.md` for CI/CD configuration.

## Using This Collection

### Example Playbook

```yaml
---
- name: Configure Graphiant network
  hosts: localhost
  gather_facts: false
  vars:
    graphiant_client_params: &graphiant_client_params
      host: "{{ graphiant_host }}"
      username: "{{ graphiant_username }}"
      password: "{{ graphiant_password }}"

  tasks:
    - name: Configure LAN interfaces
      graphiant.naas.graphiant_interfaces:
        <<: *graphiant_client_params
        interface_config_file: "interface_config.yaml"
        operation: "configure_lan_interfaces"

    - name: Configure BGP peering
      graphiant.naas.graphiant_bgp:
        <<: *graphiant_client_params
        bgp_config_file: "bgp_config.yaml"
        operation: "configure"

    - name: Configure global prefix sets
      graphiant.naas.graphiant_global_config:
        <<: *graphiant_client_params
        config_file: "global_prefix_lists.yaml"
        operation: "configure"

    - name: Push raw device configuration
      graphiant.naas.graphiant_device_config:
        <<: *graphiant_client_params
        config_file: "sample_device_config_payload.yaml"
        operation: "configure"
```

### Example Playbooks

The collection includes ready-to-use example playbooks in the `playbooks/` directory:

| Playbook | Description |
|----------|-------------|
| `hello_test.yml` | E2E integration test playbook (used in CI/CD) |
| `complete_network_setup.yml` | Full network configuration workflow |
| `interface_management.yml` | Interface and circuit operations |
| `circuit_management.yml` | Circuit-specific operations |
| `lan_segments_management.yml` | LAN segment configuration |
| `site_management.yml` | Site creation and management |
| `site_lists_management.yml` | Site list operations |
| `credential_examples.yml` | Credential management examples |
| `device_config_management.yml` | Push raw device configurations (Edge/Gateway/Core) |
| `test_collection.yml` | Collection validation and testing |

#### Data Exchange Workflows

The `playbooks/de_workflows/` directory contains playbooks for Data Exchange operations:

| Playbook | Description |
|----------|-------------|
| `00_dataex_*_prerequisites.yml` | Prerequisites setup (LAN interfaces, segments, VPN profiles) |
| `01_dataex_create_services.yml` | Create Data Exchange services |
| `02_dataex_create_customers.yml` | Create Data Exchange customers |
| `03_dataex_match_services_to_customers.yml` | Match services to customers |
| `04_dataex_delete_customers.yml` | Delete customers |
| `05_dataex_delete_services.yml` | Delete services |
| `06_dataex_accept_invitation_dry_run.yml` | Test invitation acceptance |
| `07_dataex_accept_invitation.yml` | Accept service invitations |

See [Examples Guide](docs/guides/EXAMPLES.md) for detailed usage examples.

### Module Documentation

View module documentation with `ansible-doc`:

```bash
ansible-doc graphiant.naas.graphiant_interfaces
ansible-doc graphiant.naas.graphiant_bgp
ansible-doc graphiant.naas.graphiant_global_config
ansible-doc graphiant.naas.graphiant_sites
ansible-doc graphiant.naas.graphiant_data_exchange
ansible-doc graphiant.naas.graphiant_device_config
```

## Documentation

### Quick Links

- **[Examples Guide](docs/guides/EXAMPLES.md)** - Detailed usage examples and playbook samples
- **[Credential Management Guide](docs/guides/CREDENTIAL_MANAGEMENT_GUIDE.md)** - Best practices for managing credentials securely
- **[Version Management Guide](docs/guides/VERSION_MANAGEMENT.md)** - Version management system and quick reference
- **[Release Process](docs/guides/RELEASE.md)** - Complete release process documentation
- **[Documentation Index](docs/README.md)** - Full documentation structure

### Additional Documentation

- **Module Documentation**: Use `ansible-doc` to view embedded module documentation (see above)
- **Docusite Setup**: See [docs/DOCSITE_SETUP.md](docs/DOCSITE_SETUP.md) for building HTML documentation
- **Changelog**: See [CHANGELOG.md](CHANGELOG.md) for version history and release notes

### Credential Management

**Recommended: Use YAML anchors** to avoid repetition:

```yaml
vars:
  graphiant_client_params: &graphiant_client_params
    host: "{{ graphiant_host }}"
    username: "{{ graphiant_username }}"
    password: "{{ graphiant_password }}"

tasks:
  - name: Configure interfaces
    graphiant.naas.graphiant_interfaces:
      <<: *graphiant_client_params
      interface_config_file: "config.yaml"
      operation: "configure_lan_interfaces"
```

**Other options:**
- Environment variables (`GRAPHIANT_HOST`, `GRAPHIANT_USERNAME`, `GRAPHIANT_PASSWORD`)
- Ansible Vault for encrypted credentials
- Variable files with `vars_files`

See [Credential Management Guide](docs/guides/CREDENTIAL_MANAGEMENT_GUIDE.md) for detailed examples.

### State Parameter

All modules support `state` parameter:
- `present`: Configure/create resources (maps to `configure` operation)
- `absent`: Deconfigure/remove resources (maps to `deconfigure` operation)
- When both `operation` and `state` are provided, `operation` takes precedence

### Idempotency

All modules are idempotent and correctly report `changed: false` when no modifications occur:
- Modules track whether actual changes were made to the system
- `changed: false` is reported when configurations already match the desired state
- Manager methods return structured results with `changed`, `created`, `skipped`, and `deleted` fields
- Graceful error handling for "object not found" errors in deconfigure operations

**Note:** PUT/PATCH operations (`configure_interfaces`, `configure_bgp`, etc.) always report `changed: true` as state comparison is not currently implemented for these operations.

### Detailed Logging

All modules support `detailed_logs` parameter:
- `true`: Show detailed library logs in task output
- `false`: Show only basic success/error messages (default)

```yaml
- name: Configure with detailed logs
  graphiant.naas.graphiant_interfaces:
    <<: *graphiant_client_params
    interface_config_file: "config.yaml"
    operation: "configure_lan_interfaces"
    detailed_logs: true
```

For readable output (removes `\n` characters), set:
```bash
export ANSIBLE_STDOUT_CALLBACK=debug
```

### Python Library Usage

The collection can also be used as a Python library:

```bash
# Set PYTHONPATH
export PYTHONPATH=/path/to/collection_root/ansible_collections/graphiant/naas/plugins/module_utils:$PYTHONPATH
```

```python
from libs.graphiant_config import GraphiantConfig

config = GraphiantConfig(
    base_url="https://api.graphiant.com",
    username="user",
    password="pass"
)
config.interfaces.configure_lan_interfaces("interface_config.yaml")
```

See `tests/test.py` for comprehensive Python library usage examples.

### Running Tests

The test suite (`tests/test.py`) requires environment variables for Graphiant credentials:

```bash
# Set required environment variables
export GRAPHIANT_HOST="https://api.graphiant.com"
export GRAPHIANT_USERNAME="your_username"
export GRAPHIANT_PASSWORD="your_password"

# Run tests
cd ansible_collections/graphiant/naas
python -m unittest tests.test
```

**Note:** The `test.ini` configuration file has been removed. All tests now use environment variables for credential management, which is more secure and aligns with CI/CD best practices.

## Configuration Files

Configuration files use YAML format with optional Jinja2 templating. Sample files are in the `configs/` directory:

- `sample_interface_config.yaml` - Interface configurations
- `sample_bgp_peering.yaml` - BGP peering configurations
- `sample_global_*.yaml` - Global configuration objects
- `sample_device_config_payload.yaml` - Raw device configuration payloads (Edge/Gateway Device types)
- `sample_device_config_core_device_payload.yaml` - Raw device configuration payloads (Core Device type)
- `sample_device_config_with_template.yaml` - Device config with user-defined template (`device_config_template.yaml`)

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
- `sample_sites.yaml` - Site configurations

Data Exchange configurations are in `configs/de_workflows_configs/`.

## Contributing

We welcome contributions! See [CONTRIBUTING.md](../../CONTRIBUTING.md) for:
- Development setup
- Code standards
- Testing requirements
- Pull request process

## Release Notes

See [CHANGELOG.md](CHANGELOG.md) for version history and release notes.

## Version Management

Version information is centralized in `_version.py`. To bump versions or update dependencies, see [Version Management Guide](docs/guides/VERSION_MANAGEMENT.md) and [Release Process](docs/guides/RELEASE.md) for detailed instructions.

Quick version bump:
```bash
# From repository root
# Patch release (bug fixes)
python scripts/bump_version.py patch

# Minor release (new features)
python scripts/bump_version.py minor

# Major release (breaking changes)
python scripts/bump_version.py major

# Set specific version
python scripts/bump_version.py 25.12.3
```

After bumping version, remember to:
1. Update CHANGELOG.md with actual changes
2. Install dependencies: `pip install -r requirements-ee.txt`
3. Review and commit changes

## Support

- **Documentation**: [docs.graphiant.com](https://docs.graphiant.com/)
- **Issues**: [GitHub Issues](https://github.com/Graphiant-Inc/graphiant-playbooks/issues)
- **Email**: [support@graphiant.com](mailto:support@graphiant.com)

## License

GNU General Public License v3.0 or later (GPLv3+) - see [LICENSE](LICENSE) for details.
