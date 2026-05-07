"""clickwheel CLI — command definitions."""

from __future__ import annotations

from pathlib import Path

import typer
from tqdm import tqdm

from clickwheel import __version__, actions
from clickwheel.actions import (
    EjectFailedError,
    InsufficientSpaceError,
    IpodNotFoundError,
    LastfmNotConfiguredError,
    LibraryNotFoundError,
    MissingTracksError,
    PlaylistNotFoundError,
    ScanProgress,
    SyncEvent,
)
from clickwheel.autoscan import maybe_auto_scan
from clickwheel.config import load_config
from clickwheel.db import Database
from clickwheel.output import (
    confirm,
    dim,
    error,
    info,
    live_table,
    print_panel,
    print_table,
    spinner,
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

    bar_fmt = "{desc}: {n_fmt}{unit}"
    discovery = tqdm(unit=" files", desc="Finding audio files", bar_format=bar_fmt)
    scan_bar: tqdm | None = None

    def _on_found(count: int) -> None:
        discovery.n = count
        discovery.refresh()

    def _on_progress(p: ScanProgress) -> None:
        nonlocal scan_bar
        if scan_bar is None:
            discovery.close()
            info(f"Found {p.total:,} tracks")
            scan_bar = tqdm(total=p.total, desc="Scanning", unit="file")
        scan_bar.n = p.current
        scan_bar.refresh()

    try:
        result = actions.scan_library(
            cfg, db, full=full, on_found=_on_found, on_progress=_on_progress
        )
    except LibraryNotFoundError as exc:
        discovery.close()
        if scan_bar:
            scan_bar.close()
        error(str(exc))
        db.close()
        raise typer.Exit(1) from exc

    if scan_bar is None:
        discovery.close()
    else:
        scan_bar.close()

    stats = db.get_stats()
    formats = db.get_format_breakdown()
    db.close()

    info("")
    _print_stats(stats, formats, result.errors)
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
    no_scan: bool = typer.Option(
        False, "--no-scan", help="Skip automatic library scan"
    ),
) -> None:
    """Pick artists and albums for your iPod."""
    import questionary

    cfg = load_config()
    db = Database(cfg.db_path)
    if not no_scan:
        maybe_auto_scan(cfg, db)
    artists = actions.list_artists(db)

    if not artists:
        warn("No music found. Run `clickwheel scan` first.")
        db.close()
        raise typer.Exit(1)

    capacity = cfg.ipod_capacity_bytes
    status(
        f"{len(artists)} artists available | iPod capacity: {cfg.ipod_capacity_gb} GB"
    )
    info("")

    choices = [
        questionary.Choice(
            title=(
                f"{a['name']}  "
                f"({a['tracks']} tracks, "
                f"{_fmt_size(a['total_bytes'] or 0)})"
            ),
            value=a["name"],
        )
        for a in artists
    ]

    selected_names = questionary.checkbox(
        "Select artists for your iPod (space to toggle, enter to confirm):",
        choices=choices,
    ).ask()

    if selected_names is None:
        db.close()
        raise typer.Exit(0)

    selected_paths: list[str] = []
    seen_paths: set[str] = set()
    for name in selected_names:
        artist_paths = actions.collect_tracks_for_artist(db, name)
        new = [p for p in artist_paths if p not in seen_paths]
        seen_paths.update(new)
        selected_paths.extend(new)
        confirm(f"+ {name}: {len(new)} tracks")

    selected_size = actions.calc_size_of_paths(db, selected_paths)
    _print_capacity_bar(selected_size, capacity)

    if selected_size > capacity:
        over = selected_size - capacity
        warn(f"Over capacity by {_fmt_size(over)}.")

    if selected_paths:
        actions.save_playlist(db, playlist_name, selected_paths)
        success(
            f"Playlist '{playlist_name}' saved — "
            f"{len(selected_paths)} tracks, {_fmt_size(selected_size)}"
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
        try:
            tracks = actions.get_playlist(db, name)
        except PlaylistNotFoundError as exc:
            error(str(exc))
            db.close()
            raise typer.Exit(1) from exc

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
        playlists = actions.list_playlists(db)
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
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Delete a saved playlist."""
    cfg = load_config()
    db = Database(cfg.db_path)

    try:
        tracks = actions.get_playlist(db, playlist_name)
    except PlaylistNotFoundError as exc:
        error(str(exc))
        db.close()
        raise typer.Exit(1) from exc

    if not force:
        warn(f"This will delete playlist '{playlist_name}' ({len(tracks)} tracks).")
        if not typer.confirm("Are you sure?", default=False):
            info("Cancelled.")
            db.close()
            return

    actions.delete_playlist(db, playlist_name)
    success(f"Deleted playlist '{playlist_name}'.")
    db.close()


@app.command()
def heal(
    playlist_name: str = typer.Argument(..., help="Playlist to heal"),
    no_scan: bool = typer.Option(
        False, "--no-scan", help="Skip automatic library scan"
    ),
) -> None:
    """Drop playlist references to tracks no longer on disk.

    Uses the missing-since flag set by `clickwheel scan`. Run a scan
    first if you want freshness; pass --no-scan to skip the autoscan
    if you've already scanned recently.
    """
    cfg = load_config()
    db = Database(cfg.db_path)
    if not no_scan:
        maybe_auto_scan(cfg, db)

    try:
        result = actions.heal_playlist(db, playlist_name)
    except PlaylistNotFoundError as exc:
        error(str(exc))
        db.close()
        raise typer.Exit(1) from exc

    if result["dropped"] == 0:
        confirm(
            f"'{playlist_name}' has no dead references "
            f"({result['remaining']} tracks intact)."
        )
        db.close()
        return

    success(
        f"Dropped {result['dropped']} dead reference(s) from "
        f"'{playlist_name}' ({result['remaining']} tracks remaining)."
    )
    if result["dropped_tracks"]:
        info("")
        t = table(title="Dropped tracks")
        t.add_column("Artist")
        t.add_column("Album")
        t.add_column("Title")
        for tr in result["dropped_tracks"][:20]:
            t.add_row(tr["artist"] or "?", tr["album"] or "?", tr["title"] or "?")
        if len(result["dropped_tracks"]) > 20:
            t.add_row("...", f"+ {len(result['dropped_tracks']) - 20} more", "")
        print_table(t)
        dim(
            "Re-add the artist with `clickwheel edit "
            f'{playlist_name} --add "<Artist>"` if needed.'
        )
    db.close()


@app.command()
def edit(
    playlist_name: str = typer.Argument("ipod", help="Playlist to edit"),
    add: list[str] = typer.Option([], "--add", "-a", help="Artist to add"),
    remove: list[str] = typer.Option([], "--remove", "-r", help="Artist to remove"),
    no_scan: bool = typer.Option(
        False, "--no-scan", help="Skip automatic library scan"
    ),
) -> None:
    """Add or remove artists from a playlist."""
    cfg = load_config()
    db = Database(cfg.db_path)
    if not no_scan:
        maybe_auto_scan(cfg, db)

    # Non-interactive mode: --add and/or --remove flags
    if add or remove:
        capacity = cfg.ipod_capacity_bytes

        for artist in add:
            added = actions.add_artist_to_playlist(db, playlist_name, artist)
            if added:
                confirm(f"+ {artist}: {added} tracks added")
            else:
                warn(f"No tracks found for '{artist}' (or already in playlist)")

        for artist in remove:
            removed = actions.remove_artist_from_playlist(db, playlist_name, artist)
            if removed:
                info(f"- {artist}: {removed} tracks removed")
            else:
                warn(f"'{artist}' not in playlist.")

        final_size = actions.get_playlist_size(db, playlist_name)
        tracks = db.get_playlist(playlist_name)
        success(
            f"Playlist '{playlist_name}' — "
            f"{len(tracks)} tracks, {_fmt_size(final_size)}"
        )
        if final_size > capacity:
            warn(
                f"This is {_fmt_size(final_size - capacity)} over your iPod's capacity."
            )
        db.close()
        return

    # Interactive mode (no flags)
    import questionary

    existing = db.get_playlist(playlist_name)
    if not existing:
        error(
            f"Playlist '{playlist_name}' not found. "
            "Run `clickwheel select` to create one, "
            'or use `clickwheel edit --add "Artist"` to start one.'
        )
        db.close()
        raise typer.Exit(1)

    capacity = cfg.ipod_capacity_bytes
    all_artists = actions.list_artists(db)
    playlist_artists = actions.get_playlist_artists(db, playlist_name)
    playlist_size = actions.get_playlist_size(db, playlist_name)
    current_names = {a["name"] for a in playlist_artists}

    status(f"Editing playlist: {playlist_name}")
    info(f"Current: {len(existing)} tracks, {_fmt_size(playlist_size)}")
    _print_capacity_bar(playlist_size, capacity)
    info("")

    while True:
        action = questionary.select(
            "What would you like to do?",
            choices=[
                "Add artists",
                "Remove artists",
                "Show current playlist",
                "Done",
            ],
        ).ask()

        if action is None or action == "Done":
            break

        if action == "Show current playlist":
            playlist_artists = actions.get_playlist_artists(db, playlist_name)
            if playlist_artists:
                t = table(title="Artists in playlist")
                t.add_column("Artist")
                t.add_column("Tracks", justify="right")
                t.add_column("Size", justify="right")
                for a in playlist_artists:
                    size = _fmt_size(a["total_bytes"] or 0)
                    t.add_row(a["name"], str(a["tracks"]), size)
                print_table(t)
            else:
                warn("Playlist is empty.")
            continue

        if action == "Add artists":
            available = [a for a in all_artists if a["name"] not in current_names]
            if not available:
                warn("All artists are already in the playlist.")
                continue
            choices = [
                questionary.Choice(
                    title=(
                        f"{a['name']}  "
                        f"({a['tracks']} tracks, "
                        f"{_fmt_size(a['total_bytes'] or 0)})"
                    ),
                    value=a["name"],
                )
                for a in available
            ]
            to_add = questionary.checkbox(
                "Select artists to add (space to toggle, enter to confirm):",
                choices=choices,
            ).ask()
            if to_add:
                for name in to_add:
                    added = actions.add_artist_to_playlist(db, playlist_name, name)
                    current_names.add(name)
                    confirm(f"+ {name}: {added} tracks added")

        if action == "Remove artists":
            playlist_artists = actions.get_playlist_artists(db, playlist_name)
            if not playlist_artists:
                warn("Playlist is empty.")
                continue
            choices = [
                questionary.Choice(
                    title=f"{a['name']}  ({a['tracks']} tracks)",
                    value=a["name"],
                )
                for a in playlist_artists
            ]
            to_remove = questionary.checkbox(
                "Select artists to remove (space to toggle, enter to confirm):",
                choices=choices,
            ).ask()
            if to_remove:
                for name in to_remove:
                    removed = actions.remove_artist_from_playlist(
                        db, playlist_name, name
                    )
                    current_names.discard(name)
                    info(f"Removed {name} ({removed} tracks)")

        playlist_size = actions.get_playlist_size(db, playlist_name)
        _print_capacity_bar(playlist_size, capacity)

        if playlist_size > capacity:
            over = playlist_size - capacity
            warn(f"Over capacity by {_fmt_size(over)}.")

    final_size = actions.get_playlist_size(db, playlist_name)
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
    no_scan: bool = typer.Option(
        False, "--no-scan", help="Skip automatic library scan"
    ),
) -> None:
    """Preview changes before syncing to your iPod."""
    _check_macos()
    cfg = load_config()
    db = Database(cfg.db_path)
    if not no_scan:
        maybe_auto_scan(cfg, db)

    try:
        d = actions.compute_diff(cfg, db, playlist_name)
    except (PlaylistNotFoundError, IpodNotFoundError) as exc:
        error(str(exc))
        db.close()
        raise typer.Exit(1) from exc

    summary = (
        f"{len(d.to_add)} to add, "
        f"{len(d.to_remove)} to remove, "
        f"{len(d.unchanged)} already on iPod"
    )
    print_panel(summary, title=f"Diff: {playlist_name}", style="cyan")

    if d.to_add:
        info("")
        add_table = table(title="[green]+ To Add[/green]")
        add_table.add_column("Artist")
        add_table.add_column("Album")
        add_table.add_column("Title")
        for artist, album, title in d.to_add_display():
            add_table.add_row(artist, album, title)
        print_table(add_table)

    if d.to_remove:
        info("")
        rm_table = table(title="[red]- To Remove[/red]")
        rm_table.add_column("Artist")
        rm_table.add_column("Album")
        rm_table.add_column("Title")
        for artist, album, title in d.to_remove:
            rm_table.add_row(artist, album, title)
        print_table(rm_table)

    if not d.to_add and not d.to_remove:
        confirm("Your iPod matches this playlist.")

    db.close()


@app.command()
def sync(
    playlist_name: str = typer.Argument("ipod", help="Playlist to sync"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would change without doing it"
    ),
    no_scan: bool = typer.Option(
        False, "--no-scan", help="Skip automatic library scan"
    ),
) -> None:
    """Send your playlist to the iPod."""
    _check_macos()
    cfg = load_config()
    db = Database(cfg.db_path)
    if not no_scan:
        maybe_auto_scan(cfg, db)

    try:
        d = actions.compute_diff(cfg, db, playlist_name)
    except (PlaylistNotFoundError, IpodNotFoundError) as exc:
        error(str(exc))
        db.close()
        raise typer.Exit(1) from exc

    # Pre-flight: any tracks in the playlist that are flagged missing on
    # disk? Bail with a clear pointer at `clickwheel heal` so the user
    # doesn't sit through per-file timeouts.
    missing_in_playlist = db.get_missing_tracks_in_playlist(playlist_name)
    if missing_in_playlist:
        to_add_keys = {
            (t["artist"] or "", t["album"] or "", t["title"] or "") for t in d.to_add
        }
        blocking = [
            t
            for t in missing_in_playlist
            if (t["artist"] or "", t["album"] or "", t["title"] or "") in to_add_keys
        ]
        if blocking:
            error(
                f"{len(blocking)} track(s) in '{playlist_name}' reference "
                "files that no longer exist on disk."
            )
            warn(f"Run `clickwheel heal {playlist_name}` to drop the dead refs, ")
            warn("then re-add the artist with `clickwheel edit --add`.")
            db.close()
            raise typer.Exit(1)

    status(f"Syncing playlist '{playlist_name}' to iPod")
    info(
        f"  {len(d.to_add)} to add ({_fmt_size(d.add_size_bytes)}), "
        f"{len(d.to_remove)} to remove"
    )

    if dry_run:
        warn("Dry run — nothing was changed.")
        db.close()
        return

    if not d.to_add and not d.to_remove:
        confirm("Your iPod is up to date.")
        db.close()
        return

    if not typer.confirm("Proceed with sync?", default=True):
        info("Cancelled.")
        db.close()
        return

    info("")
    sync_table = table(title="Syncing to iPod")
    sync_table.add_column("#", style="dim", width=6)
    sync_table.add_column("Artist")
    sync_table.add_column("Title")
    sync_table.add_column("Size", justify="right")
    sync_table.add_column("Status", justify="right")

    try:
        with live_table() as live:
            live.update(sync_table)

            def _on_event(event: SyncEvent) -> None:
                size = _fmt_size(event.track["file_size"] or 0)
                sync_table.add_row(
                    f"{event.current}/{event.total}",
                    event.track["artist"] or "?",
                    event.track["title"] or "?",
                    size,
                    "[green]OK[/green]",
                )
                live.update(sync_table)

            result = actions.sync_playlist(
                cfg, db, playlist_name, diff=d, on_event=_on_event
            )
    except LibraryNotFoundError as exc:
        error(str(exc))
        db.close()
        raise typer.Exit(1) from exc
    except MissingTracksError as exc:
        error(str(exc))
        warn(f"Run `clickwheel heal {playlist_name}` to drop dead references.")
        db.close()
        raise typer.Exit(1) from exc
    except InsufficientSpaceError as exc:
        error(str(exc))
        db.close()
        raise typer.Exit(1) from exc

    success(f"Copied {len(result.copied)} tracks to iPod.")
    if result.failed:
        warn(f"{len(result.failed)} tracks couldn't be copied:")
        groups: dict[tuple[str, str], int] = {}
        for t in result.failed:
            key = (t.get("artist") or "Unknown", t.get("album") or "Unknown")
            groups[key] = groups.get(key, 0) + 1
        for (artist, album), count in sorted(groups.items()):
            dim(f"  {artist} — {album} ({count} tracks)")

    if result.db_write_ok:
        success("iPod database updated.")
    else:
        warn(
            "Couldn't update the iPod database. "
            "Your music was copied, but the iPod may not show it."
        )
        if typer.confirm("Retry writing the iPod database?", default=True):
            with spinner("Retrying iPod database write..."):
                retry_ok = actions.retry_ipod_db_write(cfg, result.copied)
            if retry_ok:
                success("iPod database updated on retry.")
            else:
                error("Still couldn't update iPod database.")

    if result.removed_count:
        warn(
            f"{result.removed_count} tracks on iPod aren't in this playlist. "
            "Run `clickwheel diff` to see them."
        )

    db.close()


@app.command()
def ls() -> None:
    """Show what's on your iPod."""
    _check_macos()
    cfg = load_config()
    try:
        contents = actions.read_ipod_contents(cfg)
    except IpodNotFoundError as exc:
        error(str(exc))
        raise typer.Exit(1) from exc

    tracks = contents["tracks"]
    if not tracks:
        warn("Your iPod is empty.")
        return

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
    cfg = load_config()
    try:
        with spinner("Ejecting iPod..."):
            actions.eject_ipod(cfg)
    except IpodNotFoundError as exc:
        error(str(exc))
        raise typer.Exit(1) from exc
    except EjectFailedError as exc:
        error(str(exc))
        raise typer.Exit(1) from exc
    confirm("iPod ejected. Safe to unplug.")


@app.command()
def scrobble(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show plays without submitting"
    ),
    show_status: bool = typer.Option(
        False, "--status", help="Show Last.fm profile info"
    ),
    auth: bool = typer.Option(
        False, "--auth", help="Authorize clickwheel with your Last.fm account"
    ),
) -> None:
    """Submit your recent iPod listens to Last.fm."""
    from clickwheel.scrobble import (
        authenticate_lastfm,
        complete_lastfm_auth,
        get_lastfm_profile,
        get_pending_scrobbles,
    )

    cfg = load_config()

    if not cfg.lastfm_api_key:
        error(
            "Last.fm isn't configured. "
            "Add your API key to ~/.clickwheel/config.yaml or .env"
        )
        raise typer.Exit(1)

    if not cfg.lastfm_api_secret:
        error(
            "Last.fm API secret is missing. Add it to ~/.clickwheel/config.yaml or .env"
        )
        raise typer.Exit(1)

    if auth:
        status("Opening Last.fm in your browser...")
        info("Authorize clickwheel, then come back here.")
        url, sg = authenticate_lastfm(cfg.lastfm_api_key, cfg.lastfm_api_secret)
        info(f"  Auth URL: {url}")
        typer.prompt("Press Enter after you've approved in your browser", default="")
        try:
            session_key = complete_lastfm_auth(sg, url)
        except Exception as exc:
            error(f"Auth failed: {exc}")
            raise typer.Exit(1) from exc
        _save_session_key(cfg, session_key)
        success("Last.fm authorized! Session key saved to config.")
        return

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

    if not cfg.lastfm_session_key:
        error(
            "Last.fm not authorized. "
            "Run `clickwheel scrobble --auth` to connect your account."
        )
        raise typer.Exit(1)

    db = Database(cfg.db_path)

    # Pull plays from iPod and cache new ones
    with spinner("Checking iPod for recent listens..."):
        try:
            plays_status = actions.collect_ipod_plays(cfg, db)
        except IpodNotFoundError as exc:
            error(str(exc))
            db.close()
            raise typer.Exit(1) from exc

    if plays_status["plays_found"] == 0:
        warn("No new listens found on iPod.")
        db.close()
        return

    if (
        plays_status["oldest_age_days"] is not None
        and plays_status["oldest_age_days"] > 12
    ):
        warn(
            f"Some listens are {plays_status['oldest_age_days']:.0f} days old. "
            "Last.fm won't accept anything older than 14 days — sync soon."
        )

    info(f"Found {plays_status['plays_found']} listens to submit")
    info(f"  {plays_status['new_cached']} new, rest already submitted")

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

    with spinner(f"Sending {len(pending)} listens to Last.fm..."):
        try:
            result = actions.submit_pending_scrobbles(cfg, db, pending=pending)
        except LastfmNotConfiguredError as exc:
            error(str(exc))
            db.close()
            raise typer.Exit(1) from exc

    success(f"Sent {result.submitted} listens to Last.fm.")
    if result.failed:
        warn(f"{result.failed} failed.")
        remaining = get_pending_scrobbles(db.conn)
        if remaining and typer.confirm("Retry failed scrobbles now?", default=True):
            with spinner(f"Retrying {len(remaining)} scrobbles..."):
                retry_result = actions.submit_pending_scrobbles(
                    cfg, db, pending=remaining
                )
            if retry_result.submitted:
                success(f"Sent {retry_result.submitted} more on retry.")
            if retry_result.failed:
                warn(
                    f"{retry_result.failed} still failed. "
                    "They'll be retried next time you scrobble."
                )

    db.close()


def _print_stats(stats: dict, formats: list[dict], scan_errors: int) -> None:
    """Print scan results in a formatted table."""
    total_gb = (stats["total_bytes"] or 0) / (1024 * 1024 * 1024)
    hours = (stats["total_seconds"] or 0) / 3600

    summary = table(title="Library Summary", show_header=False)
    summary.add_column("Label")
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
    quality.add_column("Check")
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


def _save_session_key(cfg, session_key: str) -> None:
    """Append the Last.fm session key to the config file."""
    from clickwheel.config import CONFIG_FILE

    lines = []
    replaced = False
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            for line in f:
                if line.strip().startswith("lastfm_session_key:"):
                    lines.append(f"lastfm_session_key: {session_key}\n")
                    replaced = True
                else:
                    lines.append(line)
    if not replaced:
        lines.append(f"lastfm_session_key: {session_key}\n")

    with open(CONFIG_FILE, "w") as f:
        f.writelines(lines)


def _get_path() -> str:
    """Get PATH with common Homebrew locations."""
    import os

    path = os.environ.get("PATH", "")
    extra = ["/opt/homebrew/bin", "/usr/local/bin", str(Path.home() / ".local/bin")]
    return ":".join(extra + [path])


def _run_beets_fix(cfg, target: str) -> None:
    """Run the beets metadata cleanup pipeline.

    Runs five phases: catalog, fetch art, embed art, fill genres, write tags.
    Requires beets to be installed: pipx inject clickwheel 'clickwheel[fix]'
    """
    import os
    import subprocess

    beets_dir = cfg.project_dir / "beets"
    beets_dir.mkdir(parents=True, exist_ok=True)

    beets_config = beets_dir / "config.yaml"
    if not beets_config.exists():
        _generate_beets_config(beets_config, cfg)

    env = {**os.environ, "BEETSDIR": str(beets_dir)}

    def _beet(args: list[str], phase: str) -> bool:
        with spinner(phase):
            result = subprocess.run(
                ["beet", *args],
                env=env,
                capture_output=True,
                text=True,
            )
        if result.returncode != 0:
            if result.stderr:
                warn(f"  Failed: {result.stderr.strip()}")
            else:
                warn("  Failed (no error details)")
            return False
        confirm(f"  {phase} Done")
        return True

    check = subprocess.run(
        ["beet", "version"],
        env=env,
        capture_output=True,
    )
    if check.returncode != 0:
        error(
            "beets is not installed.\n"
            "  If you installed clickwheel with pipx:\n"
            "    pipx inject clickwheel 'clickwheel[fix]'\n"
            "  If you installed with pip:\n"
            "    pip install 'clickwheel[fix]'"
        )
        raise typer.Exit(1)

    target_path = Path(target)
    if target_path.is_dir() and target == str(cfg.music_dir):
        status("Step 1/5: Cataloging library...")
        subdirs = sorted(
            d
            for d in target_path.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )
        import_ok = 0
        import_fail = 0
        for d in subdirs:
            result = subprocess.run(
                ["beet", "import", "-A", str(d)],
                env=env,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                import_ok += 1
            else:
                import_fail += 1
                dim(f"  Skipped: {d.name}")
        if import_fail:
            warn(f"  Cataloged {import_ok} folders, {import_fail} skipped")
        else:
            confirm(f"  Done ({import_ok} folders)")
    else:
        _beet(["import", "-A", target], "Step 1/5: Cataloging library...")

    remaining = [
        (["fetchart", "-f"], "Step 2/5: Fetching missing album art..."),
        (["embedart", "-y"], "Step 3/5: Embedding album art..."),
        (["lastgenre"], "Step 4/5: Filling missing genres..."),
        (["write"], "Step 5/5: Writing tags to files..."),
    ]

    failed = 0
    for args, phase in remaining:
        if not _beet(args, phase):
            failed += 1

    if failed == 0:
        success("Metadata cleanup complete.")
    else:
        warn(f"Metadata cleanup finished with {failed} step(s) that had issues.")


def _generate_beets_config(config_path: Path, cfg) -> None:
    """Generate a beets config.yaml for metadata cleanup."""
    from clickwheel.output import dim

    config_path.write_text(
        f"""\
# Auto-generated by clickwheel. Edit to customize beets behavior.
# Docs: https://beets.readthedocs.io/en/stable/reference/config.html

directory: {cfg.music_dir}
library: {config_path.parent / "library.db"}

# Do not move or copy files — preserves paths for other apps (Plex, etc.)
import:
  move: no
  copy: no
  write: yes
  timid: no
  quiet_fallback: asis

# Skip hidden files and common junk directories
ignore: ['.*', 'System Volume Information', 'lost+found']
ignore_hidden: yes

paths:
  default: $albumartist/$album%aunique{{}}/$track $title
  singleton: Non-Album/$artist/$title
  comp: Compilations/$album%aunique{{}}/$track $title

plugins:
  - fetchart
  - embedart
  - lastgenre

fetchart:
  auto: no
  minwidth: 500
  maxwidth: 1200
  sources:
    - filesystem
    - coverart
    - itunes
    - amazon

embedart:
  auto: no
  ifempty: no
  maxwidth: 1200
  remove_art_file: no

lastgenre:
  auto: no
  count: 1
  fallback: ''
  source: album

match:
  strong_rec_thresh: 0.10
  preferred:
    media: ['Digital Media|File', 'CD']
  ignored: unmatched_tracks
"""
    )
    dim(f"Generated beets config at {config_path}")
