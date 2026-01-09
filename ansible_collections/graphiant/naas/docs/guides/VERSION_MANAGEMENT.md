# Version Management Guide

This collection uses **centralized version management** to ensure all version references stay synchronized across the repository.

## Overview

All version information is centralized in `_version.py`. This file contains:
- Collection version (semantic versioning: MAJOR.MINOR.PATCH)
- Dependency versions (Python packages)
- Collection dependencies (Ansible collections)
- Ansible and Python version requirements
- Module `version_added` format

## Quick Start

### Check Current Version
```bash
python -c "from _version import __version__; print(__version__)"
```

### Bump Version
```bash
# From repository root
python scripts/bump_version.py patch    # 25.11.1 -> 25.11.2
python scripts/bump_version.py minor    # 25.11.1 -> 25.12.0
python scripts/bump_version.py major    # 25.11.1 -> 26.0.0
python scripts/bump_version.py 25.12.0  # Set specific version
```

### Sync Requirements
```bash
# Note: requirements-ee.txt is manually maintained (no version pins)
# It contains only runtime dependencies for Execution Environments
```

## Versioning Strategy

We follow [Semantic Versioning](https://semver.org/):
- **MAJOR** version: Breaking changes that are not backward compatible
- **MINOR** version: New features that are backward compatible
- **PATCH** version: Bug fixes that are backward compatible

### Version Format

- **Collection version:** `MAJOR.MINOR.PATCH` (e.g., `25.11.1`)
- **Module version_added:** `MAJOR.MINOR.0` (e.g., `25.11.0`)
  - Ansible requires `version_added` to be major.minor format (no patch)
  - Patch version is always `.0` for modules

## Files Updated by Version Bump

When you run `bump_version.py`, these files are automatically updated:

1. ✅ `_version.py` - Collection version and module version
2. ✅ `galaxy.yml` - Collection metadata version
3. ✅ `CHANGELOG.md` - Adds new version entry template
4. ✅ All module files - Updates `version_added` field

## Manual Steps After Version Bump

After running the bump script, you must:

1. **Edit CHANGELOG.md** - Fill in actual changes for the new version
2. **Review changes** - Run `git diff` to verify all updates
3. **Test** - Run `ansible-test sanity` to ensure everything works
4. **Commit** - Commit the version changes
5. **Tag** - Create git tag for the release
6. **Build** - Build collection tarball
7. **Publish** - Publish to Ansible Galaxy

See [RELEASE.md](RELEASE.md) for complete release process documentation.

## Dependency Management

### Current Dependencies

Dependencies are managed in `_version.py` and synced to `requirements-ee.txt`:

**Core Python Packages:**
- PyYAML: 6.0.1
- Jinja2: 3.1.2
- future: 0.18.3
- tabulate: 0.9.0

**Graphiant SDK:**
- graphiant-sdk: 25.12.1

**Ansible:**
- ansible-core: >=2.17.0

**Development Tools:**
- flake8: 7.3.0
- pylint: 3.3.7
- ansible-lint: >=24.0.0
- pre-commit: 4.2.0
- antsibull-docs: >=2.0.0,<3.0.0

### Updating Dependencies

**Option 1: During version bump**
```bash
python scripts/bump_version.py patch --update-deps graphiant-sdk=25.12.0
```

**Option 2: Manual update**
1. Edit `_version.py` to update `DEPENDENCIES` dictionary
2. Note: `requirements-ee.txt` is manually maintained and doesn't use version pins (for Execution Environment compatibility)

### Dependency Version Pinning Strategy

- **Core dependencies** (PyYAML, Jinja2, etc.): Pin to specific versions for stability
- **Graphiant SDK**: Pin to specific versions, update when new features are needed
- **Development tools** (linting, docs): Use `>=` for flexibility
- **Ansible**: Use `>=` to support multiple Ansible versions

## Key Files

| File | Purpose | Location |
|------|---------|----------|
| `_version.py` | **Source of truth** - All version definitions | Collection root |
| `bump_version.py` | Automated version bumping script | `scripts/` (repo root) |
| `requirements-ee.txt` | Runtime dependencies for Execution Environments (manually maintained, no version pins) | Collection root |
| `galaxy.yml` | Collection metadata (auto-updated) | Collection root |
| `CHANGELOG.md` | Version history (auto-updated) | Collection root |

## Version File Structure

`_version.py` contains:
- `__version__` / `COLLECTION_VERSION` - Collection version
- `MODULE_VERSION_ADDED` - Version for module `version_added` (major.minor.0 format)
- `DEPENDENCIES` - Python package versions
- `COLLECTION_DEPENDENCIES` - Ansible collection dependencies
- `REQUIRES_PYTHON` - Minimum Python version

## Quick Reference

```bash
# Check current version
python -c "from _version import __version__; print(__version__)"

# Bump patch version (bug fixes)
python scripts/bump_version.py patch

# Bump minor version (new features)
python scripts/bump_version.py minor

# Bump major version (breaking changes)
python scripts/bump_version.py major

# Set specific version
python scripts/bump_version.py 25.12.0

# Update dependency during bump
python scripts/bump_version.py patch --update-deps graphiant-sdk=25.12.0

# Sync requirements-ee.txt
# Note: requirements-ee.txt is manually maintained (no version pins)

# Build collection (auto-syncs requirements)
python scripts/build_collection.py
```

## Benefits

✅ **Single source of truth** - All versions in one place  
✅ **Automated updates** - Script updates all files automatically  
✅ **Consistency** - No more version mismatches  
✅ **Easy releases** - Simple commands to bump versions  
✅ **Dependency tracking** - Centralized dependency version management  

## Troubleshooting

### Version Mismatch Errors

If you see version mismatch errors:
1. Check `_version.py` is the source of truth
2. Run `python scripts/bump_version.py <version>` to sync all files
3. Verify all files are updated: `git diff`

### Build Failures

If collection build fails:
1. Check `galaxy.yml` syntax
2. Verify all required files exist
3. Check for syntax errors in module files

## Related Documentation

- [RELEASE.md](RELEASE.md) - Complete release process documentation
- [README.md](../README.md) - Collection overview and usage
- `_version.py` - Source code with all version definitions

## Support

For questions about version management:
- See [RELEASE.md](RELEASE.md) for detailed procedures
- Check `bump_version.py --help` for script usage
- Review `_version.py` for current version definitions
