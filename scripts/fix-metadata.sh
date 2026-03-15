#!/usr/bin/env bash
# fix-metadata.sh — Import library into beets (as-is), then fix art and genre
#
# Uses -A flag to skip MusicBrainz lookups entirely (fast catalog).
# Then uses beets plugins to fetch art and fill genres.
#
# Usage:
#   ./scripts/fix-metadata.sh              # run full library
#   ./scripts/fix-metadata.sh "Daft Punk"  # run on specific artist folder

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
export BEETSDIR="${PROJECT_DIR}/beets"
REPORT_DIR="${PROJECT_DIR}/reports"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Load config
if [ -f "${PROJECT_DIR}/.env" ]; then
    source "${PROJECT_DIR}/.env"
fi

MUSIC_DIR="${MUSIC_DIR:?MUSIC_DIR not set. Copy .env.example to .env and configure it.}"

mkdir -p "$REPORT_DIR"

if [ ! -d "$MUSIC_DIR" ]; then
    echo "[ERROR] Music directory not found: $MUSIC_DIR"
    exit 1
fi

# Determine target
if [ -n "${1:-}" ]; then
    TARGET="${MUSIC_DIR}/${1}"
    if [ ! -d "$TARGET" ]; then
        echo "[ERROR] Directory not found: $TARGET"
        exit 1
    fi
    echo "[INFO] Target: $TARGET"
else
    TARGET="$MUSIC_DIR"
    echo "[INFO] Target: entire library"
fi

# Phase 1: Import into beets database as-is (no MusicBrainz, no tag changes)
echo ""
echo "=== Phase 1: Cataloging library (as-is, no lookups) ==="
beet import -qA "$TARGET" 2>&1 | tee "${REPORT_DIR}/import_${TIMESTAMP}.log"

echo ""
echo "[INFO] Library stats:"
beet stats

# Phase 2: Fetch missing album art
echo ""
echo "=== Phase 2: Fetching missing album art ==="
beet fetchart -f 2>&1 | tee "${REPORT_DIR}/fetchart_${TIMESTAMP}.log"

# Phase 3: Embed art into files that are missing it
echo ""
echo "=== Phase 3: Embedding album art ==="
beet embedart -y 2>&1 | tee "${REPORT_DIR}/embedart_${TIMESTAMP}.log"

# Phase 4: Fill missing genres
echo ""
echo "=== Phase 4: Filling missing genres ==="
beet lastgenre 2>&1 | tee "${REPORT_DIR}/lastgenre_${TIMESTAMP}.log"

# Phase 5: Write all tag changes to files
echo ""
echo "=== Phase 5: Writing tags to files ==="
echo "yes" | beet write 2>&1 | tee "${REPORT_DIR}/write_${TIMESTAMP}.log"

echo ""
echo "[INFO] Done. Check reports in: $REPORT_DIR"
echo "[INFO] Beets database: ${BEETSDIR}/library.db"
