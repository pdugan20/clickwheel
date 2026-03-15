#!/usr/bin/env bash
# setup.sh — Install dependencies and configure beets on a new machine
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

# Set up .env with AcoustID API key
if [ ! -f "$ENV_FILE" ]; then
    echo ""
    echo "[INFO] No .env file found."
    read -rp "Enter your AcoustID API key (from acoustid.org): " API_KEY
    echo "ACOUSTID_API_KEY=${API_KEY}" > "$ENV_FILE"
    echo "[INFO] Saved to .env"
else
    echo "[INFO] .env already exists"
fi

# Substitute API key into beets config
source "$ENV_FILE"
if [ -n "${ACOUSTID_API_KEY:-}" ] && [ "$ACOUSTID_API_KEY" != "your_key_here" ]; then
    sed -i '' "s/ACOUSTID_API_KEY_PLACEHOLDER/${ACOUSTID_API_KEY}/" "$BEETS_CONFIG"
    echo "[INFO] AcoustID API key configured in beets config"
else
    echo "[WARN] AcoustID API key not set — fingerprinting will not work"
fi

# Verify QNAP mount
MUSIC_DIR="/Volumes/Public/Multimedia/Music"
if [ -d "$MUSIC_DIR" ]; then
    echo "[INFO] QNAP music directory found: $MUSIC_DIR"
else
    echo "[WARN] QNAP not mounted at $MUSIC_DIR"
    echo "       Mount it via Finder: smb://KITCHEN-TS-264.local/Public"
fi

# Create local directories
mkdir -p "${PROJECT_DIR}/reports"

echo ""
echo "[SUCCESS] Setup complete. Run: ./scripts/fix-metadata.sh"
