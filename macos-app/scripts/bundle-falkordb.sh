#!/usr/bin/env bash
# bundle-falkordb.sh — Downloads redis-server + falkordb.so for the Mac app bundle.
#
# Usage:
#   ./scripts/bundle-falkordb.sh [output_dir]
#
# Downloads ARM64 macOS binaries into the output directory (default: build/falkordb/).
# The Mac app embeds these and starts redis-server directly — no Docker, no redislite.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT_DIR="${1:-${SCRIPT_DIR}/../build/falkordb}"

echo "=== FalkorDB Bundle Script ==="
echo "Output: ${OUTPUT_DIR}"

mkdir -p "${OUTPUT_DIR}"

# redis-server from falkordblite package (already ARM64 macOS)
REDIS_SERVER_URL="https://github.com/nicholasgasior/redis-macos/releases/download/8.0.0/redis-server"
FALKORDB_MODULE_URL="https://github.com/FalkorDB/FalkorDB/releases/latest/download/falkordb-macos-arm64v8.so"

# Check if we can copy from the local falkordblite installation first
LOCAL_REDIS="/Users/myang/.pyenv/versions/3.12.4/lib/python3.12/site-packages/redislite/bin/redis-server"
if [[ -f "${LOCAL_REDIS}" ]]; then
    echo "Copying redis-server from local falkordblite installation..."
    cp "${LOCAL_REDIS}" "${OUTPUT_DIR}/redis-server"
else
    echo "Downloading redis-server..."
    curl -sL "${REDIS_SERVER_URL}" -o "${OUTPUT_DIR}/redis-server"
fi

echo "Downloading FalkorDB module (ARM64 macOS)..."
curl -sL "${FALKORDB_MODULE_URL}" -o "${OUTPUT_DIR}/falkordb.so"

chmod +x "${OUTPUT_DIR}/redis-server" "${OUTPUT_DIR}/falkordb.so"

# Verify
echo ""
echo "--- Verifying ---"
file "${OUTPUT_DIR}/redis-server"
file "${OUTPUT_DIR}/falkordb.so"
"${OUTPUT_DIR}/redis-server" --version 2>&1 || true
echo ""
echo "Size: $(du -sh "${OUTPUT_DIR}" | cut -f1)"
echo "=== Done ==="
