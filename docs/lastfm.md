# Last.fm scrobbling

clickwheel can submit your iPod's listening history to Last.fm. The iPod records play counts and timestamps locally; `clickwheel scrobble` picks those up the next time the device is plugged in and pushes them to Last.fm as scrobbles.

The integration is opt-in: nothing is sent anywhere until you add API credentials and authorize once.

## Get an API key

1. Visit [last.fm/api/account/create](https://www.last.fm/api/account/create).
2. Fill in the form (any application name is fine — "clickwheel" is conventional).
3. You'll get back an **API key** and a **shared secret**. Keep them; you'll paste both into config.

## Configure

Add the credentials to `~/.clickwheel/config.yaml`:

```yaml
lastfm_api_key: your_api_key
lastfm_api_secret: your_shared_secret
lastfm_username: your_lastfm_username
```

The shared secret can also live in `~/.clickwheel/.env` as `LASTFM_API_SECRET=...` if you'd rather keep secrets out of the YAML file (it's easy to leak in screenshots).

## Authorize once

```bash
clickwheel scrobble --auth
```

This opens a Last.fm authorization page in your browser. Approve the request, then come back to the terminal — clickwheel will print a confirmation and write a `lastfm_session_key` into your config. After that, future `clickwheel scrobble` invocations use the session key without prompting.

If the session key ever stops working (revoked permissions, account changes), re-run `--auth` to generate a new one.

## Submit listens

```bash
clickwheel scrobble
```

With the iPod plugged in, this reads the device's play history, dedups against scrobbles already submitted (cached in `~/.clickwheel/library.db`), and submits the new ones. Output reports how many were pushed and how many were skipped as duplicates.

Plays are tracked individually so re-runs are safe — the same listen never gets submitted twice. If a submission batch fails (network blip, rate limit), the next run resumes where it left off.

## MCP tool

When clickwheel is wired into an MCP client (Claude Code, Claude Desktop, etc.), the `submit_scrobbles` tool exposes the same flow as the CLI. It's flagged as a non-idempotent mutation — the client gates it with a confirmation prompt before invocation. Useful when you're already in a chat about your library and want to push listens without leaving the conversation.

## Troubleshooting

| Symptom                                        | What to check                                                                                                                                                                                      |
| ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| "Last.fm not configured" error                 | `lastfm_api_key`, `lastfm_api_secret`, `lastfm_username` all set in `~/.clickwheel/config.yaml` (or via env vars).                                                                                 |
| Browser opens but never returns to the CLI     | Make sure you actually clicked **Allow** on the Last.fm page. The CLI polls until it sees the authorization, then writes the session key.                                                          |
| Authorization succeeds but later runs fail     | Session key may have been revoked. Re-run `clickwheel scrobble --auth` to regenerate.                                                                                                              |
| No listens submitted, but you've played tracks | Confirm the iPod is connected and recognized (`clickwheel ls` should show its contents). Plays don't appear in clickwheel's view until the device is plugged in and the local cache has been read. |
