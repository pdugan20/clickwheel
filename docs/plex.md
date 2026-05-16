# Plex playlist sync

clickwheel can mirror its playlists into a Plex music library, so Plexamp and the Plex web app see them alongside the iPod sync. Same library on disk, two consumers.

The integration is **opt-in and lazy**: if `plex_enabled` is false (the default), nothing about clickwheel changes. Even with it enabled, the `plexapi` dependency only loads when you actually call a Plex command.

## Install

Plex sync lives behind an optional `[plex]` extra:

```bash
# If you installed clickwheel with pipx
pipx inject clickwheel 'clickwheel[plex]'

# If you installed with pip
pip install 'clickwheel[plex]'
```

That brings in [`plexapi`](https://pypi.org/project/PlexAPI/), the official Python SDK for Plex. Without it, every Plex command exits with the install instructions above.

## Configure

Add this block to `~/.clickwheel/config.yaml`:

```yaml
plex_enabled: true
plex_url: http://192.168.1.10:32400 # your Plex server's local URL
plex_library_name: Music # default: 'Music'
# Optional — see "Path remap" below
plex_path_remap_local: /Volumes/Public/
plex_path_remap_plex: /share/CACHEDEV1_DATA/Public/
```

Then put your token in `~/.clickwheel/.env` (don't put tokens in the YAML — they're easy to leak in screenshots):

```bash
CLICKWHEEL_PLEX_TOKEN=...
```

### Getting a token

Plex's [official guide](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/) is the canonical reference. Fastest path:

1. Open any track in the Plex web app.
2. Click the three-dot menu → Get Info → View XML.
3. The opened URL contains `X-Plex-Token=...` — that's your token.

Treat it like a password. To revoke: Plex.tv → Account → Sign Out Everywhere.

## Path remap

The biggest config decision is whether you need a path remap. It depends on where Plex is running:

- **Plex on the same machine as clickwheel** — both processes see the music library at the same path. Leave `plex_path_remap_local` and `plex_path_remap_plex` empty (or omit them).
- **Plex on a NAS** — clickwheel sees the library over a network mount (e.g. `/Volumes/Public/...` on macOS, `Z:\Music\...` on Windows). Plex on the NAS sees the same files at a NAS-local path (e.g. `/share/CACHEDEV1_DATA/Public/...` on a QNAP, `/volume1/Music/...` on a Synology). Set the remap pair to translate.

To find Plex's view of the library:

- **Easy way:** Plex web app → Settings → Manage → Libraries → your Music library → Edit → look at "Add folders". The paths shown are exactly what Plex sees.
- **Via API:** `curl "http://<plex>:32400/library/sections?X-Plex-Token=<token>"` and look at each `Location` element.
- **Via doctor:** `clickwheel plex doctor` will report each section's root path.

The remap is a single string substitution: `local_path.startswith(plex_path_remap_local)` must be true for every track in any playlist you sync; the `plex_path_remap_local` prefix is replaced with `plex_path_remap_plex`. If a track path doesn't match the prefix, you get a `PlexPathRemapError` at sync time, not a silent zero-resolution playlist.

## Verify

```bash
clickwheel plex doctor
```

Walks five stages and reports each:

1. **config** — `plex_enabled` true, URL and token set.
2. **plexapi extra** — the `[plex]` extra is installed.
3. **connect** — Plex reachable at the configured URL with the token.
4. **music section** — `plex_library_name` matches an actual music section.
5. **sample track** — picks a random mp3 from clickwheel's index, searches Plex for it, and confirms Plex returns the same physical file path (via the remap).

If any stage fails, the detail line points at the specific config key, install command, or remap mismatch you need to fix. Cheap to run; safe to repeat.

## Sync a playlist

```bash
# One playlist
clickwheel sync-plex road-trip

# Every clickwheel playlist
clickwheel sync-plex --all
```

What happens under the hood:

1. clickwheel writes `road-trip.m3u` into `${music_dir}/.clickwheel-playlists/` (or your configured `plex_playlist_dir`). Each line is the Plex-side path to a track.
2. Plex's `/playlists/upload` endpoint reads the M3U and resolves each line through its own indexer (the same one that built the library).
3. The Plex playlist appears under your Music library and Plexamp picks it up automatically.
4. If the clickwheel playlist has a description, it's applied to the Plex playlist's summary. M3U import can't carry a description, so this is a separate edit after upload.

Re-syncing the same playlist **overwrites** the prior clickwheel-managed Plex playlist (idempotent). A user-created Plex playlist with the same name — one you made directly in Plexamp — is left alone; clickwheel only touches playlists it created.

Set a playlist's description with `clickwheel select --description`, `clickwheel edit --description`, or the `set_playlist_description` MCP tool.

### Result reporting

`pushed` is how many tracks went into the M3U. `resolved` is how many Plex actually found. A gap means some clickwheel files aren't in Plex's index yet — typically because Plex hasn't scanned them. You can either:

- Trigger a Plex library scan (Plex web → Settings → Libraries → Scan Library Files), then re-run `clickwheel sync-plex`.
- Or, leave it: the M3U landed, and re-running after the scan will pick up the missing tracks (Plex will re-resolve the same file paths).

## MCP tools

When using clickwheel through its MCP server (Claude Desktop, Claude Code, etc.), two Plex tools are exposed:

- `plex_health` — read-only. Same five-stage probe as `clickwheel plex doctor`, surfaced as a structured response so the chat client can call it on your behalf for diagnostics.
- `sync_playlist_to_plex(playlist=...)` — destructive, gated by a native Allow/Deny prompt in the client. After `create_playlist` or `update_playlist`, the agent should ask which destination(s) you want — iPod, Plex, both, or neither — rather than assuming.

## Troubleshooting

| Doctor stage fails                                             | What to check                                                                                                                                                                                          |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `config`                                                       | `plex_enabled: true` in YAML, `CLICKWHEEL_PLEX_TOKEN` in `.env`, `plex_url` reachable from this machine.                                                                                               |
| `plexapi extra`                                                | Run the `pip install 'clickwheel[plex]'` or `pipx inject` command from the error detail.                                                                                                               |
| `connect`                                                      | Token wrong (check that you can hit `http://<plex>:32400/identity?X-Plex-Token=<token>` from a terminal), or server unreachable on the LAN.                                                            |
| `music section`                                                | `plex_library_name` doesn't match any section. The detail line lists available music sections — pick one.                                                                                              |
| `sample track` says "not at the expected path"                 | Path remap is mismatched. The detail shows the expected vs returned paths — usually you need to adjust `plex_path_remap_local` or `plex_path_remap_plex`.                                              |
| `sample track` says "Plex's metadata search returned no match" | Soft signal — M3U upload uses Plex's path-based indexer, not metadata search, so sync may still work. Most often this means Plex hasn't scanned the artist yet; trigger a Plex scan and re-run doctor. |
