#!/usr/bin/env bash
# Seed the OpenWebUI OpenAI-compatible connection list with curated
# Gemini (Google AI Studio) and OpenRouter endpoints.
#
# Idempotent — safe to re-run after DB reset, container rebuild, or
# `docker compose down -v`. Reads keys from the rm-chatbot container's
# OPENAI_API_KEYS env (position 1 = Gemini, position 2 = OpenRouter,
# both 0-indexed).
#
# OpenRouter is optional: if OPENROUTER_API_KEY isn't in the container
# env, the script falls back to seeding only Gemini and prints a
# warning. The 3-entry shape (OpenAI / Gemini / OpenRouter) matches
# docker-compose.rm.yaml so the persisted DB config doesn't drift from
# the compose file — see the OpenWebUI foot-gun "PersistentConfig: env
# reads only on first boot, DB wins after" for why this matters.
#
# Usage:
#   scripts/seed-gemini-connection.sh
#
# After seeding, verify the resulting DB state with:
#   scripts/verify-llm-connections.sh
#
# Overrides:
#   HOST=http://localhost:3333
#   APP_CONTAINER=rm-chatbot
#   ADMIN_USER_ID=<uuid>     (defaults to first admin row in DB)

set -euo pipefail

HOST="${HOST:-http://localhost:3333}"
APP_CONTAINER="${APP_CONTAINER:-rm-chatbot}"
DB_CONTAINER="${DB_CONTAINER:-rm-chatbot-db}"

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

# Extract keys from the container's env. OPENAI_API_KEYS is a single env var
# of the shape `A;B;C` — position 1 is Gemini, position 2 is OpenRouter.
KEYS_RAW=$(docker exec "$APP_CONTAINER" sh -c 'printf "%s" "$OPENAI_API_KEYS"')
GEMINI_KEY=$(printf "%s" "$KEYS_RAW" | cut -d';' -f2)
OPENROUTER_KEY=$(printf "%s" "$KEYS_RAW" | cut -d';' -f3)
if [ -z "$GEMINI_KEY" ]; then
  echo "GEMINI_API_KEY missing from container env. Set GEMINI_API_KEY in .env and recreate the container." >&2
  exit 1
fi
if [ -z "$OPENROUTER_KEY" ]; then
  echo "WARN: OPENROUTER_API_KEY missing from container env — seeding Gemini only." >&2
  echo "WARN: set OPENROUTER_API_KEY in .env + recreate the container to seed OpenRouter too." >&2
fi

# Mint a short-lived admin JWT inside the container (uses its own WEBUI_SECRET_KEY).
# Pass ADMIN_USER_ID via env (-e) and read it from os.environ inside Python —
# nothing gets interpolated into the source so a UUID with unusual chars can't
# break out of the Python string literal (defensive — UUIDs shouldn't contain
# quotes, but external inputs don't belong in source either).
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

# Build the request body with python's json.dumps so secrets and every other
# value are JSON-escaped correctly. Keys that ever contain "/\ or control chars
# (Google AI Studio + OpenRouter keys don't today, but this is the right shape
# for any secret) don't corrupt the payload.
BODY=$(GEMINI_KEY="$GEMINI_KEY" OPENROUTER_KEY="$OPENROUTER_KEY" python3 - <<'PY'
import json, os

gemini_key = os.environ['GEMINI_KEY']
openrouter_key = os.environ.get('OPENROUTER_KEY', '')

# Position 0 = OpenAI placeholder, position 1 = Gemini, position 2 = OpenRouter
# (only included when OPENROUTER_KEY is set — keeps the persisted DB shape in
# sync with the actual key set the operator has configured).
base_urls = [
    'https://api.openai.com/v1',
    'https://generativelanguage.googleapis.com/v1beta/openai',
]
keys = ['', gemini_key]
configs = {
    '0': {'enable': False, 'connection_type': 'external'},
    '1': {
        'enable': True,
        'connection_type': 'external',
        'prefix_id': 'gemini',
        'tags': [{'name': 'Google'}],
        'model_ids': [
            'gemini-3.1-pro-preview',
            'gemini-3.1-flash-lite-preview',
            'gemini-2.5-pro',
            'gemini-2.5-flash',
            'gemini-2.5-flash-lite',
        ],
    },
}
if openrouter_key:
    base_urls.append('https://openrouter.ai/api/v1')
    keys.append(openrouter_key)
    # Conservative starter curation. Unknown IDs are silently filtered by the
    # picker — admins can adjust under Admin → Settings → Connections.
    configs['2'] = {
        'enable': True,
        'connection_type': 'external',
        'prefix_id': 'openrouter',
        'tags': [{'name': 'OpenRouter'}],
        'model_ids': [
            'anthropic/claude-opus-4.7',
            'anthropic/claude-sonnet-4.6',
            'anthropic/claude-haiku-4.5',
            'deepseek/deepseek-r1',
            'meta-llama/llama-3.3-70b-instruct',
        ],
    }

print(json.dumps({
    'ENABLE_OPENAI_API': True,
    'OPENAI_API_BASE_URLS': base_urls,
    'OPENAI_API_KEYS': keys,
    'OPENAI_API_CONFIGS': configs,
}))
PY
)

RESP=$(curl -sS -X POST "$HOST/openai/config/update" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "$BODY")

# Sanity-check the response
HAVE_OPENROUTER=""
[ -n "$OPENROUTER_KEY" ] && HAVE_OPENROUTER="1"
echo "$RESP" | HAVE_OPENROUTER="$HAVE_OPENROUTER" python3 -c "
import json, os, sys
r = json.load(sys.stdin)
cfgs = r.get('OPENAI_API_CONFIGS', {})
gemini_models = cfgs.get('1', {}).get('model_ids', [])
openrouter_models = cfgs.get('2', {}).get('model_ids', [])
have_openrouter = bool(os.environ.get('HAVE_OPENROUTER'))

if len(gemini_models) != 5:
    print(f'ERROR: expected 5 Gemini models, got {len(gemini_models)}', file=sys.stderr)
    sys.exit(2)
if have_openrouter and len(openrouter_models) < 3:
    print(f'ERROR: expected ≥3 OpenRouter models, got {len(openrouter_models)}', file=sys.stderr)
    sys.exit(2)

print('seeded gemini: ' + ', '.join(gemini_models))
if have_openrouter:
    print('seeded openrouter: ' + ', '.join(openrouter_models))
"
