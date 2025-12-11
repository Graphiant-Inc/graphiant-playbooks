# GitLab CI/CD Pipelines

This directory contains GitLab CI/CD pipeline definitions for the Graphiant Playbooks repository.

## Pipeline Files

- **`lint.yml`** - Linting pipeline (djlint, ansible-lint, documentation lint, ansible-test sanity with multi-version testing)
- **`run.yml`** - Test pipeline (multi-version testing, e2e-integration-test)
- **`docker.yml`** - Docker build and publish pipeline

## Configuration

The main GitLab CI configuration is in `.gitlab-ci.yml` (repository root), which includes these pipeline files.

## Pipeline Structure

### Lint Pipeline (`lint.yml`)
Runs comprehensive code quality checks:
- Jinja2 template linting (djlint)
- Ansible lint
- Documentation lint (antsibull-docs)
- ansible-test sanity (parallel matrix testing against ansible-core 2.17, 2.18, 2.19) (parallel matrix testing against ansible-core 2.17, 2.18, 2.19)

### Test Pipeline (`run.yml`)
Runs test suite and validation:
- **`test` job** - Parallel matrix job testing against ansible-core 2.17, 2.18, 2.19:
  - Python unit tests
  - Collection validation
- **`e2e-integration-test` job** - Separate job (not in matrix):
  - E2E integration test (hello_test.yml playbook) - runs when GRAPHIANT credentials are configured

**Note:** The pipeline stages run in the following order: `lint` → `run` → `build` → `publish`. This ensures tests run before building the collection.

### Docker Pipeline (`docker.yml`)
Builds and publishes Docker images:
- Docker image build with BuildKit
- Publish to GitLab Container Registry
- Publish to Docker Hub

## Usage

### Running Locally

```bash
cd ansible_collections/graphiant/graphiant_playbooks

# Linting
djlint configs -e yaml
djlint templates -e yaml
ansible-lint --config-file .ansible-lint playbooks/
ansible-test sanity --color --python 3.12 --exclude templates/ --exclude configs/de_workflows_configs/

# Testing (install ansible-core first)
pip install ansible-core~=2.17  # or 2.18, 2.19
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
ansible-playbook ~/.ansible/collections/ansible_collections/graphiant/graphiant_playbooks/playbooks/hello_test.yml
```

## Triggers

Pipelines are triggered by:
- Merge requests
- Main branch pushes
- Feature/hotfix branch pushes

## Environment Variables

### Required for E2E Integration Test

The `e2e-integration-test` job requires the following environment variables to be set in GitLab CI/CD:

- `GRAPHIANT_HOST` - Graphiant API endpoint (e.g., `https://api.graphiant.com`)
- `GRAPHIANT_USERNAME` - Graphiant API username
- `GRAPHIANT_PASSWORD` - Graphiant API password

**To configure in GitLab:**

1. Go to your GitLab project
2. Navigate to **Settings** → **CI/CD** → **Variables**
3. Click **Add variable** and add each of the following (mark as **Protected** and **Masked** for security):
   - Key: `GRAPHIANT_HOST`, Value: `https://api.graphiant.com` (or your Graphiant API endpoint)
   - Key: `GRAPHIANT_USERNAME`, Value: Your Graphiant API username
   - Key: `GRAPHIANT_PASSWORD`, Value: Your Graphiant API password

**Note:** If these variables are not set, the E2E integration test will be skipped with an informational message. This is **expected behavior** and does not indicate an error. The test will only run when all three variables are configured.

### Other Environment Variables

See `.gitlab-ci.yml` for other required environment variables and configuration.

