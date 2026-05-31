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
   (`scripts/gen-cli-reference.py`, `gen-mcp-reference.py`) + a CI job that
   regenerates and **fails on drift**. So reference pages can't go stale.
2. **Mirror fidelity:** the mirror is overwritten every sync, so it is always
   byte-equal to source `docs-mintlify/`. Never hand-edit the mirror.

---

## 3. Information architecture (Diátaxis) ✅

Keep the four modes distinct; don't blur them:

- **Tutorial** — `quickstart`: zero → first win, linear, no detours.
- **How-to guides** — task-focused (`sync-to-ipod`, `playlists`, …); assume the
  quickstart is done.
- **Reference** — generated, exhaustive, dry (`cli`, `mcp-tools`,
  `configuration`).
- **Explanation/concepts** — the _why_ (`architecture`, `design`, `mcp-server`).

Navigation: two tabs (**Guides**, **Reference**); within Guides group as
_Getting started · How-to · Concepts · Updates_.

---

## 4. Content standards ✍️

Standards we're committing to as we improve clickwheel (apply to biblio too):

- **Every page:** set `title` and `description` frontmatter. The `description`
  is the SEO and search snippet, so write a real sentence, not a label.
- **Show, don't just tell:** each how-to should include at least one **expected
  output** block, not only the command — readers want to know what success looks
  like. We favor representative **text/output code blocks** over UI screenshots
  (no screenshot upkeep, no drift, copy-pasteable). Reserve images for things
  text can't convey.
- **Use the right component for the shape of the content:**
  - linear setup → `<Steps>` (not `## 1.` `## 2.` headings)
  - OS/shell/client variants → `<Tabs>`
  - optional detail / troubleshooting → `<Accordion>` / `<AccordionGroup>`
  - cross-sell / next steps → `<CardGroup>`
  - call-outs → `<Note>` (info), `<Warning>` (footguns), `<Tip>` (nice-to-know)
  - terminal/UI captures → `<Frame>` (with a caption)
- **Voice:** second person, present tense, imperative for instructions. Short
  paragraphs. No emojis in body or code (house rule).
- **Code blocks:** always language-tagged; prefer copy-pasteable, complete
  commands; show real values, not `<placeholders>`, where safe.
- **Required pages we found missing (clickwheel):** Troubleshooting/FAQ,
  Requirements & supported devices. (Add to biblio's plan: an equivalent
  "supported libraries / limits" page.)
- **Cross-link generously** but always forward to the canonical page (one source
  of truth per fact).

---

## 5. Visual & brand standards ✍️

To be locked once we pick a direction (see the open design decision). Capture
here so biblio inherits a consistent system:

- **`docs.json` controls:** `theme`, `colors` (`primary`/`light`/`dark`),
  `logo` (light+dark SVG), `favicon`, `appearance.default`, optional `fonts`.
- **Color:** one primary that carries the brand; ensure AA contrast in both
  light and dark. Avoid the default generic indigo unless chosen deliberately.
- **Logo + favicon:** provide crisp light/dark SVGs; verify the favicon reads at
  16px.
- **Custom CSS/JS** is allowed on free — use sparingly for brand touches
  (accent, type) and never for anything load-bearing.
- **Social/OG image:** set one for good link previews (`metadata` /
  `og:image`). Each project gets its own.
- **Hero:** lead the landing page with a real visual (screenshot/terminal cast),
  not just text + cards.
- **Per-project, not shared:** logo, colors, OG image, domain. **Shared:**
  component patterns, page structure, voice, the checklist below.

---

## 6. Pre-launch checklist 🔁

- [ ] `mint broken-links` passes (CI: "Docs Links").
- [ ] Generated reference regenerated; drift CI green.
- [ ] Every page has a real `description`.
- [ ] Quickstart works copy-paste on a clean machine.
- [ ] Light + dark both legible; logo/favicon correct in both.
- [ ] OG image set; link preview checked.
- [ ] Custom domain resolves; HTTPS valid.
- [ ] Mirror sync verified (dispatch once, confirm success).
- [ ] README of the product repo points to the live docs.

---

## 7. Tooling

- **Local preview:** `mint dev` in `docs-mintlify/` (live reload).
- **Link check:** `mint broken-links`.
- **Make targets:** `make docs` (preview), `make docs-reference` (regenerate),
  `make docs-links` (check).

---

## 8. Mintlify features to leverage

Best-practice features beyond the core components, with clickwheel's adoption
status. Apply the same set to biblio.

Adopted:

- `<ParamField>` for params (type/required/default badges; descriptions wrap as
  paragraphs instead of cramped table cells)
- Synopsis line per command (`clickwheel <cmd> [OPTIONS] ...`)
- Per-group reference pages (CLI + MCP) with an overview landing
- Generated, drift-checked reference; `sidebarTitle`; a real `description` per page
- Contextual menu (Copy page / View as Markdown / Open in Claude or ChatGPT) via
  the `docs.json` `contextual` block
- `llms.txt` / `llms-full.txt` (auto-generated)

Queued:

- [ ] Feedback widget: thumbs, suggest-edit (opens a GitHub PR), and raise-issue,
      via the `docs.json` `feedback` block
- [ ] Examples per command/tool: the most-read part of a CLI reference
      (clig.dev). A short invocation plus expected output
- [ ] Reusable snippets (`snippets/`) to dedupe repeated boilerplate
- [ ] Mermaid diagram for the architecture data-flow (replace the ASCII art)
- [ ] Code block titles and `<CodeGroup>` where useful
- [ ] Branded OG/social image and card icons (fold into the visual pass)
- [ ] Analytics (GA4 / PostHog), optional, only if usage data is wanted

---

## Open decisions

- **Landing hero:** lead the page with a real visual (deferred to the visual
  polish pass). Otherwise the design direction is locked: maple theme, accent
  `#4A82EF` light / `#C4DCFF` dark, play/pause wordmark logo, adaptive
  click-wheel favicon.
