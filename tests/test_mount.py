"""Tests for library mount health + auto-remount (clickwheel/mount.py)."""

from __future__ import annotations

import time
import types
from pathlib import Path

import pytest

from clickwheel import actions, mount
from clickwheel.config import Config
from clickwheel.mount import MountResult, MountStatus

SAMPLE_MOUNT = (
    "/dev/disk3s1s1 on / (apfs, sealed, local, read-only, journaled)\n"
    "//pat@KITCHEN-TS-264._smb._tcp.local/Public on /Volumes/Public "
    "(smbfs, nodev, nosuid, mounted by patrickdugan)\n"
    "map auto_home on /System/Volumes/Data/home (autofs, nodev, nosuid)\n"
)


def _fake_run(stdout: str = "", record: list | None = None):
    def run(args, *a, **k):
        if record is not None:
            record.append(args)
        return types.SimpleNamespace(stdout=stdout, stderr="", returncode=0)

    return run


# --- probe_live -------------------------------------------------------------


def test_probe_live_true_for_real_dir(tmp_path):
    assert mount.probe_live(tmp_path) is True


def test_probe_live_false_for_missing(tmp_path):
    assert mount.probe_live(tmp_path / "nope") is False


def test_probe_live_never_hangs_on_blocking_stat():
    """A stale-mount stat blocks in the kernel; probe_live must time out and
    report not-live rather than hanging the caller."""

    class Hang:
        def is_dir(self):
            time.sleep(5)
            return True

    started = time.monotonic()
    assert mount.probe_live(Hang(), timeout=0.1) is False
    assert time.monotonic() - started < 1.0  # returned promptly, didn't hang


# --- _network_mount_for -----------------------------------------------------


def test_network_mount_for_matches_smbfs(monkeypatch):
    monkeypatch.setattr(mount.subprocess, "run", _fake_run(SAMPLE_MOUNT))
    found = mount._network_mount_for(Path("/Volumes/Public/Multimedia/Music"))
    assert found == (
        "//pat@KITCHEN-TS-264._smb._tcp.local/Public",
        "/Volumes/Public",
    )


def test_network_mount_for_ignores_local_root(monkeypatch):
    """A local path under / must NOT match the apfs root mount — otherwise we
    could force-unmount `/`."""
    monkeypatch.setattr(mount.subprocess, "run", _fake_run(SAMPLE_MOUNT))
    assert mount._network_mount_for(Path("/private/tmp/whatever")) is None


def test_smb_url():
    assert mount._smb_url("//pat@host/Public") == "smb://pat@host/Public"
    assert mount._smb_url("smb://pat@host/Public") == "smb://pat@host/Public"


def test_mountpoint_for_volumes_path():
    assert (
        mount._mountpoint_for(Path("/Volumes/Public/Multimedia/Music"))
        == "/Volumes/Public"
    )


# --- ensure_mounted ---------------------------------------------------------


def test_ensure_mounted_live(monkeypatch, tmp_path):
    monkeypatch.setattr(mount, "probe_live", lambda p, t=mount.PROBE_TIMEOUT_S: True)
    res = mount.ensure_mounted(tmp_path)
    assert res.status is MountStatus.LIVE


def test_ensure_mounted_non_darwin_is_offline(monkeypatch, tmp_path):
    monkeypatch.setattr(mount, "probe_live", lambda p, t=mount.PROBE_TIMEOUT_S: False)
    monkeypatch.setattr(mount.sys, "platform", "linux")
    res = mount.ensure_mounted(tmp_path)
    assert res.status is MountStatus.OFFLINE


def test_ensure_mounted_no_source_is_offline(monkeypatch, tmp_path):
    """Stale, on macOS, but not under any network mount and no override URL →
    OFFLINE without touching anything (never force-unmount a local disk)."""
    monkeypatch.setattr(mount, "probe_live", lambda p, t=mount.PROBE_TIMEOUT_S: False)
    monkeypatch.setattr(mount.sys, "platform", "darwin")
    monkeypatch.setattr(mount, "_network_mount_for", lambda p: None)
    ran: list = []
    monkeypatch.setattr(mount.subprocess, "run", _fake_run(record=ran))
    res = mount.ensure_mounted(tmp_path)
    assert res.status is MountStatus.OFFLINE
    assert ran == []  # no diskutil / open issued


def test_ensure_mounted_remounts_stale_share(monkeypatch):
    monkeypatch.setattr(mount.sys, "platform", "darwin")
    # First probe stale; after the remount the share comes up.
    calls = {"n": 0}

    def fake_probe(p, t=mount.PROBE_TIMEOUT_S):
        calls["n"] += 1
        return calls["n"] > 1

    monkeypatch.setattr(mount, "probe_live", fake_probe)
    monkeypatch.setattr(
        mount,
        "_network_mount_for",
        lambda p: ("//pat@host/Public", "/Volumes/Public"),
    )
    monkeypatch.setattr(mount.os.path, "ismount", lambda mp: True)
    ran: list = []
    monkeypatch.setattr(mount.subprocess, "run", _fake_run(record=ran))

    res = mount.ensure_mounted(Path("/Volumes/Public/Multimedia/Music"))
    assert res.status is MountStatus.REMOUNTED
    assert ["diskutil", "unmount", "force", "/Volumes/Public"] in ran
    assert ["open", "smb://pat@host/Public"] in ran


def test_ensure_mounted_offline_when_remount_never_comes_up(monkeypatch):
    monkeypatch.setattr(mount.sys, "platform", "darwin")
    monkeypatch.setattr(mount, "probe_live", lambda p, t=mount.PROBE_TIMEOUT_S: False)
    monkeypatch.setattr(
        mount,
        "_network_mount_for",
        lambda p: ("//pat@host/Public", "/Volumes/Public"),
    )
    monkeypatch.setattr(mount.os.path, "ismount", lambda mp: True)
    monkeypatch.setattr(mount.subprocess, "run", _fake_run())
    res = mount.ensure_mounted(
        Path("/Volumes/Public/Multimedia/Music"), remount_wait=0.2
    )
    assert res.status is MountStatus.OFFLINE


# --- actions.ensure_library_available --------------------------------------


def _cfg(tmp_path) -> Config:
    return Config(music_dir=tmp_path / "music", project_dir=tmp_path)


def test_offline_error_subclasses_library_not_found():
    assert issubclass(actions.LibraryStorageOfflineError, actions.LibraryNotFoundError)


def test_ensure_library_available_raises_when_offline(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "clickwheel.mount.ensure_mounted",
        lambda *a, **k: MountResult(MountStatus.OFFLINE, "/Volumes/Public", "asleep"),
    )
    with pytest.raises(actions.LibraryStorageOfflineError) as exc:
        actions.ensure_library_available(_cfg(tmp_path))
    assert "isn't mounted" in str(exc.value)


@pytest.mark.parametrize("status", [MountStatus.LIVE, MountStatus.REMOUNTED])
def test_ensure_library_available_ok_when_live_or_remounted(
    monkeypatch, tmp_path, status
):
    monkeypatch.setattr(
        "clickwheel.mount.ensure_mounted",
        lambda *a, **k: MountResult(status, "/Volumes/Public"),
    )
    # Should not raise.
    actions.ensure_library_available(_cfg(tmp_path))
