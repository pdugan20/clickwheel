"""Thread-safe global sync-progress state.

Long-running iPod tools (sync_playlist_to_ipod, add_tracks_to_ipod,
add_artist_to_ipod, remove_*) push progress into this module from their
per-track callbacks. The `state://clickwheel/sync-progress` MCP resource
reads from here so the sync-result iframe can poll for live updates
while a tool is mid-call.

The state is a single global because realistic clickwheel usage has at
most one sync running at a time. If we ever need concurrent operations,
swap the dict for keyed-by-operation-id storage and have tools pass an
id back to the iframe via toolInfo._meta.
"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass


@dataclass
class SyncProgress:
    """Snapshot of the most recent in-flight sync/add/remove operation.

    `kind` is the operation flavor ("add", "sync", "remove") so the
    bundle can render different copy. `detail` is a static one-liner
    summarising the whole operation (e.g. "145 MB · 8 albums") — set
    once at start, never updated mid-run. `done` flips true when the
    tool completes; at that point the iframe should stop polling and
    let its `ontoolresult` handler take over.
    """

    kind: str = "idle"
    current: int = 0
    total: int = 0
    message: str = ""
    operation: str = ""  # human-readable target ("playlist 'test-mix'", etc.)
    detail: str = ""  # static subtitle ("145 MB · 8 albums")
    started_at: float = 0.0
    done: bool = True


_lock = threading.Lock()
_state: SyncProgress = SyncProgress()


def start(kind: str, total: int, operation: str = "", detail: str = "") -> None:
    """Begin a new operation. Resets counters and flips done=False."""
    global _state
    with _lock:
        _state = SyncProgress(
            kind=kind,
            current=0,
            total=total,
            message="",
            operation=operation,
            detail=detail,
            started_at=time.time(),
            done=False,
        )


def update(current: int, total: int, message: str) -> None:
    """Record a per-track tick. Cheap, called from worker threads."""
    with _lock:
        _state.current = current
        # Total can drift if e.g. compute_diff changed it mid-flight; trust
        # the latest value rather than the initial start() estimate.
        _state.total = total
        _state.message = message


def finish() -> None:
    """Mark the operation complete. Iframe will stop polling on its
    next read."""
    with _lock:
        _state.done = True


def snapshot() -> dict:
    """Return the current state as a plain dict — safe to JSON-encode."""
    with _lock:
        return asdict(_state)
