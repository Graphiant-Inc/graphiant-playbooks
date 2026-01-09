#!/usr/bin/env python3
"""
Version bumping script for Graphiant Playbooks Ansible Collection.

This script updates all version references across the repository when bumping
the collection version.

Usage:
    # Bump patch version (25.11.1 -> 25.11.2)
    python bump_version.py patch

    # Bump minor version (25.11.1 -> 25.12.0)
    python bump_version.py minor

    # Bump major version (25.11.1 -> 26.0.0)
    python bump_version.py major

    # Set specific version
    python bump_version.py 25.12.0

    # Update dependency versions
    python bump_version.py --update-deps graphiant-sdk=25.12.0
"""

import re
import sys
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Install it with: pip install PyYAML")
    print("Or install all dependencies: pip install -r requirements-ee.txt")
    sys.exit(1)


# Get the collection root directory
# Script is at scripts/bump_version.py, collection is at ansible_collections/graphiant/naas/
SCRIPT_DIR = Path(__file__).parent  # scripts/
REPO_ROOT = SCRIPT_DIR.parent  # repository root
COLLECTION_ROOT = REPO_ROOT / "ansible_collections" / "graphiant" / "naas"


def load_version() -> str:
    """Load current version from _version.py"""
    version_file = COLLECTION_ROOT / "_version.py"
    with open(version_file, 'r') as f:
        content = f.read()
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
        if match:
            return match.group(1)
    raise ValueError("Could not find __version__ in _version.py")


def update_version_file(new_version: str) -> None:
    """Update _version.py with new version"""
    version_file = COLLECTION_ROOT / "_version.py"
    with open(version_file, 'r') as f:
        content = f.read()

    # Update __version__ and COLLECTION_VERSION
    content = re.sub(
        r'__version__\s*=\s*["\'][^"\']+["\']',
        f'__version__ = "{new_version}"',
        content
    )
    content = re.sub(
        r'COLLECTION_VERSION\s*=\s*__version__',
        'COLLECTION_VERSION = __version__',
        content
    )

    # Update MODULE_VERSION_ADDED (major.minor format)
    major, minor, patch = new_version.split('.')
    del patch  # Unused, but needed for unpacking
    module_version = f"{major}.{minor}.0"
    content = re.sub(
        r'MODULE_VERSION_ADDED\s*=\s*["\'][^"\']+["\']',
        f'MODULE_VERSION_ADDED = "{module_version}"',
        content
    )

    with open(version_file, 'w') as f:
        f.write(content)
    print(f"✅ Updated _version.py: {new_version}")


def update_galaxy_yml(new_version: str) -> None:
    """Update galaxy.yml with new version"""
    galaxy_file = COLLECTION_ROOT / "galaxy.yml"
    with open(galaxy_file, 'r') as f:
        data = yaml.safe_load(f)

    data['version'] = new_version

    with open(galaxy_file, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    print(f"✅ Updated galaxy.yml: {new_version}")


def update_changelog(new_version: str, old_version: str) -> None:
    """Add new version entry to CHANGELOG.md"""
    changelog_file = COLLECTION_ROOT / "CHANGELOG.md"
    with open(changelog_file, 'r') as f:
        content = f.read()

    # Get current date
    from datetime import date
    today = date.today().isoformat()

    # Create new changelog entry
    new_entry = f"""## [{new_version}] - {today}

### Added
- TBD

### Changed
- TBD

### Deprecated
- N/A

### Removed
- N/A

### Fixed
- TBD

### Security
- N/A

"""

    # Insert after the changelog header
    header_end = content.find("## [")
    if header_end == -1:
        # If no existing entries, insert after the header text
        header_end = content.find("Semantic Versioning")
        if header_end != -1:
            header_end = content.find("\n", header_end) + 1

    content = content[:header_end] + new_entry + content[header_end:]

    with open(changelog_file, 'w') as f:
        f.write(content)
    print(f"✅ Updated CHANGELOG.md: Added entry for {new_version}")


def update_module_version_added(new_version: str) -> None:
    """Update version_added in all module files"""
    # Extract major.minor from version (e.g., 25.12.2 -> 25.12.0)
    major, minor, patch = new_version.split('.')
    del patch  # Unused, but needed for unpacking
    module_version = f"{major}.{minor}.0"

    modules_dir = COLLECTION_ROOT / "plugins" / "modules"
    if not modules_dir.exists():
        print(f"⚠️  Warning: Modules directory not found: {modules_dir}")
        return

    module_files = list(modules_dir.glob("graphiant_*.py"))
    
    if not module_files:
        print(f"⚠️  Warning: No module files found in {modules_dir}")
        return

    updated_count = 0
    for module_file in module_files:
        with open(module_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check if version_added exists in the file
        if 'version_added' not in content:
            print(f"⚠️  Warning: {module_file.name} does not contain version_added field")
            continue

        # Update version_added in DOCUMENTATION section
        # Match: version_added: "25.11.0" or version_added: '25.11.0'
        old_content = content
        content = re.sub(
            r'version_added:\s*["\'][^"\']+["\']',
            f'version_added: "{module_version}"',
            content
        )

        # Only write if content changed
        if content != old_content:
            with open(module_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✅ Updated {module_file.name}: version_added = {module_version}")
            updated_count += 1
        else:
            print(f"ℹ️  {module_file.name}: version_added already set to {module_version}")

    if updated_count > 0:
        print(f"✅ Updated version_added in {updated_count} module(s)")
    else:
        print(f"ℹ️  No modules needed version_added updates")


def update_requirements_txt(dependency_updates: Optional[dict] = None) -> None:
    """Update requirements-ee.txt with new dependency versions (if needed)"""
    # Note: requirements-ee.txt doesn't have version pins, so this function
    # is kept for API compatibility but doesn't modify the file
    if dependency_updates:
        print("ℹ️  Note: requirements-ee.txt doesn't use version pins, skipping update")


def update_version_file_dependencies(dependency_updates: Optional[dict] = None) -> None:
    """Update dependency versions in _version.py"""
    if not dependency_updates:
        return

    version_file = COLLECTION_ROOT / "_version.py"
    with open(version_file, 'r') as f:
        content = f.read()

    for dep_name, dep_version in dependency_updates.items():
        # Update in DEPENDENCIES dict
        pattern = rf'["\']{re.escape(dep_name)}["\']:\s*["\'][^"\']+["\']'
        replacement = f'"{dep_name}": "{dep_version}"'
        content = re.sub(pattern, replacement, content)

    with open(version_file, 'w') as f:
        f.write(content)
    print("✅ Updated _version.py with dependency versions")


def bump_version(old_version: str, bump_type: str) -> str:
    """Calculate new version based on bump type"""
    major, minor, patch = map(int, old_version.split('.'))

    if bump_type == 'major':
        return f"{major + 1}.0.0"
    elif bump_type == 'minor':
        return f"{major}.{minor + 1}.0"
    elif bump_type == 'patch':
        return f"{major}.{minor}.{patch + 1}"
    else:
        # Assume it's a specific version
        if re.match(r'^\d+\.\d+\.\d+$', bump_type):
            return bump_type
        else:
            raise ValueError(f"Invalid version format: {bump_type}")


def parse_dependency_updates(args: list) -> dict:
    """Parse dependency update arguments (e.g., graphiant-sdk=25.12.0)"""
    updates = {}
    for arg in args:
        if '=' in arg:
            dep_name, dep_version = arg.split('=', 1)
            updates[dep_name] = dep_version
    return updates


def main():
    """Main function"""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    # Parse arguments
    bump_type = sys.argv[1]
    dependency_updates = parse_dependency_updates(sys.argv[2:]) if len(sys.argv) > 2 else {}

    # Load current version
    old_version = load_version()
    print(f"Current version: {old_version}")

    # Calculate new version
    if bump_type in ['major', 'minor', 'patch']:
        new_version = bump_version(old_version, bump_type)
    else:
        new_version = bump_type

    print(f"New version: {new_version}")
    print()

    # Update all files
    try:
        update_version_file(new_version)
        update_galaxy_yml(new_version)
        update_changelog(new_version, old_version)
        update_module_version_added(new_version)

        if dependency_updates:
            update_version_file_dependencies(dependency_updates)
            update_requirements_txt(dependency_updates)

        print()
        print("=" * 60)
        print("✅ Version bump completed successfully!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. Review the changes:")
        print("   git diff")
        print()
        print("2. Update CHANGELOG.md with actual changes")
        print()
        print("3. Commit the changes:")
        print("   git add -A")
        print(f"   git commit -m 'Bump version to {new_version}'")
        print()
        print("4. Create a git tag:")
        print(f"   git tag -a v{new_version} -m 'Release version {new_version}'")
        print()
        print("5. Push changes and tags:")
        print("   git push origin main")
        print(f"   git push origin v{new_version}")

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
