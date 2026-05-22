"""clickwheel CLI — command definitions."""

from __future__ import annotations

from pathlib import Path

import typer
from tqdm import tqdm

from clickwheel import __version__, actions
from clickwheel.actions import (
    AppleMusicAppleScriptError,
    AppleMusicAuthError,
    AppleMusicExtraNotInstalledError,
    AppleMusicKeyFileError,
    AppleMusicNoMatchesError,
    AppleMusicNotConfiguredError,
    AppleMusicPlaylistNotFoundError,
    AppleMusicUnreachableError,
    EjectFailedError,
    InsufficientSpaceError,
    IpodNotFoundError,
    LastfmNotConfiguredError,
    LibraryNotFoundError,
    MissingTracksError,
    PlaylistAlreadyExistsError,
    PlaylistNotFoundError,
    PlexExtraNotInstalledError,
    PlexNotConfiguredError,
    PlexPathRemapError,
    PlexPlaylistNotFoundError,
    PlexSectionNotFoundError,
    PlexSmartPlaylistError,
    PlexUnreachableError,
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
    description: str = typer.Option(
        "", "--description", "-d", help="Optional playlist description"
    ),
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
        actions.save_playlist(db, playlist_name, selected_paths, description or None)
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
        desc = actions.get_playlist_description(db, name)
        if desc:
            dim(desc)
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
        t.add_column("Description")
        t.add_column("Tracks", justify="right")
        t.add_column("Size", justify="right")
        t.add_column("Updated")

        for p in playlists:
            size_gb = (p["total_bytes"] or 0) / (1024 * 1024 * 1024)
            t.add_row(
                p["name"],
                p["description"] or "",
                str(p["tracks"]),
                f"{size_gb:.1f} GB",
                p["updated_at"],
            )

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
    description: str = typer.Option(
        "", "--description", "-d", help="Set the playlist description"
    ),
    no_scan: bool = typer.Option(
        False, "--no-scan", help="Skip automatic library scan"
    ),
) -> None:
    """Add or remove artists from a playlist."""
    cfg = load_config()
    db = Database(cfg.db_path)
    if not no_scan:
        maybe_auto_scan(cfg, db)

    # Non-interactive mode: --add / --remove / --description flags
    if add or remove or description:
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

        if description:
            try:
                actions.set_playlist_description(db, playlist_name, description)
                confirm(f'Description set for "{playlist_name}"')
            except actions.PlaylistNotFoundError:
                error(
                    f"Playlist '{playlist_name}' not found. Add artists "
                    "first, or run `clickwheel select` to create it."
                )
                db.close()
                raise typer.Exit(1) from None

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

    if result.library_updated:
        success("iPod library updated.")
    else:
        warn(
            "Couldn't update the iPod's library. "
            "Your music was copied, but the iPod may not show it."
        )
        if typer.confirm("Retry updating the iPod library?", default=True):
            with spinner("Retrying iPod library update..."):
                retry_ok = actions.retry_ipod_db_write(cfg, result.copied)
            if retry_ok:
                success("iPod library updated on retry.")
            else:
                error("Still couldn't update the iPod library.")

    if result.kept_in_place_count:
        warn(
            f"{result.kept_in_place_count} tracks on iPod aren't in this playlist. "
            "Run `clickwheel diff` to see them."
        )

    db.close()


@app.command(name="sync-plex")
def sync_plex(
    playlist_name: str = typer.Argument(
        None,
        help="Playlist to push to Plex. Omit with --all to push every playlist.",
    ),
    all_playlists: bool = typer.Option(
        False, "--all", help="Push every clickwheel playlist to Plex."
    ),
    no_scan: bool = typer.Option(
        False, "--no-scan", help="Skip automatic library scan."
    ),
) -> None:
    """Push playlist(s) to your Plex music library."""
    if not all_playlists and not playlist_name:
        error("Specify a playlist name or pass --all.")
        raise typer.Exit(1)
    if all_playlists and playlist_name:
        error("Pass --all OR a playlist name, not both.")
        raise typer.Exit(1)

    cfg = load_config()
    db = Database(cfg.db_path)
    if not no_scan:
        maybe_auto_scan(cfg, db)

    if all_playlists:
        targets = [p["name"] for p in actions.list_playlists(db)]
        if not targets:
            warn("No clickwheel playlists to push.")
            db.close()
            return
    else:
        targets = [playlist_name]

    pushed_any = False
    for target in targets:
        status(f"Pushing '{target}' to Plex")
        try:
            with spinner(f"Uploading '{target}' to Plex..."):
                result = actions.sync_playlist_to_plex(cfg, db, target)
        except PlexExtraNotInstalledError as exc:
            error(str(exc))
            db.close()
            raise typer.Exit(1) from exc
        except (
            PlexNotConfiguredError,
            PlexUnreachableError,
            PlexSectionNotFoundError,
            PlexPathRemapError,
            PlaylistNotFoundError,
        ) as exc:
            error(str(exc))
            if not all_playlists:
                db.close()
                raise typer.Exit(1) from exc
            continue

        pushed_any = True
        unresolved = result.pushed - result.resolved
        success(
            f"  '{target}' -> Plex: {result.resolved}/{result.pushed} tracks resolved"
        )
        if unresolved > 0:
            warn(
                f"  {unresolved} track(s) weren't found in Plex's index. "
                "They may not be scanned into Plex yet."
            )
        dim(f"  M3U: {result.m3u_local_path}")

    db.close()
    if all_playlists and not pushed_any:
        raise typer.Exit(1)


plex_app = typer.Typer(
    name="plex",
    help="Plex integration commands.",
    no_args_is_help=True,
)
app.add_typer(plex_app, name="plex")


@plex_app.command(name="doctor")
def plex_doctor_cmd() -> None:
    """Probe your Plex config end-to-end. Reports each stage (config,
    plexapi install, server connect, music section lookup, sample-track
    resolution) so failures point at exactly what's broken."""
    cfg = load_config()
    db = Database(cfg.db_path)
    try:
        result = actions.plex_doctor(cfg, db)
    finally:
        db.close()

    status("Plex doctor")
    for stage in result.stages:
        prefix = f"  {stage.name}:"
        if stage.ok:
            success(f"{prefix} {stage.detail}")
        else:
            error(f"{prefix} {stage.detail}")

    if not result.ok:
        raise typer.Exit(1)
    info("")
    dim("All checks passed. Try: clickwheel sync-plex <playlist>")


@plex_app.command(name="list")
def plex_list_cmd() -> None:
    """List every audio playlist on your Plex server, with kind and size.

    Manual playlists are safe to pull back into clickwheel via
    `clickwheel plex pull <name>`. Smart playlists are dynamically
    computed by Plex; pulling one freezes a snapshot and requires
    `--include-smart`.
    """
    cfg = load_config()
    try:
        with spinner("Reading Plex playlists..."):
            playlists = actions.list_plex_playlists(cfg)
    except PlexExtraNotInstalledError as exc:
        error(str(exc))
        raise typer.Exit(1) from exc
    except (PlexNotConfiguredError, PlexUnreachableError) as exc:
        error(str(exc))
        raise typer.Exit(1) from exc

    if not playlists:
        warn("No audio playlists on Plex.")
        return

    t = table(title="Plex audio playlists")
    t.add_column("Name")
    t.add_column("Kind")
    t.add_column("Tracks", justify="right")
    for pl in sorted(playlists, key=lambda p: (p.smart, p.name.lower())):
        kind_style = "[dim]smart[/dim]" if pl.smart else "[green]manual[/green]"
        t.add_row(pl.name, kind_style, f"{pl.track_count:,}")
    print_table(t)


@plex_app.command(name="pull")
def plex_pull_cmd(
    name: str = typer.Argument(..., help="Plex playlist to pull into clickwheel."),
    include_smart: bool = typer.Option(
        False,
        "--include-smart",
        help="Allow pulling a smart playlist (freezes a snapshot).",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Replace an existing clickwheel playlist with the same name.",
    ),
) -> None:
    """Pull a playlist from Plex back into clickwheel's local store.

    Useful for recovering hand-curated playlists after a clean install
    (Plex retains them server-side; clickwheel's SQLite did not). Each
    Plex track's file path is translated back to clickwheel's view via
    the configured remap and looked up in the index — only matched
    tracks land in the new playlist; unmatched ones are listed below
    so you know what to chase.
    """
    cfg = load_config()
    db = Database(cfg.db_path)
    try:
        with spinner(f"Pulling '{name}' from Plex..."):
            result = actions.pull_playlist_from_plex(
                cfg,
                db,
                name,
                include_smart=include_smart,
                overwrite=overwrite,
            )
    except PlexExtraNotInstalledError as exc:
        error(str(exc))
        raise typer.Exit(1) from exc
    except (
        PlexNotConfiguredError,
        PlexUnreachableError,
        PlexPlaylistNotFoundError,
        PlexSmartPlaylistError,
        PlaylistAlreadyExistsError,
    ) as exc:
        error(str(exc))
        raise typer.Exit(1) from exc
    finally:
        db.close()

    verb = "Replaced" if result.replaced else "Created"
    success(
        f"{verb} '{result.playlist_name}': "
        f"{result.matched}/{result.total_plex_tracks} tracks matched"
    )
    if result.description:
        dim(f"  Description: {result.description}")
    if result.skipped_no_path:
        warn(
            f"  {result.skipped_no_path} track(s) on Plex had no resolvable file "
            "path and were skipped."
        )
    if result.unmatched:
        warn(
            f"  {result.unmatched} track(s) on Plex didn't match clickwheel's "
            "index. Run `clickwheel scan` if the library has changed."
        )
        unmatched_table = table(title="Unmatched")
        unmatched_table.add_column("Artist")
        unmatched_table.add_column("Title")
        unmatched_table.add_column("Why", style="dim")
        for u in result.unmatched_details[:20]:
            unmatched_table.add_row(
                u.get("artist", "") or "?",
                u.get("title", "") or "?",
                u.get("reason", "") or "?",
            )
        print_table(unmatched_table)
        if len(result.unmatched_details) > 20:
            dim(f"  ... and {len(result.unmatched_details) - 20} more.")


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


# Per-phase timeout for beets subprocess calls. A correctly-scoped `fix`
# finishes a phase in minutes; this only trips when an SMB/NAS operation
# genuinely stalls, turning an indefinite hang into a reported failure.
FIX_PHASE_TIMEOUT = 1800


def _run_beets_fix(cfg, target: str) -> None:
    """Run the metadata cleanup pipeline.

    Four phases: catalog, cloud artwork + dates, fill genres, write tags.
    Requires beets to be installed: pipx inject clickwheel 'clickwheel[fix]'

    Album art and release years come from a native MusicBrainz / Cover Art
    Archive lookup (see `actions.apply_cloud_artwork`) rather than beets —
    beets' import matcher stalls on multi-pressing ambiguity in batch mode.
    Genres still come from beets `lastgenre`.

    Each run uses a fresh, temporary beets library. The catalog phase
    imports only `target` into it, so the whole-library beets phases that
    follow stay scoped to `target` rather than grinding over the entire
    collection — a single shared library would accumulate every album.
    """
    import os
    import subprocess
    import tempfile

    beets_dir = cfg.project_dir / "beets"
    beets_dir.mkdir(parents=True, exist_ok=True)

    beets_config = beets_dir / "config.yaml"
    if not beets_config.exists():
        _generate_beets_config(beets_config, cfg)

    env = {**os.environ, "BEETSDIR": str(beets_dir)}

    # A missing `beet` on PATH makes subprocess raise FileNotFoundError
    # rather than returning non-zero — catch it so the user gets the
    # install hint instead of a traceback.
    try:
        check = subprocess.run(
            ["beet", "version"], env=env, capture_output=True, timeout=30
        )
        beets_available = check.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        beets_available = False
    if not beets_available:
        error(
            "beets is not installed.\n"
            "  If you installed clickwheel with pipx:\n"
            "    pipx inject clickwheel 'clickwheel[fix]'\n"
            "  If you installed with pip:\n"
            "    pip install 'clickwheel[fix]'"
        )
        raise typer.Exit(1)

    with tempfile.TemporaryDirectory(prefix="clickwheel-beets-") as tmp:
        # Fresh library per run: `import` populates it with only `target`,
        # so the whole-library phases below cannot escape that scope.
        beet = ["beet", "-l", str(Path(tmp) / "library.db")]

        def _beet(args: list[str], phase: str) -> bool:
            with spinner(phase):
                try:
                    result = subprocess.run(
                        [*beet, *args],
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=FIX_PHASE_TIMEOUT,
                    )
                except subprocess.TimeoutExpired:
                    warn(
                        f"  Timed out after {FIX_PHASE_TIMEOUT // 60} min — "
                        "the music share may be slow or disconnected."
                    )
                    return False
            if result.returncode != 0:
                if result.stderr:
                    warn(f"  Failed: {result.stderr.strip()}")
                else:
                    warn("  Failed (no error details)")
                return False
            confirm(f"  {phase} Done")
            return True

        target_path = Path(target)
        if target_path.is_dir() and target == str(cfg.music_dir):
            status("Step 1/4: Cataloging library...")
            subdirs = sorted(
                d
                for d in target_path.iterdir()
                if d.is_dir() and not d.name.startswith(".")
            )
            import_ok = 0
            import_fail = 0
            for d in subdirs:
                try:
                    result = subprocess.run(
                        [*beet, "import", "-A", str(d)],
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=FIX_PHASE_TIMEOUT,
                    )
                    imported = result.returncode == 0
                except subprocess.TimeoutExpired:
                    imported = False
                if imported:
                    import_ok += 1
                else:
                    import_fail += 1
                    dim(f"  Skipped: {d.name}")
            if import_fail:
                warn(f"  Cataloged {import_ok} folders, {import_fail} skipped")
            else:
                confirm(f"  Done ({import_ok} folders)")
        else:
            _beet(["import", "-A", target], "Step 1/4: Cataloging library...")

        failed = 0

        # Step 2: cloud artwork + release years (native — see the
        # _run_beets_fix docstring for why this isn't a beets phase).
        status("Step 2/4: Fetching album art + dates from MusicBrainz...")
        try:
            art = actions.apply_cloud_artwork(
                target_path, on_album=lambda a: dim(f"  {a}")
            )
            confirm(
                f"  {art.albums_matched}/{art.albums_seen} albums matched — "
                f"art on {art.art_embedded} tracks, years on {art.years_set}"
            )
            if art.unmatched:
                warn("  No MusicBrainz match: " + ", ".join(art.unmatched))
            if art.art_fetch_failed:
                warn(
                    "  Cover Art Archive unreachable — rerun `fix` to retry: "
                    + ", ".join(art.art_fetch_failed)
                )
        except Exception as exc:
            warn(f"  Artwork step failed: {exc}")
            failed += 1

        remaining = [
            (["lastgenre"], "Step 3/4: Filling missing genres..."),
            (["write"], "Step 4/4: Writing tags to files..."),
        ]
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

# Album art and release years are handled natively by clickwheel
# (MusicBrainz + Cover Art Archive); beets is used only for genres.
plugins:
  - lastgenre

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


# ---------------------------------------------------------------------------
# Apple Music subcommand group
# ---------------------------------------------------------------------------


apple_app = typer.Typer(
    name="apple",
    help="Apple Music integration commands.",
    no_args_is_help=True,
)
app.add_typer(apple_app, name="apple")


@apple_app.command(name="auth")
def apple_auth_cmd() -> None:
    """Run the Music User Token authorization flow.

    Opens your browser to a tiny local page that loads MusicKit JS,
    asks you to sign in with your Apple ID, and posts the resulting
    user token back to clickwheel. The token is saved to
    ~/.clickwheel/.env as APPLE_MUSIC_USER_TOKEN. One-time per Mac
    per Apple ID (the token is long-lived but can be revoked).
    """
    cfg = load_config()
    status("Apple Music auth")
    info("  Opening your browser to a local auth page...")
    info("  Click 'Authorize with Apple Music', sign in, then return here.")
    try:
        with spinner("Waiting for browser authorization..."):
            token = actions.apple_music_auth(cfg)
    except AppleMusicExtraNotInstalledError as exc:
        error(str(exc))
        raise typer.Exit(1) from exc
    except (
        AppleMusicNotConfiguredError,
        AppleMusicKeyFileError,
        AppleMusicAuthError,
        AppleMusicUnreachableError,
    ) as exc:
        error(str(exc))
        raise typer.Exit(1) from exc

    success(f"Authorized. User token saved ({len(token)} chars).")
    dim("Try: clickwheel apple doctor")


@apple_app.command(name="doctor")
def apple_doctor_cmd() -> None:
    """Probe Apple Music end-to-end (config, .p8, dev token, user token,
    storefront, iCloud Music Library state). Mirrors `plex doctor`.
    """
    cfg = load_config()
    try:
        result = actions.apple_music_doctor(cfg)
    except Exception as exc:  # noqa: BLE001
        error(f"Apple Music doctor crashed: {exc}")
        raise typer.Exit(1) from exc

    status("Apple Music doctor")
    for stage in result.stages:
        prefix = f"  {stage.name}:"
        if stage.ok:
            success(f"{prefix} {stage.detail}")
        else:
            error(f"{prefix} {stage.detail}")

    if not result.ok:
        raise typer.Exit(1)
    info("")
    dim("All checks passed. Try: clickwheel apple match <playlist>")


@apple_app.command(name="match")
def apple_match_cmd(
    name: str = typer.Argument(..., help="clickwheel playlist to match."),
    refresh: bool = typer.Option(
        False, "--refresh", help="Ignore the cache and re-match every track."
    ),
    min_confidence: float = typer.Option(
        0.85, "--min-confidence", help="Threshold between matched and low-confidence."
    ),
) -> None:
    """Preview how a playlist's tracks resolve to Apple Music song IDs.

    Read-only against your Apple Music account (no playlist is created)
    but populates the local match cache so a subsequent `apple push`
    is fast. Tracks below `--min-confidence` are surfaced as
    'low-confidence' so you can eyeball them before pushing.
    """
    cfg = load_config()
    db = Database(cfg.db_path)
    try:
        with spinner(f"Matching '{name}' against Apple Music..."):
            result = actions.match_playlist_to_apple_music(
                cfg, db, name, refresh=refresh, min_confidence=min_confidence
            )
    except AppleMusicExtraNotInstalledError as exc:
        error(str(exc))
        raise typer.Exit(1) from exc
    except (
        AppleMusicNotConfiguredError,
        AppleMusicKeyFileError,
        AppleMusicUnreachableError,
        PlaylistNotFoundError,
    ) as exc:
        error(str(exc))
        raise typer.Exit(1) from exc
    finally:
        db.close()

    status(f"Match preview for '{name}'")
    info(
        f"  storefront={result.storefront}  iCloud Music Library="
        f"{'ON' if result.icml else 'OFF'}"
    )
    success(f"  matched ({result.matched}/{result.total})")
    if result.low_confidence:
        warn(f"  low confidence ({result.low_confidence})")
    if result.unmatched:
        warn(f"  unmatched ({result.unmatched})")
    info("")

    t = table(title="Tracks")
    t.add_column("Status", width=10)
    t.add_column("Artist")
    t.add_column("Title")
    t.add_column("Conf", justify="right")
    t.add_column("Why", style="dim")
    for row in result.tracks[:50]:
        if row.song_id is None:
            statuslbl = "[red]miss[/red]"
        elif row.confidence >= min_confidence:
            statuslbl = "[green]ok[/green]"
        else:
            statuslbl = "[yellow]low[/yellow]"
        t.add_row(
            statuslbl,
            row.artist or "?",
            row.title or "?",
            f"{row.confidence:.2f}" if row.song_id else "—",
            row.reason,
        )
    print_table(t)
    if len(result.tracks) > 50:
        dim(f"  ... and {len(result.tracks) - 50} more rows.")


@apple_app.command(name="push")
def apple_push_cmd(
    name: str = typer.Argument(..., help="clickwheel playlist to push to Apple Music."),
    refresh: bool = typer.Option(
        False, "--refresh", help="Ignore the cache and re-match every track."
    ),
    min_confidence: float = typer.Option(
        0.85, "--min-confidence", help="Reject matches below this confidence."
    ),
    include_low: bool = typer.Option(
        False,
        "--include-low",
        help="Push low-confidence matches too (use after reviewing).",
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip the confirmation prompt."
    ),
) -> None:
    """Create a playlist in your Apple Music account from a clickwheel playlist.

    Runs the matcher first, then pushes the matched tracks via
    `POST /v1/me/library/playlists`. Iclupow-confidence matches are skipped
    by default; pass --include-low after a `clickwheel apple match` review
    if you want them in.
    """
    cfg = load_config()
    db = Database(cfg.db_path)
    try:
        with spinner(f"Matching '{name}'..."):
            preview = actions.match_playlist_to_apple_music(
                cfg, db, name, refresh=refresh, min_confidence=min_confidence
            )
    except AppleMusicExtraNotInstalledError as exc:
        error(str(exc))
        db.close()
        raise typer.Exit(1) from exc
    except (
        AppleMusicNotConfiguredError,
        AppleMusicKeyFileError,
        AppleMusicUnreachableError,
        PlaylistNotFoundError,
    ) as exc:
        error(str(exc))
        db.close()
        raise typer.Exit(1) from exc

    will_push = preview.matched + (preview.low_confidence if include_low else 0)
    status(f"About to push '{name}' to Apple Music")
    info(
        f"  matched={preview.matched}  low_confidence="
        f"{preview.low_confidence}  unmatched={preview.unmatched}"
    )
    info(f"  pushing {will_push}/{preview.total} tracks")
    if not yes and not typer.confirm("Proceed?", default=True):
        db.close()
        raise typer.Exit(0)

    try:
        with spinner("Creating Apple Music playlist..."):
            result = actions.sync_playlist_to_apple_music(
                cfg,
                db,
                name,
                refresh=False,  # we already ran the match above
                min_confidence=min_confidence,
                include_low_confidence=include_low,
            )
    except AppleMusicNoMatchesError as exc:
        error(str(exc))
        if exc.matched_low_confidence > 0:
            dim(
                "  Re-run with `--include-low` to push the low-confidence "
                "candidates anyway, or `clickwheel apple match` to inspect."
            )
        db.close()
        raise typer.Exit(1) from exc
    except (
        AppleMusicNotConfiguredError,
        AppleMusicKeyFileError,
        AppleMusicUnreachableError,
        PlaylistNotFoundError,
    ) as exc:
        error(str(exc))
        db.close()
        raise typer.Exit(1) from exc
    finally:
        db.close()

    success(
        f"Pushed '{result.playlist_name}' to Apple Music — "
        f"{result.pushed} tracks (id {result.apple_music_playlist_id})"
    )
    if result.unmatched:
        warn(
            f"  {result.unmatched} track(s) had no Apple Music match. "
            "Check `clickwheel apple match` output."
        )
    if result.low_confidence_skipped:
        dim(
            f"  Skipped {result.low_confidence_skipped} low-confidence row(s). "
            "Re-run with `--include-low` to include them."
        )


@apple_app.command(name="list")
def apple_list_cmd() -> None:
    """List every library playlist in your Apple Music account.

    Read-only. Use before `apple pull` to find the playlist you want.
    Manual and smart playlists both appear; smart ones come back with
    `canEdit=false` (we can pull them but you can't push back).
    """
    cfg = load_config()
    try:
        with spinner("Reading Apple Music playlists..."):
            playlists = actions.list_apple_music_playlists(cfg)
    except AppleMusicExtraNotInstalledError as exc:
        error(str(exc))
        raise typer.Exit(1) from exc
    except (
        AppleMusicNotConfiguredError,
        AppleMusicKeyFileError,
        AppleMusicUnreachableError,
    ) as exc:
        error(str(exc))
        raise typer.Exit(1) from exc

    if not playlists:
        warn("No library playlists on Apple Music.")
        return
    t = table(title="Apple Music library playlists")
    t.add_column("Name")
    t.add_column("Tracks", justify="right")
    t.add_column("Editable", width=8)
    t.add_column("ID", style="dim")
    for p in sorted(playlists, key=lambda x: x.name.lower()):
        # Apple's listing endpoint doesn't include trackCount; render
        # None as `?` rather than misleading `0`.
        tracks = f"{p.track_count:,}" if p.track_count is not None else "?"
        t.add_row(p.name, tracks, "yes" if p.can_edit else "no", p.playlist_id)
    print_table(t)


@apple_app.command(name="pull")
def apple_pull_cmd(
    name: str = typer.Argument(..., help="Apple Music playlist to import."),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Replace an existing clickwheel playlist with the same name.",
    ),
    min_fuzzy_confidence: float = typer.Option(
        0.85, "--min-fuzzy", help="Fuzzy-match threshold for unmatched cache entries."
    ),
) -> None:
    """Import an Apple Music library playlist into clickwheel's local store.

    Each Apple track is resolved to a local file in this order: the
    song_map cache from prior pushes → exact metadata match against
    your SQLite index → fuzzy composite score. Unmatched rows are
    surfaced so you know what to chase (typically files Apple has
    that clickwheel hasn't scanned).
    """
    cfg = load_config()
    db = Database(cfg.db_path)
    try:
        with spinner(f"Pulling '{name}' from Apple Music..."):
            result = actions.pull_playlist_from_apple_music(
                cfg,
                db,
                name,
                overwrite=overwrite,
                min_fuzzy_confidence=min_fuzzy_confidence,
            )
    except AppleMusicExtraNotInstalledError as exc:
        error(str(exc))
        raise typer.Exit(1) from exc
    except (
        AppleMusicNotConfiguredError,
        AppleMusicKeyFileError,
        AppleMusicUnreachableError,
        AppleMusicPlaylistNotFoundError,
        PlaylistAlreadyExistsError,
    ) as exc:
        error(str(exc))
        raise typer.Exit(1) from exc
    finally:
        db.close()

    verb = "Replaced" if result.replaced else "Created"
    success(
        f"{verb} '{result.playlist_name}': "
        f"{result.matched}/{result.total} tracks matched locally"
    )
    if result.description:
        dim(f"  Description: {result.description}")
    if result.unmatched:
        warn(
            f"  {result.unmatched} track(s) on Apple Music had no local match. "
            "Run `clickwheel scan` if your library has changed, or accept the gap."
        )
        t = table(title="Unmatched")
        t.add_column("Artist")
        t.add_column("Title")
        t.add_column("Album", style="dim")
        unmatched_rows = [r for r in result.tracks if r.local_path is None]
        for r in unmatched_rows[:20]:
            t.add_row(r.artist or "?", r.title or "?", r.album or "?")
        print_table(t)
        if len(unmatched_rows) > 20:
            dim(f"  ... and {len(unmatched_rows) - 20} more.")


@apple_app.command(name="delete")
def apple_delete_cmd(
    name: str = typer.Argument(
        ..., help="Apple Music library playlist name to delete."
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip the confirmation prompt."
    ),
) -> None:
    """Delete a library playlist from your Apple Music account.

    Apple's REST API doesn't expose DELETE on library playlists, so
    clickwheel drives Music.app via AppleScript instead. Music.app's
    iCloud Music Library sync propagates the deletion to all your
    signed-in Apple devices.

    macOS-only. Music.app must be launchable (it is on every recent
    Mac, but the user must be signed in to the same Apple ID as the
    playlist). Deletes EVERY playlist matching the name — useful for
    cleaning up duplicates from earlier failed pushes.
    """
    _check_macos()
    status(f"About to delete '{name}' from Apple Music via Music.app")
    info("  This drives Music.app and propagates via iCloud Music Library.")
    if not yes and not typer.confirm("Proceed?", default=False):
        raise typer.Exit(0)

    try:
        with spinner("Deleting via AppleScript..."):
            result = actions.delete_apple_music_playlist(name)
    except AppleMusicAppleScriptError as exc:
        error(str(exc))
        raise typer.Exit(1) from exc

    if result.deleted == 0:
        warn(
            f"No Music.app playlist named '{name}' found. "
            "It may have already been deleted, or the name is misspelled."
        )
        raise typer.Exit(1)
    success(
        f"Deleted {result.deleted} playlist(s) named '{name}'. "
        "iCloud Music Library will propagate to your other devices."
    )
