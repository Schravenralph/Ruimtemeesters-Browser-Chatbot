#!/usr/bin/env bash
# Verify the OpenWebUI OpenAI-compatible connection list matches the
# curation that seed-gemini-connection.sh writes.
#
# Emits JSON to stdout (parallel to scripts/measure-brand.sh).
# Exit 0 when every criterion passes, 1 otherwise.
#
# Usage:
#   scripts/verify-llm-connections.sh
#   scripts/verify-llm-connections.sh | jq .
#
# Overrides:
#   HOST=http://localhost:3333
#   APP_CONTAINER=rm-chatbot
#   DB_CONTAINER=rm-chatbot-db
#   ADMIN_USER_ID=<uuid>             (defaults to first admin row in DB)
#   EXPECT_OPENROUTER=auto           (auto|yes|no — auto reads container env)

set -uo pipefail

HOST="${HOST:-http://localhost:3333}"
APP_CONTAINER="${APP_CONTAINER:-rm-chatbot}"
DB_CONTAINER="${DB_CONTAINER:-rm-chatbot-db}"
EXPECT_OPENROUTER="${EXPECT_OPENROUTER:-auto}"

# Resolve admin user id from DB if not provided.
ADMIN_USER_ID="${ADMIN_USER_ID:-}"
if [ -z "$ADMIN_USER_ID" ]; then
  ADMIN_USER_ID=$(docker exec "$DB_CONTAINER" psql -U rmchatbot -d rmchatbot -tAc \
    "SELECT id FROM \"user\" WHERE role = 'admin' ORDER BY created_at LIMIT 1;" 2>/dev/null | tr -d '[:space:]')
  if [ -z "$ADMIN_USER_ID" ]; then
    echo "No admin user found in DB. Sign in at $HOST first, or pass ADMIN_USER_ID." >&2
    exit 1
  fi
fi

# Decide expectation. `auto` extracts the OpenRouter key from the container's
# OPENAI_API_KEYS — a semicolon-delimited string built by docker-compose.rm.yaml
# (position 1 = Gemini, position 2 = OpenAI, position 3 = OpenRouter). The bare
# OPENROUTER_API_KEY env var does NOT exist inside the container; only
# OPENAI_API_KEYS does. seed-gemini-connection.sh uses the same `cut -d';' -f3`.
case "$EXPECT_OPENROUTER" in
  auto)
    KEYS_RAW=$(docker exec "$APP_CONTAINER" sh -c 'printf "%s" "$OPENAI_API_KEYS"' 2>/dev/null || true)
    OR_KEY=$(printf "%s" "$KEYS_RAW" | cut -d';' -f3)
    if [ -n "$OR_KEY" ]; then EXPECT_OPENROUTER=yes; else EXPECT_OPENROUTER=no; fi
    ;;
  yes|no) ;;
  *)
    echo "EXPECT_OPENROUTER must be auto|yes|no (got: $EXPECT_OPENROUTER)" >&2
    exit 1
    ;;
esac

# Mint a short-lived admin JWT inside the container (uses its own WEBUI_SECRET_KEY).
TOKEN=$(docker exec -i -e ADMIN_USER_ID="$ADMIN_USER_ID" "$APP_CONTAINER" python3 - <<'PY' 2>/dev/null | tail -1
import os
from datetime import timedelta
from open_webui.utils.auth import create_token
print(create_token({'id': os.environ['ADMIN_USER_ID']}, timedelta(minutes=5)))
PY
)
if [ -z "$TOKEN" ]; then
  echo "Failed to mint admin token in container $APP_CONTAINER." >&2
  exit 1
fi

CONFIG=$(curl -sS "$HOST/openai/config" -H "Authorization: Bearer $TOKEN")

# Validate and emit JSON. Exit non-zero on any criterion failure.
EXPECT_OPENROUTER="$EXPECT_OPENROUTER" HOST="$HOST" CONFIG="$CONFIG" python3 <<'PYEOF'
import json, os, sys, datetime

raw = os.environ.get("CONFIG", "{}")
try:
    cfg = json.loads(raw)
except Exception as e:
    print(f"verify-llm-connections: failed to parse /openai/config response: {e}", file=sys.stderr)
    print(raw[:400], file=sys.stderr)
    sys.exit(1)

expect_or = os.environ["EXPECT_OPENROUTER"] == "yes"

base_urls = cfg.get("OPENAI_API_BASE_URLS", []) or []
configs = cfg.get("OPENAI_API_CONFIGS", {}) or {}
enabled = cfg.get("ENABLE_OPENAI_API")

# A
a_pass = enabled is True

# B
expected_count = 3 if expect_or else 2
b_pass = len(base_urls) == expected_count

# C — Gemini at idx 1
c = configs.get("1", {}) or {}
c_models = c.get("model_ids", []) or []
c_prefix = c.get("prefix_id", "")
c_enabled = bool(c.get("enable"))
c_pass = c_prefix == "gemini" and c_enabled and len(c_models) == 5

# D — OpenRouter at idx 2 (only when expected)
d = configs.get("2", {}) or {}
d_models = d.get("model_ids", []) or []
d_prefix = d.get("prefix_id", "")
d_enabled = bool(d.get("enable"))
if expect_or:
    d_pass = d_prefix == "openrouter" and d_enabled and len(d_models) >= 3
    d_block = {
        "prefix_id": d_prefix,
        "enabled": d_enabled,
        "model_count": len(d_models),
        "model_ids": d_models,
        "pass": d_pass,
    }
else:
    # Skip — not applicable. Treat as neutral pass.
    d_pass = True
    d_block = {"skipped": True, "reason": "EXPECT_OPENROUTER=no", "pass": True}

# E — OpenAI placeholder at idx 0
e_url = base_urls[0] if base_urls else ""
e_enabled = bool((configs.get("0", {}) or {}).get("enable"))
e_pass = e_url == "https://api.openai.com/v1" and e_enabled is False

criteria = {
    "A_openai_api_enabled": {"value": enabled, "pass": a_pass},
    "B_base_urls_count": {"value": len(base_urls), "expected": expected_count, "pass": b_pass},
    "C_gemini_connection": {
        "prefix_id": c_prefix,
        "enabled": c_enabled,
        "model_count": len(c_models),
        "model_ids": c_models,
        "pass": c_pass,
    },
    "D_openrouter_connection": d_block,
    "E_openai_placeholder_disabled": {
        "url": e_url,
        "enabled": e_enabled,
        "pass": e_pass,
    },
}

all_pass = all(v.get("pass", False) for v in criteria.values())

out = {
    "timestamp": datetime.datetime.now().astimezone().isoformat(),
    "host": os.environ.get("HOST"),
    "expect_openrouter": expect_or,
    "criteria": criteria,
    "all_pass": all_pass,
}
print(json.dumps(out, indent=2))

if not all_pass:
    failed = [k for k, v in criteria.items() if not v.get("pass", False)]
    print(f"verify-llm-connections: failed criteria: {', '.join(failed)}", file=sys.stderr)
    sys.exit(1)
PYEOF
