# GitHub Actions Workflows

This directory contains GitHub Actions workflows for the Graphiant Playbooks collection.

## Workflows

### `lint.yml` - Comprehensive Linting
Detailed linting workflow that runs multiple linting checks in parallel:
- Jinja2 template linting (djlint)
- Ansible lint
- Documentation lint (antsibull-docs)
- ansible-test sanity (tests against ansible-core 2.17, 2.18, 2.19, 2.20)

### `test.yml` - Testing
Runs all tests for the collection:
- **`test` job** - Matrix job testing against ansible-core 2.17, 2.18, 2.19, 2.20:
  - Python unit tests
  - Full collection validation
- **`e2e-integration-test` job** - Separate job (not in matrix):
  - E2E integration test (hello_test.yml playbook) - runs when GRAPHIANT credentials are configured

### `build.yml` - Build Collection
Builds the Ansible collection:
- Creates the collection tarball
- Verifies build artifact was created successfully
- Uploads build artifact

### `release.yml` - Release and Publish
Publishes the collection to Ansible Galaxy and creates Git tags/releases:
- Manual trigger only (workflow_dispatch)
- Restricted to repository admins and maintainers only
- Requires `GALAXY_API_KEY` secret or variable to be set for publishing
- **Automatically creates Git tags** for releases
- **Automatically creates GitHub releases** with CHANGELOG references
- **Idempotent behavior**: Won't fail if tags or releases already exist (safe to re-run)

## Setup

### Required Secrets

#### For Release Workflow

For the release workflow to work, you need to set up the following secret or variable in GitHub:

1. Go to your repository settings
2. Navigate to **Secrets and variables** → **Actions**
3. Add a new secret or variable:
   - **Name**: `GALAXY_API_KEY`
   - **Value**: Your Ansible Galaxy API token (get it from https://galaxy.ansible.com/ui/token/)
   - **Note**: Can be configured as either a secret (recommended for security) or a repository variable

#### For E2E Integration Test

The `e2e-integration-test` job in `test.yml` requires the following secrets/variables:

- `GRAPHIANT_HOST` - Graphiant API endpoint (e.g., `https://api.graphiant.com`)
- `GRAPHIANT_USERNAME` - Graphiant API username
- `GRAPHIANT_PASSWORD` - Graphiant API password

**To configure:**

1. Go to your repository settings
2. Navigate to **Secrets and variables** → **Actions**
3. Add the following secrets or variables (mark as **Secret** for security):
   - `GRAPHIANT_HOST`
   - `GRAPHIANT_USERNAME`
   - `GRAPHIANT_PASSWORD`
   - **Note**: These can be configured as either secrets (recommended) or repository variables. The workflow checks secrets first, then variables.

**Note:** If these secrets are not set, the E2E integration test will be skipped (this is expected behavior). The test will only run when all three secrets are configured.

### Workflow Triggers

- **Pull Requests**: All workflows run on PRs to ensure code quality
- **Push to main/develop**: CI workflows run on pushes to main branches
- **Scheduled**: Test workflow runs nightly at 2 AM UTC
- **Manual**: Release workflow must be manually triggered via workflow_dispatch (restricted to admins and maintainers)

## Usage

### Running Workflows Locally

While you can't run GitHub Actions locally, you can run the same commands:

```bash
cd ansible_collections/graphiant/naas

# Linting
djlint configs -e yaml
djlint templates -e yaml
ansible-lint --config-file .ansible-lint playbooks/
ansible-test sanity --color --python 3.12 --exclude templates/ --exclude configs/de_workflows_configs/

# Testing (install ansible-core first)
pip install ansible-core~=2.17  # or 2.18, 2.19, 2.20
ansible-galaxy collection install . --force
export PYTHONPATH=$(pwd)/plugins/module_utils
python tests/test.py
python ../../scripts/validate_collection.py --full

# E2E Integration Test (requires GRAPHIANT credentials and ansible-core)
pip install ansible-core~=2.19
ansible-galaxy collection install . --force
export GRAPHIANT_HOST="https://api.graphiant.com"
export GRAPHIANT_USERNAME="your_username"
export GRAPHIANT_PASSWORD="your_password"
export ANSIBLE_STDOUT_CALLBACK=debug
ansible-playbook ~/.ansible/collections/ansible_collections/graphiant/naas/playbooks/hello_test.yml

# Building
python ../../scripts/build_collection.py
```

### Publishing a Release

1. Manually trigger the release workflow via `workflow_dispatch` from the GitHub Actions tab
2. Provide the collection version when prompted (e.g., `25.12.1` or `v25.12.1`)
3. The workflow will:
   - Build the collection
   - Publish to Ansible Galaxy (if `GALAXY_API_KEY` is configured)
   - Create Git tag (normalized to include 'v' prefix, e.g., `v25.12.1`)
   - Create GitHub release with CHANGELOG reference
4. **Idempotent**: The workflow can be safely re-run - it won't fail if tags or releases already exist

## Workflow Status

You can view workflow status in the **Actions** tab of your GitHub repository.

