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
  db.py           # SQLite database (tracks, playlists, scrobble cache, scan metadata)
  library.py      # music file scanning (mutagen)
  autoscan.py     # incremental library scan (mtime+size comparison)
  output.py       # Rich console helpers (tables, spinners, panels, errors)
  scrobble.py     # Last.fm scrobbling + web auth (pylast)
  ipod/           # vendored iOpenPodv2 (iTunesDB + ArtworkDB writers)
```

## Key Design Decisions

### Files stay in place

beets and clickwheel never move, copy, or rename source files. The music library is the single source of truth. Other apps (Plex) read from the same files.

### Local SQLite index

`clickwheel scan` reads metadata from the library and stores it in a local SQLite database. This avoids re-reading thousands of files over SMB every time you want to browse or select music. Scans are incremental by default — only files whose mtime or size changed are re-read. Commands like `select`, `edit`, `diff`, and `sync` auto-scan if the last scan is older than a configurable threshold (default: 30 minutes).

### Selections are playlists

When you `clickwheel select`, the result is a playlist stored in SQLite with full track paths. Playlists track size so you can see capacity usage before syncing.

### No FLAC on iPod

Stock iPod firmware doesn't support FLAC. Rather than building a transcoding pipeline, FLAC files are excluded from selection. Convert them separately if needed.

### iPod database via vendored iOpenPodv2

The iPod's stock firmware requires a proprietary database (`iTunesDB`). We vendor iOpenPodv2 (MIT-licensed, ~2,000 lines) to write it directly — no libgpod dependency, no C extensions, pure Python.

### numpy is optional

numpy is only used for RGB565 artwork conversion in the ArtworkDB writer. At ~30MB installed, it's behind an `artwork` extra: `pipx install clickwheel[artwork]`.

### Last.fm auth via web flow

Scrobbling requires a Last.fm session key, obtained through a one-time browser auth flow (`clickwheel scrobble --auth`). The session key is saved to `~/.clickwheel/config.yaml` and never expires unless the user revokes it. No passwords are stored.

## Dependencies

| Dependency  | Purpose              | Install             |
| ----------- | -------------------- | ------------------- |
| Typer       | CLI framework        | pip (auto)          |
| Rich        | Terminal formatting  | pip (auto)          |
| questionary | Interactive prompts  | pip (auto)          |
| tqdm        | Progress bars        | pip (auto)          |
| mutagen     | Audio metadata       | pip (auto)          |
| pylast      | Last.fm API          | pip (auto)          |
| beets       | Metadata cleanup     | pip (fix extra)     |
| Pillow      | Album art processing | pip (fix extra)     |
| numpy       | RGB565 conversion    | pip (artwork extra) |
