#!/bin/bash
# Build script for Graphiant Playbooks Ansible Collection docsite
# Usage: ./build_docsite.sh

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Building Graphiant Playbooks Collection Docusite${NC}"
echo "=========================================="

# Activate virtual environment
if [ -f ~/venv_pb/bin/activate ]; then
    echo "Activating virtual environment..."
    source ~/venv_pb/bin/activate
else
    echo -e "${YELLOW}Warning: Virtual environment not found at ~/venv_pb/bin/activate${NC}"
    echo "Please activate your virtual environment manually"
fi

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
COLLECTION_DIR="$SCRIPT_DIR"
PROJECT_ROOT="$(cd "$COLLECTION_DIR/../../.." && pwd)"

echo "Project root: $PROJECT_ROOT"
echo "Collection directory: $COLLECTION_DIR"

# Step 1: Install collection
echo ""
echo -e "${GREEN}Step 1: Installing collection...${NC}"
cd "$PROJECT_ROOT"
ansible-galaxy collection install ansible_collections/graphiant/graphiant_playbooks/ --force

# Step 2: Validate documentation
echo ""
echo -e "${GREEN}Step 2: Validating documentation...${NC}"
cd "$COLLECTION_DIR"
if antsibull-docs lint-collection-docs --plugin-docs --skip-rstcheck --validate-collection-refs=self . 2>&1 | grep -q "validation error"; then
    echo -e "${YELLOW}Warning: Validation errors found. Continuing with build...${NC}"
    echo "Run 'antsibull-docs lint-collection-docs --plugin-docs .' for details"
else
    echo "✓ Documentation validation passed"
fi

# Step 3: Generate RST files
echo ""
echo -e "${GREEN}Step 3: Generating RST files...${NC}"
antsibull-docs collection \
    --dest-dir docs/docsite \
    --use-current \
    --squash-hierarchy \
    graphiant.graphiant_playbooks

# Step 4: Build HTML with Sphinx
echo ""
echo -e "${GREEN}Step 4: Building HTML with Sphinx...${NC}"
cd docs/docsite

# Check if sphinx-build is available
if ! command -v sphinx-build &> /dev/null; then
    echo -e "${YELLOW}Warning: sphinx-build not found. Installing sphinx...${NC}"
    pip install sphinx sphinx-rtd-theme
fi

# Build HTML
sphinx-build -b html . _build/html

echo ""
echo -e "${GREEN}✅ Documentation built successfully!${NC}"
echo "=========================================="
echo "HTML files are in: $COLLECTION_DIR/docs/docsite/_build/html/"
echo ""
echo "To preview locally:"
echo "  cd docs/docsite/_build/html"
echo "  python3 -m http.server 8000"
echo "  Then open http://localhost:8000 in your browser"

