# ADR-0005: Consolidate chatbot repos into one

**Date:** 2026-04-02
**Status:** Accepted

## Context

Two repos existed for the chatbot product:

- `Schravenralph/Ruimtemeesters-Browser-Chatbot` — docs-only repo (specs, plans, ADRs, tool docs). Never contained implementation code.
- `Schravenralph/ruimtemeesters-browser-chatbot-staging` — OpenWebUI fork with all actual code, Docker config, rm-tools, brand assets. This was the real product repo despite the "staging" name.

The split caused confusion: specs lived in one repo, implementation in another. The docs-only repo had no code and was never "implemented" as a standalone product.

## Decision

Consolidate into one repo:

1. Move all product docs into the OpenWebUI fork under `product-docs/`
2. Rename `ruimtemeesters-browser-chatbot-staging` → `Ruimtemeesters-Browser-Chatbot` on GitHub
3. Archive the old docs-only repo

The OpenWebUI fork becomes the single source of truth for the chatbot: code, config, docs, specs, and ADRs all in one place.

## Rationale

- One repo is simpler to navigate, search, and maintain
- Docs next to code means specs stay in sync with implementation
- Product docs go in `product-docs/` to avoid clashing with upstream OpenWebUI's `docs/`
- The "staging" name was a historical accident — this is the production repo

## Consequences

- All future specs, plans, and ADRs go in `product-docs/` in this repo
- The old `Ruimtemeesters-Browser-Chatbot` repo is archived (read-only, kept for reference)
- Claude Code memory and project settings need updating to point at the new location
