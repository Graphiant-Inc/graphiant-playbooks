#!/usr/bin/env python3
"""
Check Ansible Inclusion Checklist compliance

This script validates that the collection adheres to the requirements
listed in ANSIBLE_INCLUSION_CHECKLIST.md.

Usage:
    python scripts/check_inclusion_checklist.py
    python scripts/check_inclusion_checklist.py --strict  # Exit with error on failures
"""

import re
import sys
import yaml
from pathlib import Path
from typing import Dict, List, Tuple

# Collection root directory
COLLECTION_ROOT = Path(__file__).parent.parent / "ansible_collections" / "graphiant" / "naas"
COLLECTION_MODULES_DIR = COLLECTION_ROOT / "plugins" / "modules"
REPO_ROOT = Path(__file__).parent.parent

# Matches a check_mode block where "changed = True" is assigned at the same indentation scope.
# This helps detect modules that claim full check_mode support but always report changed=True.
CHECK_MODE_ALWAYS_CHANGED_PATTERN = (
    r"(?m)^([ \t]*)if\s+module\.check_mode:\s*(?:#.*)?\n"
    r"(?:\1[ \t]+.*\n)*?\1[ \t]+changed\s*=\s*True\b"
)


def find_module_references_in_doc(text: str, module_name: str) -> List[Tuple[int, str, str]]:
    """Find references to modules in DOCUMENTATION text that don't use M() with FQCN."""
    issues: List[Tuple[int, str, str]] = []

    lines = text.split("\n")
    in_documentation = False
    in_return = False
    in_seealso = False

    for line_num, line in enumerate(lines, 1):
        # Track if we're in DOCUMENTATION section
        if "DOCUMENTATION =" in line or "DOCUMENTATION = r'''" in line:
            in_documentation = True
            in_return = False
            in_seealso = False
            continue
        if in_documentation and line.strip().startswith("EXAMPLES ="):
            break
        if "RETURN =" in line or "RETURN = r'''" in line:
            in_return = True
            in_seealso = False
            continue
        if "seealso:" in line.lower():
            in_seealso = True
            continue
        if in_seealso and line.strip() and not line.strip().startswith("-") and not line.strip().startswith("module:"):
            in_seealso = False

        if in_documentation and not in_return and not in_seealso:
            # Skip RETURN and seealso sections - module references there are in YAML format
            # We're looking for module references in notes, description text, etc.

            # Skip YAML list items in seealso (they start with - module:)
            if line.strip().startswith("- module:"):
                continue

            # Pattern 1: C(module_name) - should be M(graphiant.naas.module_name)
            if re.search(rf"C\(({module_name})\)", line, re.IGNORECASE):
                if f"M(graphiant.naas.{module_name})" not in line:
                    issues.append((line_num, line.strip(), f"C({module_name})"))

            # Pattern 2: Direct module name in documentation text (not in YAML keys)
            if re.search(rf"\b({module_name})\b", line, re.IGNORECASE):
                # Skip if it's a YAML key, in seealso section, or a YAML list item
                if (
                    not re.match(rf"^\s*{module_name}\s*:", line)
                    and not in_seealso
                    and not line.strip().startswith("- module:")
                ):
                    # Check if it's in a context that suggests it's a module reference
                    doc_keywords = (
                        "module",
                        "using",
                        "created",
                        "before",
                        "after",
                        "must",
                        "should",
                        "see",
                    )
                    if (
                        f"M(graphiant.naas.{module_name})" not in line
                        and f"M(ansible.builtin.{module_name})" not in line
                        and any(keyword in line.lower() for keyword in doc_keywords)
                    ):
                        # Make sure it's not already properly formatted
                        if "M(" not in line and "C(" not in line:
                            issues.append((line_num, line.strip(), module_name))

    return issues


def check_module_references_in_documentation() -> Dict[str, List[Tuple[int, str, str]]]:
    """Check all modules for proper M() FQCN usage in DOCUMENTATION sections."""
    issues: Dict[str, List[Tuple[int, str, str]]] = {}

    if not COLLECTION_MODULES_DIR.exists():
        print(f"❌ Error: Collection modules directory not found: {COLLECTION_MODULES_DIR}")
        return issues

    module_files = list(COLLECTION_MODULES_DIR.glob("graphiant_*.py"))
    module_names = [
        "graphiant_backbone",
        "graphiant_bgp",
        "graphiant_data_exchange",
        "graphiant_data_exchange_info",
        "graphiant_device_config",
        "graphiant_device_system",
        "graphiant_edge_services",
        "graphiant_macsec",
        "graphiant_macsec_info",
        "graphiant_global_config",
        "graphiant_interfaces",
        "graphiant_sites",
        "graphiant_vrrp",
        "graphiant_lag_interfaces",
        "graphiant_site_to_site_vpn",
        "graphiant_static_routes",
        "graphiant_ntp",
    ]

    for module_file in module_files:
        module_name = module_file.stem
        try:
            content = module_file.read_text(encoding="utf-8")
            for ref_module in module_names:
                if ref_module == module_name:
                    continue
                ref_issues = find_module_references_in_doc(content, ref_module)
                if ref_issues:
                    if module_name not in issues:
                        issues[module_name] = []
                    for line_num, line, match in ref_issues:
                        issues[module_name].append((line_num, line, match))
        except Exception as e:
            print(f"⚠️  Warning: Could not check {module_file.name}: {e}")

    return issues


def check_builtin_modules_fqcn() -> Dict[str, List[Tuple[int, str]]]:
    """Check that all builtin modules use ansible.builtin.* FQCN."""
    issues: Dict[str, List[Tuple[int, str]]] = {}

    if not COLLECTION_MODULES_DIR.exists():
        return issues

    module_files = list(COLLECTION_MODULES_DIR.glob("graphiant_*.py"))
    builtin_modules = [
        "debug",
        "copy",
        "file",
        "template",
        "lineinfile",
        "blockinfile",
        "replace",
        "set_fact",
        "assert",
        "fail",
        "include_vars",
        "uri",
        "get_url",
        "stat",
        "shell",
        "command",
    ]

    for module_file in module_files:
        module_name = module_file.stem
        try:
            content = module_file.read_text(encoding="utf-8")
            lines = content.split("\n")
            in_examples = False

            for line_num, line in enumerate(lines, 1):
                if "EXAMPLES =" in line or "EXAMPLES = r'''" in line:
                    in_examples = True
                    continue
                if in_examples and ("RETURN =" in line or line.strip().startswith("RETURN =")):
                    break

                if in_examples:
                    for builtin in builtin_modules:
                        pattern = rf"^\s+{builtin}:"
                        if re.match(pattern, line) and "ansible.builtin" not in line:
                            if module_name not in issues:
                                issues[module_name] = []
                            issues[module_name].append((line_num, line.strip()))
        except Exception as e:
            print(f"⚠️  Warning: Could not check {module_file.name}: {e}")

    return issues


def check_semantic_markup() -> Dict[str, List[Tuple[int, str, str]]]:
    """Check semantic markup usage (V/O/M/C/I/RV)."""
    issues: Dict[str, List[Tuple[int, str, str]]] = {}

    if not COLLECTION_MODULES_DIR.exists():
        return issues

    module_files = list(COLLECTION_MODULES_DIR.glob("graphiant_*.py"))

    for module_file in module_files:
        module_name = module_file.stem
        try:
            content = module_file.read_text(encoding="utf-8")
            lines = content.split("\n")
            in_documentation = False

            for line_num, line in enumerate(lines, 1):
                if "DOCUMENTATION =" in line or "DOCUMENTATION = r'''" in line:
                    in_documentation = True
                    continue
                if in_documentation and line.strip().startswith("EXAMPLES ="):
                    break

                if in_documentation:
                    # Check for option values that should use V()
                    # Look for patterns like "configure", "present", "true", "false" in description
                    if re.search(
                        r"\b(configure|deconfigure|present|absent|true|false|yes|no)\b",
                        line,
                        re.IGNORECASE,
                    ):
                        # Skip if already using V() or in certain contexts
                        if "V(" not in line and "choices:" not in line.lower() and "type:" not in line.lower():
                            # Check if it's describing an option value
                            if any(keyword in line.lower() for keyword in ["maps to", "one of", "value", "option"]):
                                if module_name not in issues:
                                    issues[module_name] = []
                                issues[module_name].append(
                                    (line_num, line.strip(), "Option value should use V() markup")
                                )
        except Exception as e:
            print(f"⚠️  Warning: Could not check {module_file.name}: {e}")

    return issues


def check_check_mode_attributes() -> Dict[str, List[str]]:
    """Check that all modules have check_mode support information in attributes."""
    issues: Dict[str, List[str]] = {}

    if not COLLECTION_MODULES_DIR.exists():
        return issues

    module_files = list(COLLECTION_MODULES_DIR.glob("graphiant_*.py"))

    for module_file in module_files:
        module_name = module_file.stem
        try:
            content = module_file.read_text(encoding="utf-8")

            # Check for attributes section
            documentation_match = re.search(r"DOCUMENTATION\s*=\s*r?([\"']{3})(.*?)\1", content, re.DOTALL)
            if not documentation_match:
                issues[module_name] = ["Missing DOCUMENTATION section"]
                continue
            try:
                documentation_yaml = yaml.safe_load(documentation_match.group(2)) or {}
            except yaml.YAMLError:
                issues[module_name] = ["Invalid DOCUMENTATION YAML format"]
                continue
            attributes = documentation_yaml.get("attributes")
            if not isinstance(attributes, dict):
                issues[module_name] = ["Missing attributes: section"]
                continue

            # Check for check_mode in attributes
            check_mode = attributes.get("check_mode")
            if not isinstance(check_mode, dict):
                issues[module_name] = ["Missing check_mode: information in attributes section"]
                continue

            # Verify it has support information
            support_value = check_mode.get("support")
            if not isinstance(support_value, str):
                if module_name not in issues:
                    issues[module_name] = []
                issues[module_name].append("check_mode: section missing support: information")
            else:
                support_level = support_value.lower()
                if support_level in {"full", "partial", "none"}:
                    # Validate support level appropriateness
                    # _info modules should have full support (read-only)
                    if module_name.endswith("_info"):
                        if support_level != "full":
                            if module_name not in issues:
                                issues[module_name] = []
                            issues[module_name].append(
                                "_info module should have support: full (read-only), " f"found: {support_level}"
                            )

                    # State-changing modules should not claim full support if they always return changed=True
                    if support_level == "full" and not module_name.endswith("_info"):
                        if re.search(CHECK_MODE_ALWAYS_CHANGED_PATTERN, content):
                            if module_name not in issues:
                                issues[module_name] = []
                            issues[module_name].append(
                                "Module claims support: full but always returns changed=True "
                                "in check mode. Should be support: partial"
                            )
        except Exception as e:
            print(f"⚠️  Warning: Could not check {module_file.name}: {e}")

    return issues


def check_check_mode_behavior() -> Dict[str, List[str]]:
    """Check check mode behavior compliance - should not always return changed=True."""
    issues: Dict[str, List[str]] = {}

    if not COLLECTION_MODULES_DIR.exists():
        return issues

    module_files = list(COLLECTION_MODULES_DIR.glob("graphiant_*.py"))

    for module_file in module_files:
        module_name = module_file.stem
        try:
            content = module_file.read_text(encoding="utf-8")

            # Skip _info modules and modules that don't support check mode
            if module_name.endswith("_info") or "support: none" in content:
                continue

            # Check if module has check mode handling
            if "if module.check_mode:" in content or "if module.check_mode" in content:
                # Look for patterns that always return changed=True
                # Pattern 1: Direct changed=True assignment
                check_mode_blocks = re.findall(
                    r"if\s+module\.check_mode:.*?module\.exit_json\([^)]*\)",
                    content,
                    re.DOTALL | re.MULTILINE,
                )

                for block in check_mode_blocks:
                    # Check if it always sets changed=True without conditions
                    if "changed=True" in block or "changed: True" in block:
                        # Check if there's any conditional logic for changed
                        has_conditional_logic = re.search(r"^\s*(if|elif)\s+.+:", block, re.MULTILINE) is not None
                        if not has_conditional_logic:
                            # Check if it's graphiant_device_config with show_validated_payload handling
                            if module_name == "graphiant_device_config" and "show_validated_payload" in block:
                                # This is OK - it has special handling
                                continue

                            # Check if documentation explains the limitation
                            documentation_patterns = (
                                r"assum(?:e|es|ed)\s+changes?",
                                r"cannot\s+determin(?:e|ed|ing)",
                                r"unable\s+to\s+determin(?:e|ed|ing)",
                                r"check\s*mode.*(?:may|might)\s+report\s+changed",
                                r"check\s*mode.*(?:cannot|unable).*(?:determin|verify)",
                            )
                            has_documented_limitation = any(
                                re.search(pattern, content, re.IGNORECASE)
                                for pattern in documentation_patterns
                            )
                            if not has_documented_limitation:
                                if module_name not in issues:
                                    issues[module_name] = []
                                issues[module_name].append(
                                    "Check mode always returns changed=True without documenting "
                                    "limitation. Should document that changes are assumed."
                                )
        except Exception as e:
            print(f"⚠️  Warning: Could not check {module_file.name}: {e}")

    return issues


def check_module_naming() -> Dict[str, List[str]]:
    """Check module naming conventions (_info, _facts)."""
    issues: Dict[str, List[str]] = {}

    if not COLLECTION_MODULES_DIR.exists():
        return issues

    module_files = list(COLLECTION_MODULES_DIR.glob("graphiant_*.py"))

    for module_file in module_files:
        module_name = module_file.stem
        try:
            content = module_file.read_text(encoding="utf-8")

            # Check if _info modules only gather information
            if module_name.endswith("_info"):
                # Parse DOCUMENTATION YAML and inspect the actual state option structure.
                doc_match = re.search(
                    r"DOCUMENTATION\s*=\s*r?([\"']{3})(.*?)\1",
                    content,
                    re.DOTALL,
                )
                if doc_match:
                    try:
                        doc_data = yaml.safe_load(doc_match.group(2)) or {}
                        state_option = ((doc_data.get("options") or {}).get("state") or {})
                        choices = state_option.get("choices") or []
                        default = state_option.get("default")
                        normalized_choices = {
                            choice.lower() for choice in choices if isinstance(choice, str)
                        }
                        normalized_default = default.lower() if isinstance(default, str) else None
                        state_changing_ops = {"configure", "deconfigure", "create", "delete"}
                        query_ops = {"query", "get"}
                        has_state_change = bool(normalized_choices & state_changing_ops) or (
                            normalized_default in state_changing_ops
                        )
                        has_query_get = bool(normalized_choices & query_ops) or (
                            normalized_default in query_ops
                        )

                        if has_state_change and not has_query_get:
                            if module_name not in issues:
                                issues[module_name] = []
                            issues[module_name].append(
                                "_info module should only gather information, " "not perform state changes"
                            )
                    except yaml.YAMLError:
                        # If DOCUMENTATION cannot be parsed, skip this specific structural check.
                        pass

            # Check if state-changing modules have query operations
            if not module_name.endswith("_info") and not module_name.endswith("_facts"):
                # Parse DOCUMENTATION YAML and inspect the actual state option structure.
                doc_match = re.search(
                    r"DOCUMENTATION\s*=\s*r?([\"']{3})(.*?)\1",
                    content,
                    re.DOTALL,
                )
                if doc_match:
                    try:
                        doc_data = yaml.safe_load(doc_match.group(2)) or {}
                        state_option = ((doc_data.get("options") or {}).get("state") or {})
                        choices = state_option.get("choices") or []
                        default = state_option.get("default")
                        has_query_get = any(
                            isinstance(choice, str) and choice.lower() in {"query", "get"}
                            for choice in choices
                        ) or (isinstance(default, str) and default.lower() in {"query", "get"})
                        if has_query_get:
                            if module_name not in issues:
                                issues[module_name] = []
                            issues[module_name].append(
                                "State-changing modules should not have query/get operations "
                                "(use _info module instead)"
                            )
                    except yaml.YAMLError:
                        # If DOCUMENTATION cannot be parsed, skip this specific structural check.
                        pass
        except Exception as e:
            print(f"⚠️  Warning: Could not check {module_file.name}: {e}")

    return issues


def check_python_version() -> Dict[str, List[str]]:
    """Check Python version requirements."""
    issues: Dict[str, List[str]] = {}

    if not COLLECTION_MODULES_DIR.exists():
        return issues

    module_files = list(COLLECTION_MODULES_DIR.glob("graphiant_*.py"))

    for module_file in module_files:
        module_name = module_file.stem
        try:
            content = module_file.read_text(encoding="utf-8")

            # Check for python requirement
            if "requirements:" not in content:
                if module_name not in issues:
                    issues[module_name] = []
                issues[module_name].append("Missing requirements: section")
                continue

            # Check python version
            if not re.search(r"\bpython\s*>=\s*3\.7\b", content, re.IGNORECASE):
                if module_name not in issues:
                    issues[module_name] = []
                issues[module_name].append("Python requirement should be >= 3.7")
        except Exception as e:
            print(f"⚠️  Warning: Could not check {module_file.name}: {e}")

    return issues


def check_license_headers() -> Dict[str, List[str]]:
    """Check that all modules have GPLv3 license headers."""
    issues: Dict[str, List[str]] = {}

    if not COLLECTION_MODULES_DIR.exists():
        return issues

    module_files = list(COLLECTION_MODULES_DIR.glob("graphiant_*.py"))

    for module_file in module_files:
        module_name = module_file.stem
        try:
            content = module_file.read_text(encoding="utf-8")

            # Check for GPL license header (full name or SPDX/identifier forms)
            has_gpl_header = any(
                re.search(pattern, content, re.IGNORECASE)
                for pattern in (
                    r"\bGNU\s+General\s+Public\s+License\b",
                    r"\bSPDX-License-Identifier:\s*GPL-[0-9](?:\.[0-9])?(?:-only|-or-later)?\b",
                    r"\bGPLv?3(?:\.[0-9])?\b",
                )
            )
            if not has_gpl_header:
                if module_name not in issues:
                    issues[module_name] = []
                issues[module_name].append("Missing GPLv3 license header")
        except Exception as e:
            print(f"⚠️  Warning: Could not check {module_file.name}: {e}")

    return issues


def check_version_added() -> Dict[str, List[str]]:
    """Check that all modules have version_added."""
    issues: Dict[str, List[str]] = {}

    if not COLLECTION_MODULES_DIR.exists():
        return issues

    module_files = list(COLLECTION_MODULES_DIR.glob("graphiant_*.py"))

    for module_file in module_files:
        module_name = module_file.stem
        try:
            content = module_file.read_text(encoding="utf-8")

            # Check for version_added
            if "version_added:" not in content:
                if module_name not in issues:
                    issues[module_name] = []
                issues[module_name].append("Missing version_added: field")
        except Exception as e:
            print(f"⚠️  Warning: Could not check {module_file.name}: {e}")

    return issues


def check_collection_structure() -> List[str]:
    """Check required collection structure files."""
    issues = []

    required_files = {
        "galaxy.yml": COLLECTION_ROOT / "galaxy.yml",
        "README.md": COLLECTION_ROOT / "README.md",
        "LICENSE": COLLECTION_ROOT / "LICENSE",
        "meta/runtime.yml": COLLECTION_ROOT / "meta" / "runtime.yml",
        "meta/execution-environment.yml": COLLECTION_ROOT / "meta" / "execution-environment.yml",
    }

    for file_name, file_path in required_files.items():
        if not file_path.exists():
            issues.append(f"Missing required file: {file_name}")

    return issues


# Ansible C() markup must not appear in changelog; use RST double backticks for literals.
# See https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html#inline-markup
ANSIBLE_C_MARKUP_IN_CHANGELOG = re.compile(r"\bC\s*\(\s*[^)\s][^)]*\)")


def _collect_changelog_entries(data: dict) -> List[Tuple[str, str]]:
    """Collect (release_version, entry_text) from changelog.yaml releases."""
    entries = []
    releases = data.get("releases") or {}
    for version, release_data in releases.items():
        if not isinstance(release_data, dict):
            continue
        changes = release_data.get("changes") or {}
        for _category, items in changes.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, str):
                    entries.append((str(version), item))
    return entries


def _validate_changelog_entry_rst(version: str, entry: str) -> List[str]:
    """
    Validate that a changelog entry uses RST inline markup, not Ansible markup.
    Per Ansible inclusion feedback and Sphinx RST:
    - Use double backticks for literals: ``module_name``, ``path/to/file``.
    - Do not use Ansible markup (C(), M(), O(), etc.); it renders verbatim.
    """
    issues = []
    # Check for Ansible C() markup (invalid in changelog; use RST ``literal``)
    if ANSIBLE_C_MARKUP_IN_CHANGELOG.search(entry):
        issues.append(
            f"Release {version}: entry uses Ansible markup C(...); "
            "changelog must be valid RST — use double backticks for literals (e.g. ``name``). "
            "See https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html#inline-markup"
        )
    return issues


def check_changelog_rst(changelog_path: Path) -> List[str]:
    """
    Validate changelog.yaml entries use RST format (no Ansible markup).
    Entry text must be valid reStructuredText; use ``literal`` for modules, files, commands.
    """
    issues = []
    try:
        content = changelog_path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
    except Exception as e:
        issues.append(f"Could not load changelog.yaml: {e}")
        return issues
    if not data or not isinstance(data, dict):
        return issues
    for version, entry in _collect_changelog_entries(data):
        issues.extend(_validate_changelog_entry_rst(version, entry))
    return issues


def check_changelog() -> List[str]:
    """Check changelog format and RST compliance of entries."""
    issues = []

    changelog_yaml = COLLECTION_ROOT / "changelogs" / "changelog.yaml"
    if not changelog_yaml.exists():
        issues.append("changelogs/changelog.yaml not found (recommended format)")
        return issues

    # Validate that entry text uses RST, not Ansible markup (per Ansible inclusion)
    rst_issues = check_changelog_rst(changelog_yaml)
    issues.extend(rst_issues)

    return issues


def main():
    """Main validation function."""
    print("🔍 Checking Ansible Inclusion Checklist compliance...")
    print("=" * 70)

    errors = []
    warnings = []

    # Check 1: Module references in DOCUMENTATION
    print("\n1. Checking module references in DOCUMENTATION sections...")
    doc_issues = check_module_references_in_documentation()
    if doc_issues:
        print("   ❌ Found module references not using M() with FQCN:")
        for module, issues_list in doc_issues.items():
            print(f"\n   📄 {module}.py:")
            for line_num, line, match in issues_list:
                print(f"      Line {line_num}: {line[:80]}")
                errors.append(f"{module}.py: Line {line_num} - Module reference should use M() with FQCN")
    else:
        print("   ✅ All module references in DOCUMENTATION use M() with FQCN")

    # Check 2: Builtin modules FQCN
    print("\n2. Checking builtin modules use FQCN in EXAMPLES...")
    builtin_issues = check_builtin_modules_fqcn()
    if builtin_issues:
        print("   ❌ Found builtin modules not using FQCN:")
        for module, issues_list in builtin_issues.items():
            print(f"\n   📄 {module}.py:")
            for line_num, line in issues_list:
                print(f"      Line {line_num}: {line[:80]}")
                errors.append(f"{module}.py: Line {line_num} - Builtin module should use ansible.builtin.* FQCN")
    else:
        print("   ✅ All builtin modules use FQCN in EXAMPLES")

    # Check 3: Check mode attributes
    print("\n3. Checking check_mode support information in attributes...")
    check_mode_issues = check_check_mode_attributes()
    if check_mode_issues:
        print("   ❌ Found modules missing check_mode information:")
        for module, issues_list in check_mode_issues.items():
            print(f"\n   📄 {module}.py:")
            for issue in issues_list:
                print(f"      - {issue}")
                errors.append(f"{module}.py: {issue}")
    else:
        print("   ✅ All modules have check_mode support information")

    # Check 3.5: Check mode behavior compliance
    print("\n3.5. Checking check_mode behavior compliance...")
    check_mode_behavior_issues = check_check_mode_behavior()
    if check_mode_behavior_issues:
        print("   ⚠️  Found check_mode behavior issues:")
        for module, issues_list in check_mode_behavior_issues.items():
            print(f"\n   📄 {module}.py:")
            for issue in issues_list:
                print(f"      - {issue}")
                warnings.append(f"{module}.py: {issue}")
    else:
        print("   ✅ All modules comply with check_mode best practices")

    # Check 4: Module naming
    print("\n4. Checking module naming conventions...")
    naming_issues = check_module_naming()
    if naming_issues:
        print("   ⚠️  Found module naming issues:")
        for module, issues_list in naming_issues.items():
            print(f"\n   📄 {module}.py:")
            for issue in issues_list:
                print(f"      - {issue}")
                warnings.append(f"{module}.py: {issue}")
    else:
        print("   ✅ Module naming conventions are correct")

    # Check 5: Python version
    print("\n5. Checking Python version requirements...")
    python_issues = check_python_version()
    if python_issues:
        print("   ❌ Found Python version issues:")
        for module, issues_list in python_issues.items():
            print(f"\n   📄 {module}.py:")
            for issue in issues_list:
                print(f"      - {issue}")
                errors.append(f"{module}.py: {issue}")
    else:
        print("   ✅ All modules specify Python >= 3.7")

    # Check 6: License headers
    print("\n6. Checking license headers...")
    license_issues = check_license_headers()
    if license_issues:
        print("   ❌ Found modules missing license headers:")
        for module, issues_list in license_issues.items():
            print(f"\n   📄 {module}.py:")
            for issue in issues_list:
                print(f"      - {issue}")
                errors.append(f"{module}.py: {issue}")
    else:
        print("   ✅ All modules have GPLv3 license headers")

    # Check 7: version_added
    print("\n7. Checking version_added fields...")
    version_issues = check_version_added()
    if version_issues:
        print("   ❌ Found modules missing version_added:")
        for module, issues_list in version_issues.items():
            print(f"\n   📄 {module}.py:")
            for issue in issues_list:
                print(f"      - {issue}")
                errors.append(f"{module}.py: {issue}")
    else:
        print("   ✅ All modules have version_added field")

    # Check 8: Collection structure
    print("\n8. Checking collection structure files...")
    structure_issues = check_collection_structure()
    if structure_issues:
        print("   ❌ Found missing required files:")
        for issue in structure_issues:
            print(f"      - {issue}")
            errors.append(issue)
    else:
        print("   ✅ All required collection structure files exist")

    # Check 9: Changelog
    print("\n9. Checking changelog...")
    changelog_issues = check_changelog()
    if changelog_issues:
        print("   ⚠️  Changelog recommendations:")
        for issue in changelog_issues:
            print(f"      - {issue}")
            warnings.append(issue)
    else:
        print("   ✅ changelogs/changelog.yaml exists")

    # Summary
    print("\n" + "=" * 70)
    if errors:
        print(f"\n❌ Found {len(errors)} error(s) that need to be fixed:")
        for error in errors[:15]:  # Show first 15
            print(f"   - {error}")
        if len(errors) > 15:
            print(f"   ... and {len(errors) - 15} more")
    if warnings:
        print(f"\n⚠️  Found {len(warnings)} warning(s):")
        for warning in warnings[:10]:  # Show first 10
            print(f"   - {warning}")
        if len(warnings) > 10:
            print(f"   ... and {len(warnings) - 10} more")

    if errors:
        print("\n💡 Please review ANSIBLE_INCLUSION_CHECKLIST.md for requirements.")
        if "--strict" in sys.argv:
            sys.exit(1)
        else:
            print("⚠️  Run with --strict to exit with error code on failures.")
            sys.exit(0)
    elif warnings:
        print("\n✅ All critical checks passed! Some warnings were found.")
        sys.exit(0)
    else:
        print("\n✅ All checks passed! Collection complies with Ansible Inclusion Checklist.")
        sys.exit(0)


if __name__ == "__main__":
    main()
