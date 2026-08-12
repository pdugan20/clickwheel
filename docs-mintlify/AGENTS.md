# Documentation mirror guidance

## Work modes

- Default to exploration for documentation, visual, and content iterations. Make focused edits directly; do not require a formal spec, separate plan, worktree, or TDD.
- Apply publication rigor only when the user explicitly asks to finalize or publish documentation. Match verification to the requested stage.

## Code Review Rules

- Flag edits made only in the generated `clickwheel-fm/docs` mirror instead of this
  source directory, or mirror-workflow changes that stop preserving an exact one-way copy.
- Flag documented commands, options, defaults, or safety behavior that disagree with the
  current CLI implementation and root repository guidance.
- Flag public docs that expose credentials, private paths/data, unreleased behavior, or
  destructive commands without the required warning and safe verification path.

## Source of truth

- This directory is the source for the generated `clickwheel-fm/docs` repository and the site at `docs.clickwheel.fm`.
- Edit documentation here. Do not edit the generated mirror directly; its sync workflow overwrites mirror changes.
- Keep product behavior aligned with the repository root guidance and the implementation in `clickwheel/`.
- Ask before publishing or triggering the mirror sync unless the user's request explicitly authorizes that exact action.
