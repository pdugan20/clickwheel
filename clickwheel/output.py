"""Centralized CLI output — all user-facing messages go through here.

This module owns the Rich console instance. Other modules should use
these helpers instead of calling console.print() with raw markup.
A pre-commit pygrep hook enforces this.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

console = Console()


def error(msg: str) -> None:
    """Print an error message. Use for failures that stop execution."""
    console.print(f"[red][ERROR][/red] {msg}")


def warn(msg: str) -> None:
    """Print a warning. Use for non-fatal issues the user should know about."""
    console.print(f"[yellow][WARNING][/yellow] {msg}")


def success(msg: str) -> None:
    """Print a success message. Use for final results of a command."""
    console.print(f"[bold green]{msg}[/bold green]")


def info(msg: str) -> None:
    """Print an informational message. Plain text, no decoration."""
    console.print(msg)


def status(msg: str) -> None:
    """Print a status/heading message. Bold, used for in-progress actions."""
    console.print(f"[bold]{msg}[/bold]")


def dim(msg: str) -> None:
    """Print a dimmed/hint message."""
    console.print(f"[dim]{msg}[/dim]")


def confirm(msg: str) -> None:
    """Print an inline confirmation. Green, not bold."""
    console.print(f"[green]{msg}[/green]")


def table(*args, **kwargs) -> Table:
    """Create a Rich Table. Caller should pass it to print_table()."""
    if "title_style" not in kwargs:
        kwargs["title_style"] = "bold not italic"
    if "title_justify" not in kwargs:
        kwargs["title_justify"] = "left"
    if "box" not in kwargs:
        kwargs["box"] = None
    if "pad_edge" not in kwargs:
        kwargs["pad_edge"] = False
    kwargs.setdefault("header_style", "bold")
    return Table(*args, **kwargs)


def print_table(t: Table) -> None:
    """Print a Rich Table."""
    console.print(t)


def print_panel(content: str, title: str = "", style: str = "dim") -> None:
    """Print content inside a bordered panel."""
    console.print(Panel(content, title=title, border_style=style))


@contextmanager
def spinner(msg: str) -> Generator[None, None, None]:
    """Show an animated spinner while work is in progress."""
    with console.status(f"[bold]{msg}[/bold]"):
        yield


def live_table() -> Live:
    """Create a Rich Live context for in-place table updates."""
    return Live(console=console, refresh_per_second=8)
