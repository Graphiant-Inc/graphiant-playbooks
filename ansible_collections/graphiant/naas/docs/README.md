# Documentation

This directory contains additional documentation for the Graphiant Playbooks Ansible Collection.

## Documentation Structure

### Collection Root Files (Required/Recommended)

- **`README.md`** - Main collection documentation (required)
- **`CHANGELOG.md`** - Version history and release notes (recommended)

### Guides (`docs/guides/`)

Detailed guides for specific topics:

- **[VERSION_MANAGEMENT.md](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/docs/guides/VERSION_MANAGEMENT.md)** - Version management system and release process
- **[RELEASE.md](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/docs/guides/RELEASE.md)** - Complete release process documentation
- **[CREDENTIAL_MANAGEMENT_GUIDE.md](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/docs/guides/CREDENTIAL_MANAGEMENT_GUIDE.md)** - Best practices for managing credentials
- **[EXAMPLES.md](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/docs/guides/EXAMPLES.md)** - Detailed usage examples and playbook samples

### Docusite (`docs/docsite/`)

Documentation site configuration for building HTML documentation with Sphinx/antsibull-docs.

See [DOCSITE_SETUP.md](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/docs/DOCSITE_SETUP.md) for building the documentation site.

## Quick Links

- [Main README](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/README.md) - Collection overview and quick start
- [Version Management](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/docs/guides/VERSION_MANAGEMENT.md) - How to manage versions
- [Release Process](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/docs/guides/RELEASE.md) - How to release new versions
- [Examples](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/docs/guides/EXAMPLES.md) - Usage examples
- [Credential Management](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/docs/guides/CREDENTIAL_MANAGEMENT_GUIDE.md) - Security best practices

## Module Documentation

Module documentation is embedded in the module files themselves. Common options (Graphiant portal host, username, password) are defined in the shared doc fragment `graphiant.naas.graphiant_portal_auth` and included by all modules. Use `ansible-doc` to view:

```bash
ansible-doc graphiant.naas.graphiant_interfaces
ansible-doc graphiant.naas.graphiant_bgp
ansible-doc graphiant.naas.graphiant_site_to_site_vpn
ansible-doc graphiant.naas.graphiant_global_config
ansible-doc graphiant.naas.graphiant_sites
ansible-doc graphiant.naas.graphiant_data_exchange
ansible-doc graphiant.naas.graphiant_static_routes
ansible-doc graphiant.naas.graphiant_ntp
```

## Building Documentation Site

To build the HTML documentation site:

```bash
# From collection root
python ../../scripts/build_docsite.sh
```

Or from the collection directory:

```bash
cd docs
./build.sh
```

See [DOCSITE_SETUP.md](https://github.com/Graphiant-Inc/graphiant-playbooks/blob/main/ansible_collections/graphiant/naas/docs/DOCSITE_SETUP.md) for detailed instructions.
