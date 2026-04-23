# Contributing to Graphiant Playbooks Collection

Thank you for your interest in contributing!

> **Note:** Version management is centralized in `_version.py`. See [Version Management Guide](ansible_collections/graphiant/naas/docs/guides/VERSION_MANAGEMENT.md) and [Release Process](ansible_collections/graphiant/naas/docs/guides/RELEASE.md) for version bumping and release procedures.

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork:**
   ```bash
   git clone https://github.com/Graphiant-Inc/graphiant-playbooks.git
   cd graphiant-playbooks
   ```
3. **Set up development environment:**
   ```bash
   python3.12 -m venv venv
   source venv/bin/activate
   pip install -r ansible_collections/graphiant/naas/requirements-ee.txt
   ```

## Development Workflow

1. Create a feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Check Ansible Inclusion Checklist compliance:**
   ```bash
   # From repository root
   python scripts/check_inclusion_checklist.py
   
   # Or with strict mode (exits with error on failures)
   python scripts/check_inclusion_checklist.py --strict
   ```
   > **Important:** Before committing or raising a PR, ensure your changes comply with the requirements in `ANSIBLE_INCLUSION_CHECKLIST.md`. The checklist covers:
   > - FQCN usage (including `ansible.builtin.*` for builtin modules)
   > - Module references in DOCUMENTATION sections using `M()` with FQCN
   > - Semantic markup (V() for values, O() for options, etc.)
   > - Check mode support information
   > - And many other Ansible Galaxy inclusion requirements

3. **Validate collection structure:**
   ```bash
   # From repository root
   python scripts/validate_collection.py
   
   # Or from collection directory
   python ../../scripts/validate_collection.py
   ```

4. **Build and install collection:**
   ```bash
   ansible-galaxy collection install ansible_collections/graphiant/naas/ --force
   ```

5. **Run linting (before commit):**
   ```bash
   # Install development tools needed for linting
   source venv/bin/activate
   pip install black flake8 pylint djlint ansible-lint pre-commit
   # Pylint needs ansible-core to resolve ansible.module_utils.* (same as python-lint in lint.yml)
   pip install "ansible-core>=2.17"

   # Python code formatting check with black (runs in CI)
   black ansible_collections/graphiant/naas/plugins/ -l 120 --check
   
   # Python code formatting with black if required
   black ansible_collections/graphiant/naas/plugins/ -l 120 --check --diff
   black ansible_collections/graphiant/naas/plugins/ -l 120

   # Python linting with flake8 (runs in CI)
   flake8 ansible_collections/graphiant/naas/plugins/ --max-line-length=120

   # Python linting with pylint (runs in CI)
   # Repository root on PYTHONPATH so FQCN imports (ansible_collections.graphiant.naas… and ansible.module_utils) resolve
   export PYTHONPATH=$(pwd)
   pylint --errors-only ansible_collections/graphiant/naas/plugins/
   # Optional: use the repository `.pylintrc` so a full run reports only E/F messages
   # (10.00/10 when there are no errors) — same scope in practice as `--errors-only` above
   # pylint --rcfile=.pylintrc ansible_collections/graphiant/naas/plugins/ ansible_collections/graphiant/naas/tests/unit/

   # Ansible playbook linting (runs in CI, requires collection to be installed first)
   ansible-galaxy collection install ansible_collections/graphiant/naas/ --force
   ansible-lint --config-file ~/.ansible/collections/ansible_collections/graphiant/naas/.ansible-lint ~/.ansible/collections/ansible_collections/graphiant/naas/playbooks/

   # YAML/Jinja template linting (runs in CI)
   djlint ansible_collections/graphiant/naas/configs -e yaml
   djlint ansible_collections/graphiant/naas/templates -e yaml

   # Static type checking (runs in CI; same as python-lint “Mypy” step)
   pip install mypy types-PyYAML types-tabulate
   export PYTHONPATH=.
   mypy --config-file mypy.ini
   ```

6. **Run E2E integration test (hello_test.yml):**
   ```bash
   # Set credentials
   export GRAPHIANT_HOST="https://api.graphiant.com"
   export GRAPHIANT_USERNAME="your_username"
   export GRAPHIANT_PASSWORD="your_password"

   # Optional: Enable pretty output for detailed_logs
   export ANSIBLE_STDOUT_CALLBACK=debug
   
   # Run hello_test.yml to verify collection works (also runs in CI as e2e-integration-test)
   ansible-playbook ~/.ansible/collections/ansible_collections/graphiant/naas/playbooks/hello_test.yml
   ```

7. **Run pre-commit hooks (if installed):**
   ```bash
   # Install pre-commit hooks (one-time setup)
   pre-commit install
   
   # Run hooks manually
   pre-commit run --all-files
   ```
   > **Note:** Pre-commit hooks (see `.pre-commit-config.yaml`) include `flake8` and `pylint --errors-only` on `plugins/`, plus the Ansible Inclusion Checklist check (FQCN and semantic markup). Run `black` locally or rely on the `python-lint` CI job for formatting checks.

8. **Commit with clear messages:**
   ```bash
   git commit -m "Add: description of changes"
   ```
   > **Important:** Before committing, ensure:
   > - ✅ Ansible Inclusion Checklist compliance: `python scripts/check_inclusion_checklist.py --strict`
   > - ✅ Collection structure validation: `python scripts/validate_collection.py`
   > - ✅ All tests pass locally

9. **Push and create a pull request**
   
   > **Before raising a PR, verify:**
   > - ✅ All checks in `ANSIBLE_INCLUSION_CHECKLIST.md` are reviewed
   > - ✅ CI/CD workflows will pass (lint, test, build)
   > - ✅ Documentation is updated if needed
   > - ✅ Changelog is updated for user-facing changes

## Linting Tools

The project uses multiple linting tools to ensure code quality:

| Tool | Purpose | Target | CI/CD |
|------|---------|--------|-------|
| `black` | Python formatting | `ansible_collections/graphiant/naas/plugins/` | Yes (`python-lint` job in `lint.yml`) |
| `flake8` | Python style guide (PEP 8) | `ansible_collections/graphiant/naas/plugins/` | Yes (`python-lint` job) |
| `pylint` | Python code analysis (`--errors-only`) | `ansible_collections/graphiant/naas/plugins/` | Yes (`python-lint` job) |
| `ansible-lint` | Ansible playbook best practices | `playbooks/` | Yes (lint stage) |
| `djlint` | Jinja2/YAML template linting | `configs/`, `templates/` | Yes (lint stage) |
| `ansible-test sanity` | Ansible collection sanity tests | Collection | Yes (lint and test/run stages) |
| `mypy` | Static type checking | `plugins/` (see `mypy.ini`) and `scripts/` | Yes (`python-lint` job) |
| `pre-commit` | Local git hooks (`flake8`, `pylint`, inclusion checklist; see `.pre-commit-config.yaml`) | Plugins tree (per config) | Optional locally; not a GitHub Actions job |

Configuration files:
- `mypy.ini` (repository root) - mypy options; check `files` / `exclude` before adding modules
- `.ansible-lint` - Ansible lint rules
- `.pre-commit-config.yaml` (repository root) - optional local hooks aligned with Python lint targets

**Note:** The **`python-lint`** job in `lint.yml` runs `black --check`, `flake8`, `pylint --errors-only`, and `mypy` on the collection `plugins/` tree and `scripts/` (per `mypy.ini`). CI also runs `ansible-lint`, `djlint`, `antsibull-docs` / changelog lint, `ansible-test sanity`, the inclusion checklist script, and (when configured) E2E integration tests.

### Unit tests (`ansible-test units`)

Offline pytest unit tests live under `ansible_collections/graphiant/naas/tests/unit/` and are run in the **`test` job** in [`.github/workflows/test.yml`](.github/workflows/test.yml) (the **Run ansible-test units** step; no Graphiant API required). They improve coverage of `plugins/module_utils` and `plugins/modules` beyond sanity import/compile metrics. Layout mirrors `plugins/`, for example `tests/unit/plugins/module_utils/`, `tests/unit/plugins/module_utils/libs/`, and `tests/unit/plugins/modules/` (mocked `AnsibleModule` and `get_graphiant_connection` where needed).

```bash
cd ansible_collections/graphiant/naas
pip install -r requirements-ee.txt -r tests/unit/requirements.txt
ansible-test units --local --python 3.12
```

### ansible-test Sanity Configuration

The collection uses command-line exclusions and proper directory structure:

1. **Yamllint exclusions** - Jinja2 template directories are excluded using `--exclude templates/ --exclude configs/de_workflows_configs/`, as these contain Jinja2 templates with syntax that yamllint cannot parse.

2. **Utility scripts** - Utility scripts (build_collection.py, bump_version.py, validate_collection.py, build_docsite.sh) are located in the `scripts/` directory at the repository root, outside the collection directory. This means they are not checked by `ansible-test sanity`, so the shebang test runs normally on collection files.

This approach is cleaner and more maintainable than maintaining version-specific ignore files or configuration files.

## Code Standards

### Python Code
- Follow PEP 8 style guidelines
- Include docstrings for functions and classes
- Use type hints where appropriate (see **Python type hints and supported runtimes** below)

### Python type hints and supported runtimes

The collection supports **Python 3.7+** (per the repo badge and `ansible-test` import checks). That affects how you write annotations in `plugins/module_utils` and `plugins/modules`:

- **Do not use PEP 604** union syntax (`str | None`, `int | str`) in the collection: it is only valid from **Python 3.10+** and fails `ansible-test` **import** sanity on 3.7–3.9 with `TypeError: unsupported operand type(s) for |`.
- Prefer **`typing.Optional`**, **`typing.Union`**, and **capital** names from `typing` (`Dict`, `List`, `Set`, `Tuple`, …) instead of **PEP 585** built-in generics (`dict[str, …]`, `list[…]`, `set[…]`, `tuple[…]`) if the code must run on **3.7 / 3.8** (built-in subscripting for those is 3.9+).
- Optional `from __future__ import annotations` can help in some cases, but **ansible-test** may still load modules in a way that evaluates annotations; when in doubt, keep signatures compatible with 3.7+ or omit a parameter’s annotation and document the type in the docstring.
- **Abstract** bases: use an empty body of `pass` (or a short `raise NotImplementedError`) for `@abstractmethod` stubs, not a bare `...`, to satisfy Pylint’s `unnecessary-ellipsis` in CI.

**Mypy** (see `mypy.ini`) is run from the **repository root** with `PYTHONPATH=.` and checks `ansible_collections/graphiant/naas/plugins` and `scripts/`. Install stub packages for untyped third-party imports used in the tree, e.g. `types-PyYAML` and `types-tabulate` (as in the `python-lint` workflow). After changing types or adding dependencies, run `mypy --config-file mypy.ini` locally before pushing.

### Ansible Modules
- Include `DOCUMENTATION`, `EXAMPLES`, and `RETURN` strings
- Ensure idempotency
- Handle errors gracefully
- Support check mode

### Example Module Structure

```python
#!/usr/bin/python
# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
---
module: your_module
short_description: Brief description
description:
  - Detailed description
options:
  option_name:
    description: Option description
    required: true
    type: str
'''

EXAMPLES = r'''
- name: Example task
  graphiant.naas.your_module:
    option_name: value
'''

RETURN = r'''
result:
  description: Result description
  returned: always
  type: dict
'''

from ansible.module_utils.basic import AnsibleModule

def main():
    module = AnsibleModule(
        argument_spec=dict(
            option_name=dict(type='str', required=True),
        ),
        supports_check_mode=True
    )
    module.exit_json(changed=False, result={})

if __name__ == '__main__':
    main()
```

## Version Management

All version information is centralized in `_version.py`. This ensures consistency across:
- Collection version (`galaxy.yml`)
- Module `version_added` fields
- Dependency versions (`requirements-ee.txt`)
- Changelog entries

### For Maintainers: Updating Versions

Use the automated version bump script:

```bash
# Patch release (bug fixes) - from repository root
python scripts/bump_version.py patch

# Minor release (new features)  
python scripts/bump_version.py minor

# Major release (breaking changes)
python scripts/bump_version.py major
```

The script automatically updates all version references. See [Version Management Guide](ansible_collections/graphiant/naas/docs/guides/VERSION_MANAGEMENT.md) and [Release Process](ansible_collections/graphiant/naas/docs/guides/RELEASE.md) for complete release procedures.

### For Contributors

You typically don't need to update versions. Focus on your code changes, and maintainers will handle version bumps during releases.

## Pull Request Checklist

- [ ] Code follows style guidelines
- [ ] Tests pass locally
- [ ] Documentation updated
- [ ] Changelog updated (if applicable)
- [ ] Commit messages are clear
- [ ] Commits are signed with GPG (required)
- [ ] Branch is rebased (no merge commits allowed)
- [ ] All CI/CD checks pass (lint, test, code quality, code scanning)

## Branch Protection Requirements

This repository has branch protection rules that must be satisfied before a pull request can be merged:

### Required Approvals
- **SRE Team Approval**: All pull requests require approval from `@Graphiant-Inc/sre`
- **Code Owners**: Additional approvals may be required based on CODEOWNERS file

### Merge Requirements
- **Merge Method**: Only **squash merge** or **rebase merge** are allowed (standard merge is disabled)
- **No Merge Commits**: Your branch must not contain merge commits
  - Use `git rebase` instead of `git merge` when updating your branch
  - Example: `git pull --rebase origin main` or `git rebase origin/main`

### Commit Requirements
- **Signed Commits**: All commits must be verified with GPG signatures
  - Set up GPG signing: https://docs.github.com/en/authentication/managing-commit-signature-verification
  - Configure Git: `git config --global commit.gpgsign true`
  - Verify your commits are signed: `git log --show-signature`

### Code Quality Checks
- **Code Scanning (CodeQL)**: Must pass security analysis
- **Code Quality**: Must pass quality checks for all analyzed languages
- **CI/CD Pipelines**: All workflows (lint, test, build) must pass

### Troubleshooting

**"This branch must not contain merge commits"**
```bash
# Rebase your branch instead of merging
git checkout your-branch
git rebase origin/main
# Resolve any conflicts, then force push (if needed)
git push --force-with-lease origin your-branch
```

**"Commits must have verified signatures" / "gpg failed to sign the data"**

If you get `error: gpg failed to sign the data`, follow these steps:

1. **Check if you have a GPG key:**
   ```bash
   gpg --list-secret-keys --keyid-format=long
   ```

2. **If no key exists, generate one:**
   ```bash
   gpg --full-generate-key
   # Choose: (1) RSA and RSA (default)
   # Key size: 4096
   # Expiration: 0 (no expiration) or your preference
   # Enter your name and email (use your GitHub email)
   ```

3. **Get your key ID and configure Git:**
   ```bash
   gpg --list-secret-keys --keyid-format=long
   # Copy the key ID (the long hex string after "sec   rsa4096/")
   git config --global user.signingkey YOUR_KEY_ID
   git config --global commit.gpgsign true
   ```

4. **Set GPG_TTY (required for macOS/Linux):**
   ```bash
   # Add to your ~/.zshrc or ~/.bashrc
   export GPG_TTY=$(tty)
   # Then reload: source ~/.zshrc
   ```

5. **Add GPG key to GitHub:**
   ```bash
   gpg --armor --export YOUR_KEY_ID
   # Copy the output and add it to: https://github.com/settings/gpg/new
   ```

6. **Test GPG signing:**
   ```bash
   echo "test" | gpg --clearsign
   # If this works, try committing again
   ```

7. **If still failing, check GPG agent:**
   ```bash
   # Restart GPG agent
   gpgconf --kill gpg-agent
   gpgconf --launch gpg-agent
   ```

8. **Re-sign existing commits (if needed):**
   ```bash
   git rebase -i HEAD~N  # N = number of commits
   # Mark commits as 'edit', then amend with signature
   git commit --amend --no-edit -S
   git rebase --continue
   ```

**"Waiting on required approvals"**
- Ensure `@Graphiant-Inc/sre` team members review and approve your PR
- Check that CODEOWNERS file includes the SRE team for your changed files

## Getting Help

- **Issues**: [GitHub Issues](https://github.com/Graphiant-Inc/graphiant-playbooks/issues)
- **Email**: support@graphiant.com

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
