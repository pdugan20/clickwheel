#!/usr/bin/env bash
# Regenerate the favicon assets served by the MCP HTTP transport.
#
# Source of truth is the inlined SVG in clickwheel/mcp/_runtime.py
# (SERVER_ICON) — the same orange clickwheel mark used as the MCP protocol
# icon. This rasterizes it to the formats Google's favicon crawler wants
# (.ico + PNG), which is what drives the Claude connector-list icon
# (https://www.google.com/s2/favicons?domain=clickwheel.fm).
#
# Requires ImageMagick 7 (`magick`). Run from the repo root:
#   ./scripts/generate-favicon.sh
set -euo pipefail

cd "$(dirname "$0")/.."

PY=".venv/bin/python"
[ -x "$PY" ] || PY="python3"

ASSETS="clickwheel/mcp/assets"
mkdir -p "$ASSETS"

TMP_SVG="$(mktemp -t clickwheel-icon-XXXX.svg)"
trap 'rm -f "$TMP_SVG"' EXIT

# Decode the data-URI SVG out of SERVER_ICON so the asset never drifts from
# the protocol icon.
"$PY" - "$TMP_SVG" <<'PY'
import base64, sys
from clickwheel.mcp._runtime import SERVER_ICON

b64 = SERVER_ICON.src.split(",", 1)[1]
with open(sys.argv[1], "wb") as fh:
    fh.write(base64.b64decode(b64))
PY

echo "Rasterizing $TMP_SVG -> $ASSETS"
magick -background none "$TMP_SVG" -depth 8 -resize 32x32   "$ASSETS/favicon-32.png"
magick -background none "$TMP_SVG" -depth 8 -resize 180x180 "$ASSETS/apple-touch-icon.png"
magick -background none "$TMP_SVG" -depth 8 -define icon:auto-resize=16,32,48 "$ASSETS/favicon.ico"

echo "Done:"
ls -l "$ASSETS"
