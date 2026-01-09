# Ansible Collection Docusite Setup Guide

This guide explains how to build and publish the documentation site for the Graphiant Playbooks Ansible Collection using `antsibull-docs`.

## Prerequisites

1. **Python Virtual Environment** (recommended):
   ```bash
   source ~/venv_pb/bin/activate
   ```

2. **Required Packages**:
   ```bash
   pip install ansible-core antsibull-docs sphinx sphinx-ansible-theme
   ```

3. **Collection Setup**:
   - Ensure the collection is properly structured in `ansible_collections/graphiant/naas/`
   - Set `ANSIBLE_COLLECTIONS_PATH` to point to the project root directory (which contains `ansible_collections/`)

## Directory Structure

The docsite structure should look like this:
```
ansible_collections/graphiant/naas/
├── docs/
│   ├── docsite/
│   │   └── links.yml          # Docusite configuration
│   └── DOCSITE_SETUP.md       # This file
├── meta/
│   └── galaxy.yml             # Collection metadata
└── plugins/
    └── modules/               # Module documentation (auto-extracted)
```

## Building the Docusite

### Method 1: Using sphinx-init (Recommended)

This method sets up a complete Sphinx project with all necessary configuration files.

#### Step 1: Initialize Sphinx Project

```bash
# Activate virtual environment
source ~/venv_pb/bin/activate

# Navigate to collection directory
cd ansible_collections/graphiant/naas

# Install the collection (required for antsibull-docs)
cd ../..
ansible-galaxy collection install ansible_collections/graphiant/naas/ --force

# Navigate back to collection directory
cd ansible_collections/graphiant/naas

# Initialize Sphinx project
antsibull-docs sphinx-init \
    --use-current \
    --dest-dir docs \
    --squash-hierarchy \
    graphiant.naas
```

This creates:
- `docs/conf.py` - Sphinx configuration
- `docs/build.sh` - Build script
- `docs/requirements.txt` - Python dependencies
- `docs/antsibull-docs.cfg` - antsibull-docs configuration
- `docs/rst/` - Directory for RST files

#### Step 2: Install Dependencies

```bash
cd docs
pip install -r requirements-ee.txt
```

#### Step 3: Build the Docusite

```bash
# Run the build script
./build.sh
```

This will:
1. Generate RST files from module documentation
2. Build HTML using Sphinx
3. Output HTML files to `docs/_build/html/`

#### Step 4: Preview Locally

```bash
cd _build/html
python3 -m http.server 8000
# Open http://localhost:8000 in your browser
```

### Method 2: Manual Two-Step Build

If you prefer more control over the build process:

#### Step 1: Install the Collection

```bash
# Activate virtual environment
source ~/venv_pb/bin/activate

# Navigate to project root
cd /Users/shaik/graphiant-playbooks

# Install the collection from source
ansible-galaxy collection install ansible_collections/graphiant/naas/ --force

# Verify collection is accessible
ansible-doc --list graphiant.naas
```

#### Step 2: Generate RST Files

```bash
# Navigate to collection directory
cd ansible_collections/graphiant/naas

# Generate RST files
antsibull-docs collection \
    --dest-dir docs/rst \
    --use-current \
    --squash-hierarchy \
    graphiant.naas
```

#### Step 3: Build HTML with Sphinx

```bash
cd docs
sphinx-build -b html . _build/html
```

**Note**: This method requires a properly configured `conf.py` file. Use Method 1 (sphinx-init) to generate it automatically.

## Publishing Options

### Option 1: GitHub Pages (Recommended)

1. **Build the docsite** (follow Method 1 Steps 1-3 above)

2. **Create a `gh-pages` branch**:
   ```bash
   # From project root
   cd /Users/shaik/graphiant-playbooks
   git checkout -b gh-pages
   git rm -rf .
   git clean -fxd
   ```

3. **Copy built HTML contents**:
   ```bash
   # From project root
   cp -r ansible_collections/graphiant/naas/docs/build/html/* .
   ```

4. **Commit and push**:
   ```bash
   git add .
   git commit -m "Add collection documentation site"
   git push origin gh-pages
   ```

5. **Enable GitHub Pages**:
   - Go to repository Settings → Pages
   - Select `gh-pages` branch as source
   - Documentation will be available at: `https://graphiant.github.io/graphiant-playbooks/`

### Option 2: Your Existing Documentation Site

If you have an existing documentation site at `https://docs.graphiant.com/docs/graphiant-playbooks`:

1. **Build the docsite** (follow Method 1 Steps 1-3 above)

2. **Copy built HTML to your documentation server**:
   ```bash
   # From collection directory
   cd ansible_collections/graphiant/naas
   # Example: Copy to your docs server
   rsync -av docs/build/html/ user@docs-server:/path/to/docs/graphiant-playbooks/
   ```

3. **Update your documentation site** to serve the generated HTML files

### Option 3: Include in Repository (Not Recommended)

While antsibull-docs documentation recommends against including RST files, you can generate them if needed:

```bash
antsibull-docs collection-plugins \
    --dest-dir docs/ \
    --output-format simplified-rst \
    --use-current \
    --fqcn-plugin-names graphiant.naas
```

**Note**: This is not recommended. A rendered docsite provides a better user experience.

## Automated Building with GitHub Actions

You can automate docsite building using GitHub Actions. See the [antsibull-docs documentation](https://ansible.readthedocs.io/projects/antsibull-docs/collection-docs/) for examples.

## Validating Documentation

Before building, validate your documentation:

```bash
# Lint collection documentation
antsibull-docs lint-collection-docs \
    --plugin-docs \
    --skip-rstcheck \
    --validate-collection-refs=self \
    .
```

This will check for:
- YAML syntax errors
- Missing required fields
- Invalid markup
- Cross-reference issues

## Troubleshooting

### Issue: "Collection not found"

**Solution**: Ensure `ANSIBLE_COLLECTIONS_PATH` is set correctly:
```bash
export ANSIBLE_COLLECTIONS_PATH=$(pwd)
# Verify
ansible-doc --list graphiant.naas
```

### Issue: "Module documentation not found"

**Solution**: Ensure modules have proper `DOCUMENTATION` strings:
```bash
# Check if ansible-doc can read the module
ansible-doc graphiant.naas.graphiant_interfaces
```

### Issue: "Build fails with validation errors"

**Solution**: Fix validation errors first:
```bash
antsibull-docs lint-collection-docs --plugin-docs .
```

## Updating Documentation

When you update module documentation:

1. **Update the `DOCUMENTATION` string** in the module file
2. **Validate**:
   ```bash
   antsibull-docs lint-collection-docs --plugin-docs .
   ```
3. **Rebuild the docsite**:
   ```bash
   antsibull-docs collection --dest-dir docs/docsite --use-current graphiant.naas
   ```
4. **Commit and push** (if using GitHub Pages, push to `gh-pages` branch)

## Additional Resources

- [antsibull-docs Documentation](https://ansible.readthedocs.io/projects/antsibull-docs/collection-docs/)
- [Ansible Collection Development Guide](https://docs.ansible.com/ansible/latest/dev_guide/developing_collections.html)
- [Ansible Module Documentation Standards](https://docs.ansible.com/ansible/latest/dev_guide/developing_modules_documenting.html)

