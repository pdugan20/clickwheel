#!/usr/bin/env bash
# audit.sh — Scan music library and report on metadata quality and album art
# Non-destructive: reads files only, writes report to ../reports/

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
REPORT_DIR="${PROJECT_DIR}/reports"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT_FILE="${REPORT_DIR}/audit_${TIMESTAMP}.txt"

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

echo "[INFO] Starting music library audit..."
echo "[INFO] Source: $MUSIC_DIR"
echo "[INFO] Report: $REPORT_FILE"

# Header
{
    echo "Music Library Audit Report"
    echo "========================="
    echo "Date: $(date)"
    echo "Source: $MUSIC_DIR"
    echo ""
} >"$REPORT_FILE"

# File format breakdown
echo "[INFO] Counting files by format..."
{
    echo "File Format Summary"
    echo "-------------------"
    find "$MUSIC_DIR" -type f \( -iname "*.mp3" -o -iname "*.flac" -o -iname "*.m4a" \
        -o -iname "*.aac" -o -iname "*.wav" -o -iname "*.aiff" -o -iname "*.ogg" \
        -o -iname "*.wma" \) 2>/dev/null | awk -F. '{print tolower($NF)}' | sort | uniq -c | sort -rn
    echo ""
} >>"$REPORT_FILE"

# Check for embedded album art using ffprobe
echo "[INFO] Checking for missing album art (this may take a while)..."
MISSING_ART_FILE="${REPORT_DIR}/missing_art_${TIMESTAMP}.txt"
HAS_ART_COUNT=0
NO_ART_COUNT=0

{
    echo "Files Missing Embedded Album Art"
    echo "--------------------------------"
} >"$MISSING_ART_FILE"

while IFS= read -r -d '' file; do
    if ffprobe -v quiet -select_streams v -show_entries stream=codec_type "$file" 2>/dev/null | grep -q "video"; then
        HAS_ART_COUNT=$((HAS_ART_COUNT + 1))
    else
        NO_ART_COUNT=$((NO_ART_COUNT + 1))
        echo "$file" >>"$MISSING_ART_FILE"
    fi
done < <(find "$MUSIC_DIR" -type f \( -iname "*.mp3" -o -iname "*.flac" -o -iname "*.m4a" \) -print0 2>/dev/null)

{
    echo "Album Art Summary"
    echo "-----------------"
    echo "Files with embedded art: $HAS_ART_COUNT"
    echo "Files missing art:       $NO_ART_COUNT"
    echo "See: $MISSING_ART_FILE"
    echo ""
} >>"$REPORT_FILE"

# Check for missing/empty metadata fields using ffprobe
echo "[INFO] Checking metadata fields..."
MISSING_META_FILE="${REPORT_DIR}/missing_metadata_${TIMESTAMP}.txt"
GOOD_META=0
BAD_META=0

{
    echo "Files With Missing/Empty Metadata"
    echo "----------------------------------"
    echo "Format: file | missing_fields"
} >"$MISSING_META_FILE"

while IFS= read -r -d '' file; do
    MISSING_FIELDS=""

    TAGS=$(ffprobe -v quiet -show_entries format_tags=artist,album,title,track,genre \
        -of default=noprint_wrappers=1 "$file" 2>/dev/null)

    for field in artist album title track genre; do
        VALUE=$(echo "$TAGS" | grep -i "TAG:${field}=" | cut -d= -f2- || true)
        if [ -z "$VALUE" ]; then
            MISSING_FIELDS="${MISSING_FIELDS}${field},"
        fi
    done

    if [ -n "$MISSING_FIELDS" ]; then
        BAD_META=$((BAD_META + 1))
        echo "$file | ${MISSING_FIELDS%,}" >>"$MISSING_META_FILE"
    else
        GOOD_META=$((GOOD_META + 1))
    fi
done < <(find "$MUSIC_DIR" -type f \( -iname "*.mp3" -o -iname "*.flac" -o -iname "*.m4a" \) -print0 2>/dev/null)

{
    echo "Metadata Completeness"
    echo "---------------------"
    echo "Files with complete metadata: $GOOD_META"
    echo "Files with missing fields:    $BAD_META"
    echo "See: $MISSING_META_FILE"
    echo ""
} >>"$REPORT_FILE"

# Total size
TOTAL_SIZE=$(du -sh "$MUSIC_DIR" 2>/dev/null | cut -f1)
{
    echo "Library Size"
    echo "------------"
    echo "Total: $TOTAL_SIZE"
    echo ""
} >>"$REPORT_FILE"

echo "[INFO] Audit complete."
echo "[INFO] Report: $REPORT_FILE"
echo "[INFO] Missing art list: $MISSING_ART_FILE"
echo "[INFO] Missing metadata list: $MISSING_META_FILE"

# Print summary to terminal
echo ""
echo "=== Summary ==="
echo "Files with art:      $HAS_ART_COUNT"
echo "Files missing art:   $NO_ART_COUNT"
echo "Complete metadata:   $GOOD_META"
echo "Incomplete metadata: $BAD_META"
echo "Total size:          $TOTAL_SIZE"
