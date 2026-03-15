# Music Library Tools

Audit, clean metadata/album art, and sync a music library to an iPod Classic (stock firmware).

## Prerequisites

- macOS with [Homebrew](https://brew.sh)
- Music library accessible via local or network mount
- [AcoustID API key](https://acoustid.org/my-applications) (free, for audio fingerprinting)
- iPod Classic (for sync features)

## Quick Start

```bash
git clone https://github.com/pdugan20/music-library-tools.git
cd music-library-tools
cp .env.example .env        # edit with your music path + API key
./scripts/setup.sh          # install dependencies, configure beets
./scripts/audit.sh          # scan library (read-only)
./scripts/fix-metadata.sh   # fix tags, art, genres
```

## Configuration

All scripts read from `.env` in the project root:

```bash
MUSIC_DIR=/path/to/your/music       # local path or network mount
ACOUSTID_API_KEY=your_key_here      # from acoustid.org
```

## Project Structure

```text
beets/              # beets configuration
  config.yaml       # beets config (paths injected from .env)
scripts/
  setup.sh          # install dependencies, configure beets
  audit.sh          # metadata/art quality audit (non-destructive)
  fix-metadata.sh   # apply metadata fixes via beets
playlists/          # iPod subset definitions
reports/            # audit output and logs (gitignored)
```

## Workflow

1. **Audit** — scan library, report on metadata quality and missing album art
2. **Review** — inspect reports, decide what to fix
3. **Clean** — apply metadata fixes (beets), fetch album art, fill genres
4. **Select** — define iPod subset (playlist or artist/album list)
5. **Sync** — push selected files to iPod via gpod-utils

## Tools

- **[beets](https://beets.io)** — music library manager for metadata cleanup
- **[ffprobe](https://ffmpeg.org)** — audio file inspection (part of ffmpeg)
- **[Chromaprint](https://acoustid.org/chromaprint)** — audio fingerprinting
- **[gpod-utils](https://github.com/whatdoineed2do/gpod-utils)** — CLI iPod sync (stock firmware)

## Notes

- Metadata changes are written in-place. If your music library is shared with other apps (e.g., Plex), changes will be picked up on their next scan.
- beets is configured to never move or rename files.
- The audit script is fully non-destructive (read-only).
- FLAC files need conversion (ALAC/MP3) for iPod compatibility.
