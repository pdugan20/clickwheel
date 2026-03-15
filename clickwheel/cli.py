"""clickwheel CLI — command definitions."""

from __future__ import annotations

from pathlib import Path

import typer
from tqdm import tqdm

from clickwheel import __version__
from clickwheel.config import load_config
from clickwheel.db import Database
from clickwheel.library import find_audio_files, scan_file
from clickwheel.output import (
    confirm,
    dim,
    error,
    info,
    print_table,
    status,
    success,
    table,
    warn,
)

app = typer.Typer(
    name="clickwheel",
    help="Sync your music library to a classic iPod.",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        info(f"clickwheel {__version__}")
        raise typer.Exit()


def _check_macos() -> None:
    """Exit if not running on macOS."""
    import sys

    if sys.platform != "darwin":
        error("clickwheel requires macOS. iPod sync depends on macOS disk utilities.")
        raise typer.Exit(1)


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-v", help="Show version", callback=_version_callback
    ),
) -> None:
    """clickwheel — sync your music library to a classic iPod."""


@app.command()
def scan(
    full: bool = typer.Option(
        False, "--full", "-f", help="Rescan everything from scratch"
    ),
    stats_only: bool = typer.Option(
        False, "--stats", help="Show library stats without scanning again"
    ),
) -> None:
    """Scan your music library and check for missing info."""
    cfg = load_config()
    db = Database(cfg.db_path)

    if stats_only:
        stats = db.get_stats()
        if stats["total_tracks"] == 0:
            warn("No music found. Run `clickwheel scan` first.")
            db.close()
            raise typer.Exit(1)
        formats = db.get_format_breakdown()
        db.close()
        info("")
        _print_stats(stats, formats, 0)
        return

    if not cfg.music_dir.is_dir():
        error(f"Music folder not found: {cfg.music_dir}")
        raise typer.Exit(1)

    if full:
        db.clear_tracks()

    status(f"Scanning {cfg.music_dir}...")
    files = find_audio_files(cfg.music_dir)
    info(f"Found {len(files):,} tracks")

    scanned = 0
    scan_errors = 0
    for f in tqdm(files, desc="Scanning", unit="file"):
        track = scan_file(f)
        if track:
            db.upsert_track(track)
            scanned += 1
        else:
            scan_errors += 1

        if scanned % 500 == 0:
            db.commit()

    db.commit()

    stats = db.get_stats()
    formats = db.get_format_breakdown()
    db.close()

    info("")
    _print_stats(stats, formats, scan_errors)
    dim("Run `clickwheel select` to pick music for your iPod.")


@app.command()
def fix(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be done without making changes"
    ),
    artist: str = typer.Argument(
        None, help="Artist folder name to target (default: entire library)"
    ),
) -> None:
    """Fill in missing album art, genres, and other track details."""
    cfg = load_config()

    target = str(cfg.music_dir / artist) if artist else str(cfg.music_dir)

    if dry_run:
        status("Dry run — would clean up metadata:")
        info(f"  Target: {target}")
        info("  Steps: catalog, fetch art, embed art, fill genres, write tags")
        return

    _run_beets_fix(cfg, target)


@app.command()
def select(
    playlist_name: str = typer.Option("ipod", "--name", "-n", help="Playlist name"),
) -> None:
    """Pick artists and albums for your iPod."""
    cfg = load_config()
    db = Database(cfg.db_path)
    artists = db.get_artists()

    if not artists:
        warn("No music found. Run `clickwheel scan` first.")
        db.close()
        raise typer.Exit(1)

    capacity = cfg.ipod_capacity_bytes
    status(
        f"{len(artists)} artists available | iPod capacity: {cfg.ipod_capacity_gb} GB"
    )
    info("")

    _print_artist_table(artists)

    dim(
        "Enter artist numbers (comma-separated), "
        "'all' for everything, or 'done' to finish."
    )

    selected_paths: list[str] = []
    selected_size = 0

    while True:
        _print_capacity_bar(selected_size, capacity)
        prompt = (
            f"Selected: {len(selected_paths)} tracks, {_fmt_size(selected_size)} > "
        )
        choice = typer.prompt(prompt, default="done")

        if choice.lower() == "done":
            break
        if choice.lower() == "all":
            for a in artists:
                _add_artist_tracks(db, a["name"], selected_paths)
            selected_size = _calc_size(db, selected_paths)
            confirm("Added all artists")
            continue

        try:
            indices = [int(x.strip()) for x in choice.split(",")]
        except ValueError:
            warn("Invalid input. Enter numbers or 'done'.")
            continue

        for idx in indices:
            if 1 <= idx <= len(artists):
                a = artists[idx - 1]
                added = _add_artist_tracks(db, a["name"], selected_paths)
                confirm(f"+ {a['name']}: {added} tracks")

        selected_size = _calc_size(db, selected_paths)

        if selected_size > capacity:
            over = selected_size - capacity
            warn(
                f"Over capacity by {_fmt_size(over)}. "
                "Remove some artists, or type 'done' to save anyway."
            )

    if selected_paths:
        db.save_playlist(playlist_name, selected_paths)
        success(
            f"Playlist '{playlist_name}' saved — "
            f"{len(selected_paths)} tracks, {_fmt_size(selected_size)}"
        )
        if selected_size > capacity:
            warn(
                f"This is {_fmt_size(selected_size - capacity)} "
                "over your iPod's capacity."
            )

    db.close()


@app.command()
def playlist(
    name: str = typer.Argument(None, help="Playlist name to show details"),
) -> None:
    """Show your saved playlists."""
    cfg = load_config()
    db = Database(cfg.db_path)

    if name:
        tracks = db.get_playlist(name)
        if not tracks:
            error(f"Playlist '{name}' not found.")
            db.close()
            raise typer.Exit(1)

        t = table(title=f"Playlist: {name}")
        t.add_column("#", style="dim", width=5)
        t.add_column("Artist")
        t.add_column("Album")
        t.add_column("Title")
        t.add_column("Size", justify="right")

        total_size = 0
        for i, tr in enumerate(tracks, 1):
            size_mb = (tr["file_size"] or 0) / (1024 * 1024)
            total_size += tr["file_size"] or 0
            t.add_row(
                str(i),
                tr["artist"] or "?",
                tr["album"] or "?",
                tr["title"] or "?",
                f"{size_mb:.1f} MB",
            )

        print_table(t)
        total_gb = total_size / (1024 * 1024 * 1024)
        status(f"\n{len(tracks)} tracks, {total_gb:.1f} GB")
    else:
        playlists = db.list_playlists()
        if not playlists:
            warn("No playlists yet. Run `clickwheel select` to create one.")
            db.close()
            return

        t = table(title="Playlists")
        t.add_column("Name")
        t.add_column("Tracks", justify="right")
        t.add_column("Size", justify="right")
        t.add_column("Updated")

        for p in playlists:
            size_gb = (p["total_bytes"] or 0) / (1024 * 1024 * 1024)
            t.add_row(p["name"], str(p["tracks"]), f"{size_gb:.1f} GB", p["updated_at"])

        print_table(t)

    db.close()


@app.command()
def delete(
    playlist_name: str = typer.Argument(..., help="Playlist to delete"),
) -> None:
    """Delete a saved playlist."""
    cfg = load_config()
    db = Database(cfg.db_path)

    if db.delete_playlist(playlist_name):
        success(f"Deleted playlist '{playlist_name}'.")
    else:
        error(f"Playlist '{playlist_name}' not found.")
        db.close()
        raise typer.Exit(1)

    db.close()


@app.command()
def edit(
    playlist_name: str = typer.Argument("ipod", help="Playlist to edit"),
) -> None:
    """Add or remove artists from a playlist."""
    cfg = load_config()
    db = Database(cfg.db_path)

    existing = db.get_playlist(playlist_name)
    if not existing:
        error(
            f"Playlist '{playlist_name}' not found. "
            "Run `clickwheel select` to create one."
        )
        db.close()
        raise typer.Exit(1)

    capacity = cfg.ipod_capacity_bytes
    all_artists = db.get_artists()
    playlist_artists = db.get_playlist_artists(playlist_name)
    playlist_size = db.get_playlist_size(playlist_name)

    status(f"Editing playlist: {playlist_name}")
    info(f"Current: {len(existing)} tracks, {_fmt_size(playlist_size)}")
    _print_capacity_bar(playlist_size, capacity)
    info("")

    if playlist_artists:
        t = table(title="Artists in playlist")
        t.add_column("Artist")
        t.add_column("Tracks", justify="right")
        t.add_column("Size", justify="right")
        for a in playlist_artists:
            size = _fmt_size(a["total_bytes"] or 0)
            t.add_row(a["name"], str(a["tracks"]), size)
        print_table(t)
        info("")

    dim(
        "Commands: +N (add artist #N), -ArtistName (remove), "
        "'list' (show all artists), 'done' (finish)"
    )

    while True:
        playlist_size = db.get_playlist_size(playlist_name)
        _print_capacity_bar(playlist_size, capacity)
        choice = typer.prompt("edit", default="done")

        if choice.lower() == "done":
            break

        if choice.lower() == "list":
            _print_artist_table(all_artists)
            continue

        if choice.startswith("+"):
            try:
                idx = int(choice[1:].strip())
                if 1 <= idx <= len(all_artists):
                    artist = all_artists[idx - 1]["name"]
                    added = db.add_artist_to_playlist(playlist_name, artist)
                    confirm(f"+ {artist}: {added} tracks added")
                else:
                    warn("That number isn't in the list.")
            except ValueError:
                warn("Use +N where N is the artist number.")
            continue

        if choice.startswith("-"):
            artist_name = choice[1:].strip()
            removed = db.remove_artist_from_playlist(playlist_name, artist_name)
            if removed:
                info(f"Removed {artist_name} ({removed} tracks)")
            else:
                warn(f"'{artist_name}' not in playlist.")
            continue

        warn("Unknown command. Use +N, -ArtistName, list, or done.")

    final_size = db.get_playlist_size(playlist_name)
    tracks = db.get_playlist(playlist_name)
    success(
        f"Playlist '{playlist_name}' saved — "
        f"{len(tracks)} tracks, {_fmt_size(final_size)}"
    )
    if final_size > capacity:
        warn(f"This is {_fmt_size(final_size - capacity)} over your iPod's capacity.")
    db.close()


@app.command()
def diff(
    playlist_name: str = typer.Argument("ipod", help="Playlist to diff against iPod"),
) -> None:
    """Preview changes before syncing to your iPod."""
    _check_macos()
    cfg = load_config()
    db = Database(cfg.db_path)

    ipod = _require_ipod(cfg)
    ipod_tracks = _get_ipod_track_list(ipod)
    ipod_set = {
        (t.get("artist", ""), t.get("album", ""), t.get("title", ""))
        for t in ipod_tracks
    }

    playlist_tracks = db.get_playlist(playlist_name)
    if not playlist_tracks:
        error(f"Playlist '{playlist_name}' not found.")
        db.close()
        raise typer.Exit(1)

    playlist_set = {
        (t["artist"] or "", t["album"] or "", t["title"] or "") for t in playlist_tracks
    }

    to_add = playlist_set - ipod_set
    to_remove = ipod_set - playlist_set
    unchanged = playlist_set & ipod_set

    status(f"Comparing playlist '{playlist_name}' with your iPod")
    info(
        f"  {len(to_add)} to add, "
        f"{len(to_remove)} to remove, "
        f"{len(unchanged)} already on iPod"
    )

    if to_add:
        info("")
        add_table = table(title="To Add")
        add_table.add_column("Artist")
        add_table.add_column("Album")
        add_table.add_column("Title")
        for artist, album, title in sorted(to_add):
            add_table.add_row(artist, album, title)
        print_table(add_table)

    if to_remove:
        info("")
        rm_table = table(title="To Remove")
        rm_table.add_column("Artist")
        rm_table.add_column("Album")
        rm_table.add_column("Title")
        for artist, album, title in sorted(to_remove):
            rm_table.add_row(artist, album, title)
        print_table(rm_table)

    if not to_add and not to_remove:
        confirm("Your iPod matches this playlist.")

    db.close()


@app.command()
def sync(
    playlist_name: str = typer.Argument("ipod", help="Playlist to sync"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would change without doing it"
    ),
) -> None:
    """Send your playlist to the iPod."""
    _check_macos()
    import shutil

    from clickwheel.ipod.sync import copy_tracks_to_ipod, write_ipod_db

    cfg = load_config()
    db = Database(cfg.db_path)

    ipod = _require_ipod(cfg)
    ipod_tracks = _get_ipod_track_list(ipod)
    ipod_set = {
        (t.get("artist", ""), t.get("album", ""), t.get("title", ""))
        for t in ipod_tracks
    }

    playlist_tracks = db.get_playlist(playlist_name)
    if not playlist_tracks:
        error(f"Playlist '{playlist_name}' not found.")
        db.close()
        raise typer.Exit(1)

    playlist_set = {
        (t["artist"] or "", t["album"] or "", t["title"] or "") for t in playlist_tracks
    }

    to_add = [
        t
        for t in playlist_tracks
        if (t["artist"] or "", t["album"] or "", t["title"] or "") not in ipod_set
    ]
    to_remove_keys = ipod_set - playlist_set

    add_size = sum(t["file_size"] or 0 for t in to_add)

    status(f"Syncing playlist '{playlist_name}' to iPod")
    info(
        f"  {len(to_add)} to add ({_fmt_size(add_size)}), "
        f"{len(to_remove_keys)} to remove"
    )

    if dry_run:
        warn("Dry run — nothing was changed.")
        db.close()
        return

    if not to_add and not to_remove_keys:
        confirm("Your iPod is up to date.")
        db.close()
        return

    # Check available space on iPod
    ipod_stat = shutil.disk_usage(str(cfg.ipod_mount))
    if add_size > ipod_stat.free:
        error(
            f"Not enough space on iPod. "
            f"Need {_fmt_size(add_size)} but only {_fmt_size(ipod_stat.free)} free."
        )
        db.close()
        raise typer.Exit(1)

    # Copy files
    info("")
    progress = tqdm(total=len(to_add), desc="Copying", unit="file")

    def _on_progress(current: int, total: int) -> None:
        progress.update(1)

    copied = copy_tracks_to_ipod(to_add, cfg.ipod_mount, _on_progress)
    progress.close()

    copy_errors = len(to_add) - len(copied)
    success(f"Copied {len(copied)} tracks to iPod.")
    if copy_errors:
        warn(f"{copy_errors} tracks couldn't be copied.")

    # Write iTunesDB — include both existing iPod tracks and newly copied ones
    info("Updating iPod database...")
    db_ok = write_ipod_db(cfg.ipod_mount, copied)
    if db_ok:
        success("iPod database updated.")
    else:
        error(
            "Couldn't update the iPod database. "
            "Your music was copied, but the iPod may not show it."
        )

    if to_remove_keys:
        warn(
            f"{len(to_remove_keys)} tracks on iPod aren't in this playlist. "
            "Run `clickwheel diff` to see them."
        )

    db.close()


@app.command()
def ls() -> None:
    """Show what's on your iPod."""
    _check_macos()
    cfg = load_config()
    ipod = _require_ipod(cfg)
    tracks = _get_ipod_track_list(ipod)

    if not tracks:
        warn("Your iPod is empty.")
        return

    # Group by artist
    artists: dict[str, list[dict]] = {}
    total_size = 0
    for t in tracks:
        name = t.get("artist", "Unknown")
        artists.setdefault(name, []).append(t)
        total_size += t.get("size", 0)

    t = table(title="iPod Contents")
    t.add_column("Artist")
    t.add_column("Tracks", justify="right")
    t.add_column("Albums", justify="right")

    for name in sorted(artists, key=str.lower):
        artist_tracks = artists[name]
        albums = {tr.get("album", "") for tr in artist_tracks}
        t.add_row(name, str(len(artist_tracks)), str(len(albums)))

    print_table(t)
    status(f"\n{len(tracks)} tracks, {len(artists)} artists, {_fmt_size(total_size)}")


@app.command()
def eject() -> None:
    """Safely disconnect the iPod."""
    _check_macos()
    import subprocess

    cfg = load_config()
    _require_ipod(cfg)  # verify iPod is mounted

    status("Ejecting iPod...")
    result = subprocess.run(
        ["diskutil", "eject", str(cfg.ipod_mount)],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        confirm("iPod ejected. Safe to unplug.")
    else:
        error(result.stderr.strip())
        raise typer.Exit(1)


@app.command()
def scrobble(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show plays without submitting"
    ),
    show_status: bool = typer.Option(
        False, "--status", help="Show Last.fm profile info"
    ),
) -> None:
    """Submit your recent iPod listens to Last.fm."""
    import time as _time

    from clickwheel.scrobble import (
        cache_scrobbles,
        get_lastfm_profile,
        get_pending_scrobbles,
        read_ipod_plays,
        submit_scrobbles,
    )

    cfg = load_config()

    if not cfg.lastfm_api_key:
        error(
            "Last.fm isn't configured. "
            "Add your API key to ~/.clickwheel/config.yaml or .env"
        )
        raise typer.Exit(1)

    if show_status:
        profile = get_lastfm_profile(
            cfg.lastfm_api_key, cfg.lastfm_api_secret, cfg.lastfm_username
        )
        if profile:
            status(f"Last.fm: {profile['name']}")
            info(f"  Total scrobbles: {profile['playcount']:,}")
            info(f"  {profile['url']}")
        else:
            error("Couldn't reach Last.fm. Check your API key and internet connection.")
        return

    if not cfg.lastfm_api_secret:
        error(
            "Last.fm API secret is missing. Add it to ~/.clickwheel/config.yaml or .env"
        )
        raise typer.Exit(1)

    _require_ipod(cfg)
    db = Database(cfg.db_path)

    # Read plays from iPod
    status("Checking iPod for recent listens...")
    plays = read_ipod_plays(cfg.ipod_mount)

    if not plays:
        warn("No new listens found on iPod.")
        db.close()
        return

    # Check for old plays
    now = int(_time.time())
    oldest = min(p.timestamp for p in plays)
    age_days = (now - oldest) / 86400
    if age_days > 12:
        warn(
            f"Some listens are {age_days:.0f} days old. "
            "Last.fm won't accept anything older than 14 days — sync soon."
        )

    info(f"Found {len(plays)} listens to submit")

    # Cache to avoid duplicates
    cached = cache_scrobbles(db.conn, plays)
    info(f"  {cached} new, rest already submitted")

    pending = get_pending_scrobbles(db.conn)
    if not pending:
        confirm("All listens already submitted.")
        db.close()
        return

    if dry_run:
        from datetime import datetime

        t = table(title=f"Pending Scrobbles ({len(pending)})")
        t.add_column("Time")
        t.add_column("Artist")
        t.add_column("Title")
        t.add_column("Album")
        for s in pending[:50]:
            ts = datetime.fromtimestamp(s["timestamp"]).strftime("%m/%d %H:%M")
            t.add_row(ts, s["artist"], s["title"], s.get("album") or "")
        if len(pending) > 50:
            t.add_row("...", f"+ {len(pending) - 50} more", "", "")
        print_table(t)
        warn("Dry run — nothing was submitted.")
        db.close()
        return

    # Submit to Last.fm
    info(f"Sending {len(pending)} listens to Last.fm...")
    submitted, submit_errors = submit_scrobbles(
        cfg.lastfm_api_key,
        cfg.lastfm_api_secret,
        cfg.lastfm_username,
        pending,
        db.conn,
    )

    success(f"Sent {submitted} listens to Last.fm.")
    if submit_errors:
        warn(f"{submit_errors} failed. They'll be retried next time you scrobble.")

    db.close()


def _print_stats(stats: dict, formats: list[dict], scan_errors: int) -> None:
    """Print scan results in a formatted table."""
    total_gb = (stats["total_bytes"] or 0) / (1024 * 1024 * 1024)
    hours = (stats["total_seconds"] or 0) / 3600

    summary = table(title="Library Summary", show_header=False, box=None)
    summary.add_column("Label", style="bold")
    summary.add_column("Value")
    summary.add_row("Tracks", f"{stats['total_tracks']:,}")
    summary.add_row("Artists", f"{stats['artists']:,}")
    summary.add_row("Albums", f"{stats['albums']:,}")
    summary.add_row("Total size", f"{total_gb:.1f} GB")
    summary.add_row("Total duration", f"{hours:.1f} hours")
    print_table(summary)

    info("")
    fmt_table = table(title="Formats")
    fmt_table.add_column("Format")
    fmt_table.add_column("Tracks", justify="right")
    fmt_table.add_column("Size", justify="right")
    for f in formats:
        size_gb = (f["total_bytes"] or 0) / (1024 * 1024 * 1024)
        fmt_table.add_row(f["format"].upper(), f"{f['count']:,}", f"{size_gb:.1f} GB")
    print_table(fmt_table)

    info("")
    quality = table(title="Metadata Quality")
    quality.add_column("Check", style="bold")
    quality.add_column("OK", justify="right", style="green")
    quality.add_column("Missing", justify="right", style="red")

    total = stats["total_tracks"]
    quality.add_row(
        "Album art",
        str(stats["with_art"]),
        str(stats["without_art"]),
    )
    quality.add_row(
        "Genre",
        str(total - stats["missing_genre"]),
        str(stats["missing_genre"]),
    )
    quality.add_row(
        "Title",
        str(total - stats["missing_title"]),
        str(stats["missing_title"]),
    )
    quality.add_row(
        "Artist",
        str(total - stats["missing_artist"]),
        str(stats["missing_artist"]),
    )
    print_table(quality)

    if scan_errors:
        warn(f"{scan_errors} files couldn't be read")


def _print_artist_table(artists: list[dict]) -> None:
    """Print numbered table of artists."""
    t = table(title="Artists")
    t.add_column("#", style="dim", width=5)
    t.add_column("Artist")
    t.add_column("Albums", justify="right")
    t.add_column("Tracks", justify="right")
    t.add_column("Size", justify="right")

    for i, a in enumerate(artists, 1):
        size_gb = (a["total_bytes"] or 0) / (1024 * 1024 * 1024)
        t.add_row(
            str(i),
            a["name"],
            str(a["albums"]),
            str(a["tracks"]),
            f"{size_gb:.2f} GB",
        )

    print_table(t)


def _print_capacity_bar(used: int, capacity: int) -> None:
    """Print a visual capacity bar."""
    pct = (used / capacity * 100) if capacity > 0 else 0
    bar_width = 40
    filled = int(bar_width * min(pct, 100) / 100)
    bar = "#" * filled + "-" * (bar_width - filled)
    msg = f"[{bar}] {pct:.1f}% ({_fmt_size(used)} / {_fmt_size(capacity)})"
    if pct >= 80:
        warn(msg)
    else:
        confirm(msg)


def _fmt_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    if size_bytes >= 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / 1024:.1f} KB"


def _add_artist_tracks(
    db: Database, artist_name: str, selected_paths: list[str]
) -> int:
    """Add all tracks by an artist to the selected list. Returns count added."""
    albums = db.get_albums_by_artist(artist_name)
    added = 0
    for album in albums:
        tracks = db.get_tracks_by_album(artist_name, album["album"])
        for t in tracks:
            if t["path"] not in selected_paths:
                selected_paths.append(t["path"])
                added += 1
    return added


def _calc_size(db: Database, paths: list[str]) -> int:
    """Calculate total file size for a list of track paths."""
    total = 0
    for p in paths:
        row = db.conn.execute(
            "SELECT file_size FROM tracks WHERE path = ?", (p,)
        ).fetchone()
        if row:
            total += row["file_size"] or 0
    return total


def _require_ipod(cfg) -> dict:
    """Find and read the iPod, or exit with an error."""
    from clickwheel.ipod import find_ipod, read_ipod

    if not find_ipod(cfg.ipod_mount):
        error("No iPod found. Make sure it's plugged in and shows up in Finder.")
        raise typer.Exit(1)

    return read_ipod(cfg.ipod_mount)


def _get_ipod_track_list(ipod_db: dict) -> list[dict]:
    """Extract the track list from a parsed iPod database."""
    from clickwheel.ipod import get_ipod_tracks

    return get_ipod_tracks(ipod_db)


def _get_path() -> str:
    """Get PATH with common Homebrew locations."""
    import os

    path = os.environ.get("PATH", "")
    extra = ["/opt/homebrew/bin", "/usr/local/bin", str(Path.home() / ".local/bin")]
    return ":".join(extra + [path])


def _run_beets_fix(cfg, target: str) -> None:
    """Run the beets metadata cleanup pipeline.

    Runs five phases: catalog, fetch art, embed art, fill genres, write tags.
    Requires beets to be installed (pip install beets).
    """
    import subprocess

    beets_dir = cfg.project_dir / "beets"
    beets_dir.mkdir(parents=True, exist_ok=True)

    env = {
        "BEETSDIR": str(beets_dir),
        "PATH": _get_path(),
        "HOME": str(Path.home()),
    }

    def _beet(args: list[str], phase: str) -> bool:
        status(phase)
        result = subprocess.run(
            ["beet", *args],
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 and result.stderr:
            warn(result.stderr.strip())
        return result.returncode == 0

    # Check beets is installed
    check = subprocess.run(
        ["beet", "version"],
        env=env,
        capture_output=True,
    )
    if check.returncode != 0:
        error("beets is not installed. Install it with: pip install beets")
        raise typer.Exit(1)

    _beet(
        ["import", "-qA", target],
        "Step 1/5: Cataloging library...",
    )
    _beet(["fetchart", "-f"], "Step 2/5: Fetching missing album art...")
    _beet(["embedart", "-y"], "Step 3/5: Embedding album art...")
    _beet(["lastgenre"], "Step 4/5: Filling missing genres...")
    _beet(["write", "-y"], "Step 5/5: Writing tags to files...")

    success("Metadata cleanup complete.")
