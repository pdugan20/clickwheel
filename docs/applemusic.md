# Apple Music

clickwheel pushes and pulls playlists against the user's Apple Music account via the official MusicKit API. Playlists sync across Apple devices through iCloud Music Library.

## Install

```bash
pipx inject clickwheel 'clickwheel[applemusic]'   # or: pip install 'clickwheel[applemusic]'
```

## Configure

Three things to set up, in order:

**1. A MusicKit key.** Requires a paid Apple Developer Program membership. At [developer.apple.com/account/resources/authkeys/list](https://developer.apple.com/account/resources/authkeys/list), create a key with **Media Services (MusicKit)** enabled, configure it for an existing or new MusicKit identifier, and download the `.p8`. Apple only lets you download it once at creation — back it up to 1Password immediately.

**2. clickwheel config:**

```yaml
# ~/.clickwheel/config.yaml
apple_music_enabled: true
apple_music_storefront: us
apple_music_key_id: <Key ID, 10 chars>
apple_music_team_id: <Team ID, top-right of developer.apple.com>
apple_music_key_file: /Users/you/.clickwheel/AuthKey_<KEYID>.p8
```

`chmod 600` the `.p8`.

**3. One-time browser authorization** for the Music User Token:

```bash
clickwheel apple auth
```

Opens MusicKit JS in your default browser; sign in with your Apple ID and clickwheel saves the resulting user token to `~/.clickwheel/.env`.

Then run `clickwheel apple doctor` — nine stages should pass. If anything's wrong, the doctor's per-stage detail tells you exactly which fix to apply.

## Commands

| Command                          | Description                                                                    |
| -------------------------------- | ------------------------------------------------------------------------------ |
| `clickwheel apple auth`          | One-time browser flow; mints a long-lived user token                           |
| `clickwheel apple doctor`        | End-to-end probe (config, `.p8`, both tokens, iCML state, storefront)          |
| `clickwheel apple list`          | List your Apple Music library playlists                                        |
| `clickwheel apple match <name>`  | Preview how a clickwheel playlist's tracks resolve to Apple Music song IDs     |
| `clickwheel apple push <name>`   | Push a clickwheel playlist to your Apple Music account                         |
| `clickwheel apple pull <name>`   | Import an Apple Music playlist into clickwheel                                 |
| `clickwheel apple delete <name>` | Delete an Apple Music library playlist (macOS-only; AppleScript via Music.app) |

All commands accept `--help` for full flag reference. `push` takes `--refresh`, `--min-confidence`, `--include-low`, `--yes`; `pull` takes `--overwrite`, `--min-fuzzy`.

## MCP tools

| Tool                             | What it does                                      |
| -------------------------------- | ------------------------------------------------- |
| `apple_music_health`             | Same nine-stage probe as the doctor command       |
| `list_apple_music_playlists`     | List Apple Music library playlists                |
| `sync_playlist_to_apple_music`   | Push (destructive; client-gated)                  |
| `pull_playlist_from_apple_music` | Pull (destructive; writes to clickwheel's SQLite) |
| `delete_apple_music_playlist`    | Delete via AppleScript (destructive; macOS-only)  |

## Troubleshooting

| Doctor stage fails     | What to check                                                                                                                                |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `config`               | `apple_music_enabled: true`, Team ID set, and either `APPLE_MUSIC_DEVELOPER_TOKEN` in `.env` _or_ Key ID + `.p8` path configured             |
| `applemusic extra`     | `pip install 'clickwheel[applemusic]'`                                                                                                       |
| `p8 readable`          | Path wrong or file isn't a PEM private key. The `.p8` downloads only once at creation — regen if lost                                        |
| `developer token`      | `.p8` malformed or Key ID wrong                                                                                                              |
| `catalog reachable`    | Apple returned 401: key revoked, Team ID wrong, or key not authorized for MusicKit                                                           |
| `user token`           | Run `clickwheel apple auth`                                                                                                                  |
| `user token verified`  | Token expired or revoked; re-run `clickwheel apple auth`                                                                                     |
| `iCloud Music Library` | If OFF, only catalog tracks match. Enable on Mac (Music.app → Settings → General → Sync Library) or iPhone (Settings → Music → Sync Library) |
| `storefront match`     | Config and Apple disagree on country code; update `apple_music_storefront`                                                                   |

## How it works

**Two token types.** MusicKit needs a _developer token_ (JWT signed locally with your `.p8`, 180-day max — clickwheel re-signs on demand) and a _Music User Token_ (long-lived, minted via browser auth, scoped to the user). User-scoped endpoints (library, playlist mutation) require both; catalog reads only need the developer token.

**Match ladder.** Push resolves each clickwheel track to an Apple Music song ID via (1) ISRC tag lookup, (2) catalog fuzzy search scored by title 55% + artist 35% + album 10%, (3) library search when iCML is on. Resolved IDs cache in SQLite keyed by absolute path, so subsequent pushes skip the network. Pull uses the reverse: cache → exact metadata → fuzzy.

**No REST DELETE.** Apple deliberately doesn't expose `DELETE /v1/me/library/playlists/{id}` — it returns HTTP 401 on every auth combination ([confirmed by Apple developers](https://developer.apple.com/forums/thread/107807)). `clickwheel apple delete` drives Music.app on macOS via AppleScript as the documented workaround; iCloud Music Library propagates the deletion to other devices.

**Pre-signed developer tokens.** If you already have a JWT from another project's deploy (e.g. a Cloudflare Worker), set `APPLE_MUSIC_DEVELOPER_TOKEN=<jwt>` in `.env` and the `.p8`/Key ID/Team ID fields become optional. clickwheel uses the pre-signed token instead of re-signing; you're then responsible for rotation when it expires.
