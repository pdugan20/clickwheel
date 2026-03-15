"""clickwheel CLI — command definitions."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from tqdm import tqdm

from clickwheel import __version__
from clickwheel.config import load_config
from clickwheel.db import Database
from clickwheel.library import find_audio_files, scan_file

app = typer.Typer(
    name="clickwheel",
    help="A CLI for syncing a music library to a classic iPod.",
    no_args_is_help=True,
)
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"clickwheel {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-v", help="Show version", callback=_version_callback
    ),
) -> None:
    """clickwheel — sync your music library to a classic iPod."""


@app.command()
def scan(
    full: bool = typer.Option(False, "--full", "-f", help="Force full rescan"),
) -> None:
    """Index the music library and report on metadata quality."""
    cfg = load_config()

    if not cfg.music_dir.is_dir():
        console.print(f"[red][ERROR][/red] Music directory not found: {cfg.music_dir}")
        raise typer.Exit(1)

    db = Database(cfg.db_path)

    if full:
        db.clear_tracks()

    console.print(f"[bold]Scanning:[/bold] {cfg.music_dir}")
    files = find_audio_files(cfg.music_dir)
    console.print(f"Found {len(files):,} audio files")

    scanned = 0
    errors = 0
    for f in tqdm(files, desc="Scanning", unit="file"):
        track = scan_file(f)
        if track:
            db.upsert_track(track)
            scanned += 1
        else:
            errors += 1

        if scanned % 500 == 0:
            db.commit()

    db.commit()

    stats = db.get_stats()
    formats = db.get_format_breakdown()
    db.close()

    console.print()
    _print_stats(stats, formats, errors)


@app.command()
def fix() -> None:
    """Clean up metadata, fetch album art, and fill genres via beets."""
    cfg = load_config()
    scripts_dir = cfg.project_dir / "scripts"
    fix_script = scripts_dir / "fix-metadata.sh"

    if not fix_script.exists():
        console.print(f"[red][ERROR][/red] Script not found: {fix_script}")
        raise typer.Exit(1)

    import subprocess

    console.print("[bold]Running beets metadata cleanup...[/bold]")
    result = subprocess.run(
        [str(fix_script)],
        env={"BEETSDIR": str(cfg.project_dir / "beets"), "PATH": _get_path()},
        cwd=str(cfg.project_dir),
    )
    raise typer.Exit(result.returncode)


@app.command()
def select() -> None:
    """Interactively pick artists/albums for the iPod."""
    cfg = load_config()
    db = Database(cfg.db_path)
    artists = db.get_artists()

    if not artists:
        console.print(
            "[yellow]No tracks indexed.[/yellow] Run `clickwheel scan` first."
        )
        db.close()
        raise typer.Exit(1)

    console.print(f"[bold]{len(artists)} artists available[/bold] (FLAC excluded)")
    console.print()

    selected_paths: list[str] = []
    selected_size = 0

    table = Table(title="Artists", show_lines=False)
    table.add_column("#", style="dim", width=5)
    table.add_column("Artist")
    table.add_column("Albums", justify="right")
    table.add_column("Tracks", justify="right")
    table.add_column("Size", justify="right")

    for i, a in enumerate(artists, 1):
        size_mb = (a["total_bytes"] or 0) / (1024 * 1024)
        table.add_row(
            str(i),
            a["name"] or "(unknown)",
            str(a["albums"]),
            str(a["tracks"]),
            f"{size_mb:.0f} MB",
        )

    console.print(table)
    console.print()
    console.print(
        "[dim]Enter artist numbers (comma-separated), "
        "'all' for everything, or 'done' to finish.[/dim]"
    )

    while True:
        total_mb = selected_size / (1024 * 1024)
        prompt = f"Selected: {len(selected_paths)} tracks, {total_mb:.0f} MB > "
        choice = typer.prompt(prompt, default="done")

        if choice.lower() == "done":
            break
        if choice.lower() == "all":
            for a in artists:
                albums = db.get_albums_by_artist(a["name"])
                for album in albums:
                    tracks = db.get_tracks_by_album(a["name"], album["album"])
                    for t in tracks:
                        if t["path"] not in selected_paths:
                            selected_paths.append(t["path"])
                            selected_size += t["file_size"] or 0
            console.print("[green]Added all artists[/green]")
            continue

        try:
            indices = [int(x.strip()) for x in choice.split(",")]
        except ValueError:
            console.print("[red]Invalid input.[/red] Enter numbers or 'done'.")
            continue

        for idx in indices:
            if 1 <= idx <= len(artists):
                a = artists[idx - 1]
                albums = db.get_albums_by_artist(a["name"])
                added = 0
                for album in albums:
                    tracks = db.get_tracks_by_album(a["name"], album["album"])
                    for t in tracks:
                        if t["path"] not in selected_paths:
                            selected_paths.append(t["path"])
                            selected_size += t["file_size"] or 0
                            added += 1
                console.print(f"[green]+[/green] {a['name']}: {added} tracks")

    if selected_paths:
        name = typer.prompt("Playlist name", default="ipod")
        db.save_playlist(name, selected_paths)
        total_mb = selected_size / (1024 * 1024)
        total_gb = selected_size / (1024 * 1024 * 1024)
        console.print(
            f"\n[bold green]Saved playlist '{name}':[/bold green] "
            f"{len(selected_paths)} tracks, {total_gb:.1f} GB"
        )

    db.close()


@app.command()
def playlist(
    name: str = typer.Argument(None, help="Playlist name to show details"),
) -> None:
    """List saved playlists or show details of a specific playlist."""
    cfg = load_config()
    db = Database(cfg.db_path)

    if name:
        tracks = db.get_playlist(name)
        if not tracks:
            console.print(f"[red]Playlist '{name}' not found or empty.[/red]")
            db.close()
            raise typer.Exit(1)

        table = Table(title=f"Playlist: {name}")
        table.add_column("#", style="dim", width=5)
        table.add_column("Artist")
        table.add_column("Album")
        table.add_column("Title")
        table.add_column("Size", justify="right")

        total_size = 0
        for i, t in enumerate(tracks, 1):
            size_mb = (t["file_size"] or 0) / (1024 * 1024)
            total_size += t["file_size"] or 0
            table.add_row(
                str(i),
                t["artist"] or "?",
                t["album"] or "?",
                t["title"] or "?",
                f"{size_mb:.1f} MB",
            )

        console.print(table)
        total_gb = total_size / (1024 * 1024 * 1024)
        console.print(f"\n[bold]{len(tracks)} tracks, {total_gb:.1f} GB[/bold]")
    else:
        playlists = db.list_playlists()
        if not playlists:
            console.print("[yellow]No playlists saved yet.[/yellow]")
            db.close()
            return

        table = Table(title="Playlists")
        table.add_column("Name")
        table.add_column("Tracks", justify="right")
        table.add_column("Size", justify="right")
        table.add_column("Updated")

        for p in playlists:
            size_gb = (p["total_bytes"] or 0) / (1024 * 1024 * 1024)
            table.add_row(
                p["name"], str(p["tracks"]), f"{size_gb:.1f} GB", p["updated_at"]
            )

        console.print(table)

    db.close()


@app.command()
def diff(
    playlist_name: str = typer.Argument("ipod", help="Playlist to diff against iPod"),
) -> None:
    """Preview what would be added/removed on the iPod."""
    console.print(
        f"[yellow]iPod sync not yet implemented.[/yellow] "
        f"Playlist '{playlist_name}' is ready — iPod integration coming in Phase 5."
    )


@app.command()
def sync(
    playlist_name: str = typer.Argument("ipod", help="Playlist to sync"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without syncing"),
) -> None:
    """Push the current selection to the iPod."""
    console.print(
        f"[yellow]iPod sync not yet implemented.[/yellow] "
        f"Playlist '{playlist_name}' is ready — iPod integration coming in Phase 5."
    )


@app.command()
def ls() -> None:
    """Show what's currently on the iPod."""
    console.print(
        "[yellow]iPod integration not yet implemented.[/yellow] Coming in Phase 5."
    )


@app.command()
def eject() -> None:
    """Safely unmount the iPod."""
    console.print(
        "[yellow]iPod integration not yet implemented.[/yellow] Coming in Phase 5."
    )


def _print_stats(stats: dict, formats: list[dict], errors: int) -> None:
    """Print scan results in a formatted table."""
    total_gb = (stats["total_bytes"] or 0) / (1024 * 1024 * 1024)
    hours = (stats["total_seconds"] or 0) / 3600

    table = Table(title="Library Summary", show_header=False, box=None)
    table.add_column("Label", style="bold")
    table.add_column("Value")
    table.add_row("Tracks", f"{stats['total_tracks']:,}")
    table.add_row("Artists", f"{stats['artists']:,}")
    table.add_row("Albums", f"{stats['albums']:,}")
    table.add_row("Total size", f"{total_gb:.1f} GB")
    table.add_row("Total duration", f"{hours:.1f} hours")
    console.print(table)

    console.print()
    fmt_table = Table(title="Formats")
    fmt_table.add_column("Format")
    fmt_table.add_column("Tracks", justify="right")
    fmt_table.add_column("Size", justify="right")
    for f in formats:
        size_gb = (f["total_bytes"] or 0) / (1024 * 1024 * 1024)
        fmt_table.add_row(f["format"].upper(), f"{f['count']:,}", f"{size_gb:.1f} GB")
    console.print(fmt_table)

    console.print()
    quality_table = Table(title="Metadata Quality")
    quality_table.add_column("Check", style="bold")
    quality_table.add_column("OK", justify="right", style="green")
    quality_table.add_column("Missing", justify="right", style="red")

    total = stats["total_tracks"]
    quality_table.add_row(
        "Album art",
        str(stats["with_art"]),
        str(stats["without_art"]),
    )
    quality_table.add_row(
        "Genre",
        str(total - stats["missing_genre"]),
        str(stats["missing_genre"]),
    )
    quality_table.add_row(
        "Title",
        str(total - stats["missing_title"]),
        str(stats["missing_title"]),
    )
    quality_table.add_row(
        "Artist",
        str(total - stats["missing_artist"]),
        str(stats["missing_artist"]),
    )
    console.print(quality_table)

    if errors:
        console.print(f"\n[yellow]{errors} files could not be read[/yellow]")


def _get_path() -> str:
    """Get PATH with common Homebrew locations."""
    import os

    path = os.environ.get("PATH", "")
    extra = ["/opt/homebrew/bin", "/usr/local/bin", str(Path.home() / ".local/bin")]
    return ":".join(extra + [path])
