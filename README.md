# Music Library Tools

Tools for auditing, cleaning, and syncing a music library from a QNAP NAS to a flash-modded iPod 4th Gen (Click Wheel).

## Setup

- **Source**: QNAP KITCHEN-TS-264, mounted at `/Volumes/Public/Multimedia/Music`
- **Backup**: QNAP BSMNT-TS-251 (backup of KITCHEN)
- **iPod**: 4th Gen Click Wheel (A1059), flash modded (~64GB, confirm exact size)
- **Plex**: Library currently reads from the same source files

## Library Stats

- ~12,000 audio files (11,340 MP3, 456 M4A, 231 FLAC)
- ~90 GB total (exceeds iPod capacity, subset selection required)

## Project Structure

```text
beets/              # beets configuration
  config.yaml       # beets config pointing at QNAP library
scripts/            # automation scripts
  audit.sh          # metadata/art audit (non-destructive)
  fix-metadata.sh   # apply metadata fixes via beets
  convert.sh        # FLAC conversion for iPod compatibility
  sync-ipod.sh      # stage and sync subset to iPod
playlists/          # iPod subset definitions (m3u, text lists)
reports/            # audit output and logs
```

## Workflow

1. **Audit** — scan library, report on metadata quality and missing album art
2. **Review** — inspect audit report, decide what to fix
3. **Clean** — apply metadata fixes (beets), fetch album art
4. **Select** — define iPod subset (playlist, artist list, etc.)
5. **Stage** — rsync selected files to local staging directory
6. **Sync** — push staged files to iPod

## Constraints

- All metadata changes affect Plex (same source files) — changes should be improvements only
- Metadata snapshot taken before any writes for rollback reference
- FLAC files must be converted (MP3/AAC/ALAC) for stock iPod firmware
- Network mount must be stable during audit/clean phases
