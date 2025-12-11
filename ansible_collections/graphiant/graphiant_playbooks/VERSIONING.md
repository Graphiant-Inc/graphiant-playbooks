# Version Management System

## Overview

The Graphiant Playbooks collection uses **centralized version management** to ensure all version references stay synchronized.

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
```

### Sync Requirements
```bash
# From repository root
python scripts/generate_requirements.py
```

## Files

| File | Purpose |
|------|---------|
| `_version.py` | **Source of truth** - All version definitions |
| `bump_version.py` | Automated version bumping script |
| `generate_requirements.py` | Generate `requirements.txt` from `_version.py` |
| `RELEASE.md` | Complete release process documentation |
| `README_VERSION_MANAGEMENT.md` | Quick reference guide |
| `VERSION_MANAGEMENT_SUMMARY.md` | System overview and benefits |

## What Gets Updated

When you run `bump_version.py`, these files are automatically updated:

1. ✅ `_version.py` - Collection version
2. ✅ `galaxy.yml` - Collection metadata
3. ✅ `CHANGELOG.md` - New version entry
4. ✅ All modules - `version_added` field

## Version Format

- **Collection:** `MAJOR.MINOR.PATCH` (e.g., `25.11.1`)
- **Module version_added:** `MAJOR.MINOR.0` (e.g., `25.11.0`)
  - Ansible requires major.minor format (no patch)

## Dependencies

Dependencies are managed in `_version.py` and synced to `requirements.txt`:

```python
DEPENDENCIES = {
    "graphiant-sdk": "25.11.1",
    "PyYAML": "6.0.1",
    # ... etc
}
```

## Documentation

- **[RELEASE.md](RELEASE.md)** - Step-by-step release process
- **[README_VERSION_MANAGEMENT.md](README_VERSION_MANAGEMENT.md)** - Quick reference
- **[VERSION_MANAGEMENT_SUMMARY.md](VERSION_MANAGEMENT_SUMMARY.md)** - Detailed overview

## Benefits

✅ Single source of truth  
✅ Automated updates  
✅ Consistency guaranteed  
✅ Easy version bumps  
✅ Centralized dependency management  
