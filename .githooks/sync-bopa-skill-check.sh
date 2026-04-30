#!/usr/bin/env bash
# Pre-commit hook: when .claude/skills/bopa/SKILL.md is staged, verify
# it still matches the canonical in Ruimtemeesters-MCP-Servers. Skips
# silently when the sibling repo isn't checked out (see sync-bopa-skill.sh).
set -e

REPO_ROOT="$(git rev-parse --show-toplevel)"
MIRROR_PATH=".claude/skills/bopa/SKILL.md"

if ! git diff --cached --name-only | grep -qx "$MIRROR_PATH"; then
  exit 0
fi

"$REPO_ROOT/scripts/sync-bopa-skill.sh" --check
