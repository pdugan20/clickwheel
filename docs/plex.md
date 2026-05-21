# Plex playlist sync

clickwheel mirrors playlists into a Plex music library so Plexamp and Plex web see them alongside the iPod sync. Bidirectional: push from clickwheel to Plex, or pull from Plex back to clickwheel.

## Install

```bash
pipx inject clickwheel 'clickwheel[plex]'   # or: pip install 'clickwheel[plex]'
```

## Configure

```yaml
# ~/.clickwheel/config.yaml
plex_enabled: true
plex_url: http://192.168.1.10:32400
plex_library_name: Music

# Only needed when Plex runs on a different host than clickwheel (e.g. NAS).
# See "Path remap" under How it works.
plex_path_remap_local: /Volumes/Public/
plex_path_remap_plex: /share/CACHEDEV1_DATA/Public/
```

```bash
# ~/.clickwheel/.env (mode 600)
CLICKWHEEL_PLEX_TOKEN=...
```

Token shortcut: in Plex web, click any track → ⋯ → Get Info → View XML. The opened URL contains `X-Plex-Token=...`. Treat it like a password.

Run `clickwheel plex doctor` to verify config, network, library section, and the remap (if set).

## Commands

| Command                       | Description                                                                   |
| ----------------------------- | ----------------------------------------------------------------------------- |
| `clickwheel plex doctor`      | Probe config → connect → library → remap (read-only, five stages)             |
| `clickwheel sync-plex <name>` | Push a playlist via M3U import. Overwrites any prior clickwheel-managed copy. |
| `clickwheel sync-plex --all`  | Push every clickwheel playlist                                                |
| `clickwheel plex list`        | List Plex audio playlists (manual + smart, with track counts)                 |
| `clickwheel plex pull <name>` | Import a Plex playlist into clickwheel (`--overwrite`, `--include-smart`)     |

## MCP tools

| Tool                      | What it does                                      |
| ------------------------- | ------------------------------------------------- |
| `plex_health`             | Same five-stage probe as `clickwheel plex doctor` |
| `list_plex_playlists`     | List Plex audio playlists                         |
| `sync_playlist_to_plex`   | Push (destructive; client-gated)                  |
| `pull_playlist_from_plex` | Pull (destructive; writes to clickwheel's SQLite) |

## Troubleshooting

| Doctor stage fails                      | What to check                                                                                |
| --------------------------------------- | -------------------------------------------------------------------------------------------- |
| `config`                                | `plex_enabled: true`, `CLICKWHEEL_PLEX_TOKEN` set, `plex_url` reachable                      |
| `plexapi extra`                         | `pip install 'clickwheel[plex]'`                                                             |
| `connect`                               | Bad token (try `http://<plex>:32400/identity?X-Plex-Token=<token>`) or LAN unreachable       |
| `music section`                         | `plex_library_name` doesn't match a music library; detail lists available names              |
| `sample track` — "not at expected path" | Path remap mismatched; adjust `plex_path_remap_local` / `plex_path_remap_plex`               |
| `sample track` — "no metadata match"    | Soft signal; M3U upload uses path-based indexing, so sync may still work. Re-scan Plex first |

## How it works

**Push** writes an EXTM3U file to `{music_dir}/.clickwheel-playlists/` whose body is Plex-side paths, then Plex's M3U-import endpoint resolves each line through its own indexer. The result reports `pushed` (lines in the M3U) and `resolved` (lines Plex matched); a gap means Plex hasn't scanned those files yet — trigger a Plex library scan and re-run. Re-syncing the same playlist overwrites the prior clickwheel-managed copy; a user-created Plex playlist with the same name is left alone.

**Pull** reads the named Plex playlist's track list, reverses the path remap, and matches each path against clickwheel's SQLite index. Unmatched rows surface in the output table. Smart playlists are dynamic Plex queries — pulling materializes a snapshot, so the command refuses by default unless you pass `--include-smart`.

**Path remap.** clickwheel and Plex may see the same files at different paths — clickwheel mounts the library over SMB while Plex on the NAS sees its local filesystem. The remap is a single string substitution: every track path's `plex_path_remap_local` prefix is swapped for `plex_path_remap_plex` (and vice versa for pull). Find Plex's view at Plex web → Settings → Manage → Libraries → your music library → Add folders. Leave both keys empty when Plex runs on the same machine as clickwheel.
