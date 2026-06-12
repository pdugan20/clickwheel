# clickwheel.fm apex worker

A Cloudflare Worker that serves the `clickwheel.fm` apex itself instead of
redirecting to the Mintlify docs. It exists for one reason: control the
favicon Google caches for `clickwheel.fm`.

## Why

`clickwheel.fm` used to redirect (a Cloudflare Redirect Rule) to
`docs.clickwheel.fm`. The Mintlify docs page advertises a transparent
`apple-touch-icon`, which Google's favicon service flattens onto black and
returns as a JPEG at 48/64px — the black square the Claude clients render
for the connector. (This is the same failure mode rewind.rest hit.)

This worker serves the apex directly and advertises **only** a transparent,
square favicon — **no apple-touch** — so Google falls back to the
transparent favicon at every size. Deep links still forward to the docs.

## What it serves

- `/` — minimal landing page (favicon links only, no apple-touch) with a
  link to `docs.clickwheel.fm`.
- `/favicon.ico`, `/favicon.svg` — transparent, square (28x28).
- `/apple-touch-icon.png`, `/apple-touch-icon-precomposed.png` — `404`.
- everything else — `302` to `docs.clickwheel.fm`.

## Deploy

1. **Remove the existing Cloudflare Redirect Rule** for
   `clickwheel.fm → docs.clickwheel.fm` (Rules → Redirect Rules). The
   worker route would otherwise never run.
2. Deploy the worker:

   ```bash
   cd apex-worker
   npm install
   npx wrangler deploy
   ```

   The route `clickwheel.fm/*` is configured in `wrangler.toml`.

3. Verify:

   ```bash
   curl -sI https://clickwheel.fm/ | head -1                 # 200, not 301
   curl -sI https://clickwheel.fm/apple-touch-icon.png | head -1   # 404
   ```

Google's cached favicon updates on its next re-crawl (days to weeks).
