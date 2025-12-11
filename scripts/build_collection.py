#!/usr/bin/env python3
"""
Build script for Graphiant Ansible Collection

This script wraps ansible-galaxy collection build command.
It's the industry standard way to build Ansible collections.

Before building, ensure versions are up to date:
    python generate_requirements.py  # Sync requirements.txt from _version.py

Usage:
    python build_collection.py

Or directly use ansible-galaxy:
    cd ansible_collections/graphiant/graphiant_playbooks
    ansible-galaxy collection build .
"""

import subprocess
import sys
from pathlib import Path


def build_collection():
    """Build the Ansible collection using ansible-galaxy."""
    # Ensure requirements.txt is in sync with _version.py
    try:
        # Add scripts directory to path to import generate_requirements
        script_dir = Path(__file__).parent
        sys.path.insert(0, str(script_dir))
        from generate_requirements import generate_requirements_txt
        print("🔄 Syncing requirements.txt from _version.py...")
        generate_requirements_txt()
        print()
    except ImportError:
        print("⚠️  Warning: Could not sync requirements.txt (generate_requirements.py not found)")
        print()
    """Build the Ansible collection using ansible-galaxy."""
    print("🚀 Building Graphiant Ansible Collection")
    print("=" * 50)

    # Get the collection directory (scripts/ is at repo root, collection is in ansible_collections/graphiant/graphiant_playbooks)
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    collection_dir = repo_root / "ansible_collections" / "graphiant" / "graphiant_playbooks"

    # Create output directory at repo root
    output_dir = repo_root / "build"
    output_dir.mkdir(exist_ok=True)

    print(f"Collection directory: {collection_dir}")
    print(f"Output directory: {output_dir}")
    print()

    # Build the collection using ansible-galaxy
    cmd = [
        "ansible-galaxy",
        "collection",
        "build",
        str(collection_dir),
        "--output-path", str(output_dir),
        "--force"  # Overwrite existing archive
    ]

    print(f"Running: {' '.join(cmd)}")
    print()

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print(result.stderr)

        # Find the built tarball
        tarballs = list(output_dir.glob("graphiant-graphiant_playbooks-*.tar.gz"))
        if tarballs:
            tarball = tarballs[0]
            print(f"✅ Collection built successfully: {tarball}")
            print(f"📦 Collection size: {tarball.stat().st_size / 1024:.1f} KB")
            print()
            print("Next steps:")
            print()
            print("  📥 Install locally:")
            print(f"     ansible-galaxy collection install {tarball} --force")
            print()
            print("  ✅ Verify installation:")
            print("     ansible-galaxy collection list graphiant.graphiant_playbooks")
            print()
            print("  🚀 Publish to Ansible Galaxy:")
            print("     1. Get API token from: https://galaxy.ansible.com/ui/token/")
            print(f"     2. ansible-galaxy collection publish {tarball} --api-key=<YOUR_API_TOKEN>")
            print()
            print("     Or set token in environment:")
            print("        export ANSIBLE_GALAXY_TOKEN=<YOUR_API_TOKEN>")
            print(f"        ansible-galaxy collection publish {tarball}")
            return 0
        else:
            print("⚠️  Build completed but tarball not found")
            return 1

    except subprocess.CalledProcessError as e:
        print(f"❌ Build failed with exit code {e.returncode}")
        if e.stdout:
            print(e.stdout)
        if e.stderr:
            print(e.stderr)
        return e.returncode
    except FileNotFoundError:
        print("❌ ansible-galaxy command not found.")
        print("   Please ensure Ansible is installed: pip install ansible-core")
        return 1


if __name__ == '__main__':
    sys.exit(build_collection())
