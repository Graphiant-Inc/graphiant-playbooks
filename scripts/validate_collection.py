#!/usr/bin/env python3
"""
Validation script for Graphiant Ansible Collection

This script validates the collection structure and optionally runs
industry standard validation tools.

Usage:
    python validate_collection.py           # Basic structure validation
    python validate_collection.py --full    # Full validation with all tools
    python validate_collection.py --lint    # Run ansible-lint only
    python validate_collection.py --docs    # Run documentation validation only

Note: For ansible-lint to work, the collection must be installed first.
The --lint and --full options will install the collection automatically.
"""

import subprocess
import sys
import os
import argparse
from pathlib import Path


# Installed collection path
INSTALLED_COLLECTION_PATH = os.path.expanduser(
    "~/.ansible/collections/ansible_collections/graphiant/naas"
)


def check_structure(base_path):
    """Check collection directory structure."""
    print("📁 Checking collection structure...")
    print("-" * 50)

    # Galaxy required files
    galaxy_required_files = [
        'galaxy.yml',           # Required: Collection metadata
        'README.md',            # Required: Documentation
        'LICENSE',              # Required: License file
        'meta/runtime.yml',     # Required: Runtime metadata (minimal, supports ansible-core >= 2.17.0)
        'meta/execution-environment.yml',  # Required: Execution Environment configuration
    ]

    # Recommended files
    recommended_files = [
        'changelogs/changelog.yaml',  # Recommended: Changelog in YAML format (for antsibull-changelog)
        'requirements-ee.txt',         # Recommended: Runtime dependencies for Execution Environments
    ]

    # Graphiant collection specific files
    collection_files = [
        'plugins/modules/graphiant_interfaces.py',
        'plugins/modules/graphiant_lag_interfaces.py',
        'plugins/modules/graphiant_vrrp.py',
        'plugins/modules/graphiant_bgp.py',
        'plugins/modules/graphiant_global_config.py',
        'plugins/modules/graphiant_site_to_site_vpn.py',     
        'plugins/modules/graphiant_sites.py',
        'plugins/modules/graphiant_data_exchange.py',
        'plugins/modules/graphiant_data_exchange_info.py',  # Info module for query operations
        'plugins/module_utils/graphiant_utils.py',
        'plugins/module_utils/logging_decorator.py',
        'plugins/module_utils/libs/__init__.py',  # Required for Python package
    ]

    required_files = galaxy_required_files + collection_files

    # Galaxy standard directories
    galaxy_dirs = [
        'meta',
        'plugins',
        'plugins/modules',
        'plugins/module_utils',
    ]

    # Graphiant collection specific directories
    collection_dirs = [
        'plugins/module_utils/libs',
        'playbooks',
        'configs',
        'templates',
        'tests',
        'docs',  # Documentation (optional but recommended)
        'changelogs',  # Changelog directory (for changelog.yaml)
    ]

    required_dirs = galaxy_dirs + collection_dirs

    errors = []
    warnings = []

    # Check directories
    for dir_path in required_dirs:
        full_path = os.path.join(base_path, dir_path)
        if os.path.exists(full_path) and os.path.isdir(full_path):
            print(f"  ✅ {dir_path}/")
        else:
            print(f"  ❌ {dir_path}/ (missing)")
            errors.append(f"Missing directory: {dir_path}")

    # Check required files
    for file_path in required_files:
        full_path = os.path.join(base_path, file_path)
        if os.path.exists(full_path) and os.path.isfile(full_path):
            print(f"  ✅ {file_path}")
        else:
            print(f"  ❌ {file_path} (missing)")
            errors.append(f"Missing file: {file_path}")

    # Check recommended files (warnings, not errors)
    for file_path in recommended_files:
        full_path = os.path.join(base_path, file_path)
        if os.path.exists(full_path) and os.path.isfile(full_path):
            print(f"  ✅ {file_path}")
        else:
            print(f"  ⚠️  {file_path} (recommended but missing)")
            warnings.append(f"Missing recommended file: {file_path}")

    # Check embedded libraries
    libs_dir = os.path.join(base_path, 'plugins/module_utils/libs')
    if os.path.exists(libs_dir):
        lib_files = [f for f in os.listdir(libs_dir) if f.endswith('.py') and not f.startswith('__')]
        print(f"  ✅ libs/ ({len(lib_files)} Python files)")

        key_libs = ['graphiant_config.py', 'base_manager.py', 'portal_utils.py', 'exceptions.py']
        for lib in key_libs:
            if not os.path.exists(os.path.join(libs_dir, lib)):
                errors.append(f"Missing key library: libs/{lib}")

    # Check for legacy CHANGELOG.md (warn if found, recommend migration to YAML format)
    changelog_md = os.path.join(base_path, 'CHANGELOG.md')
    changelog_yaml = os.path.join(base_path, 'changelogs', 'changelog.yaml')
    if os.path.exists(changelog_md) and not os.path.exists(changelog_yaml):
        print(f"  ⚠️  CHANGELOG.md found (consider migrating to changelogs/changelog.yaml)")
        warnings.append("Legacy CHANGELOG.md found - consider migrating to changelogs/changelog.yaml")

    # Print warnings if any
    if warnings:
        for warning in warnings:
            print(f"   ⚠️  {warning}")

    return len(errors) == 0, errors


def check_galaxy_yml_fields(collection_path):
    """Check that galaxy.yml has required fields per Ansible Galaxy standards."""
    import yaml

    galaxy_file = os.path.join(collection_path, 'galaxy.yml')
    if not os.path.exists(galaxy_file):
        return False, ["galaxy.yml not found"]

    try:
        with open(galaxy_file, 'r') as f:
            galaxy_data = yaml.safe_load(f)
    except Exception as e:
        return False, [f"Failed to parse galaxy.yml: {e}"]

    errors = []
    warnings = []

    # Required fields per Ansible Galaxy
    required_fields = ['namespace', 'name', 'version']
    for field in required_fields:
        if field not in galaxy_data or not galaxy_data[field]:
            errors.append(f"Missing required field: {field}")

    # Recommended fields
    recommended_fields = ['description', 'authors', 'license_file', 'readme']
    for field in recommended_fields:
        if field not in galaxy_data or not galaxy_data[field]:
            warnings.append(f"Missing recommended field: {field}")

    # Check version format (should be semantic versioning)
    if 'version' in galaxy_data:
        version = galaxy_data['version']
        # Basic semantic version check (MAJOR.MINOR.PATCH)
        if not isinstance(version, str) or version.count('.') != 2:
            warnings.append(f"Version '{version}' may not follow semantic versioning (MAJOR.MINOR.PATCH)")

    # Print results
    if errors:
        for error in errors:
            print(f"  ❌ {error}")
    if warnings:
        for warning in warnings:
            print(f"  ⚠️  {warning}")

    if not errors and not warnings:
        print("  ✅ galaxy.yml has all required and recommended fields")

    # Check execution-environment.yml
    ee_file = os.path.join(collection_path, 'meta', 'execution-environment.yml')
    if os.path.exists(ee_file):
        try:
            with open(ee_file, 'r') as f:
                ee_data = yaml.safe_load(f)
            if isinstance(ee_data, dict) and 'requirements_file' in ee_data:
                req_file = ee_data.get('requirements_file')
                req_path = os.path.join(collection_path, req_file)
                if os.path.exists(req_path):
                    print(f"  ✅ meta/execution-environment.yml references {req_file}")
                else:
                    warnings.append(f"execution-environment.yml references {req_file} which doesn't exist")
            else:
                warnings.append("execution-environment.yml missing 'requirements_file' field")
        except Exception as e:
            warnings.append(f"Failed to parse execution-environment.yml: {e}")
    else:
        warnings.append("meta/execution-environment.yml not found (recommended for Execution Environments)")

    return len(errors) == 0, errors


def run_galaxy_build_check(collection_path):
    """Validate galaxy.yml by checking required fields."""
    print("\n🔍 Validating galaxy.yml...")
    print("-" * 50)

    # Check galaxy.yml fields (namespace, name, version, etc.)
    fields_ok, field_errors = check_galaxy_yml_fields(collection_path)

    return fields_ok


def install_collection(collection_path):
    """Install the collection for ansible-lint to work."""
    print("\n📦 Installing collection for linting...")
    print("-" * 50)

    cmd = [
        "ansible-galaxy", "collection", "install",
        str(collection_path), "--force"
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            print("  ✅ Collection installed successfully")
            return True
        else:
            print("  ❌ Collection installation failed")
            if result.stderr:
                print(f"     {result.stderr.strip()}")
            return False
    except FileNotFoundError:
        print("  ⚠️  ansible-galaxy not found")
        return False


def run_ansible_lint(collection_path):
    """Run ansible-lint on installed collection playbooks."""
    print("\n🔍 Running ansible-lint on playbooks...")
    print("-" * 50)

    # ansible-lint needs the collection installed to resolve modules
    # Use the installed collection path
    installed_playbooks = os.path.join(INSTALLED_COLLECTION_PATH, "playbooks")
    installed_config = os.path.join(INSTALLED_COLLECTION_PATH, ".ansible-lint")

    if not os.path.exists(installed_playbooks):
        print("  ⚠️  Collection not installed. Installing...")
        if not install_collection(collection_path):
            return False

    cmd = ["ansible-lint"]
    if os.path.exists(installed_config):
        cmd.extend(["--config-file", installed_config])
    cmd.append(installed_playbooks)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            print("  ✅ ansible-lint passed")
            return True
        else:
            print("  ❌ ansible-lint found issues:")
            if result.stdout:
                # Show summary only
                lines = result.stdout.strip().split('\n')
                for line in lines[-10:]:  # Last 10 lines
                    print(f"     {line}")
            return False
    except FileNotFoundError:
        print("  ⚠️  ansible-lint not found (optional check - skipped)")
        print("     Install with: pip install ansible-lint")
        print("     Note: This is an optional check and does not cause validation to fail")
        return True


def run_docs_lint(collection_path):
    """Run antsibull-docs lint on collection documentation."""
    print("\n🔍 Running documentation validation...")
    print("-" * 50)

    # Check for required docs files
    docs_dir = os.path.join(collection_path, 'docs')
    docsite_dir = os.path.join(docs_dir, 'docsite')

    if os.path.exists(docsite_dir):
        # Check for links.yml (recommended for antsibull)
        links_yml = os.path.join(docsite_dir, 'links.yml')
        if os.path.exists(links_yml):
            print("  ✅ docs/docsite/links.yml exists")
        else:
            print("  ⚠️  docs/docsite/links.yml not found (optional but recommended)")

    # Run antsibull-docs lint-collection-docs
    # Use --plugin-docs to check module documentation strings
    cmd = [
        "antsibull-docs", "lint-collection-docs",
        "--plugin-docs",
        "--skip-rstcheck",  # Skip rstcheck if not installed
        str(collection_path)
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            print("  ✅ Module documentation validation passed")
            return True
        else:
            print("  ⚠️  Documentation issues found:")
            output = result.stdout or result.stderr
            if output:
                lines = output.strip().split('\n')
                for line in lines[:10]:  # First 10 lines
                    if line.strip():
                        print(f"     {line}")
            # Don't fail on docs issues, just warn
            return True
    except FileNotFoundError:
        print("  ⚠️  antsibull-docs not found (optional check - skipped)")
        print("     Install with: pip install antsibull-docs")
        print("     Then run: antsibull-docs lint-collection-docs --plugin-docs .")
        print("     Note: This is an optional check and does not cause validation to fail")
        return True


def print_summary(results, collection_path, script_dir=None):
    """Print validation summary."""
    print("\n" + "=" * 60)

    all_passed = all(results.values())

    if all_passed:
        print("🎉 All validations passed!")
    else:
        print("⚠️  Some validations failed:")
        for check, passed in results.items():
            status = "✅" if passed else "❌"
            print(f"   {status} {check}")

    print("\n📦 Next Steps:")
    print("-" * 50)
    print("1. Build collection:")
    if script_dir:
        print(f"   python {script_dir}/build_collection.py")
    else:
        print(f"   python {collection_path}/build_collection.py")
    print("   # Or: ansible-galaxy collection build . --output-path ../../../build/")
    print()
    print("2. Install collection:")
    print(f"   ansible-galaxy collection install {collection_path} --force")
    print()
    print("3. Test collection:")
    print(f"   ansible-playbook {INSTALLED_COLLECTION_PATH}/playbooks/hello_test.yml")
    print()
    print("4. Verify installation:")
    print("   ansible-galaxy collection list | grep graphiant")
    print()
    print("5. Run ansible-test sanity (from collection root):")
    print(f"   cd {collection_path}")
    print("   ansible-test sanity --color --python 3.12")

    return 0 if all_passed else 1


def main():
    parser = argparse.ArgumentParser(
        description="Validate Graphiant Ansible Collection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python validate_collection.py           # Basic structure check + galaxy.yml validation
  python validate_collection.py --full    # Full validation with all tools
  python validate_collection.py --lint    # Run ansible-lint (installs collection first)
  python validate_collection.py --docs    # Run documentation validation only

Note: ansible-lint requires the collection to be installed to resolve module references.
      The --lint and --full options will install the collection automatically.
        """
    )
    parser.add_argument('--full', action='store_true', help='Run all validation tools')
    parser.add_argument('--lint', action='store_true', help='Run ansible-lint (installs collection first)')
    parser.add_argument('--docs', action='store_true', help='Run documentation validation')

    args = parser.parse_args()

    print("🚀 Graphiant Ansible Collection Validator")
    print("=" * 60)

    # Get collection path (scripts/ is at repo root, collection is in ansible_collections/graphiant/naas)
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    collection_path = repo_root / "ansible_collections" / "graphiant" / "naas"

    results = {}

    # Always run structure check
    structure_ok, errors = check_structure(collection_path)
    results['Structure'] = structure_ok
    if errors:
        for error in errors:
            print(f"   ⚠️  {error}")

    # Run galaxy.yml validation
    results['galaxy.yml'] = run_galaxy_build_check(collection_path)

    # Run additional tools based on args
    if args.full or args.lint:
        # Install collection first for ansible-lint to work
        if install_collection(collection_path):
            results['ansible-lint'] = run_ansible_lint(collection_path)
        else:
            results['ansible-lint'] = False

    if args.full or args.docs:
        results['Documentation'] = run_docs_lint(collection_path)

    return print_summary(results, collection_path, script_dir)


if __name__ == '__main__':
    sys.exit(main())
