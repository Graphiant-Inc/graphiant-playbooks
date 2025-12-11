# Graphiant Playbooks

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Ansible](https://img.shields.io/badge/ansible--core-2.17+-green.svg)](https://docs.ansible.com/)
[![Terraform](https://img.shields.io/badge/terraform-1.14+-red.svg)](https://developer.hashicorp.com/terraform/install)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Documentation](https://img.shields.io/badge/docs-latest-brightgreen.svg)](https://docs.graphiant.com/docs/graphiant-sdk-python)

Automated network infrastructure management for [Graphiant Network-as-a-Service (NaaS)](https://www.graphiant.com) offerings.

Refer [Graphiant Docs](https://docs.graphiant.com) to get started with [Graphiant Network-as-a-Service (NaaS)](https://www.graphiant.com) offerings.

## 📚 Documentation

- **Official Documentation**: [Graphiant Plybooks Guide](https://docs.graphiant.com/docs/graphiant-playbooks) <-> [Graphiant Automation Docs](https://docs.graphiant.com/docs/automation)
- **Ansible Collection**: [Ansible Galaxy Collection - graphiant.graphiant_playbooks](https://galaxy.ansible.com/ui/repo/published/graphiant/graphiant_playbooks)

## Components

| Component | Description | Documentation |
|-----------|-------------|---------------|
| **Ansible Collection** | Ansible modules for Graphiant NaaS automation | [📖 Documentation](ansible_collections/graphiant/graphiant_playbooks/README.md) |
| **Terraform Modules** | Infrastructure as Code for cloud connectivity | [📖 Documentation](terraform/README.md) |
| **CI/CD Pipelines** | Automated testing, linting, and Docker builds | [📖 GitLab](.gitlab/pipelines/README.md) \| [📖 GitHub](.github/workflows/README.md) |
| **Docker Support** | Containerized execution environment | [📖 Documentation](Docker.md) |

## Quick Start

### Prerequisites

- Python 3.10+
- Ansible Core 2.17+
- Terraform v1.14+

### Ansible Collection (Recommended)

```bash
# Clone the repository
git clone https://github.com/Graphiant-Inc/graphiant-playbooks.git
cd graphiant-playbooks

# Create virtual environment
python3.10 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r ansible_collections/graphiant/graphiant_playbooks/requirements.txt

# Install collection from source
ansible-galaxy collection install ansible_collections/graphiant/graphiant_playbooks/ --force

# Or install from Ansible Galaxy
ansible-galaxy collection install graphiant.graphiant_playbooks
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
      graphiant.graphiant_playbooks.graphiant_interfaces:
        <<: *graphiant_client_params
        interface_config_file: "interface_config.yaml"
        operation: "configure_lan_interfaces"
```

**See the [Ansible Collection README](ansible_collections/graphiant/graphiant_playbooks/README.md) for complete documentation and [EXAMPLES.md](ansible_collections/graphiant/graphiant_playbooks/EXAMPLES.md) for detailed usage examples.**

### Python Library

The collection can also be used as a Python library:

```bash
# Set PYTHONPATH for direct Python usage
export PYTHONPATH=$(pwd)/ansible_collections/graphiant/graphiant_playbooks/plugins/module_utils:$PYTHONPATH
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

See `ansible_collections/graphiant/graphiant_playbooks/tests/test.py` for comprehensive Python library usage examples.

### Terraform Modules

Deploy cloud connectivity infrastructure with Terraform:

```bash
# Azure ExpressRoute
cd terraform/azure-expressroute
terraform init
terraform plan -var-file="../../terraform/configs/azure_config.tfvars"
terraform apply -var-file="../../terraform/configs/azure_config.tfvars"

# AWS Direct Connect
cd terraform/AWS/directConnect
terraform init
terraform plan -var-file="../../../terraform/configs/aws_config.tfvars"
terraform apply -var-file="../../../terraform/configs/aws_config.tfvars"
```

**See the [Terraform README](terraform/README.md) for detailed setup instructions.**

## Project Structure

```
graphiant-playbooks/
├── ansible_collections/graphiant/graphiant_playbooks/  # Ansible collection
├── terraform/                                          # Terraform modules
├── scripts/                                            # Utility scripts (version management, validation, building)
│   ├── build_collection.py                           # Collection build script
│   ├── bump_version.py                               # Version bumping script
│   ├── generate_requirements.py                      # Requirements generator
│   ├── validate_collection.py                        # Collection validation script
│   └── build_docsite.sh                              # Documentation build script
├── .gitlab/                                            # GitLab CI/CD configuration
│   └── pipelines/                                      # GitLab pipeline definitions
│       ├── lint.yml                                   # Linting pipeline
│       ├── run.yml                                    # Test pipeline
│       ├── docker.yml                                 # Docker build pipeline
│       └── README.md                                  # GitLab documentation
├── .github/workflows/                                 # GitHub Actions workflows
│   ├── lint.yml                                       # Linting workflow
│   ├── test.yml                                       # Test workflow
│   ├── build.yml                                      # Build workflow
│   ├── release.yml                                    # Release workflow
│   └── README.md                                      # GitHub documentation
├── .gitlab-ci.yml                                      # GitLab CI main configuration
└── README.md                                           # This file
```

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](ansible_collections/graphiant/graphiant_playbooks/CONTRIBUTING.md) for:
- Development setup
- Code standards
- Testing requirements
- Pull request process

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

- **Official Documentation**: [Graphiant Plybooks Guide](https://docs.graphiant.com/docs/graphiant-playbooks) <-> [Graphiant Automation Docs](https://docs.graphiant.com/docs/automation)
- **Issues**: [GitHub Issues](https://github.com/Graphiant-Inc/graphiant-playbooks/issues)
- **Email**: support@graphiant.com

## 🔗 Related Projects

- [Graphiant SDK Python](https://github.com/Graphiant-Inc/graphiant-sdk-python)
- [Graphiant SDK Go](https://github.com/Graphiant-Inc/graphiant-sdk-go)

---

**Made with ❤️ by the Graphiant Team**