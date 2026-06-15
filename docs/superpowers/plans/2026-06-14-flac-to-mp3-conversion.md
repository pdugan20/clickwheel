# FLAC → MP3 Conversion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit `clickwheel convert` command that transcodes selected FLAC albums to MP3 in a dedicated directory outside the music library, indexes the outputs, and lets them flow through the unchanged iPod sync pipeline.

**Architecture:** A new pure module `clickwheel/transcode.py` shells out to ffmpeg. `actions.convert_tracks` orchestrates: resolve FLAC sources → skip cached/unchanged → transcode → record in a new `transcodes` table → index the MP3 into `tracks`. The CLI `convert` command is a display adapter (interactive questionary picker + scripting flags). Converted MP3s live in `cfg.transcode_dir` (default `~/.clickwheel/transcoded`), outside `music_dir`, so Plex never sees them and `scan` never touches them.

**Tech Stack:** Python 3.11+, Typer, questionary, tqdm, mutagen, SQLite, ffmpeg (libmp3lame). Tests: pytest with subprocess mocking.

**Spec:** `docs/superpowers/specs/2026-06-14-flac-to-mp3-conversion-design.md`

---

## File Structure

- **Create** `clickwheel/transcode.py` — ffmpeg discovery + single-file transcode (pure logic, no Rich/typer).
- **Create** `tests/test_convert.py` — transcode module, `actions.convert_tracks`, and scan-invariant tests.
- **Modify** `clickwheel/config.py` — add `transcode_dir`, `transcode_bitrate`.
- **Modify** `clickwheel/db.py` — add `transcodes` table + `record_transcode`/`get_transcode`/`list_transcodes`/`get_flac_albums`/`get_flac_tracks`.
- **Modify** `clickwheel/actions.py` — add `FfmpegNotFoundError`, `ConvertResult`, `resolve_flac_sources`, `convert_tracks`, `list_convertible_albums`, `_safe_path_component`; fix Phase 3 missing-sweep scope.
- **Modify** `clickwheel/cli.py` — add `convert` command.
- **Modify** `tests/test_config.py`, `tests/test_db.py` — unit tests for new config + db methods.
- **Modify** `CLAUDE.md`, `docs/architecture.md`, `README.md` — relax Rule #4, document the command.

---

## Task 1: Config fields

**Files:**
- Modify: `clickwheel/config.py` (dataclass fields ~49-80, `__post_init__` ~86-91, `load_config` ~112-154, `_YAML_TO_ENV` ~20-44)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
def test_transcode_config_defaults(tmp_path):
    from clickwheel.config import Config

    cfg = Config(music_dir=tmp_path, project_dir=tmp_path)
    assert cfg.transcode_bitrate == 320
    assert cfg.transcode_dir == tmp_path / "transcoded"


def test_transcode_dir_override(tmp_path):
    from clickwheel.config import Config

    custom = tmp_path / "elsewhere"
    cfg = Config(music_dir=tmp_path, project_dir=tmp_path, transcode_dir=custom)
    assert cfg.transcode_dir == custom
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py::test_transcode_config_defaults -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'transcode_dir'` (or AttributeError).

- [ ] **Step 3: Add the fields and post-init defaulting**

In `clickwheel/config.py`, add two fields to the `Config` dataclass, immediately before `db_path: Path = field(init=False)`:

```python
    transcode_dir: Path | None = None
    transcode_bitrate: int = 320
```

In `__post_init__`, after the existing `self.db_path = self.project_dir / "clickwheel.db"` line, add:

```python
        self.transcode_dir = (
            Path(self.transcode_dir)
            if self.transcode_dir
            else self.project_dir / "transcoded"
        )
        self.transcode_bitrate = int(self.transcode_bitrate)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py::test_transcode_config_defaults tests/test_config.py::test_transcode_dir_override -v`
Expected: PASS

- [ ] **Step 5: Wire env/yaml override into `load_config`**

In `clickwheel/config.py`, add two entries to `_YAML_TO_ENV`:

```python
    "transcode_dir": "CLICKWHEEL_TRANSCODE_DIR",
    "transcode_bitrate": "CLICKWHEEL_TRANSCODE_BITRATE",
```

In the `return Config(...)` call inside `load_config`, add these two keyword args (anywhere before the closing paren):

```python
        transcode_dir=(os.environ.get("CLICKWHEEL_TRANSCODE_DIR") or None),
        transcode_bitrate=int(os.environ.get("CLICKWHEEL_TRANSCODE_BITRATE", 320)),
```

- [ ] **Step 6: Run the full config suite**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (all)

- [ ] **Step 7: Commit**

```bash
git add clickwheel/config.py tests/test_config.py
git commit -m "feat(config): add transcode_dir and transcode_bitrate settings"
```

---

## Task 2: `transcodes` table + cache methods

**Files:**
- Modify: `clickwheel/db.py` (`SCHEMA` ~8-106; add methods after `clear_tracks` ~157)
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_db.py`:

```python
def test_transcode_record_and_get(tmp_db):
    assert tmp_db.get_transcode("/music/a.flac") is None
    tmp_db.record_transcode("/music/a.flac", 123.0, "/t/a.mp3", 320)
    row = tmp_db.get_transcode("/music/a.flac")
    assert row["output_path"] == "/t/a.mp3"
    assert row["source_mtime"] == 123.0
    assert row["bitrate"] == 320


def test_transcode_record_upserts(tmp_db):
    tmp_db.record_transcode("/music/a.flac", 1.0, "/t/old.mp3", 256)
    tmp_db.record_transcode("/music/a.flac", 2.0, "/t/new.mp3", 320)
    row = tmp_db.get_transcode("/music/a.flac")
    assert row["output_path"] == "/t/new.mp3"
    assert row["source_mtime"] == 2.0
    assert len(tmp_db.list_transcodes()) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db.py::test_transcode_record_and_get -v`
Expected: FAIL — `AttributeError: 'Database' object has no attribute 'record_transcode'`.

- [ ] **Step 3: Add the table to `SCHEMA`**

In `clickwheel/db.py`, inside the `SCHEMA` string, add this block immediately before the `CREATE INDEX` lines (after the `genre_matches` table, ~line 98):

```sql
-- FLAC→MP3 transcode cache. Maps a source FLAC path (+ its mtime at
-- conversion time) to the MP3 written under cfg.transcode_dir. A re-run of
-- `clickwheel convert` skips a source whose mtime is unchanged and whose
-- output still exists, unless --force. CREATE IF NOT EXISTS covers existing
-- DBs, so no _migrate() entry is needed.
CREATE TABLE IF NOT EXISTS transcodes (
    source_path  TEXT PRIMARY KEY,
    source_mtime REAL,
    output_path  TEXT NOT NULL,
    bitrate      INTEGER,
    converted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

- [ ] **Step 4: Add the methods**

In `clickwheel/db.py`, add immediately after the `clear_tracks` method (~line 157):

```python
    def record_transcode(
        self, source_path: str, source_mtime: float, output_path: str, bitrate: int
    ) -> None:
        """Upsert a FLAC→MP3 conversion record."""
        self.conn.execute(
            """
            INSERT INTO transcodes (source_path, source_mtime, output_path, bitrate)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(source_path) DO UPDATE SET
                source_mtime = excluded.source_mtime,
                output_path = excluded.output_path,
                bitrate = excluded.bitrate,
                converted_at = CURRENT_TIMESTAMP
            """,
            (source_path, source_mtime, output_path, bitrate),
        )
        self.conn.commit()

    def get_transcode(self, source_path: str) -> dict | None:
        """Return the transcode record for a source FLAC path, or None."""
        row = self.conn.execute(
            "SELECT * FROM transcodes WHERE source_path = ?", (source_path,)
        ).fetchone()
        return dict(row) if row else None

    def list_transcodes(self) -> list[dict]:
        """Return all transcode records, newest first."""
        rows = self.conn.execute(
            "SELECT * FROM transcodes ORDER BY converted_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_db.py::test_transcode_record_and_get tests/test_db.py::test_transcode_record_upserts -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add clickwheel/db.py tests/test_db.py
git commit -m "feat(db): add transcodes cache table and accessors"
```

---

## Task 3: FLAC source queries

**Files:**
- Modify: `clickwheel/db.py` (add after `get_tracks_by_album` ~441)
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_db.py`:

```python
def _add_flac(db, path, artist="Olivia Rodrigo", album="GUTS", track=1):
    db.upsert_track(
        {
            "path": path,
            "title": f"T{track}",
            "artist": artist,
            "album_artist": artist,
            "album": album,
            "format": "flac",
            "track_number": track,
            "disc_number": 1,
            "file_size": 8_000_000,
        }
    )


def test_get_flac_tracks_scoped(tmp_db):
    _add_flac(tmp_db, "/m/o/g/01.flac", track=1)
    _add_flac(tmp_db, "/m/o/g/02.flac", track=2)
    _add_flac(tmp_db, "/m/other/x/01.flac", artist="Other", album="X")
    tmp_db.commit()

    guts = tmp_db.get_flac_tracks(artist="Olivia Rodrigo", album="GUTS")
    assert {t["path"] for t in guts} == {"/m/o/g/01.flac", "/m/o/g/02.flac"}
    assert len(tmp_db.get_flac_tracks()) == 3  # unscoped = all flac


def test_get_flac_albums_reports_conversion_status(tmp_db):
    _add_flac(tmp_db, "/m/o/g/01.flac", track=1)
    _add_flac(tmp_db, "/m/o/g/02.flac", track=2)
    tmp_db.commit()
    albums = tmp_db.get_flac_albums()
    assert len(albums) == 1
    assert albums[0]["artist"] == "Olivia Rodrigo"
    assert albums[0]["album"] == "GUTS"
    assert albums[0]["tracks"] == 2
    assert albums[0]["converted"] == 0

    tmp_db.record_transcode("/m/o/g/01.flac", 1.0, "/t/01.mp3", 320)
    assert tmp_db.get_flac_albums()[0]["converted"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db.py::test_get_flac_tracks_scoped -v`
Expected: FAIL — `AttributeError: 'Database' object has no attribute 'get_flac_tracks'`.

- [ ] **Step 3: Add the queries**

In `clickwheel/db.py`, add immediately after `get_tracks_by_album` (~line 441):

```python
    def get_flac_albums(self) -> list[dict]:
        """FLAC albums available to convert, with per-album conversion status.

        Unlike get_albums_by_artist (which excludes FLAC), this is the convert
        *source* list, so it INCLUDES format='flac'. `converted` counts source
        tracks already present in the transcodes cache.
        """
        rows = self.conn.execute(
            """
            SELECT
                COALESCE(NULLIF(t.album_artist, ''), t.artist) AS artist,
                t.album AS album,
                COUNT(*) AS tracks,
                SUM(t.file_size) AS total_bytes,
                SUM(CASE WHEN tr.source_path IS NOT NULL THEN 1 ELSE 0 END)
                    AS converted
            FROM tracks t
            LEFT JOIN transcodes tr ON tr.source_path = t.path
            WHERE t.format = 'flac' AND t.missing_since IS NULL
            GROUP BY artist, album
            ORDER BY artist COLLATE NOCASE, album COLLATE NOCASE
            """
        ).fetchall()
        return [dict(r) for r in rows]

    def get_flac_tracks(
        self, artist: str | None = None, album: str | None = None
    ) -> list[dict]:
        """Source FLAC tracks to convert, optionally scoped by artist/album.

        INCLUDES format='flac' (the convert source); excludes missing-on-disk.
        """
        sql = ["SELECT * FROM tracks WHERE format = 'flac' AND missing_since IS NULL"]
        params: list[str] = []
        if artist is not None:
            sql.append("AND (album_artist = ? OR artist = ?)")
            params += [artist, artist]
        if album is not None:
            sql.append("AND album = ?")
            params.append(album)
        sql.append("ORDER BY disc_number, track_number")
        rows = self.conn.execute(" ".join(sql), params).fetchall()
        return [dict(r) for r in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db.py::test_get_flac_tracks_scoped tests/test_db.py::test_get_flac_albums_reports_conversion_status -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add clickwheel/db.py tests/test_db.py
git commit -m "feat(db): add FLAC source queries for conversion"
```

---

## Task 4: `transcode.py` module

**Files:**
- Create: `clickwheel/transcode.py`
- Test: `tests/test_convert.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_convert.py`:

```python
"""Tests for FLAC→MP3 conversion: transcode module + actions.convert_tracks."""

from __future__ import annotations

from pathlib import Path

import pytest

# A minimal valid MP3 frame (matches tests/conftest.py music_dir_with_mp3).
MP3_BYTES = (b"\xff\xfb\x90\x00" + b"\x00" * 413) * 10


def test_transcode_to_mp3_invokes_ffmpeg_and_moves(tmp_path, monkeypatch):
    from clickwheel import transcode

    src = tmp_path / "a.flac"
    src.write_bytes(b"fakeflac")
    dest = tmp_path / "out" / "a.mp3"
    captured = {}

    class FakeProc:
        returncode = 0
        stderr = ""

    def fake_run(cmd, capture_output, text):
        captured["cmd"] = cmd
        Path(cmd[-1]).write_bytes(MP3_BYTES)  # write the .part file
        return FakeProc()

    monkeypatch.setattr(transcode.subprocess, "run", fake_run)
    transcode.transcode_to_mp3(src, dest, 320, "/usr/bin/ffmpeg")

    assert dest.exists()
    assert not dest.with_name(dest.name + ".part").exists()
    assert "libmp3lame" in captured["cmd"]
    assert "320k" in captured["cmd"]


def test_transcode_to_mp3_raises_on_failure(tmp_path, monkeypatch):
    from clickwheel import transcode

    class FakeProc:
        returncode = 1
        stderr = "boom"

    monkeypatch.setattr(transcode.subprocess, "run", lambda *a, **k: FakeProc())
    src = tmp_path / "a.flac"
    src.write_bytes(b"x")
    with pytest.raises(transcode.TranscodeError):
        transcode.transcode_to_mp3(src, tmp_path / "o.mp3", 320, "/usr/bin/ffmpeg")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_convert.py::test_transcode_to_mp3_invokes_ffmpeg_and_moves -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'clickwheel.transcode'`.

- [ ] **Step 3: Create the module**

Create `clickwheel/transcode.py`:

```python
"""FLAC→MP3 transcoding via ffmpeg.

Pure logic: no Rich, typer, tqdm, or questionary. The actions layer resolves
the ffmpeg binary once and passes it in; per-track failures raise
TranscodeError, which the caller aggregates.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


class TranscodeError(Exception):
    """A single ffmpeg transcode invocation failed."""

    def __init__(self, source: str, detail: str) -> None:
        super().__init__(f"Transcode failed for {source}: {detail}")
        self.source = source
        self.detail = detail


def find_ffmpeg() -> str | None:
    """Locate the ffmpeg binary on PATH, or None if not installed."""
    return shutil.which("ffmpeg")


def transcode_to_mp3(src: Path, dest: Path, bitrate: int, ffmpeg: str) -> None:
    """Transcode one FLAC to CBR MP3, preserving tags and embedded cover art.

    Writes atomically (temp ``.part`` file then os.replace) so an interrupted
    run never leaves a half-written MP3 that a later run mistakes for complete.
    Raises TranscodeError on non-zero ffmpeg exit.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(src),
        "-map",
        "0:a:0",  # first audio stream
        "-map",
        "0:v?",  # embedded cover art if present (optional)
        "-c:a",
        "libmp3lame",
        "-b:a",
        f"{bitrate}k",  # CBR
        "-c:v",
        "copy",  # copy art stream as-is into ID3 APIC
        "-id3v2_version",
        "3",
        "-map_metadata",
        "0",  # carry tags across
        "-f",
        "mp3",
        str(part),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        part.unlink(missing_ok=True)
        raise TranscodeError(str(src), (proc.stderr or "")[-2000:])
    os.replace(part, dest)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_convert.py -v`
Expected: PASS (both transcode tests)

- [ ] **Step 5: Commit**

```bash
git add clickwheel/transcode.py tests/test_convert.py
git commit -m "feat(transcode): add ffmpeg FLAC->MP3 module"
```

---

## Task 5: `actions.convert_tracks` orchestration

**Files:**
- Modify: `clickwheel/actions.py` (errors ~69-222; dataclasses near `ScanResult`; add functions)
- Test: `tests/test_convert.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_convert.py`:

```python
def _make_flac_source(tmp_db, music_dir):
    flac = music_dir / "Olivia Rodrigo" / "GUTS" / "01 bad idea right.flac"
    flac.parent.mkdir(parents=True, exist_ok=True)
    flac.write_bytes(b"fakeflac")
    tmp_db.upsert_track(
        {
            "path": str(flac),
            "title": "bad idea right!",
            "artist": "Olivia Rodrigo",
            "album_artist": "Olivia Rodrigo",
            "album": "GUTS",
            "format": "flac",
            "track_number": 1,
            "disc_number": 1,
            "file_size": 8,
            "mtime": flac.stat().st_mtime,
            "duration_seconds": 180.0,
        }
    )
    tmp_db.commit()
    return flac


def _patch_transcode(monkeypatch):
    from clickwheel import transcode

    monkeypatch.setattr(transcode, "find_ffmpeg", lambda: "/usr/bin/ffmpeg")

    def fake(src, dest, bitrate, ffmpeg):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(MP3_BYTES)

    monkeypatch.setattr(transcode, "transcode_to_mp3", fake)


def test_convert_tracks_transcodes_and_indexes(tmp_db, tmp_path, monkeypatch):
    from clickwheel import actions
    from clickwheel.config import Config

    music = tmp_path / "music"
    music.mkdir()
    flac = _make_flac_source(tmp_db, music)
    _patch_transcode(monkeypatch)
    cfg = Config(music_dir=music, project_dir=tmp_path)

    result = actions.convert_tracks(
        cfg,
        tmp_db,
        scopes=[{"artist": "Olivia Rodrigo", "album": "GUTS"}],
        bitrate=320,
    )

    assert len(result.converted) == 1
    out = Path(result.converted[0])
    assert out.exists() and out.suffix == ".mp3"
    assert str(out) in tmp_db.get_all_tracked_paths()  # indexed as playable mp3
    assert tmp_db.get_transcode(str(flac)) is not None  # cached


def test_convert_tracks_is_idempotent(tmp_db, tmp_path, monkeypatch):
    from clickwheel import actions
    from clickwheel.config import Config

    music = tmp_path / "music"
    music.mkdir()
    flac = _make_flac_source(tmp_db, music)
    _patch_transcode(monkeypatch)
    cfg = Config(music_dir=music, project_dir=tmp_path)
    scopes = [{"artist": "Olivia Rodrigo", "album": "GUTS"}]

    actions.convert_tracks(cfg, tmp_db, scopes=scopes, bitrate=320)
    second = actions.convert_tracks(cfg, tmp_db, scopes=scopes, bitrate=320)

    assert second.converted == []
    assert second.skipped == [str(flac)]


def test_convert_tracks_raises_without_ffmpeg(tmp_db, tmp_path, monkeypatch):
    from clickwheel import actions, transcode
    from clickwheel.config import Config

    monkeypatch.setattr(transcode, "find_ffmpeg", lambda: None)
    cfg = Config(music_dir=tmp_path, project_dir=tmp_path)
    with pytest.raises(actions.FfmpegNotFoundError):
        actions.convert_tracks(cfg, tmp_db, all_flac=True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_convert.py::test_convert_tracks_transcodes_and_indexes -v`
Expected: FAIL — `AttributeError: module 'clickwheel.actions' has no attribute 'convert_tracks'`.

- [ ] **Step 3: Add the error class**

In `clickwheel/actions.py`, in the error hierarchy section (after `IpodNotFoundError`, ~line 90), add:

```python
class FfmpegNotFoundError(ClickwheelError):
    """ffmpeg is required for FLAC conversion but isn't installed."""
```

- [ ] **Step 4: Add `ConvertResult` and helpers**

In `clickwheel/actions.py`, near the other `@dataclass` result types (search for `class ScanResult`), add:

```python
@dataclass
class ConvertResult:
    """Outcome of a convert_tracks run."""

    converted: list[str] = field(default_factory=list)  # output mp3 paths
    skipped: list[str] = field(default_factory=list)  # source paths (cache hit)
    failed: list[dict] = field(default_factory=list)  # {"path": str, "reason": str}
    output_dir: str = ""


def _safe_path_component(name: str) -> str:
    """Make a tag value safe to use as a single path segment."""
    cleaned = re.sub(r"[/\\:]", "_", name).strip()
    return cleaned or "Unknown"


def resolve_flac_sources(
    db: Database,
    *,
    scopes: list[dict] | None = None,
    all_flac: bool = False,
) -> list[dict]:
    """Resolve the set of source FLAC track dicts to convert.

    `all_flac=True` returns every FLAC in the library. Otherwise each scope is
    `{"artist": str, "album": str | None}`; album=None converts all of that
    artist's FLAC. Duplicates across scopes are removed (first occurrence wins).
    """
    if all_flac:
        return db.get_flac_tracks()
    seen: set[str] = set()
    out: list[dict] = []
    for sc in scopes or []:
        for t in db.get_flac_tracks(sc.get("artist"), sc.get("album")):
            if t["path"] not in seen:
                seen.add(t["path"])
                out.append(t)
    return out
```

- [ ] **Step 5: Add `convert_tracks` and `list_convertible_albums`**

In `clickwheel/actions.py`, add (near the other iPod/library actions):

```python
def list_convertible_albums(db: Database) -> list[dict]:
    """FLAC albums available to convert, with per-album conversion status."""
    return db.get_flac_albums()


def convert_tracks(
    cfg: Config,
    db: Database,
    *,
    scopes: list[dict] | None = None,
    all_flac: bool = False,
    bitrate: int | None = None,
    force: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
) -> ConvertResult:
    """Transcode the selected FLAC sources to MP3 under cfg.transcode_dir.

    Skips sources whose mtime is unchanged and whose output still exists
    (unless force=True), records each conversion in the transcodes cache, and
    indexes every produced MP3 into the tracks table so it flows through the
    normal sync pipeline. Raises FfmpegNotFoundError if ffmpeg is absent.
    """
    from clickwheel import transcode

    ffmpeg = transcode.find_ffmpeg()
    if ffmpeg is None:
        raise FfmpegNotFoundError(
            "ffmpeg not found. Install it with: brew install ffmpeg"
        )

    use_bitrate = bitrate or cfg.transcode_bitrate
    sources = resolve_flac_sources(db, scopes=scopes, all_flac=all_flac)
    result = ConvertResult(output_dir=str(cfg.transcode_dir))
    total = len(sources)

    for i, track in enumerate(sources, 1):
        src = Path(track["path"])
        label = primary_artist(track.get("artist"), track.get("album_artist"))
        album = track.get("album") or "Unknown Album"
        dest = (
            cfg.transcode_dir
            / _safe_path_component(label)
            / _safe_path_component(album)
            / (src.stem + ".mp3")
        )

        try:
            cur_mtime = src.stat().st_mtime
        except OSError:
            result.failed.append(
                {"path": str(src), "reason": "source missing on disk"}
            )
            if progress_callback:
                progress_callback(i, total)
            continue

        if not force:
            cached = db.get_transcode(str(src))
            if (
                cached
                and cached["source_mtime"] == cur_mtime
                and Path(cached["output_path"]).exists()
            ):
                result.skipped.append(str(src))
                if progress_callback:
                    progress_callback(i, total)
                continue

        try:
            transcode.transcode_to_mp3(src, dest, use_bitrate, ffmpeg)
        except transcode.TranscodeError as e:
            result.failed.append(
                {"path": str(src), "reason": e.detail or "ffmpeg error"}
            )
            if progress_callback:
                progress_callback(i, total)
            continue

        db.record_transcode(str(src), cur_mtime, str(dest), use_bitrate)
        scanned = scan_file(dest)
        if scanned:
            db.upsert_track(scanned)
        result.converted.append(str(dest))
        if progress_callback:
            progress_callback(i, total)

    db.commit()
    return result
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_convert.py -v`
Expected: PASS (all convert tests)

- [ ] **Step 7: Commit**

```bash
git add clickwheel/actions.py tests/test_convert.py
git commit -m "feat(actions): add convert_tracks FLAC->MP3 orchestration"
```

---

## Task 6: Scan invariant — don't flag converted tracks as missing

**Files:**
- Modify: `clickwheel/actions.py` (`scan_library` Phase 3, ~471-475)
- Test: `tests/test_convert.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_convert.py`:

```python
def test_scan_does_not_mark_converted_tracks_missing(tmp_db, tmp_path):
    from clickwheel import actions
    from clickwheel.config import Config

    music = tmp_path / "music"
    music.mkdir()
    cfg = Config(music_dir=music, project_dir=tmp_path)

    # A converted mp3 indexed under transcode_dir (OUTSIDE music_dir).
    conv_path = str(cfg.transcode_dir / "A" / "B" / "x.mp3")
    tmp_db.upsert_track(
        {"path": conv_path, "format": "mp3", "artist": "A", "album": "B",
         "file_size": 1, "mtime": 1.0}
    )
    # A real library track that has since vanished from disk.
    gone = str(music / "gone.mp3")
    tmp_db.upsert_track(
        {"path": gone, "format": "mp3", "artist": "C", "album": "D",
         "file_size": 1, "mtime": 1.0}
    )
    tmp_db.commit()

    actions.scan_library(cfg, tmp_db)  # incremental

    tracked = tmp_db.get_all_tracked_paths()
    assert conv_path in tracked  # converted track preserved
    assert gone not in tracked  # vanished library track flagged missing
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_convert.py::test_scan_does_not_mark_converted_tracks_missing -v`
Expected: FAIL — `assert conv_path in tracked` fails (the converted track gets wrongly marked missing).

- [ ] **Step 3: Scope the missing-sweep to `music_dir`**

In `clickwheel/actions.py`, replace the Phase 3 block (currently ~471-475):

```python
    # Phase 3: detect deleted files (incremental only)
    if not full:
        disk_paths = {str(p) for p in disk_files}
        missing_paths = db_paths - disk_paths
        if missing_paths:
            result.missing = db.mark_missing(missing_paths)
```

with:

```python
    # Phase 3: detect deleted files (incremental only)
    if not full:
        disk_paths = {str(p) for p in disk_files}
        # Only sweep tracks that live under music_dir. Tracks indexed from
        # outside it (e.g. `clickwheel convert` MP3s in cfg.transcode_dir) are
        # owned by their producer, not scan, and must not be flagged missing.
        missing_paths = {
            p
            for p in (db_paths - disk_paths)
            if Path(p).is_relative_to(cfg.music_dir)
        }
        if missing_paths:
            result.missing = db.mark_missing(missing_paths)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_convert.py::test_scan_does_not_mark_converted_tracks_missing -v`
Expected: PASS

- [ ] **Step 5: Run the scan/library suites to check for regressions**

Run: `uv run pytest tests/test_library.py tests/test_autoscan.py tests/test_convert.py -v`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add clickwheel/actions.py tests/test_convert.py
git commit -m "fix(scan): scope missing-sweep to music_dir so converted tracks survive"
```

---

## Task 7: `convert` CLI command

**Files:**
- Modify: `clickwheel/cli.py` (imports ~10-54; add command near `select`)
- Test: `tests/test_convert.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_convert.py`:

```python
def test_convert_command_registered():
    from typer.testing import CliRunner

    from clickwheel.cli import app

    result = CliRunner().invoke(app, ["convert", "--help"])
    assert result.exit_code == 0
    assert "Convert FLAC" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_convert.py::test_convert_command_registered -v`
Expected: FAIL — exit code non-zero / "No such command 'convert'".

- [ ] **Step 3: Add `FfmpegNotFoundError` to the CLI imports**

In `clickwheel/cli.py`, add `FfmpegNotFoundError,` to the alphabetical `from clickwheel.actions import (...)` block (after `EjectFailedError,`).

- [ ] **Step 4: Add the command**

In `clickwheel/cli.py`, add immediately after the `select` command (after its closing `db.close()`, ~line 269):

```python
@app.command(rich_help_panel="Library")
def convert(
    artist: str = typer.Option(
        "", "--artist", "-a", help="Convert FLAC for this artist"
    ),
    album: str = typer.Option(
        "", "--album", help="Restrict to this album (use with --artist)"
    ),
    all_flac: bool = typer.Option(
        False, "--all-flac", help="Convert every FLAC album in the library"
    ),
    bitrate: int = typer.Option(
        0, "--bitrate", help="MP3 CBR kbps (default: config transcode_bitrate)"
    ),
    force: bool = typer.Option(
        False, "--force", help="Re-convert even if already converted"
    ),
    no_scan: bool = typer.Option(
        False, "--no-scan", help="Skip automatic library scan"
    ),
) -> None:
    """Convert FLAC albums to iPod-playable MP3."""
    from clickwheel.transcode import find_ffmpeg

    cfg = load_config()
    db = Database(cfg.db_path)
    if not no_scan:
        maybe_auto_scan(cfg, db)

    if find_ffmpeg() is None:
        error("ffmpeg not found. Install it with: brew install ffmpeg")
        db.close()
        raise typer.Exit(1)

    scopes: list[dict] = []
    if all_flac:
        pass  # resolved by the all_flac flag below
    elif artist:
        scopes = [{"artist": artist, "album": album or None}]
    else:
        import questionary

        albums = actions.list_convertible_albums(db)
        if not albums:
            warn("No FLAC albums found to convert.")
            db.close()
            raise typer.Exit(0)
        choices = [
            questionary.Choice(
                title=(
                    f"{a['artist']} — {a['album']}  "
                    f"({a['tracks']} tracks, {_fmt_size(a['total_bytes'] or 0)})"
                    + ("  ✓ converted" if a["converted"] >= a["tracks"] else "")
                ),
                value={"artist": a["artist"], "album": a["album"]},
            )
            for a in albums
        ]
        picked = questionary.checkbox(
            "Select FLAC albums to convert (space to toggle, enter to confirm):",
            choices=choices,
        ).ask()
        if not picked:
            db.close()
            raise typer.Exit(0)
        scopes = picked

    use_bitrate = bitrate or cfg.transcode_bitrate
    sources = actions.resolve_flac_sources(
        db, scopes=None if all_flac else scopes, all_flac=all_flac
    )
    if not sources:
        warn("No FLAC tracks matched.")
        db.close()
        raise typer.Exit(0)

    status(f"Converting {len(sources)} tracks to MP3 @ {use_bitrate} kbps")
    dim(f"Output: {cfg.transcode_dir}")

    with tqdm(total=len(sources), desc="Transcoding", unit="track") as bar:
        result = actions.convert_tracks(
            cfg,
            db,
            scopes=None if all_flac else scopes,
            all_flac=all_flac,
            bitrate=use_bitrate,
            force=force,
            progress_callback=lambda done, _total: bar.update(done - bar.n),
        )

    success(
        f"Converted {len(result.converted)}, "
        f"skipped {len(result.skipped)} (already current), "
        f"failed {len(result.failed)}."
    )
    for f in result.failed:
        warn(f"  ✗ {f['path']}: {f['reason']}")
    dim("Add them to the iPod with `clickwheel select` or `clickwheel sync`.")
    db.close()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_convert.py::test_convert_command_registered -v`
Expected: PASS

- [ ] **Step 6: Lint check (output helper rule + formatting)**

Run: `uv run ruff check clickwheel/cli.py clickwheel/actions.py clickwheel/transcode.py && uv run ruff format --check clickwheel/`
Expected: PASS — no direct `console.print()` (Rule #1), no lint errors.

- [ ] **Step 7: Commit**

```bash
git add clickwheel/cli.py tests/test_convert.py
git commit -m "feat(cli): add convert command for FLAC->MP3"
```

---

## Task 8: Docs + rule update

**Files:**
- Modify: `CLAUDE.md` (Rule #4 ~line "FLAC files are excluded"; Commands list)
- Modify: `docs/architecture.md` (~line 72 "no transcoding pipeline" note)
- Modify: `README.md` (command list + config section)

- [ ] **Step 1: Relax Rule #4 in `CLAUDE.md`**

Replace the Rule #4 text:

```
4. **FLAC files are excluded from iPod sync** — stock iPod firmware doesn't support FLAC. Don't add transcoding.
```

with:

```
4. **FLAC is excluded from the iPod *sync* path** — stock iPod firmware can't decode FLAC, so sync/select/add-to-ipod never copy FLAC directly. There is NO transparent/automatic transcoding in the sync path. The explicit `clickwheel convert` command (FLAC→MP3 into `transcode_dir`, outside `music_dir`) is the sanctioned way to get FLAC onto the iPod; it indexes its MP3 outputs so they then flow through the normal pipeline. See `docs/superpowers/specs/2026-06-14-flac-to-mp3-conversion-design.md`.
```

- [ ] **Step 2: Add `convert` to the `CLAUDE.md` Commands list**

After the `clickwheel scan` bullet, add:

```
- `clickwheel convert` — transcode selected FLAC albums to MP3 (interactive picker or `--artist`/`--album`/`--all-flac`); writes to `transcode_dir` and indexes the results
```

- [ ] **Step 3: Update `docs/architecture.md`**

Replace the note around line 72 ("Rather than building a transcoding pipeline, FLAC files are excluded from selection. Convert them separately if needed.") with:

```
Stock iPod firmware doesn't decode FLAC, so the sync path excludes FLAC at the
DB query layer. To put a FLAC album on the iPod, run `clickwheel convert`: it
transcodes FLAC to CBR MP3 (default 320 kbps, libmp3lame) into `transcode_dir`
(default `~/.clickwheel/transcoded`, outside `music_dir` so Plex is unaffected),
records each conversion in the `transcodes` cache, and indexes the MP3s into the
library so `select`/`sync` treat them as ordinary MP3s. `scan`'s missing-sweep is
scoped to `music_dir`, so it never touches the converted files.
```

- [ ] **Step 4: Update `README.md`**

Add `convert` to the command list and document `transcode_dir` / `transcode_bitrate` in the configuration section, plus the ffmpeg prerequisite (`brew install ffmpeg`). Match the surrounding README style for command and config entries.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/architecture.md README.md
git commit -m "docs: document convert command and relax FLAC rule"
```

---

## Final verification

- [ ] **Run the full suite with coverage**

Run: `uv run pytest --cov=clickwheel --cov-report=term-missing`
Expected: all pass; coverage ≥ 60% (the threshold in CLAUDE.md).

- [ ] **Lint + typecheck**

Run: `make lint && make typecheck`
Expected: PASS

- [ ] **Manual smoke (optional, needs ffmpeg + real FLAC)**

Run: `clickwheel convert --artist "Olivia Rodrigo" --album "GUTS"` then `clickwheel sync` (or `select`). Confirm MP3s land in `~/.clickwheel/transcoded/...` and appear on the iPod.

---

## Self-review notes

- **Spec coverage:** config (T1) ✓, transcodes table (T2) ✓, FLAC queries (T3) ✓, transcode module w/ art+tags+atomic write (T4) ✓, convert_tracks + errors + idempotency (T5) ✓, indexing contract / scan invariant (T6) ✓, CLI interactive+flags (T7) ✓, docs incl. Rule #4 (T8) ✓. MCP tool + orphan cleanup explicitly out of scope per spec.
- **Type consistency:** `convert_tracks(scopes=, all_flac=, bitrate=, force=, progress_callback=)`, `resolve_flac_sources(scopes=, all_flac=)`, `ConvertResult(converted, skipped, failed, output_dir)`, `transcode_to_mp3(src, dest, bitrate, ffmpeg)`, `TranscodeError(source, detail)`, `record_transcode(source_path, source_mtime, output_path, bitrate)` — referenced identically across tasks.
- **No placeholders:** every code/test step contains full content.
