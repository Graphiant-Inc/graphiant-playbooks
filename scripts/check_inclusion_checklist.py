#!/usr/bin/env python3
"""
Check Ansible Inclusion Checklist compliance

This script validates that the collection adheres to the requirements
listed in ANSIBLE_INCLUSION_CHECKLIST.md.

Usage:
    python scripts/check_inclusion_checklist.py
    python scripts/check_inclusion_checklist.py --strict  # Exit with error on failures
"""

import ast
import re
import sys
import yaml
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Tuple

# Collection root directory
COLLECTION_ROOT = Path(__file__).parent.parent / "ansible_collections" / "graphiant" / "naas"
COLLECTION_MODULES_DIR = COLLECTION_ROOT / "plugins" / "modules"
REPO_ROOT = Path(__file__).parent.parent

DOCUMENTATION_PATTERN = re.compile(r"DOCUMENTATION\s*=\s*r?([\"']{3})(.*?)\1", re.DOTALL)


@lru_cache(maxsize=None)
def _extract_documentation_block(content: str) -> str | None:
    """Extract DOCUMENTATION YAML text from module source content."""
    match = DOCUMENTATION_PATTERN.search(content)
    if not match:
        return None
    return match.group(2)


def _is_module_check_mode_test(test: ast.expr) -> bool:
    """Return True for `if module.check_mode:` style tests."""
    return (
        isinstance(test, ast.Attribute)
        and isinstance(test.value, ast.Name)
        and test.value.id == "module"
        and test.attr == "check_mode"
    )


def _contains_changed_true_assignment(statements: List[ast.stmt]) -> bool:
    """Check whether `changed = True` occurs in the provided statement list."""
    for stmt in statements:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name) and target.id == "changed":
                    if isinstance(stmt.value, ast.Constant) and stmt.value.value is True:
                        return True
        elif isinstance(stmt, ast.AnnAssign):
            if isinstance(stmt.target, ast.Name) and stmt.target.id == "changed":
                if isinstance(stmt.value, ast.Constant) and stmt.value.value is True:
                    return True
    return False


def _has_check_mode_always_changed(source: str) -> bool:
    """AST-based detection of `if module.check_mode:` blocks assigning `changed = True`."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_module_check_mode_test(node.test):
            if _contains_changed_true_assignment(node.body):
                return True
    return False


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
    module_names = sorted(module_file.stem for module_file in module_files)

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
        except (OSError, UnicodeDecodeError) as e:
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
        except (OSError, UnicodeDecodeError) as e:
            print(f"⚠️  Warning: Could not check {module_file.name}: {e}")

    return issues


def check_semantic_markup() -> Dict[str, List[Tuple[int, str, str]]]:
    """Check semantic markup in DOCUMENTATION: option refs use O(), choice refs use V() (§2.3.1)."""
    issues: Dict[str, List[Tuple[int, str, str]]] = {}

    if not COLLECTION_MODULES_DIR.exists():
        return issues

    for module_file in COLLECTION_MODULES_DIR.glob("graphiant_*.py"):
        module_name = module_file.stem
        try:
            content = module_file.read_text(encoding="utf-8")
            doc_text = _extract_documentation_block(content)
            if not doc_text:
                continue
            try:
                doc_data = yaml.safe_load(doc_text) or {}
            except yaml.YAMLError:
                continue

            options = doc_data.get("options") or {}
            option_names = set(options.keys())

            in_doc = False
            for line_num, line in enumerate(content.split("\n"), 1):
                if re.search(r"^\s*DOCUMENTATION\s*=", line):
                    in_doc = True
                    continue
                if in_doc and re.search(r"^\s*EXAMPLES\s*=", line):
                    break
                if not in_doc:
                    continue

                stripped = line.strip()
                if not stripped:
                    continue
                # Skip structural YAML keys and bare list items (choice values themselves)
                if re.match(
                    r"^(?:choices|type|default|required|version_added|elements|suboptions|options)\s*:",
                    stripped,
                    re.IGNORECASE,
                ):
                    continue

                # Check: "the <option_name> parameter/option/field/argument" → should use O()
                for opt_name in option_names:
                    if len(opt_name) < 3:
                        continue
                    if re.search(
                        rf"\bthe\s+{re.escape(opt_name)}\s+(?:parameter|option|field|argument)\b",
                        line,
                        re.IGNORECASE,
                    ) and f"O({opt_name})" not in line:
                        issues.setdefault(module_name, []).append(
                            (line_num, stripped[:100], f"option {opt_name!r} should use O({opt_name}) markup")
                        )
        except (OSError, UnicodeDecodeError) as e:
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
            documentation_text = _extract_documentation_block(content)
            if documentation_text is None:
                issues[module_name] = ["Missing DOCUMENTATION section"]
                continue
            try:
                documentation_yaml = yaml.safe_load(documentation_text) or {}
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
                                f"_info module should have support: full (read-only), found: {support_level}"
                            )

                    # State-changing modules should not claim full support if they always return changed=True
                    if support_level == "full" and not module_name.endswith("_info"):
                        if _has_check_mode_always_changed(content):
                            if module_name not in issues:
                                issues[module_name] = []
                            issues[module_name].append(
                                "Module claims support: full but always returns changed=True "
                                "in check mode. Should be support: partial"
                            )
        except (OSError, UnicodeDecodeError, re.error, yaml.YAMLError) as e:
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
                        try:
                            parsed_block = ast.parse(block)
                            has_conditional_logic = False
                            # The captured block starts with `if module.check_mode:`.
                            # Only flag as unconditional if there is no *additional* branching
                            # nested inside that outer check-mode body.
                            for stmt in parsed_block.body:
                                if not (
                                    isinstance(stmt, ast.If)
                                    and isinstance(stmt.test, ast.Attribute)
                                    and stmt.test.attr == "check_mode"
                                    and isinstance(stmt.test.value, ast.Name)
                                    and stmt.test.value.id == "module"
                                ):
                                    continue
                                if any(
                                    isinstance(node, (ast.If, ast.IfExp, ast.Match))
                                    for node in ast.walk(stmt)
                                    if node is not stmt
                                ):
                                    has_conditional_logic = True
                                    break
                        except SyntaxError:
                            # Fallback for partial/non-parseable block captures
                            has_conditional_logic = (
                                re.search(r"\b(if|elif)\b\s*.*:", block) is not None
                            )
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
                                "_info module should only gather information, not perform state changes"
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
                                (
                                    "State-changing modules should not have query/get operations "
                                    + "(use _info module instead)"
                                )
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

            documentation_yaml = None
            try:
                tree = ast.parse(content)
                for node in tree.body:
                    if (
                        isinstance(node, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == "DOCUMENTATION" for t in node.targets)
                        and isinstance(node.value, ast.Constant)
                        and isinstance(node.value.value, str)
                    ):
                        documentation_yaml = node.value.value
                        break
            except SyntaxError:
                documentation_yaml = None

            if not documentation_yaml:
                if module_name not in issues:
                    issues[module_name] = []
                issues[module_name].append("Missing requirements: section")
                continue

            doc_data = yaml.safe_load(documentation_yaml) or {}
            requirements = doc_data.get("requirements")

            if not requirements:
                if module_name not in issues:
                    issues[module_name] = []
                issues[module_name].append("Missing requirements: section")
                continue

            if isinstance(requirements, str):
                requirement_entries = [requirements]
            elif isinstance(requirements, list):
                requirement_entries = [str(entry) for entry in requirements]
            else:
                requirement_entries = [str(requirements)]

            python_req_pattern = re.compile(r"\bpython\b\s*>=\s*3\.7(?:\.\d+)*\b", re.IGNORECASE)
            if not any(python_req_pattern.search(entry) for entry in requirement_entries):
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


# Flat quantifiers only — avoids ReDoS from nested alternation in the full semver spec regex.
_SEMVER_RE = re.compile(
    r"^\d+\.\d+\.\d+"                                   # MAJOR.MINOR.PATCH
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"         # optional pre-release identifiers separated by dots
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"       # optional build metadata identifiers separated by dots
)


def check_galaxy_yml() -> List[str]:
    """Validate galaxy.yml: semantic versioning, license, tags, dependency bounds (§2.1, §2.2, §3.5, §3.6)."""
    issues: List[str] = []
    galaxy_file = COLLECTION_ROOT / "galaxy.yml"
    if not galaxy_file.exists():
        return ["galaxy.yml not found"]
    try:
        data = yaml.safe_load(galaxy_file.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        return [f"galaxy.yml parse error: {e}"]

    version = str(data.get("version") or "").strip()
    if not _SEMVER_RE.match(version):
        issues.append(f"version {version!r} does not follow MAJOR.MINOR.PATCH semantic versioning")

    license_val = data.get("license")
    license_file_val = str(data.get("license_file") or "").strip()
    if not license_val and not license_file_val:
        issues.append("missing 'license' or 'license_file' field")
    elif license_val:
        licenses = license_val if isinstance(license_val, list) else [license_val]
        if not any(re.search(r"GPL", str(lic), re.IGNORECASE) for lic in licenses):
            issues.append(f"license {licenses!r} is not GPL-compatible (Ansible requires GPL)")
    elif license_file_val:
        license_path = COLLECTION_ROOT / license_file_val
        if not license_path.exists():
            issues.append(f"license_file {license_file_val!r} does not exist")

    if not data.get("tags"):
        issues.append("missing or empty 'tags' field")

    deps = data.get("dependencies") or {}
    if isinstance(deps, dict):
        for dep, spec_raw in deps.items():
            spec = str(spec_raw or "").strip()
            if not spec:
                issues.append(f"dependency {dep!r} has no version specification")
                continue
            lower = re.search(r">=?\s*([\d.]+)", spec)
            if not lower:
                issues.append(f"dependency {dep!r} has no lower bound (must specify >= 1.0.0)")
            else:
                parts = lower.group(1).split(".")
                try:
                    if int(parts[0]) < 1:
                        issues.append(f"dependency {dep!r} lower bound {lower.group(1)!r} must be >= 1.0.0")
                except (ValueError, IndexError):
                    issues.append(f"dependency {dep!r} lower bound {lower.group(1)!r} could not be parsed as a version")

    return issues


def check_runtime_yml() -> List[str]:
    """Check meta/runtime.yml defines requires_ansible (§3.7)."""
    issues: List[str] = []
    runtime_file = COLLECTION_ROOT / "meta" / "runtime.yml"
    if not runtime_file.exists():
        return ["meta/runtime.yml not found"]
    try:
        data = yaml.safe_load(runtime_file.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        return [f"meta/runtime.yml parse error: {e}"]

    requires_ansible = str(data.get("requires_ansible") or "").strip()
    if not requires_ansible:
        issues.append("missing 'requires_ansible' field")
    elif not re.search(r">=?\s*2\.", requires_ansible):
        issues.append(f"requires_ansible {requires_ansible!r} should specify a minimum ansible-core >= 2.x version")

    return issues


def check_documentation_sections() -> Dict[str, List[str]]:
    """Check all modules have DOCUMENTATION, EXAMPLES, and RETURN sections (§2.3)."""
    issues: Dict[str, List[str]] = {}

    if not COLLECTION_MODULES_DIR.exists():
        return issues

    for module_file in COLLECTION_MODULES_DIR.glob("graphiant_*.py"):
        module_name = module_file.stem
        try:
            content = module_file.read_text(encoding="utf-8")
            module_issues = []
            for section in ("DOCUMENTATION", "EXAMPLES", "RETURN"):
                if not re.search(rf"^\s*{section}\s*=", content, re.MULTILINE):
                    module_issues.append(f"Missing {section} section")
            if module_issues:
                issues[module_name] = module_issues
        except (OSError, UnicodeDecodeError) as e:
            print(f"⚠️  Warning: Could not check {module_file.name}: {e}")

    return issues


def check_module_count() -> List[str]:
    """Check collection has at least one module (§3.2)."""
    if not COLLECTION_MODULES_DIR.exists():
        return ["plugins/modules/ directory not found"]
    modules = list(COLLECTION_MODULES_DIR.glob("graphiant_*.py"))
    if not modules:
        return [f"No modules found (collection must have at least 1 module)"]
    return []


def check_plugin_types() -> List[str]:
    """Check only allowed plugin types are present (§2.6)."""
    issues: List[str] = []
    plugins_dir = COLLECTION_ROOT / "plugins"
    if not plugins_dir.exists():
        return issues

    allowed = {"modules", "module_utils", "doc_fragments"}
    for child in plugins_dir.iterdir():
        if child.is_dir() and child.name not in allowed:
            issues.append(
                f"plugins/{child.name}/ uses plugin type {child.name!r}; "
                f"only {sorted(allowed)} are allowed for Ansible inclusion"
            )

    return issues


def check_supports_check_mode() -> Dict[str, List[str]]:
    """Check all modules declare supports_check_mode in AnsibleModule (§2.4)."""
    issues: Dict[str, List[str]] = {}

    if not COLLECTION_MODULES_DIR.exists():
        return issues

    for module_file in COLLECTION_MODULES_DIR.glob("graphiant_*.py"):
        module_name = module_file.stem
        try:
            content = module_file.read_text(encoding="utf-8")
            if "AnsibleModule(" not in content:
                continue
            if not re.search(r"supports_check_mode\s*=", content):
                issues.setdefault(module_name, []).append(
                    "Missing supports_check_mode= in AnsibleModule constructor"
                )
        except (OSError, UnicodeDecodeError) as e:
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


# Ansible semantic markup (C(), M(), O(), V(), I(), RV()) must not appear in changelog;
# use RST double backticks for literals.
# See https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html#inline-markup
ANSIBLE_C_MARKUP_IN_CHANGELOG = re.compile(r"\b(?:C|M|O|V|I|RV)\s*\(\s*[^)\s][^)]*\)")


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

    # Check 0a: Module count (§3.2)
    print("\n0a. Checking module count...")
    module_count_issues = check_module_count()
    if module_count_issues:
        for issue in module_count_issues:
            print(f"   ❌ {issue}")
            errors.append(issue)
    else:
        modules_found = len(list(COLLECTION_MODULES_DIR.glob("graphiant_*.py")))
        print(f"   ✅ {modules_found} module(s) found")

    # Check 0b: Plugin types (§2.6)
    print("\n0b. Checking allowed plugin types...")
    plugin_type_issues = check_plugin_types()
    if plugin_type_issues:
        for issue in plugin_type_issues:
            print(f"   ❌ {issue}")
            errors.append(issue)
    else:
        print("   ✅ Only allowed plugin types present")

    # Check 0c: galaxy.yml — semver, license, tags, dependency bounds (§2.1, §2.2, §3.5, §3.6)
    print("\n0c. Checking galaxy.yml (semantic versioning, license, tags, dependencies)...")
    galaxy_issues = check_galaxy_yml()
    if galaxy_issues:
        print("   ❌ galaxy.yml issues:")
        for issue in galaxy_issues:
            print(f"      - {issue}")
            errors.append(f"galaxy.yml: {issue}")
    else:
        print("   ✅ galaxy.yml passes all structural checks")

    # Check 0d: meta/runtime.yml — requires_ansible (§3.7)
    print("\n0d. Checking meta/runtime.yml...")
    runtime_issues = check_runtime_yml()
    if runtime_issues:
        print("   ❌ meta/runtime.yml issues:")
        for issue in runtime_issues:
            print(f"      - {issue}")
            errors.append(f"meta/runtime.yml: {issue}")
    else:
        print("   ✅ meta/runtime.yml defines requires_ansible")

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

    # Check 1.5: DOCUMENTATION, EXAMPLES, RETURN sections (§2.3)
    print("\n1.5. Checking DOCUMENTATION, EXAMPLES, and RETURN sections...")
    doc_section_issues = check_documentation_sections()
    if doc_section_issues:
        print("   ❌ Found modules with missing sections:")
        for module, issues_list in doc_section_issues.items():
            print(f"\n   📄 {module}.py:")
            for issue in issues_list:
                print(f"      - {issue}")
                errors.append(f"{module}.py: {issue}")
    else:
        print("   ✅ All modules have DOCUMENTATION, EXAMPLES, and RETURN sections")

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

    # Check 3.7: supports_check_mode declaration (§2.4)
    print("\n3.7. Checking supports_check_mode declarations...")
    scm_issues = check_supports_check_mode()
    if scm_issues:
        print("   ❌ Found modules missing supports_check_mode:")
        for module, issues_list in scm_issues.items():
            print(f"\n   📄 {module}.py:")
            for issue in issues_list:
                print(f"      - {issue}")
                errors.append(f"{module}.py: {issue}")
    else:
        print("   ✅ All modules declare supports_check_mode")

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
