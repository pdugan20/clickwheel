# Configuration

clickwheel reads from `~/.clickwheel/config.yaml`. Environment variables (`MUSIC_DIR`, `AUTO_SCAN`, etc.) override file values.

## Full schema

```yaml
# Required
music_dir: /Volumes/Music/Library

# iPod
ipod_capacity_gb: 64 # default: 64; only used for fit estimates

# Library auto-scan (see "How auto-scan works" below)
auto_scan: true # default: true
auto_scan_staleness_minutes: 1440 # default: 1440 = 24h

# Last.fm scrobbling (see "Last.fm scrobbling")
lastfm_api_key: your_key
lastfm_api_secret: your_secret
lastfm_username: your_username

# Database location (rarely changed)
db_path: ~/.clickwheel/library.db # default
```

## How auto-scan works

`select`, `edit`, `diff`, and `sync` check whether the library index is stale before running. The check is **two-tier**:

1. **Cheap probe** — stats the music directory and its top-level folders (~5s on SMB). If the most-recent child mtime is newer than the last full scan, the library has changed (new artist/album folders) and a full re-scan is triggered.
2. **24-hour fallback** — even if the cheap probe says "no change", a full re-scan runs once `auto_scan_staleness_minutes` has elapsed since the last scan. Catches cases the probe can't see (a new track in an existing album folder, since most filesystems don't propagate child-of-child mtimes).

The cheap probe is ~40× faster than a full SMB walk, so the practical cost of running the auto-scan on every command is minimal.

### Skip or tune

- Pass `--no-scan` to any command to skip both tiers entirely (use cached data).
- Set `auto_scan: false` in config to disable for the whole session.
- Lower `auto_scan_staleness_minutes` if you frequently add tracks within existing albums and want the fallback to fire more often.

### When you must scan manually

The cheap probe doesn't notice metadata-only edits to existing files (it can't see inside files). After running `clickwheel fix` or any external metadata editor, run `clickwheel scan` manually so the library index picks up the new tags.

The MCP server **never** auto-scans — chat tool calls always serve cached data. Run `clickwheel scan` from the terminal when you've added music; the next chat session will see it.

## Metadata cleanup (`fix`)

`clickwheel fix` uses [beets](https://beets.io/) to fetch album art, fill genres, and clean up tags. Install the extras first:

```bash
# pipx
pipx inject clickwheel 'clickwheel[fix]'

# pip
pip install 'clickwheel[fix]'
```

On first run, clickwheel generates a beets config at `~/.clickwheel/beets/config.yaml`. You can edit it to customize sources, matching thresholds, and so on. The config is set up so beets never moves or renames your files (other tools may rely on the existing paths — Plex, music players, etc.).

```bash
# fix one folder
clickwheel fix "Artist - Album Name"

# fix the whole library
clickwheel fix
```

## Last.fm scrobbling

clickwheel can submit your iPod listens to Last.fm.

1. Get an API key at [last.fm/api/account/create](https://www.last.fm/api/account/create).
2. Add the credentials to `~/.clickwheel/config.yaml` (the `lastfm_*` keys above).
3. Authorize once:

   ```bash
   clickwheel scrobble --auth
   ```

4. After that, run `clickwheel scrobble` any time your iPod is connected.

Plays are cached locally and tracked individually, so re-runs never duplicate-submit. If a submission batch fails (network blip, rate limit), the next run resumes where it left off.

## Database location

clickwheel stores its index in `~/.clickwheel/library.db` (SQLite, WAL mode). Override with `db_path` in config or `DB_PATH` env var. The database is safe to delete — running `clickwheel scan` rebuilds it from your music directory.
