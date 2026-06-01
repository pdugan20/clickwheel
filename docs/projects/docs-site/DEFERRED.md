# Docs site — deferred / out of scope

Items intentionally parked, each with a reason. Nothing here is "forgotten" —
pull an item back into [TRACKER.md](TRACKER.md) when its reason no longer holds.

## Deferred

- **Separate Astro/Pages landing site** (like rewind's `rewind-www`).
  _Reason:_ rewind has a marketing site because rewind.rest is a product;
  clickwheel is an OSS tool and Mintlify's intro page is a sufficient landing.
  Revisit only if clickwheel needs distinct marketing separate from docs.

- **Point the apex `clickwheel.fm/` at the docs** (redirect or serve).
  _Reason:_ the apex is the Access-gated MCP endpoint; a public redirect there
  reopens the same path-bypass complexity we just dealt with. `docs.clickwheel.fm`
  stands alone fine. Revisit if/when MCP moves off the apex.

- **Versioned docs** (per-release doc snapshots).
  _Reason:_ clickwheel is pre-1.0, single-tenant, low API-surface churn; one
  "latest" is enough. Revisit at 1.0 or if breaking changes accelerate.

- **Vale prose-style linting** in CI.
  _Reason:_ valuable at team scale; for a solo project the freshness check +
  `mint validate` cover the high-value cases. Easy to add later.

- **"Stale page" flag for narrative docs untouched 90+ days.**
  _Reason:_ the generated reference (the part that actually rots) is already
  drift-checked; narrative pages are low-volume. Add a timestamp-diff check later
  if narrative drift becomes a real problem.

- **Docs analytics / search analytics.**
  _Reason:_ Mintlify provides basics out of the box; custom analytics is premature.

## Diagrams to design (polished visuals)

Plain-text and Mermaid diagrams were pulled (too generic for the visual bar).
Add back as polished, designed visuals (a styled SVG or image) during the visual
pass. The prose bullets stay in place meanwhile, so nothing is lost.

- **Architecture data-flow** (`concepts/architecture.mdx`, "The data flow"):
  Music files →(scan)→ SQLite catalog →(select / edit)→ Playlist →(diff / sync)→
  iPod (iTunesDB); `fix` writes tags back into the library files.
- **Remote / mobile access flow** (`guides/remote-mcp.mdx`, "How it works"):
  Claude app →(HTTPS)→ Cloudflare (Access auth) →(tunnel)→ Mac running
  `clickwheel-mcp serve --http`.

## Explicitly NOT in this project (separate track)

- Finishing the **remote-access round**: launchd persistence, connector
  live-test (phone + iPod), merging #48. Tracked in
  `docs/mcp/remote-mobile-access-tracker.md`; resumed after the docs site.

## Parked for the Troubleshooting page

Moved off the Requirements page (it's an operational edge case, not a
requirement). Add to Troubleshooting when that page gets its content pass:

> **Network-stored libraries.** If your `music_dir` lives on a network share
> (SMB/NAS), clickwheel handles a stale mount by force-remounting before a
> file-touching operation instead of hanging. You can provide an explicit
> `smb://` fallback via `library_mount_url`. See
> [Configuration](/reference/configuration).

Also moved off the Sync to iPod guide (it's device troubleshooting, not part of
the sync flow):

> **iPod not detected.** Classic iPods spin down and may auto-dismount when
> idle. If a command can't find the device, nudge it awake (touch the wheel, or
> replug) and retry.
