"""Library storage mount health + automatic remount (macOS network shares).

The music library lives on a network share — typically a NAS over SMB
(`/Volumes/Public` from a QNAP, in the reference setup). Network shares
drop: after the Mac sleeps, a Wi-Fi blip, or a NAS reboot, the mount goes
*stale* — it still shows up in `mount`, but any access blocks on a long
kernel timeout and then errors. A plain `Path.is_dir()` guard HANGS on a
stale mount, which is exactly wrong for the remote-MCP case (a tool call
fired from your phone spins instead of recovering).

This module provides:

- `probe_live()` — a timeout-bounded liveness check that never hangs (a
  stale-mount stat can block uninterruptibly in the kernel, so we run it in
  a daemon thread and abandon it on timeout; a subsequent force-unmount
  frees the blocked stat).
- `ensure_mounted()` — probe, and if the share is stale/dropped, force-
  unmount the dead mount and re-establish it via NetFS (`open smb://…`,
  which pulls SMB credentials from the login keychain and works headlessly
  under a launchd GUI agent). Returns a status; never force-touches a local
  disk (it only ever acts on *network* filesystems).

The disk-spindown case (the most common "lag") needs nothing from this
module — the probe simply returns as soon as the disks wake. The generous
probe timeout exists precisely so a slow spin-up isn't mistaken for a stale
mount and needlessly remounted.

macOS-only for the remount path. On other platforms it degrades to a
best-effort probe and reports OFFLINE rather than attempting a remount.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

logger = logging.getLogger(__name__)

# Generous enough that a NAS spinning its disks back up from standby (5-15s)
# returns LIVE rather than being mistaken for a stale mount. The probe returns
# as soon as the stat completes, so this only costs wall-clock in the genuinely
# stale case (where we then remount).
PROBE_TIMEOUT_S = 10.0
# How long to wait for a freshly-issued remount to come up before giving up.
REMOUNT_WAIT_S = 15.0
# Network filesystem types we know how to remount. We NEVER act on a local
# filesystem (apfs/hfs) — that guards against force-unmounting `/` when a path
# happens to resolve to the root mount.
_NETWORK_FS_TYPES = ("smbfs", "nfs", "afpfs", "webdav")


class MountStatus(StrEnum):
    """Outcome of an `ensure_mounted` call."""

    LIVE = "live"  # already healthy (incl. a disk that just spun up)
    REMOUNTED = "remounted"  # was stale/dropped; we re-established it
    OFFLINE = "offline"  # unreachable and couldn't be remounted


@dataclass
class MountResult:
    status: MountStatus
    mountpoint: str
    detail: str = ""


def probe_live(path: Path, timeout: float = PROBE_TIMEOUT_S) -> bool:
    """Return True if `path` is a readable directory, decided within `timeout`.

    Runs the stat in a daemon thread so a stale-mount stat (which can block
    uninterruptibly in the kernel) can't hang the caller — on timeout we
    abandon the thread and report not-live. The thread unblocks on its own
    once the I/O returns or the mount is force-unmounted.
    """
    result: list[bool] = []

    def _check() -> None:
        try:
            result.append(path.is_dir())
        except OSError:
            result.append(False)

    t = threading.Thread(target=_check, daemon=True)
    t.start()
    t.join(timeout)
    return bool(result) and result[0]


def _network_mount_for(path: Path) -> tuple[str, str] | None:
    """Return `(source_url, mountpoint)` for the *network* mount that contains
    `path`, or None if `path` isn't under one.

    Parses `mount` output, e.g.::

        //pat@host._smb._tcp.local/Public on /Volumes/Public (smbfs, nodev, ...)

    Only network filesystem types are considered (see `_NETWORK_FS_TYPES`), so
    a local path under `/` never matches the root mount. Picks the longest
    matching mountpoint when several apply.
    """
    try:
        out = subprocess.run(
            ["mount"], capture_output=True, text=True, timeout=5
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None

    target = str(path)
    best: tuple[str, str] | None = None
    for line in out.splitlines():
        # "<src> on <mountpoint> (<fstype>, <opts...>)"
        if " on " not in line or "(" not in line:
            continue
        src, _, rest = line.partition(" on ")
        mountpoint, _, opts = rest.partition(" (")
        mountpoint = mountpoint.strip()
        fstype = opts.split(",", 1)[0].strip().rstrip(")")
        if fstype not in _NETWORK_FS_TYPES:
            continue
        under = target == mountpoint or target.startswith(mountpoint.rstrip("/") + "/")
        if under and (best is None or len(mountpoint) > len(best[1])):
            best = (src.strip(), mountpoint)
    return best


def _smb_url(source: str) -> str:
    """Turn a mount source like `//pat@host/Public` into `smb://pat@host/Public`
    so `open` can hand it to NetFS (which authenticates from the keychain)."""
    source = source.strip()
    if source.startswith("//"):
        return "smb:" + source
    return source


def ensure_mounted(
    music_dir: Path,
    *,
    mount_url: str = "",
    auto_remount: bool = True,
    probe_timeout: float = PROBE_TIMEOUT_S,
    remount_wait: float = REMOUNT_WAIT_S,
) -> MountResult:
    """Ensure `music_dir` is on a live mount, remounting a stale/dropped network
    share if possible. Returns a `MountResult`; the caller decides how to
    surface OFFLINE (this function never raises for the offline case).

    `mount_url` is an explicit `smb://…` (or `//…`) fallback used when the
    share has fully unmounted (no `mount` entry to read the source from). For
    the common stale case the source is recovered from the existing entry.
    """
    if probe_live(music_dir, probe_timeout):
        return MountResult(MountStatus.LIVE, str(music_dir))

    if not auto_remount or sys.platform != "darwin":
        return MountResult(
            MountStatus.OFFLINE,
            str(music_dir),
            "library share is not reachable",
        )

    found = _network_mount_for(music_dir)
    if found is None and not mount_url:
        # Not under any known network mount and no override — nothing safe to
        # remount (don't touch local disks).
        return MountResult(
            MountStatus.OFFLINE,
            str(music_dir),
            "no network mount source known (set library_mount_url to enable "
            "remount of a fully-unmounted share)",
        )

    mountpoint = found[1] if found else _mountpoint_for(music_dir)
    source = mount_url or found[0]  # type: ignore[index]
    url = _smb_url(source)

    # Force-unmount a stale mount so the remount lands back on the SAME
    # mountpoint (music_dir + Plex path-remap are hardcoded to it; otherwise
    # macOS would remount at "<mountpoint>-1").
    if found is not None:
        subprocess.run(
            ["diskutil", "unmount", "force", mountpoint],
            capture_output=True,
            text=True,
        )

    logger.info("library share stale/dropped; remounting %s at %s", url, mountpoint)
    try:
        subprocess.run(["open", url], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        return MountResult(MountStatus.OFFLINE, mountpoint, f"remount failed: {exc}")

    # NetFS mounts asynchronously — poll until the share comes up (bounded).
    deadline = time.monotonic() + remount_wait
    while time.monotonic() < deadline:
        if os.path.ismount(mountpoint) and probe_live(music_dir, probe_timeout):
            return MountResult(MountStatus.REMOUNTED, mountpoint, f"remounted {url}")
        time.sleep(0.5)

    return MountResult(
        MountStatus.OFFLINE,
        mountpoint,
        f"remount of {url} did not come up within {remount_wait:.0f}s "
        "(the NAS may be asleep or off the network)",
    )


def _mountpoint_for(music_dir: Path) -> str:
    """Best-guess mountpoint for a music dir when it's fully unmounted (no
    `mount` entry to read). For `/Volumes/<share>/...` that's `/Volumes/<share>`.
    """
    parts = music_dir.parts
    if len(parts) >= 3 and parts[1] == "Volumes":
        return str(Path(parts[0], parts[1], parts[2]))
    return str(music_dir)
