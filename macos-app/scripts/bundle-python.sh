#!/usr/bin/env bash
# bundle-python.sh — Creates a standalone Python environment for the Mac app bundle.
#
# Usage:
#   ./scripts/bundle-python.sh [output_dir]
#
# This script:
#   1. Creates a Python venv
#   2. Installs codegraphcontext + falkordb into it
#   3. Copies the venv to the output directory (app bundle's Resources/python/)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT_DIR="${1:-${SCRIPT_DIR}/../build/python}"
VENV_DIR="${SCRIPT_DIR}/../build/venv-staging"

# Python version requirement
PYTHON_MIN_VERSION="3.10"

echo "=== CodeGraphContext Python Bundler ==="
echo "Output: ${OUTPUT_DIR}"

# Find a suitable Python
for py in python3.12 python3.11 python3; do
    if command -v "$py" &>/dev/null; then
        PYTHON="$(command -v "$py")"
        break
    fi
done

if [[ -z "${PYTHON:-}" ]]; then
    echo "ERROR: Python 3.11+ not found" >&2
    exit 1
fi

PY_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Using Python ${PY_VERSION} at ${PYTHON}"

# Create fresh venv
echo "--- Creating virtual environment ---"
rm -rf "${VENV_DIR}"
"$PYTHON" -m venv "${VENV_DIR}"

# Activate and install
echo "--- Installing dependencies ---"
"${VENV_DIR}/bin/pip" install --upgrade pip --quiet

# Install CodeGraphContext (from the local repo or PyPI)
CGC_REPO="${CGC_REPO_PATH:-/Users/myang/git/CodeGraphContext}"
if [[ -d "${CGC_REPO}" ]]; then
    echo "Installing codegraphcontext from local repo: ${CGC_REPO}"
    "${VENV_DIR}/bin/pip" install -e "${CGC_REPO}" --quiet
else
    echo "Installing codegraphcontext from PyPI"
    "${VENV_DIR}/bin/pip" install codegraphcontext --quiet
fi

# Install FalkorDB client (connects to Docker-based FalkorDB server)
echo "--- Installing FalkorDB client ---"
"${VENV_DIR}/bin/pip" install falkordb --quiet

# Verify installations
echo "--- Verifying ---"
"${VENV_DIR}/bin/python" -c "import codegraphcontext; print(f'CGC version: {codegraphcontext.__version__}')" 2>/dev/null || \
    echo "WARNING: codegraphcontext import check failed (may need __version__ attribute)"
"${VENV_DIR}/bin/python" -c "import falkordb; print('FalkorDB client: OK')"

# Copy to output directory
echo "--- Copying to output ---"
rm -rf "${OUTPUT_DIR}"
mkdir -p "$(dirname "${OUTPUT_DIR}")"
cp -a "${VENV_DIR}" "${OUTPUT_DIR}"

# Make the venv relocatable by fixing shebang lines
echo "--- Making relocatable ---"
find "${OUTPUT_DIR}/bin" -type f -exec grep -l "^#!.*${VENV_DIR}" {} \; 2>/dev/null | while read -r f; do
    sed -i '' "s|${VENV_DIR}|${OUTPUT_DIR}|g" "$f"
done

echo "=== Done ==="
echo "Bundled Python environment at: ${OUTPUT_DIR}"
echo "Size: $(du -sh "${OUTPUT_DIR}" | cut -f1)"
