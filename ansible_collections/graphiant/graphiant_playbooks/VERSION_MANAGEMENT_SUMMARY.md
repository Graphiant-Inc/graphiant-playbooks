# Version Management System Summary

## Overview

The Graphiant Playbooks collection now uses a **centralized version management system** to ensure consistency across all version references in the repository.

## Key Files

### `_version.py` - Source of Truth
- **Location:** `ansible_collections/graphiant/graphiant_playbooks/_version.py`
- **Purpose:** Central definition of all versions
- **Contains:**
  - Collection version (`__version__`)
  - Python dependency versions (`DEPENDENCIES`)
  - Ansible collection dependencies (`COLLECTION_DEPENDENCIES`)
  - Version requirements (`REQUIRES_ANSIBLE`, `REQUIRES_PYTHON`)
  - Module version format (`MODULE_VERSION_ADDED`)

### `bump_version.py` - Version Bumping Script
- **Location:** `ansible_collections/graphiant/graphiant_playbooks/bump_version.py`
- **Purpose:** Automatically update all version references
- **Usage:**
  ```bash
  python scripts/bump_version.py patch    # 25.11.1 -> 25.11.2
  python scripts/bump_version.py minor    # 25.11.1 -> 25.12.0
  python scripts/bump_version.py major    # 25.11.1 -> 26.0.0
  python scripts/bump_version.py 25.12.0  # Set specific version
  ```

### `generate_requirements.py` - Requirements Generator
- **Location:** `ansible_collections/graphiant/graphiant_playbooks/generate_requirements.py`
- **Purpose:** Generate `requirements.txt` from `_version.py`
- **Usage:**
  ```bash
  python scripts/generate_requirements.py
  ```

## Files Updated by Version Bump

When you run `bump_version.py`, these files are automatically updated:

1. ✅ `_version.py` - Collection version and module version
2. ✅ `galaxy.yml` - Collection metadata version
3. ✅ `CHANGELOG.md` - Adds new version entry template
4. ✅ All module files - Updates `version_added` field

## Manual Steps After Version Bump

After running the bump script, you must:

1. **Edit CHANGELOG.md** - Fill in actual changes for the new version
2. **Review changes** - Run `git diff` to verify updates
3. **Test** - Run `ansible-test sanity` to ensure everything works
4. **Commit** - Commit the version changes
5. **Tag** - Create git tag for the release
6. **Build** - Build collection tarball
7. **Publish** - Publish to Ansible Galaxy

## Dependency Management

### Current Dependencies (from `_version.py`)

**Core Python Packages:**
- PyYAML: 6.0.1
- Jinja2: 3.1.2
- future: 0.18.3
- tabulate: 0.9.0

**Graphiant SDK:**
- graphiant-sdk: 25.11.1

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
2. Run `python scripts/generate_requirements.py` to sync `requirements.txt`

## Version Format

- **Collection version:** `MAJOR.MINOR.PATCH` (e.g., `25.11.1`)
- **Module version_added:** `MAJOR.MINOR.0` (e.g., `25.11.0`)
  - Ansible requires `version_added` to be major.minor format
  - Patch version is always `.0` for modules

## Benefits

✅ **Single source of truth** - All versions in one place  
✅ **Automated updates** - Script updates all files automatically  
✅ **Consistency** - No more version mismatches  
✅ **Easy releases** - Simple commands to bump versions  
✅ **Dependency tracking** - Centralized dependency version management  

## Quick Reference

```bash
# Check current version
python -c "from _version import __version__; print(__version__)"

# Bump patch version
python scripts/bump_version.py patch

# Bump minor version
python scripts/bump_version.py minor

# Bump major version
python scripts/bump_version.py major

# Set specific version
python scripts/bump_version.py 25.12.0

# Update dependency
python scripts/bump_version.py patch --update-deps graphiant-sdk=25.12.0

# Sync requirements.txt
python scripts/generate_requirements.py

# Build collection (auto-syncs requirements)
python scripts/build_collection.py
```

## Documentation

- **[RELEASE.md](RELEASE.md)** - Complete release process documentation
- **[README_VERSION_MANAGEMENT.md](README_VERSION_MANAGEMENT.md)** - Quick start guide
- **`_version.py`** - Source code with all version definitions

## Migration Notes

If you have existing version references that aren't updated by the script:

1. Check `_version.py` is the source of truth
2. Manually update any missed files
3. Consider adding them to `bump_version.py` for future automation

## Support

For questions about version management:
- See [RELEASE.md](RELEASE.md) for detailed procedures
- Check `bump_version.py --help` for script usage
- Review `_version.py` for current version definitions
