# clickwheel threat model

Protected assets are the source music library, iPod contents and database, Plex and Last.fm
credentials, playlists, ratings, play counts, and transcode output. Tags, filenames, device
mounts, provider responses, configuration, and CLI/MCP input are untrusted.

## Current local authorization boundary

The CLI and optional local MCP server act with the local account's filesystem and
service credentials. MCP mutation tools advertise `destructiveHint=true`; this is
metadata, not server-enforced consent. The server does not elicit approval or
accept a confirmation parameter (`clickwheel/mcp/_runtime.py`, `AGENTS.md`). The
client/operator must obtain approval for the exact mutation and target before
calling a tool. The controls below are review requirements, not proof of atomic
writes or complete recovery for every media/device format.

## Required controls

- Never move or rename source-library files during ordinary operations, and confine writes
  to explicitly selected library, device, or transcode roots.
- Preview and validate destructive or bulk mutations; use atomic writes/backups where the
  target format permits and leave failures recoverable.
- Keep credentials and unrelated private data out of logs, fixtures, MCP responses,
  and errors. Limit paths and library/provider metadata returned by tools to the
  fields needed for the requested operation; use synthetic fixtures.
- Do not copy FLAC to stock-firmware iPods or transcode implicitly; only the explicit
  conversion command may create bounded outputs outside the source library.
- Keep CLI and MCP adapters on the same tested action layer so neither bypasses validation.

Update this model when credentials, device writes, conversion, sync, provider access, MCP
tools, or destructive operations change.
