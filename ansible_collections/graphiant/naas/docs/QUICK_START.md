# Quick Start: Building the Collection Docusite

This is a quick reference guide for building the documentation site.

## Prerequisites

```bash
# Activate virtual environment
source ~/venv_pb/bin/activate

# Install required packages
pip install ansible-core antsibull-docs sphinx sphinx-rtd-theme
```

## Quick Build (Recommended Method)

### Using sphinx-init (One-time setup)

```bash
# 1. Activate virtual environment
source ~/venv_pb/bin/activate

# 2. Navigate to project root and install collection
cd /Users/shaik/graphiant-playbooks
ansible-galaxy collection install ansible_collections/graphiant/naas/ --force

# 3. Navigate to collection directory
cd ansible_collections/graphiant/naas

# 4. Initialize Sphinx project (one-time setup)
antsibull-docs sphinx-init --use-current --dest-dir docs --squash-hierarchy graphiant.naas

# 5. Install dependencies
cd docs
pip install -r requirements-ee.txt

# 6. Build the docsite
./build.sh

# 7. Preview locally
cd _build/html
python3 -m http.server 8000
# Open http://localhost:8000 in your browser
```

### Subsequent Builds

After the initial setup, simply run:

```bash
cd ansible_collections/graphiant/naas/docs
./build.sh
```

## Alternative: Using Custom Build Script

```bash
# Navigate to collection directory
cd ansible_collections/graphiant/naas

# Run the custom build script
./docs/build_docsite.sh
```

## Validation Before Building

Before building, validate your documentation:

```bash
cd ansible_collections/graphiant/naas
antsibull-docs lint-collection-docs --plugin-docs --skip-rstcheck --validate-collection-refs=self .
```

## Publishing to GitHub Pages

```bash
# After building the docsite using ./build.sh
# HTML files are in: docs/build/html/

# Create or switch to gh-pages branch (from project root)
cd /Users/shaik/graphiant-playbooks
git checkout -b gh-pages  # or git checkout gh-pages if it exists
git rm -rf .
git clean -fxd

# Copy all HTML files to root
cp -r ansible_collections/graphiant/naas/docs/build/html/* .

# Commit and push
git add .
git commit -m "Update collection documentation"
git push origin gh-pages
```

Then enable GitHub Pages in repository Settings → Pages.

## Troubleshooting

**Issue**: "unable to locate collection"
- **Solution**: Install the collection first: `ansible-galaxy collection install ansible_collections/graphiant/naas/ --force`

**Issue**: Validation errors during build
- **Solution**: Run `antsibull-docs lint-collection-docs --plugin-docs .` to see specific errors
- Fix validation errors in module DOCUMENTATION strings
- Rebuild the docsite

**Issue**: Module documentation shows error pages
- **Solution**: These are caused by validation errors. Fix the DOCUMENTATION strings and rebuild.

