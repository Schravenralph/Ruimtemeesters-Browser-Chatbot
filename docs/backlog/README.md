# Backlog

GitHub Issues are disabled on the fork (`Schravenralph/Ruimtemeesters-Browser-Chatbot`).
This directory is the substitute: one Markdown file per tracked bug, observation,
or follow-up that's worth a paper trail beyond a PR description.

## Conventions

- **One file per item.** Filename: `YYYY-MM-DD-short-slug.md`.
- **Frontmatter** at the top of every file:
  ```yaml
  ---
  date: 2026-04-30
  status: open | in-progress | resolved | wontfix
  severity: low | medium | high
  reporter: <name or "user-report">
  related: PR #NN, commit <sha>, …
  ---
  ```
- **Body shape** (free-form, but most items have these sections):
  - Reporter quote / repro steps
  - Diagnosis (file:line, root cause)
  - Fix plan or workaround
  - Tracking (links to PRs that touched this)

## Lifecycle

When an item ships, add a `**Resolved by:** PR #NN` line at the top of the
body and flip `status: resolved`. Don't delete the file — the trail is the
point. Once a quarter, archive resolved items into `docs/backlog/archive/`.

## When NOT to use this folder

- Routine TODOs or scratch notes — those belong in `docs/superpowers/` specs
  or just in conversation context.
- Anything already captured in a forge spec (`docs/superpowers/specs/forge-*.md`)
  that's actively being worked.
- Security-sensitive details — file those at `docs/SECURITY.md` instead.
