#!/usr/bin/env bash
# scripts/setup-hooks.sh — run once per fresh checkout.
#
# Points git at the repo-committed .githooks/ directory so pre-commit
# checks (like no-public-bind-check) actually run locally. Without this,
# .git/hooks/ is untouched and the hooks sit dormant.
set -e
git config core.hooksPath .githooks
echo "git hooks enabled from .githooks/"
