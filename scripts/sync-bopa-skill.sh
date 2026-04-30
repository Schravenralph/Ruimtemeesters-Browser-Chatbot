#!/usr/bin/env bash
# Sync the BOPA skill from its canonical source in
# Ruimtemeesters-MCP-Servers to the chatbot's local mirror.
#
# Canonical: ../Ruimtemeesters-MCP-Servers/packages/memory/skills/bopa.md
# Mirror:    .claude/skills/bopa/SKILL.md
#
# Usage:
#   scripts/sync-bopa-skill.sh                  # copy canonical → mirror
#   scripts/sync-bopa-skill.sh --check          # exit 1 on drift (no write)
#
# Overrides:
#   BOPA_SKILL_SOURCE=<path>                    # override canonical path
#
# Skip semantics:
#   In --check mode, if the canonical source isn't present (e.g. a
#   contributor hasn't checked out the sibling repo), the script
#   prints SKIP on stderr and exits 0 instead of failing the
#   pre-commit hook or CI step. In write mode, missing source is a
#   hard error (exit 2).

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
DEFAULT_SOURCE="$REPO_ROOT/../Ruimtemeesters-MCP-Servers/packages/memory/skills/bopa.md"
SOURCE="${BOPA_SKILL_SOURCE:-$DEFAULT_SOURCE}"
MIRROR="$REPO_ROOT/.claude/skills/bopa/SKILL.md"

MODE="write"
while [ $# -gt 0 ]; do
  case "$1" in
    --check) MODE="check"; shift ;;
    --source) SOURCE="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,20p' "$0"
      exit 0
      ;;
    *)
      echo "sync-bopa-skill: unknown arg: $1" >&2
      exit 64
      ;;
  esac
done

if [ ! -f "$SOURCE" ]; then
  if [ "$MODE" = "check" ]; then
    echo "sync-bopa-skill: SKIP — canonical not at $SOURCE (sibling repo not checked out?)" >&2
    exit 0
  fi
  echo "sync-bopa-skill: ERROR — canonical source not found at: $SOURCE" >&2
  echo "sync-bopa-skill: check out Ruimtemeesters-MCP-Servers as a sibling repo, or set BOPA_SKILL_SOURCE." >&2
  exit 2
fi

if [ ! -f "$MIRROR" ]; then
  if [ "$MODE" = "check" ]; then
    echo "sync-bopa-skill: ERROR — mirror missing at $MIRROR" >&2
    exit 1
  fi
  mkdir -p "$(dirname "$MIRROR")"
fi

if [ "$MODE" = "check" ]; then
  if cmp -s "$SOURCE" "$MIRROR"; then
    exit 0
  fi
  echo "sync-bopa-skill: DRIFT — $MIRROR differs from $SOURCE" >&2
  echo "sync-bopa-skill: run scripts/sync-bopa-skill.sh to update the mirror." >&2
  diff -u "$MIRROR" "$SOURCE" >&2 || true
  exit 1
fi

cp "$SOURCE" "$MIRROR"
echo "sync-bopa-skill: copied $SOURCE → $MIRROR"
