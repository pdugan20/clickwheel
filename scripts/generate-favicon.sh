#!/usr/bin/env bash
# Regenerate the rasterized favicon assets served by the MCP HTTP transport.
#
# Source of truth is clickwheel/mcp/assets/favicon.svg (the clickwheel mark).
# These rasters are what Google's favicon crawler consumes, which is what paints
# the Claude connector-list icon (https://www.google.com/s2/favicons?domain=clickwheel.fm).
#
# The SVG is taller than it is wide, so each raster is rendered preserving aspect
# and centered on a square transparent canvas (favicons must be square).
#
# Requires ImageMagick 7 (`magick`). Run from the repo root:
#   ./scripts/generate-favicon.sh
set -euo pipefail

cd "$(dirname "$0")/.."

ASSETS="clickwheel/mcp/assets"
SVG="$ASSETS/favicon.svg"
[ -f "$SVG" ] || {
    echo "missing $SVG" >&2
    exit 1
}

# Square master at high res, icon centered on a transparent canvas.
MASTER="$(mktemp -t clickwheel-fav-XXXX.png)"
trap 'rm -f "$MASTER"' EXIT
magick -background none "$SVG" -resize 256x256 -gravity center -extent 256x256 "$MASTER"

echo "Rasterizing $SVG -> $ASSETS"
magick "$MASTER" -resize 32x32 "$ASSETS/favicon-32.png"
magick "$MASTER" -resize 180x180 "$ASSETS/apple-touch-icon.png"
magick "$MASTER" -define icon:auto-resize=16,32,48 "$ASSETS/favicon.ico"

echo "Done:"
ls -l "$ASSETS"
