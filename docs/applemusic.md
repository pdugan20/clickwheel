# Apple Music integration

clickwheel can authenticate against Apple Music as a third-party developer, opening the door to bidirectional playlist sync with a user's Apple Music account (Music.app on macOS, Apple Music on iPhone, etc.). This first PR ships **auth + doctor only**; push/pull commands land in follow-ups.

The integration is **opt-in and lazy**: if `apple_music_enabled` is false (the default), nothing about clickwheel changes. Even with it enabled, the `pyjwt[crypto]` dependency only loads when an Apple Music command actually runs.

## Install

Apple Music lives behind an optional `[applemusic]` extra:

```bash
# If you installed clickwheel with pipx
pipx inject clickwheel 'clickwheel[applemusic]'

# If you installed with pip
pip install 'clickwheel[applemusic]'
```

That brings in [`pyjwt[crypto]`](https://pypi.org/project/PyJWT/) for ES256 token signing.

## Prerequisites

You need a paid **Apple Developer Program** membership ($99/yr) and a MusicKit key. If you already have one (e.g., from a Music-app integration in another project), reuse it — the key is per-developer, not per-app. If not:

1. Open [Certificates, Identifiers & Profiles → Keys](https://developer.apple.com/account/resources/authkeys/list).
2. Click **+**, name the key (e.g. `clickwheel`), and check **Media Services (MusicKit)**. If you also want ShazamKit / Apple Music Feed access, check those too.
3. Click **Configure** next to Media Services and either pick an existing MusicKit identifier or create one (`<your-team>.<your-bundle-id>.musickit`).
4. Continue → Register → **Download** the `.p8`. This is the only time Apple lets you download it — back it up immediately (1Password attachment is the recommended pattern; see the project's `reference_apple_music_credentials` memory note for the exact item shape).
5. Note the **Key ID** (10 chars, shown on the confirmation page and in the filename) and **Team ID** (top right of any developer.apple.com page).

## Configure

Add to `~/.clickwheel/config.yaml`:

```yaml
apple_music_enabled: true
apple_music_storefront: us # 2-letter country code; controls catalog region
apple_music_key_id: H458T54N43
apple_music_team_id: 2DS67Q47ES
apple_music_key_file: /Users/you/.clickwheel/AuthKey_H458T54N43.p8
```

Lock the `.p8` to mode `600`:

```bash
chmod 600 ~/.clickwheel/AuthKey_<KEYID>.p8
```

The user token comes later via `clickwheel apple auth` and lands in `~/.clickwheel/.env` as `APPLE_MUSIC_USER_TOKEN` — don't set it manually.

### Reusing a pre-signed token

If you already have a long-lived MusicKit developer token (for example from another project's deploy environment), set `APPLE_MUSIC_DEVELOPER_TOKEN=<jwt>` in `~/.clickwheel/.env` and the `.p8`/Key ID/Team ID fields become optional. clickwheel will use the pre-signed token instead of signing on demand. Useful for sharing a single token across projects; less robust than signing locally (clickwheel can re-sign when the cached token expires; a pre-signed one needs manual rotation).

## Authorize

```bash
clickwheel apple auth
```

Opens your default browser to a tiny local page (`http://127.0.0.1:<random-port>/`) that loads MusicKit JS and asks you to sign in with your Apple ID. Click **Authorize with Apple Music**, sign in, and the page POSTs the resulting Music User Token back to clickwheel, which saves it to `~/.clickwheel/.env`. The terminal exits when the token is captured.

Token characteristics:

- **Long-lived** — Apple doesn't publish an exact expiration; in practice tokens last months to years until the user revokes the app in their Apple ID settings.
- **Per-Mac, per-Apple-ID** — moving to a new machine means re-running `clickwheel apple auth`.
- **Subscription required** for most user-scoped endpoints (library, playlist mutation). Catalog reads work without one.

## Verify

```bash
clickwheel apple doctor
```

Walks up to nine stages and reports each:

1. **config** — `apple_music_enabled` true, Team ID set, Key ID + .p8 path set (or a pre-signed token).
2. **applemusic extra** — `pyjwt[crypto]` is installed.
3. **p8 readable** — file exists at the configured path and parses as a PEM private key.
4. **developer token** — ES256 signing succeeds with the configured Key ID + Team ID.
5. **catalog reachable** — token authenticates against `/v1/catalog/<storefront>/search`. A 401 here is the classic "the underlying key was revoked on developer.apple.com" — regen.
6. **user token** — `APPLE_MUSIC_USER_TOKEN` is present in `.env`.
7. **user token verified** — `/v1/me/storefront` round-trips successfully (proves the token isn't revoked/expired).
8. **iCloud Music Library** — probes `/v1/me/library/songs`; reports whether iCML is ON or OFF for this user. Affects what tracks can be put in playlists (only catalog tracks if OFF; uploaded library tracks too if ON).
9. **storefront match** — checks that the configured `apple_music_storefront` matches the user's actual region.

If any stage fails, the detail line points at the specific config key, install command, or auth step you need to fix. Cheap to run; safe to repeat.

## MCP tool

`apple_music_health` — read-only, mirrors the CLI doctor. Returns the same nine-stage probe as a structured response for chat clients (Claude Desktop, Claude Code, etc.). Push/pull tools will land in follow-ups.

## Troubleshooting

| Doctor stage fails     | What to check                                                                                                                                                                       |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `config`               | `apple_music_enabled: true` in YAML, Team ID set, and either `APPLE_MUSIC_DEVELOPER_TOKEN` in `.env` _or_ Key ID + `.p8` path configured.                                           |
| `applemusic extra`     | Run `pipx inject clickwheel 'clickwheel[applemusic]'` (or the `pip install` variant). The detail line has the exact command.                                                        |
| `p8 readable`          | Path doesn't exist or the file isn't a PEM private key. The `.p8` only downloads once at creation — if you've lost it, regen on developer.apple.com.                                |
| `developer token`      | Signing failed. Almost always means the `.p8` is malformed or the Key ID is wrong. Re-download.                                                                                     |
| `catalog reachable`    | Apple returned 401. Either the key behind `kid` was revoked on developer.apple.com (regen), or the Team ID is wrong, or the key isn't authorized for MusicKit (Media Services off). |
| `user token`           | Run `clickwheel apple auth`.                                                                                                                                                        |
| `user token verified`  | User token expired or was revoked. Re-run `clickwheel apple auth`.                                                                                                                  |
| `iCloud Music Library` | If OFF and you want broader matching, enable on Mac (Music.app → Settings → General → Sync Library) or iPhone (Settings → Music → Sync Library).                                    |
| `storefront match`     | Update `apple_music_storefront` to match the value the doctor reports for your account, or accept the discrepancy if you're intentionally targeting a different region's catalog.   |

## What's not here yet

This PR is the foundation. The actual playoff lands in follow-ups:

- **Push** (`clickwheel apple push <playlist>`) — match clickwheel tracks against Apple Music catalog (ISRC → fuzzy → user library), create a playlist in the user's Apple Music account, populate it.
- **Pull** (`clickwheel apple pull <name>` / `clickwheel apple list`) — read-back symmetry mirroring the Plex pull command.
- **MCP tools** — `sync_playlist_to_apple_music`, `pull_playlist_from_apple_music`, `list_apple_music_playlists`.

These all hang off the auth + doctor surface this PR ships. Track the follow-ups on [GitHub](https://github.com/pdugan20/clickwheel/issues).
