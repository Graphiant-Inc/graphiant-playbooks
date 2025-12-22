# Ansible Collection Changelog

All notable changes to the Graphiant Playbooks collection will be documented in this file.

The format is based on [Ansible Collection Changelog Guidelines](https://docs.ansible.com/ansible/latest/dev_guide/developing_collections.html#changelogs),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Idempotency tracking for all modules - `changed: false` is now correctly reported when no modifications occur
- Graceful error handling for "object not found" errors in deconfigure operations

### Changed
- Manager methods now return structured result dictionaries with `changed`, `created`, `skipped`, and `deleted` fields
- Modules correctly interpret and propagate `changed` status from manager results

### Note
- PUT/PATCH operations (`configure_interfaces`, `configure_bgp`, etc.) always report `changed: true` as state comparison is not implemented

## [25.12.1] - 2025-12-18

### Added
- Updated to Graphiant SDK 25.12.1 for latest API support
- Enhanced compatibility with Graphiant API v25.12.1

### Changed
- **Dependencies:**
  - Updated Graphiant SDK dependency to 25.12.1
  - Collection version bumped to 25.12.1
- **Version Management:**
  - Updated module `version_added` to 25.12.0 format

### Deprecated
- N/A

### Removed
- N/A

### Fixed
- N/A

### Security
- Updated security documentation to reflect 25.12.x as current stable release

## [25.11.3] - 2025-12-13

### Added
- **Security:**
  - Comprehensive `SECURITY.md` with security best practices, vulnerability reporting process, and security checklist
  - Security policy covering credential management, code security, dependency management, and CI/CD security
- **Documentation:**
  - Reorganized documentation structure following Ansible collection best practices
  - Moved `CONTRIBUTING.md` to repository root for better visibility
  - Consolidated version management documentation into `docs/guides/VERSION_MANAGEMENT.md`
  - Enhanced `CONTRIBUTING.md` with detailed branch protection requirements and GPG signing instructions
- **Repository Management:**
  - Added `.github/CODEOWNERS` file for automatic code review assignments
  - Improved code ownership structure with SRE team approval requirements

### Changed
- **Credential Management:**
  - Removed `test.ini` file in favor of environment variable-based credential management
  - Updated `tests/test.py` to require environment variables (`GRAPHIANT_HOST`, `GRAPHIANT_USERNAME`, `GRAPHIANT_PASSWORD`)
  - Enhanced credential examples in playbooks to reflect best practices
- **Documentation:**
  - Updated all documentation references to reflect new file locations
  - Improved documentation organization with guides in `docs/guides/` directory
  - Enhanced release process documentation with version management details

### Deprecated
- N/A

### Removed
- `ansible_collections/graphiant/naas/tests/test.ini` - Replaced with environment variable-based configuration
- `setup.cfg` - No longer required for collection configuration

### Fixed
- Improved GPG signing documentation and troubleshooting guidance
- Enhanced branch protection rule compliance documentation
- Better credential management practices and examples

### Security
- Added comprehensive security best practices documentation
- Improved credential handling with environment variable requirements
- Enhanced security checklist for contributors

## [25.11.2] - 2025-12-12

### Added
- **CI/CD Infrastructure:**
  - GitHub Actions workflows for linting, testing, building, and releasing
  - Multi-version testing support (ansible-core 2.17, 2.18, 2.19)
  - E2E integration test workflow with conditional execution
- **Documentation:**
  - `ANSIBLE_INCLUSION_CHECKLIST.md` - Comprehensive checklist for Ansible collection inclusion (repository root)
  - `CODE_OF_CONDUCT.md` - Code of conduct for contributors (repository root)
  - `docs/guides/` - Additional documentation guides:
    - `VERSION_MANAGEMENT.md` - Version management guide
  - `docs/guides/RELEASE.md` - Release procedures and guidelines
  - `docs/guides/CREDENTIAL_MANAGEMENT_GUIDE.md` - Credential management best practices
  - `docs/guides/EXAMPLES.md` - Detailed usage examples
  - `docs/guides/VERSION_MANAGEMENT.md` - Version management guide
  - GitHub Actions pipeline documentation
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
- `ansible_collections/graphiant/naas/meta/execution-environment.yml` - Execution environment definition file removed (TE-4256)
- Large scale test configuration files (consolidated into scale2 versions)

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
- Requires Graphiant SDK >= 25.12.1

## Support

- GitHub Issues: https://github.com/Graphiant-Inc/graphiant-playbooks/issues
- Documentation: https://docs.graphiant.com/docs/graphiant-playbooks
- Email: support@graphiant.com
