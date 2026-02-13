# Release Process Documentation

This document describes the process for releasing new versions of the Graphiant Playbooks Ansible Collection.

> **Quick Start:** See [VERSION_MANAGEMENT.md](VERSION_MANAGEMENT.md) for a quick reference guide.

## Version Management

All version information is centralized in `_version.py`. This file contains:
- Collection version (semantic versioning: MAJOR.MINOR.PATCH)
- Dependency versions (Python packages)
- Collection dependencies (Ansible collections)
- Ansible and Python version requirements

## Versioning Strategy

We follow [Semantic Versioning](https://semver.org/):
- **MAJOR** version: Breaking changes that are not backward compatible
- **MINOR** version: New features that are backward compatible
- **PATCH** version: Bug fixes that are backward compatible

### Current Version

The current collection version is defined in `_version.py`:
```python
__version__ = "26.2.1"
```

## Release Process

### Automated vs Manual Release

The collection supports two release approaches:

1. **Automated Release (Recommended)**: Use the GitHub Actions release workflow (`.github/workflows/release.yml`)
   - Automatically builds the collection
   - Publishes to Ansible Galaxy
   - Creates Git tags
   - Creates GitHub releases with CHANGELOG references
   - **Idempotent**: Safe to re-run - won't fail if tags or releases already exist

2. **Manual Release**: Follow all steps manually (useful for troubleshooting or custom workflows)

### Prerequisites

1. Ensure you have write access to the repository
2. Ensure all tests pass: `ansible-test sanity --python 3.12`
3. Ensure all changes are committed to the repository
4. Review and update `CHANGELOG.md` with all changes

### Step 1: Install Dependencies (if needed)

Ensure PyYAML is installed for the bump script:

```bash
cd ansible_collections/graphiant/naas
pip install -r requirements-ee.txt
```

### Step 2: Update Version

Use the `bump_version.py` script to update all version references:

```bash
# For a patch release (bug fixes)
python scripts/bump_version.py patch

# For a minor release (new features)
python scripts/bump_version.py minor

# For a major release (breaking changes)
python scripts/bump_version.py major

# For a specific version
python scripts/bump_version.py 26.2.1
```

The script automatically updates:
- `_version.py` - Central version file
- `galaxy.yml` - Collection metadata
- `CHANGELOG.md` - Adds new version entry
- All module files - Updates `version_added` field

### Step 2: Update Dependencies (Optional)

If you need to update dependency versions, you can do so in two ways:

**Option A: Update during version bump**
```bash
python scripts/bump_version.py patch --update-deps graphiant-sdk=26.2.1
```

**Option B: Update manually**
1. Edit `_version.py` to update `DEPENDENCIES` dictionary
2. Edit `requirements-ee.txt` to match the versions in `_version.py`

### Step 4: Review Changes

Review all changes made by the bump script:

```bash
git diff
```

Pay special attention to:
- `CHANGELOG.md` - Ensure the new entry is correct
- Module files - Verify `version_added` is updated correctly
- `galaxy.yml` - Verify version is correct

### Step 5: Update CHANGELOG.md

Edit `CHANGELOG.md` and fill in the actual changes for the new version:

```markdown
## [25.11.2] - 2025-01-15

### Added
- New feature X
- New feature Y

### Changed
- Improved error handling in module Z

### Fixed
- Fixed bug in module A
- Fixed issue with dependency B
```

### Step 6: Commit Changes

Commit all version-related changes:

```bash
git add -A
git commit -m "Bump version to 25.11.2"
```

### Step 7: Create Git Tag

**Option A: Using GitHub Actions Release Workflow (Recommended)**

The release workflow automatically creates Git tags and GitHub releases. If a tag or release already exists, the workflow will skip creation and continue without failing (idempotent behavior).

**Option B: Manual Tag Creation**

Create an annotated git tag for the release:

```bash
git tag -a v25.11.2 -m "Release version 25.11.2"
```

Or use the collection version format:

```bash
git tag -a 25.11.2 -m "Release version 25.11.2"
```

**Note:** If you're using the GitHub Actions release workflow, manual tag creation is optional as the workflow handles it automatically.

### Step 8: Build Collection

Build the collection tarball:

```bash
python scripts/build_collection.py
```

This creates a tarball in the `build/` directory:
```
build/graphiant-naas-25.11.2.tar.gz
```

### Step 9: Verify Build

Verify the collection was built correctly:

```bash
# Install the collection locally
ansible-galaxy collection install build/graphiant-naas-25.11.2.tar.gz --force

# Verify installation
ansible-galaxy collection list graphiant.naas

# Run sanity tests
cd ansible_collections/graphiant/naas
ansible-test sanity --python 3.12
```

### Step 10: Push Changes and Tags

Push the commit and tag to the remote repository:

```bash
git push origin main
git push origin v25.11.2
```

Or if using the collection version format:

```bash
git push origin 25.11.2
```

### Step 11: Create GitHub Release (Optional)

1. Go to GitHub repository: https://github.com/Graphiant-Inc/graphiant-playbooks
2. Click "Releases" → "Draft a new release"
3. Select the tag you just pushed
4. Copy the changelog entry for this version
5. Upload the collection tarball as a release asset
6. Publish the release

### Step 12: Publish to Ansible Galaxy

Publish the collection to Ansible Galaxy:

**Option A: Using GitHub Actions Release Workflow (Recommended)**
- The release workflow automatically:
  1. Builds the collection
  2. Publishes to Ansible Galaxy (if `GALAXY_API_KEY` is configured)
  3. Creates Git tag (if it doesn't already exist)
  4. Creates GitHub release (if it doesn't already exist)
- Ensure `GALAXY_API_KEY` secret or variable is configured in GitHub
- The workflow is idempotent: it won't fail if tags or releases already exist

**Option B: Manual publish**
```bash
# Get API token from: https://galaxy.ansible.com/ui/token/
export ANSIBLE_GALAXY_TOKEN=<YOUR_API_TOKEN>

# Publish
ansible-galaxy collection publish \
  build/graphiant-naas-25.11.2.tar.gz \
  --api-key=$ANSIBLE_GALAXY_TOKEN
```

## Version Update Checklist

Before releasing, ensure:

- [ ] All tests pass (`ansible-test sanity`)
- [ ] All changes are documented in `CHANGELOG.md`
- [ ] Version is updated in `_version.py`
- [ ] Version is updated in `galaxy.yml`
- [ ] `version_added` is updated in all modules
- [ ] Dependencies are up to date (if needed)
- [ ] Collection builds successfully
- [ ] Git tag is created (or use GitHub Actions release workflow)
- [ ] Changes are pushed to repository
- [ ] Collection is published to Ansible Galaxy (or use GitHub Actions release workflow)
- [ ] GitHub release is created (or use GitHub Actions release workflow)

## Dependency Management

### Updating Dependency Versions

Dependencies are managed in two places:
1. `_version.py` - Source of truth for all versions
2. `requirements-ee.txt` - Used by pip for installation

When updating dependencies:

1. Update `_version.py`:
```python
DEPENDENCIES = {
    "graphiant-sdk": "26.2.1",  # Use >= 26.1.1
    # ... other dependencies
}
```

2. Update `requirements-ee.txt` to match (no version pins):
```
graphiant-sdk
```

3. Test with the new dependency versions:
```bash
pip install -r requirements-ee.txt --upgrade
ansible-test sanity --python 3.12
```

### Dependency Version Pinning Strategy

- **Core dependencies** (PyYAML, Jinja2, etc.): No version pins (flexible for Execution Environments)
- **Graphiant SDK**: No version pins (flexible for Execution Environments)
- **Development tools** (linting, docs): No version pins (use latest compatible versions)
- **Ansible**: Use `>=` to support multiple Ansible versions (tested against 2.17, 2.18, 2.19, 2.20)

## Troubleshooting

### Version Mismatch Errors

If you see version mismatch errors:
1. Check `_version.py` is the source of truth
2. Run `python scripts/bump_version.py <version>` to sync all files
3. Verify all files are updated: `git diff`

### Build Failures

If collection build fails:
1. Check `galaxy.yml` syntax: `ansible-galaxy collection build --help`
2. Verify all required files exist
3. Check for syntax errors in module files

### Publishing Failures

If publishing to Galaxy fails:
1. Verify API token is correct
2. Check collection name matches Galaxy namespace
3. Ensure version doesn't already exist on Galaxy
4. Check Galaxy API status

## Quick Reference

```bash
# Bump patch version
python scripts/bump_version.py patch

# Bump minor version
python scripts/bump_version.py minor

# Bump major version
python scripts/bump_version.py major

# Set specific version
python scripts/bump_version.py 26.2.1

# Update dependency during bump
python scripts/bump_version.py patch --update-deps graphiant-sdk=26.2.1

# Build collection
python scripts/build_collection.py

# Publish to Galaxy
ansible-galaxy collection publish build/graphiant-naas-*.tar.gz --api-key=$TOKEN
```

## Related Files

- `_version.py` - Centralized version definitions
- `bump_version.py` - Version bumping script
- `galaxy.yml` - Collection metadata
- `CHANGELOG.md` - Release notes
- `requirements-ee.txt` - Python dependencies
- `build_collection.py` - Collection build script
