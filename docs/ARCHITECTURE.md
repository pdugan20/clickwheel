# Architecture

## Overview

clickwheel is split into two layers:

1. **Bash scripts** — one-time library maintenance (audit, metadata cleanup via beets)
2. **Python CLI** — ongoing iPod workflow (scan, select, sync)

The bash scripts are standalone and don't depend on the Python CLI. The Python CLI wraps beets for the `fix` command but otherwise operates independently.

## Data Flow

```text
Music Library (NAS/local)
        |
        v
   clickwheel scan ──> SQLite index (local)
        |
        v
   clickwheel select ──> playlist files (saved selections)
        |
        v
   clickwheel sync ──> iPod (via libgpod)
```

## Key Design Decisions

### Files stay in place

beets and clickwheel never move, copy, or rename source files. The music library is the single source of truth. Other apps (Plex) read from the same files.

### Local SQLite index

`clickwheel scan` reads metadata from the library and stores it in a local SQLite database. This avoids re-reading thousands of files over SMB every time you want to browse or select music. The index is rebuilt on each scan.

### Selections are playlists

When you `clickwheel select`, the result is a playlist file (m3u or a simple text list of paths). This is portable, human-readable, and easy to edit manually. Playlists are stored in `playlists/`.

### No FLAC on iPod

Stock iPod firmware doesn't support FLAC. Rather than building a transcoding pipeline into the sync command, FLAC files are excluded from selection. If you want FLAC albums on the iPod, convert them to ALAC/MP3 beforehand as a one-off batch job.

### iPod database via libgpod

The iPod's stock firmware requires a proprietary database (`iTunesDB`). We use libgpod's Python bindings to write to it. This lets the iPod display proper metadata, artist/album groupings, and album art — exactly like iTunes would set it up.

## Dependencies

| Dependency   | Purpose               | Install                              |
| ------------ | --------------------- | ------------------------------------ |
| Python 3.11+ | CLI runtime           | brew / system                        |
| Typer        | CLI framework         | pip                                  |
| Rich         | Terminal UI           | pip                                  |
| tqdm         | Progress bars         | pip                                  |
| beets        | Metadata cleanup      | pipx                                 |
| libgpod      | iPod database         | brew (libgpod) + pip (gpod bindings) |
| ffprobe      | Audio file inspection | brew (ffmpeg)                        |
| Chromaprint  | Audio fingerprinting  | brew (chromaprint)                   |
| ShellCheck   | Bash linting          | brew                                 |
| shfmt        | Bash formatting       | brew                                 |
