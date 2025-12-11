# Version Management Quick Start

This collection uses centralized version management. All versions are defined in `_version.py`.

## Files Updated by Version Bump

When you run `python scripts/bump_version.py <version>`, the following files are automatically updated:

1. **`_version.py`** - Central version definitions
2. **`galaxy.yml`** - Collection metadata version
3. **`CHANGELOG.md`** - Adds new version entry
4. **All module files** - Updates `version_added` field

## Manual Updates Required

After running the bump script, you must manually:

1. **Update CHANGELOG.md** - Fill in actual changes for the new version
2. **Review changes** - Run `git diff` to verify all updates
3. **Test** - Run `ansible-test sanity` to ensure everything works

## Common Tasks

### Bump Version
```bash
python scripts/bump_version.py patch    # 25.11.1 -> 25.11.2
python scripts/bump_version.py minor    # 25.11.1 -> 25.12.0
python scripts/bump_version.py major    # 25.11.1 -> 26.0.0
python scripts/bump_version.py 25.12.0  # Set specific version
```

### Update Dependency
```bash
# Update during version bump
python scripts/bump_version.py patch --update-deps graphiant-sdk=25.12.0

# Or update manually in _version.py, then:
python scripts/generate_requirements.py
```

### Sync Requirements
```bash
# Generate requirements.txt from _version.py
python scripts/generate_requirements.py
```

## Version File Structure

`_version.py` contains:
- `__version__` / `COLLECTION_VERSION` - Collection version
- `MODULE_VERSION_ADDED` - Version for module `version_added` (major.minor.0 format)
- `DEPENDENCIES` - Python package versions
- `COLLECTION_DEPENDENCIES` - Ansible collection dependencies
- `REQUIRES_ANSIBLE` - Minimum Ansible version
- `REQUIRES_PYTHON` - Minimum Python version

## See Also

- [RELEASE.md](RELEASE.md) - Complete release process documentation
- `_version.py` - Source of truth for all versions
- `bump_version.py` - Version bumping script
