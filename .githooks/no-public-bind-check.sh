#!/usr/bin/env bash
# .githooks/no-public-bind-check.sh
#
# Refuse commits that introduce public-interface bindings. Inspects only
# NEWLY ADDED lines in the staged diff, so legacy code is grandfathered
# until it's touched.
#
# Escape hatch: put the literal string `public-bind-ok` on the same line
# (as a comment in YAML / JS / TS, or inside a string).
#
# Context: this is the code-time safety net for the 2026-04-17 AKIRA
# ransomware incident. See ADRs:
#   - security-never-expose-mongodb.md (the invariant)
#   - ADR-0004-enforce-no-public-docker-bindings-at-firewall.md (runtime)
#   - ADR-0005-no-public-bind-pre-commit.md (this hook)

set -euo pipefail

added=$(git diff --cached --no-color -U0 --diff-filter=ACMR 2>/dev/null |
  grep -E '^\+[^+]' | sed 's/^+//') || true
[ -z "${added:-}" ] && exit 0

violations=""
add_v() { violations+="  - $1"$'\n'; }

while IFS= read -r line; do
  [[ "$line" == *"public-bind-ok"* ]] && continue

  # 1) Literal 0.0.0.0 in quotes or backticks.
  if echo "$line" | grep -qE "['\"\`]0\.0\.0\.0['\"\`]"; then
    add_v "literal 0.0.0.0 → ${line:0:140}"
    continue
  fi

  # 2) docker-compose 'ports:' short-form without loopback prefix.
  #    Accepts 127.0.0.1:X:Y, rejects X:Y / ${VAR}:Y / 0.0.0.0:X:Y.
  if echo "$line" | grep -qE '^[[:space:]]*-[[:space:]]*"?([0-9]+|0\.0\.0\.0:[0-9]+|\$\{[A-Z_][^}]*\}):[0-9]+"?[[:space:]]*$'; then
    add_v "compose port without 127.0.0.1: prefix → ${line:0:140}"
    continue
  fi

  # 3) package.json script flags: bare --host or --host <non-loopback>.
  #    The line has --host inside a dev/start/serve/server/preview script,
  #    AND the --host is NOT followed by 127.0.0.1 / localhost / ::1.
  if echo "$line" | grep -qE '"(dev|start|serve|server|preview)"[[:space:]]*:[[:space:]]*"[^"]*--host\b'; then
    if ! echo "$line" | grep -qE '\--host[[:space:]]+(127\.0\.0\.1|localhost|::1)\b'; then
      add_v "script uses --host without explicit loopback → ${line:0:140}"
      continue
    fi
  fi
done <<< "$added"

if [ -n "$violations" ]; then
  cat >&2 <<EOF

no-public-bind-check: commit refused.

Newly-added lines look like they'd expose a service on a public
interface. This is the class of mistake that led to the 2026-04-17
AKIRA ransomware wipe of the Transcriber MongoDB.

Violations:

$violations

Fix (pick one):
  - Bind to 127.0.0.1 and let Caddy reverse-proxy if the service
    speaks HTTP/WebSocket. Example: app.listen(PORT, '127.0.0.1').
  - Use 'expose:' in docker-compose for services that stay on the
    compose network.  Example: expose: ["5432"]
  - Keep a host-side binding but prefix with 127.0.0.1.
    Example: ports: ["127.0.0.1:5432:5432"]
  - If the exposure is genuinely intentional, add 'public-bind-ok'
    on the same line.  YAML: # public-bind-ok  |  JS: // public-bind-ok

Rules live in .githooks/no-public-bind-check.sh.
EOF
  exit 1
fi

exit 0
