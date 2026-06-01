# Docs site — best practices playbook

A living, portable playbook for building and shipping a Mintlify docs site for a
single-maintainer OSS project. Captured while building `docs.clickwheel.fm` so
the **bibliocommons-mcp** site (and any future ones) is a fast-follow, not a
re-derivation.

Legend: ✅ proven in practice · 🔁 repeatable recipe · 🧪 to validate · ✍️ to fill
in as we set standards.

---

## 1. Hosting & infrastructure ✅🔁

The free-tier constraints and the workaround we proved end-to-end:

- **Mintlify free (Hobby) = one site per Mintlify account.** Multi-site is
  gated to paid/Enterprise. A second free site needs a **second Mintlify
  account** (use a `dugan.pat+<project>@gmail.com` alias).
- **The Mintlify GitHub App installs once per GitHub owner**, bound to one
  workspace. The personal account `pdugan20` is already bound to the first site
  (rewind), so a second account sees **no selectable repos** there — the
  symptom that blocks the naive path.
- **Fix: connect each additional site to a repo owned by its own GitHub org.**
  An org gives a clean app-installation surface. Proven 2026-05-30.
- **Free tier:** custom domain ✅, private source repo ✅; the published site is
  always public (password protection is Pro; auth/SSO is Enterprise).

### Per-site launch recipe 🔁

1. **Create a dedicated GitHub org** (browser only — no API):
   `github.com/account/organizations/new`, Free plan. Name it after the docs
   domain (e.g. `clickwheel-fm`). Org names are global; check availability with
   `gh api /users/<name>` (404 = free).
2. **Create the mirror repo** in the org (e.g. `<org>/docs`), public.
3. **Enable workflow write permissions on the org** (browser):
   Org → Settings → Actions → General → Workflow permissions → _Read and write_.
   New orgs ship read-only, which blocks the sync push. (API needs `admin:org`:
   `gh api --method PUT /orgs/<org>/actions/permissions/workflow -f default_workflow_permissions=write`.)
4. **Seed the mirror** with the source `docs-mintlify/` contents at the repo
   **root** (so `docs.json` is top-level — no subdirectory toggle in Mintlify).
5. **Add the pull-based sync workflow** to the mirror (see §2).
6. **Install the Mintlify App** on the org, scoped to the mirror repo.
7. **Connect** from the project's `+alias` Mintlify account → org / mirror /
   `main`, subdirectory **off**.
8. **Add the custom domain** in Mintlify; create the DNS **CNAME** it shows
   (`docs` → Mintlify's target).

---

## 2. Source → mirror sync (drift-proof) ✅🔁

The docs are authored in the **product repo** (`pdugan20/<project>/docs-mintlify`)
so the generators and anti-drift CI sit next to the code. Mintlify needs a repo
under a **different owner** (the org), so a one-way mirror bridges them.

- **Pull, don't push.** A workflow _in the mirror_ clones the public source,
  `rsync --delete`s `docs-mintlify/` to the mirror root, and self-pushes with
  the built-in `GITHUB_TOKEN`. This needs **no cross-repo credentials** —
  reading a public repo is auth-free and a repo's own token can push to itself.
  (Deploy keys and PATs both required extra setup or were org-disabled; the pull
  model sidesteps all of it.)
- **Triggers:** `schedule` (30-min safety net) + `workflow_dispatch` (manual) +
  `repository_dispatch: docs-changed` (optional near-instant trigger from the
  source repo, if/when a cross-repo token is added).
- **Preserve mirror-only files** in the rsync excludes: `.git`, `.github`,
  `README.md` (the "generated — do not edit" banner).
- **Pin `permissions: contents: write`** in the workflow and set the repo token
  to write (`gh api --method PUT /repos/<org>/docs/actions/permissions/workflow -f default_workflow_permissions=write`).

### Anti-drift, two layers ✅

1. **Content correctness** lives in the source repo: generators
   (`scripts/gen-cli-reference.py`, `gen-mcp-reference.py`, `gen-changelog.py`)
   - a CI job that regenerates and **fails on drift**. So reference and
     changelog pages can't go stale.
2. **Mirror fidelity:** the mirror is overwritten every sync, so it is always
   byte-equal to source `docs-mintlify/`. Never hand-edit the mirror.

---

## 3. Information architecture (Diátaxis) ✅

Keep the four modes distinct; don't blur them:

- **Tutorial** — `quickstart`: zero → first win, linear, no detours.
- **How-to guides** — task-focused; assume the quickstart is done.
- **Reference** — generated, exhaustive, dry (`cli`, `mcp-tools`,
  `configuration`).
- **Explanation/concepts** — the _why_ (`architecture`, `design`, `mcp-server`).

**Navigation: group how-tos by topic, not by Diátaxis label, once you have more
than a few.** A single flat "How-to guides" list stops scanning well past ~5
entries. clickwheel landed on **Getting started · Everyday use · Integrations ·
Claude (MCP) · Concepts · Help**, with the AI/MCP story as its own group. For
biblio, expect a parallel shape (Getting started · Everyday use · the catalog/
holds groups · Claude (MCP) · Concepts · Help).

---

## 4. Content standards ✅

Proven on clickwheel; apply verbatim to biblio.

### Frontmatter & nav

- **Every page sets `title` + a real-sentence `description`** (it's the SEO and
  search snippet — write a sentence, not a label).
- **Add an `icon:` to every page in a tab**, uniformly (half-iconed groups look
  unfinished). Reuse the homepage card icons so nav and cards match.
- **Use `sidebarTitle` to keep nav labels short** when the page `title` is long
  (e.g. title "Design principles", sidebarTitle "Design").

### Framing & voice

- **Lead with the differentiator, not the crowded category.** clickwheel is
  framed iPod-first (the rare thing) rather than "another library manager."
  Find biblio's equivalent rare hook and lead with it.
- **A short "what it does" in 2–4 capability pillars**, not a feature dump.
- **Second person, present tense, imperative.** Short paragraphs.
- **No em dashes.** Hard rule. Use commas, colons, or parentheses. (Grep `—`
  before shipping.)
- **No hardcoded, drift-prone counts** ("37 tools") unless programmatically
  derived. Illustrative sample-output blocks are fine; keep **one consistent
  fictional library** across pages (clickwheel used ~642 albums; example artists
  Nirvana / Beastie Boys).
- **Strip implementation jargon from user-facing pages** — keep the capability,
  drop the mechanism. We cut "native pipeline", "pylast-driven", and bare module
  name-drops. Reference/concepts pages may be more technical.

### Callouts — minimal, consistent palette

- **`<Note>` (blue) is the default** for any advisory or important info.
- **`<Warning>` (yellow) is reserved for the genuinely irreversible** (data
  loss, can't-undo — e.g. "the `.p8` downloads only once").
- **Avoid `<Tip>` (green).** It just adds a third color; demote nice-to-knows to
  prose.
- **Don't stack callouts.** One per concept, and prefer prose unless it's a real
  gate or caution. Two colored boxes back-to-back is a smell.

### Links

- **Link once, on first meaningful mention.** Don't double-link the same target
  in close proximity (e.g. lead paragraph and the bullet four lines below).
- **Link to the most specific relevant page** (a per-domain reference beats a
  generic overview), and always forward to the canonical page — one source of
  truth per fact.

### Code examples

- Always language-tagged; use **code-block titles** for config / `.env` blocks
  (filename in the title bar).
- **Align inline `#` comments and keep them short** so the block doesn't scroll
  horizontally.
- **Prefer runnable copy-paste over shell plumbing** — `echo "k: v" > file`
  beats a heredoc in a quickstart.
- **Realistic-but-clean paths:** `~/Music/Artist/Album/Track.m4a`; drop
  `/Volumes/...` and track-number prefixes.
- **Real values where safe; placeholders for secrets and domains**
  (`<your-token>`, `mcp.example.com`). Keep secrets in `~/.<app>/.env`
  (mode `600`); **inline the env var** in prose rather than a sparse
  `KEY=...` block; treat tokens like passwords and link the provider's official
  "find your token" page (durable, vs. a UI click-path that rots).

### Components by shape

- Linear setup → `<Steps>`; **set `titleSize="h3"`** so the steps populate the
  right-rail TOC (default `p` leaves a step page with an empty TOC).
- Client/OS/shell variants → `<Tabs>`.
- Optional / troubleshooting / advanced detail → `<Accordion>` /
  `<AccordionGroup>` (progressive disclosure). Link to a full repo runbook
  rather than inlining long ops.
- Next steps / cross-sell → `<CardGroup>`.

### Verify before you document

- **Check command names, arg names, flags, and limits against the source.** This
  pass caught a wrong `fix` argument ("Artist - Album Name" → it's an artist
  folder) and an over/under-claimed supported-device list. Don't guess; read the
  code, and verify tool behavior (e.g. Mintlify config) against the official
  docs.
- **Generated pages (reference, changelog) are never hand-edited** — change the
  generator and regenerate. Don't fight the automation: we left release-please's
  changelog noise and pre-1.0 formatting alone rather than post-processing it.

### Pages every project needs

- **Quickstart**, **Requirements / supported-X**, **Troubleshooting.**
- **Requirements**: present "what each integration needs" as a **table**
  (`Extra | Credentials`), and surface gotchas (e.g. paid Apple Developer
  membership) at the requirements level, not buried in the guide.
- **Troubleshooting**: bucket by area, and **point at self-diagnostic tools**
  (the `doctor` commands) rather than re-explaining setup.

### The MCP / AI cross-reference pattern

On each feature or integration guide, add a single **one-line "From Claude"
nudge** that links (a) MCP setup and (b) the **per-domain tool reference** (e.g.
the Plex guide):

> You can also drive this from Claude. Set up the [MCP server](...), then the
> [Plex tools](/reference/mcp-tools/plex) are yours.

Do **not** dump tool names inline (the reference owns them) and do **not** repeat
a gating/permission note on every page — document client-side gating **once** on
the MCP server page.

---

## 5. The content & polish pass (process) 🔁

How we actually moved through clickwheel page-by-page. Repeat for biblio:

1. **Reorg the nav first** (topic groups, §3), then walk pages **in nav order**
   (Welcome → … → Changelog).
2. **Per page: holistic read first.** "What should this page do? What's wrong,
   redundant, or missing?" Come back with recommendations, _then_ make targeted
   edits. Not every page needs heavy editing — say so when a page is already
   strong.
3. **Options-first iteration.** For any wording or structure choice, present 2–3
   options + a recommendation and let the maintainer pick. Don't unilaterally
   rewrite while riffing.
4. **Verify against source as you go** (commands, args, flags, limits).
5. **Commit per page** (small, logical commits). **Apply pre-commit hooks
   manually first** — `uv run pre-commit run --files <changed>` — to dodge the
   stash-conflict dance that hits when a file has both staged and unstaged
   changes (prettier auto-fix mid-commit triggers it).
6. **Run `mint broken-links` after each page.**
7. **Park tangents** (an edge-case note that belongs on another page) in
   `DEFERRED.md`. When you reach that page, **check whether it already covers
   them** — clickwheel's Troubleshooting already had both parked notes, so the
   parking was redundant.

---

## 6. Visual & brand standards ✅

Brand direction is locked for clickwheel; the system (not the values) carries to
biblio.

- **`docs.json` controls:** `theme`, `colors` (`primary`/`light`/`dark`),
  `logo` (light+dark), `favicon`, `appearance.default`, optional `fonts`.
  clickwheel: maple theme, primary `#4A82EF` / light `#C4DCFF` / dark `#4A82EF`.
- **One brand primary**, AA contrast in both light and dark. Avoid the default
  generic indigo unless chosen deliberately.
- **Logo:** provide light + dark. Constrain size in custom CSS **and set
  `aspect-ratio` on the logo `img`** so it doesn't flash at intrinsic size on
  client-side navigation.
- **Favicon:** a single **adaptive SVG** (black default + `prefers-color-scheme:
dark` → white) reads in both modes. Mintlify generates the PNG derivatives at
  **server start**, so restart `mint dev` to see favicon changes (content/CSS
  hot-reload, the favicon doesn't).
- **Page icons:** see §4 — uniform within a tab, reused from the homepage cards.
- **Callout palette:** see §4 (Note default, Warning for irreversible).
- **OG/social image + landing hero:** per-project, deferred to a visual pass.
  Prefer **designed SVG diagrams over Mermaid** (Mermaid reads too generic).
- **Per-project, not shared:** logo, colors, OG image, domain. **Shared:**
  component patterns, page structure, voice, the callout palette, the checklist.

---

## 7. Mintlify mechanics & gotchas ✅

Verified against `mintlify.com/docs` and in practice this pass:

- **Theme toggle is all-or-nothing.** `appearance.strict: true` hides _every_
  toggle; there is no per-location control, so you get both the sidebar pill and
  the footer switcher, or neither. They drive one global setting. Leave both;
  duplicated beats no toggle.
- **`footer.links` adds an extra footer tier** (in maple) above "Powered by
  Mintlify" — with only a couple of links it reads as a confusing second footer.
  GitHub can also end up listed 3× (navbar `primary` button at the sidebar
  bottom + footer social icon + footer link); keep it to the navbar button +
  footer icon.
- **No native PyPI/social slot for PyPI.** Link it inline at the install step
  (and/or a footer `links` column if you want it global).
- **Step titles only hit the right-rail TOC with `titleSize="h2"/"h3"`** — use
  this for a step-based page instead of `mode: "wide"` (which hides the TOC and
  widens the page).
- **`mode`:** `wide` hides the right-rail TOC; `center` removes sidebar + TOC;
  `custom` strips chrome. Section `##`/`###` headings feed the right rail — keep
  them short (we shortened Design's full-sentence headings for this reason).
- **maple has no top navbar bar:** `navbar.primary` renders at the **bottom of
  the left sidebar**, and `navbar.links` near it.

---

## 8. Pre-launch checklist 🔁

- [ ] `mint broken-links` passes (CI: "Docs Links").
- [ ] Generated reference + changelog regenerated; drift CI green.
- [ ] Every page has a real `description` and an `icon`; nav labels short.
- [ ] No em dashes anywhere (grep `—`).
- [ ] Callout palette consistent (Note default; Warning only for irreversible;
      no stray Tips).
- [ ] Commands, args, flags, and limits verified against source.
- [ ] Example domains/secrets genericized (`mcp.example.com`, `<your-token>`).
- [ ] Quickstart works copy-paste on a clean machine.
- [ ] Light + dark both legible; logo/favicon correct in both (logo doesn't
      flash on navigation).
- [ ] OG image set; link preview checked.
- [ ] Custom domain resolves; HTTPS valid.
- [ ] Mirror sync verified (dispatch once, confirm success).
- [ ] README of the product repo points to the live docs.

---

## 9. Tooling

- **Local preview:** `mint dev` in `docs-mintlify/` (live reload; favicon needs
  a restart).
- **Link check:** `mint broken-links`.
- **Make targets:** `make docs` (preview), `make docs-reference` (regenerate),
  `make docs-links` (check).

---

## 10. Mintlify features to leverage

Adopted on clickwheel; apply the same set to biblio:

- `<ParamField>` for params (type/required/default badges; descriptions wrap as
  paragraphs instead of cramped table cells).
- Synopsis line per command (`clickwheel <cmd> [OPTIONS] ...`).
- Per-group reference pages (CLI + MCP) with an overview landing.
- Generated, drift-checked reference + changelog; `sidebarTitle`; a real
  `description` per page.
- Contextual menu (Copy page / View as Markdown / Open in Claude or ChatGPT) via
  the `docs.json` `contextual` block.
- Feedback thumbs (`docs.json` `feedback`); suggest-edit/raise-issue skipped
  because the connected repo is the generated mirror, not the source.
- CLI Examples per command (curated `scripts/cli_examples.py`); MCP "Try asking"
  prompts per domain (`scripts/mcp_examples.py`).
- Code-block titles for config and `.env` blocks (filename in the title bar).
- `llms.txt` / `llms-full.txt` (auto-generated).

Reconsidered this pass:

- **Reusable snippets:** we tried a shared Allow/Deny gating snippet across
  guides and **removed it.** Client-side gating is general MCP behavior —
  document it **once** on the MCP server page, don't repeat it per guide. Use
  `snippets/` only for genuinely repeated, page-agnostic boilerplate.

Decided against:

- **Mermaid diagrams.** The shapes/arrows read too generic; can't be styled to
  "designed" quality. Diagrams are parked in [DEFERRED.md](DEFERRED.md) to add
  back as polished SVGs in the visual pass.

Queued:

- [ ] `<CodeGroup>` (tabbed code) where useful.
- [ ] Branded OG/social image (fold into the visual pass).
- [ ] Analytics (GA4 / PostHog), optional, only if usage data is wanted.

---

## Open decisions

- **Brand is locked:** maple theme, accent `#4A82EF` light / `#C4DCFF` dark,
  play/pause wordmark logo, adaptive click-wheel favicon, per-page sidebar icons.
- **Remaining (visual pass):** landing hero visual, the two designed SVG diagrams
  parked in [DEFERRED.md](DEFERRED.md) (architecture data-flow, remote-mcp flow),
  and a branded OG image.
