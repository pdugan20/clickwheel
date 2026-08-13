# clickwheel

[![PyPI](https://img.shields.io/pypi/v/clickwheel?logo=pypi&logoColor=white)](https://pypi.org/project/clickwheel/)
[![CI](https://github.com/pdugan20/clickwheel/actions/workflows/ci.yml/badge.svg)](https://github.com/pdugan20/clickwheel/actions/workflows/ci.yml)
[![docs](https://img.shields.io/badge/docs-docs.clickwheel.fm-blue)](https://docs.clickwheel.fm)
[![Python](https://img.shields.io/badge/Python-%3E%3D3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?logo=opensourceinitiative&logoColor=white)](https://opensource.org/licenses/MIT)

Sync a music library to a classic iPod from a modern Mac, no iTunes required.
Scan your library, choose what goes on the iPod, and keep it up to date from the
terminal.

Full documentation: [docs.clickwheel.fm](https://docs.clickwheel.fm).

## Install

```bash
pipx install clickwheel
```

Requires macOS, Python 3.11+, and a supported stock-firmware iPod connected over
USB. See the [complete requirements](https://docs.clickwheel.fm/requirements).

## Quickstart

Point clickwheel at your music:

```bash
mkdir -p ~/.clickwheel
echo "music_dir: /path/to/your/music" > ~/.clickwheel/config.yaml
```

Then index your library and load the iPod:

```bash
clickwheel scan      # build the library index
clickwheel select    # choose artists and albums
clickwheel diff      # preview the sync
clickwheel sync      # write to the iPod
clickwheel eject     # safely unmount
```

See the [quickstart](https://docs.clickwheel.fm/quickstart) for the complete
first-sync walkthrough.

## What clickwheel can do

- [Sync music to an iPod](https://docs.clickwheel.fm/guides/sync-to-ipod): preview and load music without iTunes.
- [Build playlists](https://docs.clickwheel.fm/guides/playlists): create, edit, and reuse curated collections.
- [Convert FLAC for iPod](https://docs.clickwheel.fm/guides/convert-flac): create indexed MP3 copies without modifying the source files.
- [Repair metadata](https://docs.clickwheel.fm/guides/fix-metadata): fill in album artists, artwork, years, and genres in place.

## Integrations

- [Plex / Plexamp](https://docs.clickwheel.fm/guides/plex): push and pull playlists between clickwheel and Plex.
- [Apple Music](https://docs.clickwheel.fm/guides/apple-music): push, pull, and delete playlists in your Apple Music account.
- [Last.fm](https://docs.clickwheel.fm/guides/scrobbling): submit listens from your iPod.

## Optional MCP server

Install the optional MCP server to use clickwheel from compatible AI clients:

```bash
pipx inject clickwheel 'clickwheel[mcp]'
```

See the [MCP server docs](https://docs.clickwheel.fm/concepts/mcp-server) for
client setup, remote access, and the generated tool reference.

## Help and contributing

See [Troubleshooting](https://docs.clickwheel.fm/troubleshooting),
[open an issue](https://github.com/pdugan20/clickwheel/issues), or read the
[contribution guide](https://github.com/pdugan20/clickwheel/blob/main/CONTRIBUTING.md).
