# Explicit FLAC → MP3 conversion (`clickwheel convert`)

**Date:** 2026-06-14
**Status:** Approved design — pending implementation plan

## Problem

Stock classic-iPod firmware can't decode FLAC, so clickwheel currently
excludes FLAC from iPod sync entirely (four `WHERE format != 'flac'` clauses
in `db.py`; documented in `docs/architecture.md`). When the user adds a
FLAC-only album (e.g. a new release) they have no way to get it onto the iPod.

This design adds an **explicit, opt-in** conversion step that produces iPod-
playable MP3s from selected FLAC albums. It deliberately does **not** add
transparent transcoding to the sync pipeline.

### Relationship to existing rules

- **Rule #4 ("Don't add transcoding")** is relaxed to: *no automatic/transparent
  transcoding in the sync path; explicit, user-invoked conversion is allowed.*
  This document is the record of that deliberate decision. Update Rule #4 and
  `docs/architecture.md` as part of implementation.
- **Rule #2 ("Never move or rename source files — Plex reads from the same
  library")** is honored: converted MP3s are written to a directory **outside**
  `music_dir`, so Plex never sees them and source FLACs are never touched.

## Goals

- Convert specific FLAC albums/artists (or all FLAC) to MP3 on demand.
- Converted tracks become first-class library tracks usable by
  `select` / `add-to-ipod` / `sync` / `diff` with **zero changes** to the
  sync pipeline.
- Incremental by default (Rule #10 house style): re-runs do zero work unless
  a source FLAC changed or `--force` is passed.
- Preserve all tags and embedded cover art into the MP3.

## Non-goals (v1)

- An MCP `convert` tool (long CPU-bound op; can be added later as a thin
  `actions` wrapper per Rule #11).
- Auto-cleanup of orphaned MP3s when a source FLAC is deleted.
- Transparent transcode-on-sync. Conversion stays decoupled.
- Formats other than MP3 320 kbps CBR.

## Architecture overview

```
clickwheel convert  (cli.py)
        │  interactive questionary picker  OR  --artist/--album/--all-flac flags
        ▼
actions.convert_tracks(specs, bitrate, force, progress_callback)   ← pure logic
        │
        ├─ db.get_flac_albums() / resolve FLAC source tracks
        ├─ skip if transcodes-cache hit and source mtime unchanged (unless --force)
        ├─ transcode.transcode_to_mp3(src, dest, bitrate)   → shells out to ffmpeg
        ├─ db.record_transcode(source_path, mtime, output_path, bitrate)
        └─ library.scan_file(output) + db.upsert_track(output)   ← index the MP3
        ▼
   transcode_dir/<album_artist>/<album>/<name>.mp3   (outside music_dir)
        ▼
   appears in select / add-to-ipod / sync / diff as an ordinary MP3
```

The key idea: `convert` **indexes its own outputs** into the `tracks` table.
Everything downstream already handles MP3s, so no sync-path change is needed.

## Components

### 1. Config (`clickwheel/config.py`)

Two new fields on `Config`:

| Field | Default | Meaning |
|-------|---------|---------|
| `transcode_dir` | `~/.clickwheel/transcoded` (under `project_dir`) | Where converted MP3s are written. Outside `music_dir`. |
| `transcode_bitrate` | `320` | MP3 CBR bitrate in kbps. |

Both overridable via `config.yaml` and env vars, per the existing config
precedence (env > `.env` > yaml).

### 2. New module `clickwheel/transcode.py`

Pure, framework-free logic (no Rich/typer/questionary), consistent with the
`actions.py` purity boundary.

- `find_ffmpeg() -> str | None` — locate the ffmpeg binary via `shutil.which`.
- `transcode_to_mp3(src: Path, dest: Path, bitrate: int) -> None` —
  shell out to ffmpeg:
  - `-map 0:a:0` audio + copy embedded cover art into an ID3 APIC frame
    (`-map 0:v? -c:v copy -id3v2_version 3`)
  - `-c:a libmp3lame -b:a {bitrate}k` (CBR)
  - `-map_metadata 0` to carry tags across
  - create parent dirs for `dest`; write atomically (temp file → rename) so a
    killed conversion never leaves a half-written MP3 that later looks valid.
  - raise `TranscodeError` on non-zero ffmpeg exit.

Output path: `transcode_dir/<album_artist>/<album>/<original_filename>.mp3`
(sanitize path components; reuse any existing sanitization helper if present).

### 3. Database (`clickwheel/db.py`)

New `transcodes` table:

```sql
CREATE TABLE IF NOT EXISTS transcodes (
    source_path  TEXT UNIQUE NOT NULL,
    source_mtime REAL,
    output_path  TEXT NOT NULL,
    bitrate      INTEGER,
    converted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Methods:
- `record_transcode(source_path, source_mtime, output_path, bitrate)` — upsert.
- `get_transcode(source_path) -> dict | None`.
- `list_transcodes() -> list[dict]`.
- `get_flac_albums() -> list[dict]` — FLAC albums for the picker, each with a
  converted/not-converted status derived from the `transcodes` table. (Existing
  artist/album queries intentionally exclude FLAC, so a dedicated query is
  needed.)
- `get_flac_tracks(artist=None, album=None) -> list[dict]` — resolve source
  FLAC tracks to convert for a given scope.

Cache-skip rule: skip a source if a `transcodes` row exists **and**
`source_mtime` matches the file's current mtime **and** the output MP3 still
exists on disk — unless `force=True`.

### 4. Orchestration (`clickwheel/actions.py`)

- `list_convertible_albums() -> list[dict]` — FLAC albums + conversion status.
- `convert_tracks(specs, *, bitrate=None, force=False, progress_callback=None) -> ConvertResult`
  - resolve FLAC sources from `specs` (artist/album scopes or all-FLAC),
  - skip cached/unchanged unless `force`,
  - run `transcode.transcode_to_mp3`,
  - `db.record_transcode(...)`,
  - index each output via `library.scan_file` + `db.upsert_track`,
  - aggregate counts.
- `ConvertResult` dataclass: `converted`, `skipped`, `failed` (with per-item
  detail for failures), `output_dir`.

New typed errors under `ClickwheelError`:
- `FfmpegNotFoundError` — raised when `find_ffmpeg()` returns `None`; message
  includes an install hint (`brew install ffmpeg`).
- `TranscodeError` — a single track failed to convert (carries source path +
  ffmpeg stderr tail).

### 5. CLI (`clickwheel/cli.py`)

New `convert` command:
- Bare → questionary checkbox of FLAC albums (✓/✗ converted marker),
  mirroring `select`.
- Flags: `--artist`, `--album`, `--all-flac`, `--bitrate`, `--force`.
- Resolves config, prints a plan summary (album count, track count, target
  bitrate, output dir) via `output.py` helpers, then runs.
- `tqdm` progress bar (many small items, per the progress convention).
- **No confirmation prompt** — conversion is non-destructive (writes new files,
  never modifies or deletes source FLACs). It still prints a clear summary.
- All output via `output.py` helpers (Rule #1). Lazy-imports questionary.

### 6. Indexing contract (critical invariant)

- Converted MP3s are indexed **by `convert`**, not by `scan`.
- `scan` walks only `music_dir`. It must neither rediscover the transcode dir
  nor mark transcoded tracks as missing. Verify the incremental scan's
  "mark missing" sweep is scoped to `music_dir` (it is — confirm in
  implementation) so converted tracks are never false-flagged.
- Reset path: delete the transcode dir (and/or `transcodes` rows) then
  re-run with `--force`.

## Error handling

- ffmpeg absent → `FfmpegNotFoundError` with install hint; command exits 1 via
  `output.error()` + `raise typer.Exit(1)`.
- A single track failing transcoding is collected into `ConvertResult.failed`
  and reported at the end; the run continues for the remaining tracks
  (partial success is representable, matching the sync/MCP envelope style).
- Source FLAC missing on disk at convert time → counted as a failure with a
  clear reason.

## Testing

- `transcode.py`: ffmpeg invocation mocked via `subprocess` — assert correct
  args (codec, bitrate, metadata/art mapping), atomic-write behavior, and
  `TranscodeError` on non-zero exit. (CI has no guaranteed LAME encoder.)
- `db.py`: `transcodes` CRUD, `get_flac_albums`/`get_flac_tracks` correctness.
- `actions.convert_tracks`: idempotency (unchanged re-run → zero ffmpeg calls),
  stale-source re-convert (mtime changed → re-runs), `--force` override,
  partial-failure aggregation, and that outputs get indexed into `tracks`.
- Invariant test: a `scan` over `music_dir` does **not** mark converted tracks
  (which live outside `music_dir`) as missing.
- Coverage stays at/above the 60% threshold.

## Docs to update

- `CLAUDE.md` Rule #4 — reword to the relaxed policy + add a `convert` entry to
  the command list.
- `docs/architecture.md` — replace the "no transcoding pipeline" note with the
  explicit-conversion design.
- `README` — document `convert`, `transcode_dir`, `transcode_bitrate`, and the
  ffmpeg prerequisite.
