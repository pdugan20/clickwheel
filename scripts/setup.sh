#!/usr/bin/env bash
# setup.sh — Install dependencies and configure beets
#
# Usage: ./scripts/setup.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BEETS_CONFIG="${PROJECT_DIR}/beets/config.yaml"
ENV_FILE="${PROJECT_DIR}/.env"

echo "[INFO] Setting up music-library-tools..."

# Check for Homebrew
if ! command -v brew &>/dev/null; then
    echo "[ERROR] Homebrew not found. Install from https://brew.sh"
    exit 1
fi

# Install system dependencies
echo "[INFO] Installing system dependencies..."
brew install ffmpeg chromaprint 2>/dev/null

# Install beets via pipx
if ! command -v pipx &>/dev/null; then
    echo "[INFO] Installing pipx..."
    brew install pipx
    pipx ensurepath
fi

if ! command -v beet &>/dev/null; then
    echo "[INFO] Installing beets..."
    pipx install beets
    pipx inject beets pyacoustid requests pillow pylast
else
    echo "[INFO] beets already installed: $(beet version | head -1)"
fi

# Set up .env
if [ ! -f "$ENV_FILE" ]; then
    echo ""
    read -rp "Enter path to your music library: " MUSIC_PATH
    read -rp "Enter your AcoustID API key (from acoustid.org): " API_KEY
    cat > "$ENV_FILE" <<EOF
MUSIC_DIR=${MUSIC_PATH}
ACOUSTID_API_KEY=${API_KEY}
EOF
    echo "[INFO] Saved config to .env"
else
    echo "[INFO] .env already exists"
fi

# Generate beets config from template
source "$ENV_FILE"

BEETS_TEMPLATE="${PROJECT_DIR}/beets/config.yaml.template"
if [ ! -f "$BEETS_TEMPLATE" ]; then
    echo "[ERROR] Beets config template not found: $BEETS_TEMPLATE"
    exit 1
fi

sed \
    -e "s|MUSIC_DIR_PLACEHOLDER|${MUSIC_DIR}|" \
    -e "s|LIBRARY_DB_PLACEHOLDER|${PROJECT_DIR}/beets/library.db|" \
    -e "s|REPORTS_DIR_PLACEHOLDER|${PROJECT_DIR}/reports|" \
    -e "s|ACOUSTID_API_KEY_PLACEHOLDER|${ACOUSTID_API_KEY:-not_set}|" \
    "$BEETS_TEMPLATE" > "$BEETS_CONFIG"

echo "[INFO] Generated beets/config.yaml from template"

if [ -z "${ACOUSTID_API_KEY:-}" ] || [ "$ACOUSTID_API_KEY" = "your_key_here" ]; then
    echo "[WARN] AcoustID API key not set -- fingerprinting will not work"
fi

# Verify music directory
if [ -d "$MUSIC_DIR" ]; then
    echo "[INFO] Music directory found: $MUSIC_DIR"
else
    echo "[WARN] Music directory not found: $MUSIC_DIR"
    echo "       Make sure the path is correct and any network drives are mounted."
fi

# Create local directories
mkdir -p "${PROJECT_DIR}/reports"

echo ""
echo "[SUCCESS] Setup complete."
echo "  Audit:   ./scripts/audit.sh"
echo "  Fix:     ./scripts/fix-metadata.sh"
