# Architecture

## Overview

clickwheel is a Python CLI that manages the full iPod sync workflow:

1. **Scan** — read metadata from a music library into a local SQLite index
2. **Fix** — clean up metadata and album art via beets
3. **Select** — interactively pick artists/albums that fit on the iPod
4. **Sync** — write files and the iTunesDB to the iPod

## Data Flow

```text
Music Library (NAS/local)
        |
        v
   clickwheel scan --> SQLite index (~/.clickwheel/clickwheel.db)
        |
        v
   clickwheel select --> playlist (saved in SQLite)
        |
        v
   clickwheel sync --> iPod (via vendored iOpenPodv2)
```

## Module Layout

```text
clickwheel/
  cli.py          # Typer command definitions
  config.py       # config loading (~/.clickwheel/config.yaml, env vars)
  db.py           # SQLite database (tracks, playlists, scrobble cache)
  library.py      # music file scanning (mutagen)
  output.py       # Rich console helpers (tables, status, errors)
  scrobble.py     # Last.fm scrobbling (pylast)
  ipod/           # vendored iOpenPodv2 (iTunesDB + ArtworkDB writers)
```

## Key Design Decisions

### Files stay in place

beets and clickwheel never move, copy, or rename source files. The music library is the single source of truth. Other apps (Plex) read from the same files.

### Local SQLite index

`clickwheel scan` reads metadata from the library and stores it in a local SQLite database. This avoids re-reading thousands of files over SMB every time you want to browse or select music.

### Selections are playlists

When you `clickwheel select`, the result is a playlist stored in SQLite with full track paths. Playlists track size so you can see capacity usage before syncing.

### No FLAC on iPod

Stock iPod firmware doesn't support FLAC. Rather than building a transcoding pipeline, FLAC files are excluded from selection. Convert them separately if needed.

### iPod database via vendored iOpenPodv2

The iPod's stock firmware requires a proprietary database (`iTunesDB`). We vendor iOpenPodv2 (MIT-licensed, ~2,000 lines) to write it directly — no libgpod dependency, no C extensions, pure Python.

### numpy is optional

numpy is only used for RGB565 artwork conversion in the ArtworkDB writer. At ~30MB installed, it's behind an `artwork` extra: `pipx install clickwheel[artwork]`.

## Dependencies

| Dependency | Purpose              | Install             |
| ---------- | -------------------- | ------------------- |
| Typer      | CLI framework        | pip (auto)          |
| Rich       | Terminal formatting  | pip (auto)          |
| tqdm       | Progress bars        | pip (auto)          |
| mutagen    | Audio metadata       | pip (auto)          |
| pylast     | Last.fm API          | pip (auto)          |
| beets      | Metadata cleanup     | pipx (user install) |
| Pillow     | Album art processing | pip (artwork extra) |
| numpy      | RGB565 conversion    | pip (artwork extra) |
