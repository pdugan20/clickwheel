# Last.fm scrobbling

clickwheel submits your iPod's listen history to Last.fm. Opt-in; nothing leaves the Mac until you add credentials.

## Install

No extra needed — Last.fm support is in the base install.

## Configure

Get an API key + shared secret at [last.fm/api/account/create](https://www.last.fm/api/account/create). Any application name works ("clickwheel" is conventional). Then:

```yaml
# ~/.clickwheel/config.yaml
lastfm_api_key: your_api_key
lastfm_username: your_lastfm_username
```

```bash
# ~/.clickwheel/.env (mode 600 — keeps the secret out of YAML)
LASTFM_API_SECRET=your_shared_secret
```

Run the one-time authorization:

```bash
clickwheel scrobble --auth
```

A browser opens to Last.fm; approve, and clickwheel writes a session key into your config. Future runs use it without prompting.

The same `lastfm_api_key` is also used by `clickwheel fix` to fetch album genres (read-only — no session key required). If you only want genre tagging and never plan to scrobble, you can stop after the API key is in place and skip `--auth`.

## Commands

| Command                      | Description                                                             |
| ---------------------------- | ----------------------------------------------------------------------- |
| `clickwheel scrobble --auth` | One-time browser authorization; mints a session key                     |
| `clickwheel scrobble`        | Push new iPod listens to Last.fm (idempotent; dedups against past runs) |

## MCP tools

| Tool               | What it does                                              |
| ------------------ | --------------------------------------------------------- |
| `submit_scrobbles` | Same as `clickwheel scrobble` (destructive; client-gated) |

## Troubleshooting

| Symptom                                       | What to check                                                 |
| --------------------------------------------- | ------------------------------------------------------------- |
| "Last.fm not configured" error                | `lastfm_api_key`, `lastfm_api_secret`, `lastfm_username` set  |
| Browser opens but never returns to the CLI    | Make sure you clicked **Allow** on the Last.fm page           |
| Authorization succeeds, later runs fail       | Session key revoked. Re-run `clickwheel scrobble --auth`      |
| No listens submitted but you've played tracks | iPod must be plugged in for clickwheel to read its play cache |
