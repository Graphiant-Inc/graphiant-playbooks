# Ansible Collection Changelog

All notable changes to the Graphiant Playbooks collection will be documented in this file.

The format is based on [Ansible Collection Changelog Guidelines](https://docs.ansible.com/ansible/latest/dev_guide/developing_collections.html#changelogs),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [25.11.2] - 2025-12-12

### Added
- **CI/CD Infrastructure:**
  - GitHub Actions workflows for linting, testing, building, and releasing
  - GitLab CI/CD pipeline reorganization (moved to `.gitlab/pipelines/` directory)
  - Multi-version testing support (ansible-core 2.17, 2.18, 2.19)
  - E2E integration test workflow with conditional execution
- **Documentation:**
  - `ANSIBLE_INCLUSION_CHECKLIST.md` - Comprehensive checklist for Ansible collection inclusion
  - `CODE_OF_CONDUCT.md` - Code of conduct for contributors
  - `README_VERSION_MANAGEMENT.md` - Version management documentation
  - `RELEASE.md` - Release procedures and guidelines
  - `VERSIONING.md` - Version management system documentation
  - `VERSION_MANAGEMENT_SUMMARY.md` - Version management summary
  - GitHub Actions and GitLab CI/CD pipeline documentation
- **Version Management:**
  - Centralized version management system (`_version.py`)
  - Version bumping script (`scripts/bump_version.py`)
  - Requirements generator script (`scripts/generate_requirements.py`)
  - Utility scripts moved to `scripts/` directory at repository root
- **Testing:**
  - `tests/sanity/requirements.txt` - Sanity test dependencies
  - Improved collection validation and testing infrastructure

### Changed
- **CI/CD Pipeline Improvements:**
  - Reorganized GitLab CI/CD pipelines (moved from `pipelines/` to `.gitlab/pipelines/`)
  - Updated all CI/CD workflows to use centralized version management
  - Improved multi-version testing across ansible-core versions
  - Enhanced E2E integration test with better credential handling
- **Module Updates:**
  - Updated all modules with improved error handling and documentation
  - Enhanced module utilities with better SDK client integration
  - Improved configuration template handling
- **Documentation:**
  - Updated collection README with comprehensive installation and usage instructions
  - Enhanced CONTRIBUTING.md with detailed development guidelines
  - Updated project structure documentation
- **Dockerfile:** Removed scripts directory copy from Docker build process
- **Configuration Files:**
  - Updated `.ansible-lint` configuration
  - Added `.gitignore` for collection directory
  - Updated `galaxy.yml` and `meta/runtime.yml` metadata

### Deprecated
- N/A

### Removed
- `ansible_collections/graphiant/graphiant_playbooks/meta/execution-environment.yml` - Execution environment definition file removed (TE-4256)
- Large scale test configuration files (consolidated into scale2 versions)
- Old pipeline documentation (replaced with `.gitlab/pipelines/README.md`)

### Fixed
- Improved error handling across all modules
- Enhanced SDK client integration and error reporting
- Better configuration validation and template processing
- Improved collection structure validation

### Security
- N/A

## [25.11.1] - 2025-12-08

### Added
- Initial release of Graphiant Playbooks Ansible Collection
- **Modules:**
  - `graphiant_interfaces` - Manage interfaces and circuits (LAN/WAN)
  - `graphiant_bgp` - Manage BGP peering and routing policies
  - `graphiant_global_config` - Manage global configuration objects
  - `graphiant_sites` - Manage sites and site attachments
  - `graphiant_data_exchange` - Manage Data Exchange workflows
- Self-contained collection with embedded Python libraries
- Sample playbooks and configuration files
- Jinja2 templates for configuration generation
- Comprehensive documentation

### Changed
- N/A

### Deprecated
- N/A

### Removed
- N/A

### Fixed
- N/A

### Security
- N/A

## Release Notes

### Requirements
- Requires ansible-core >= 2.17.0
- Requires Python >= 3.10
- Requires Graphiant SDK >= 25.11.1

## Support

- GitHub Issues: https://github.com/Graphiant-Inc/graphiant-playbooks/issues
- Documentation: https://docs.graphiant.com/docs/graphiant-playbooks
- Email: support@graphiant.com
