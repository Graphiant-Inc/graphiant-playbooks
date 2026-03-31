# Graphiant Playbooks

[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![Ansible](https://img.shields.io/badge/ansible--core-2.17+-green.svg)](https://docs.ansible.com/)
[![Terraform](https://img.shields.io/badge/terraform-1.14+-red.svg)](https://developer.hashicorp.com/terraform/install)
[![License: GPL v3+](https://img.shields.io/badge/License-GPLv3+-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Documentation](https://img.shields.io/badge/docs-latest-brightgreen.svg)](https://docs.graphiant.com/docs/graphiant-playbooks)

Automated network infrastructure management for [Graphiant Network-as-a-Service (NaaS)](https://www.graphiant.com) offerings.

Refer [Graphiant Docs](https://docs.graphiant.com) to get started with [Graphiant Network-as-a-Service (NaaS)](https://www.graphiant.com) offerings.

## Graphiant portal authentication

Automation in this repository talks to the Graphiant API using a **portal access token** or **username/password**. The recommended local setup matches [Test Infrastructure](https://gitlab.com/graphiant/oss/test-infrastructure/-/blob/main/README.md) **Quick Start → Set Graphiant Environment Variables**: use the **graphiant** CLI to obtain a token, or export tester credentials.

### Option 1: Graphiant CLI (`graphiant login`)

```bash
# Fetch a Graphiant portal API access token using the graphiant CLI
graphiant login --portal-url https://portal.test.graphiant.io
source ~/.graphiant/env.sh

# Optional: reload shell configuration so the token is available in new terminals
source ~/.zshrc

# Verify the environment variable
env | grep GRAPHIANT_ACCESS_TOKEN
```

The Ansible collection accepts `access_token` on modules and honors **`GRAPHIANT_ACCESS_TOKEN`** when set (bearer auth is used before username/password when the token is valid). See [Credential Management Guide](ansible_collections/graphiant/naas/docs/guides/CREDENTIAL_MANAGEMENT_GUIDE.md).

### Option 2: Portal username and password

```bash
# Add to your shell profile (~/.zshrc, ~/.bashrc, etc.) or export for the session
export TESTER_USER_EMAIL='your-email@graphiant.com'
export TESTER_USER_PASSWORD='your-password'

# Verify
env | grep TESTER
```

Pass `username` / `password` (or your vault equivalents) into playbooks and roles as required by each module.

## 📚 Documentation

- **Official Documentation**: [Graphiant Playbooks Guide](https://docs.graphiant.com/docs/graphiant-playbooks) <-> [Graphiant Automation Docs](https://docs.graphiant.com/docs/automation)
- **Ansible Collection**: [Ansible Galaxy Collection - graphiant.naas](https://galaxy.ansible.com/ui/repo/published/graphiant/naas)
- **Changelog**: [changelogs/changelog.yaml](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/changelogs/changelog.yaml) - Version history and release notes
- **Security Policy**: [SECURITY.md](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/SECURITY.md) - Security best practices and vulnerability reporting

## Components

| Component | Description | Documentation |
|-----------|-------------|---------------|
| **Ansible Collection** | Ansible modules for Graphiant NaaS automation (v26.3.0) | [📖 Documentation](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/README.md) |
| **Terraform Modules** | Infrastructure as Code for cloud connectivity | [📖 Documentation](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/terraform/README.md) |
| **CI/CD Pipelines** | Automated testing, linting, building, and releasing | [📖 GitHub](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/.github/workflows/README.md) |
| **Docker Support** | Containerized execution environment | [📖 Documentation](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/Docker.md) |

## Quick Start

### Prerequisites

- Python 3.7+ (compatible with ansible-core 2.17, 2.18, 2.19, and 2.20)
- Ansible Core 2.17+
- Terraform v1.14+

### Ansible Collection (Recommended)

```bash
# Clone the repository
git clone https://github.com/Graphiant-Inc/graphiant-playbooks.git
cd graphiant-playbooks

# Create virtual environment
python3.7 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r ansible_collections/graphiant/naas/requirements-ee.txt

# Install collection from source
ansible-galaxy collection install ansible_collections/graphiant/naas/ --force

# Or install from Ansible Galaxy
ansible-galaxy collection install graphiant.naas
```

**Example Playbook:**

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
```

**See the [Ansible Collection README](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/README.md) for complete documentation and [Examples Guide](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/docs/guides/EXAMPLES.md) for detailed usage examples.**

### Key Features

- **Idempotent Operations**: All modules correctly report `changed: false` when no modifications occur
- **Structured Results**: Manager methods return detailed results with `changed`, `created`, `skipped`, and `deleted` fields
- **Graceful Error Handling**: Handles "object not found" errors gracefully in deconfigure operations
- **Jinja2 Template Support**: Configuration files support Jinja2 templating for dynamic generation
- **Comprehensive Logging**: Optional detailed logging for debugging and troubleshooting
- **Automated Releases**: GitHub Actions workflow for building, publishing, and creating releases

### Python Library

The collection can also be used as a Python library:

```bash
# Set PYTHONPATH for direct Python usage
export PYTHONPATH=$(pwd)/ansible_collections/graphiant/naas/plugins/module_utils:$PYTHONPATH
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

See [ansible_collections/graphiant/naas/tests/test.py](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/tests/test.py) for comprehensive Python library usage examples.

### Terraform Modules

Deploy cloud connectivity infrastructure with Terraform:

```bash
# Azure ExpressRoute
cd terraform/gateway_services/azure
terraform init
terraform plan -var-file="../../configs/gateway_services/azure_config.tfvars"
terraform apply -var-file="../../configs/gateway_services/azure_config.tfvars"

# AWS Direct Connect
cd terraform/gateway_services/aws
terraform init
terraform plan -var-file="../../configs/gateway_services/aws_config.tfvars"
terraform apply -var-file="../../configs/gateway_services/aws_config.tfvars"

# GCP InterConnect
cd terraform/gateway_services/gcp
terraform init
terraform plan -var-file="../../configs/gateway_services/gcp_config.tfvars"
terraform apply -var-file="../../configs/gateway_services/gcp_config.tfvars"
```

**See the [Terraform README](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/terraform/README.md) for detailed setup instructions.**

## Project Structure

```
graphiant-playbooks/
├── ansible_collections/graphiant/naas/               # Ansible collection 
│   ├── plugins/modules/                              # Ansible modules (9 modules)
│   ├── plugins/module_utils/                         # Python library code
│   ├── playbooks/                                    # Example playbooks
│   ├── configs/                                      # Configuration templates
│   ├── templates/                                    # Jinja2 templates
│   ├── docs/                                         # Documentation
│   ├── changelogs/changelog.yaml                     # Version history
│   ├── README.md                                     # Collection documentation
│   └── _version.py                                   # Centralized version management
├── terraform/                                        # Terraform modules
│   ├── gateway_services/                             # Cloud gateway services (AWS/Azure/GCP)
│   └── edge_services/                                # Edge services
├── scripts/                                          # Utility scripts
│   ├── build_collection.py                          # Collection build script
│   ├── bump_version.py                              # Version bumping script
│   ├── validate_collection.py                       # Collection validation script
│   └── build_docsite.sh                             # Documentation build script
├── .github/workflows/                                # GitHub Actions workflows
│   ├── lint.yml                                     # Linting workflow
│   ├── test.yml                                     # Test workflow (multi-version testing)
│   ├── build.yml                                    # Build workflow
│   ├── release.yml                                  # Release workflow (auto-tag/release)
│   └── README.md                                    # GitHub documentation
├── SECURITY.md                                       # Security policy
├── CONTRIBUTING.md                                   # Contribution guidelines
├── CODE_OF_CONDUCT.md                               # Code of conduct
└── README.md                                         # This file
```

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/CONTRIBUTING.md) for:
- Development setup
- Code standards
- Testing requirements
- Pull request process
- Branch protection requirements
- GPG signing requirements

See [CODE_OF_CONDUCT.md](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/CODE_OF_CONDUCT.md) for our community guidelines.

## 📄 License

This project is licensed under the GNU General Public License v3.0 or later (GPLv3+) - see the [LICENSE](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/LICENSE) file for details.

## 🆘 Support

- **Official Documentation**: [Graphiant Playbooks Guide](https://docs.graphiant.com/docs/graphiant-playbooks) <-> [Graphiant Automation Docs](https://docs.graphiant.com/docs/automation)
- **Changelog**: [changelogs/changelog.yaml](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/changelogs/changelog.yaml) - Version history and release notes
- **Security**: [SECURITY.md](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/SECURITY.md) - Security policy and vulnerability reporting
- **Issues**: [GitHub Issues](https://github.com/Graphiant-Inc/graphiant-playbooks/issues)
- **Email**: support@graphiant.com

## 🔗 Related Projects

- [Graphiant SDK Python](https://github.com/Graphiant-Inc/graphiant-sdk-python)
- [Graphiant SDK Go](https://github.com/Graphiant-Inc/graphiant-sdk-go)

---

**Made with ❤️ by the Graphiant Team**