# clickwheel threat model

Protected assets are the source music library, iPod contents and database, Plex and Last.fm
credentials, playlists, ratings, play counts, and transcode output. Tags, filenames, device
mounts, provider responses, configuration, and CLI/MCP input are untrusted.

Required controls:

- Never move or rename source-library files during ordinary operations, and confine writes
  to explicitly selected library, device, or transcode roots.
- Preview and validate destructive or bulk mutations; use atomic writes/backups where the
  target format permits and leave failures recoverable.
- Keep tokens, private paths, library metadata, and raw provider responses out of logs,
  fixtures, MCP responses, and errors.
- Do not copy FLAC to stock-firmware iPods or transcode implicitly; only the explicit
  conversion command may create bounded outputs outside the source library.
- Keep CLI and MCP adapters on the same tested action layer so neither bypasses validation.

Update this model when credentials, device writes, conversion, sync, provider access, MCP
tools, or destructive operations change.
