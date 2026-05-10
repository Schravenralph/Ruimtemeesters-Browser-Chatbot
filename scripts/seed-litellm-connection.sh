#!/usr/bin/env bash
# Seed the OpenWebUI OpenAI-compatible connection list with the single
# LiteLLM-proxy connection (post-cutover, ADR-0010).
#
# Idempotent — safe to re-run after DB reset, container rebuild, or
# `docker compose down -v`. Reads LITELLM_MASTER_KEY from the rm-chatbot
# container's OPENAI_API_KEYS env (post-cutover that env holds a single
# value: the LiteLLM master key).
#
# Why this script still exists when the env should be enough:
# OpenWebUI's `OPENAI_API_BASE_URLS` / `OPENAI_API_KEYS` / `OPENAI_API_CONFIGS`
# are all PersistentConfig — read from env on FIRST boot, then DB wins.
# An existing prod with stale 3-provider state from the pre-cutover
# seed-gemini-connection.sh keeps showing direct OpenAI / Gemini /
# OpenRouter connections after a redeploy. This script POSTs the new
# single-LiteLLM shape to /openai/config/update to overwrite that state.
#
# Also resets DEFAULT_MODELS to the bare LiteLLM model_name (no prefix_id
# survives the cutover) — pre-cutover users had `gemini.gemini-2.5-flash-lite`
# in their per-instance config which no longer resolves. Done by reading
# the full config via /api/v1/configs/export, mutating ui.default_models,
# and writing the merged blob back via /api/v1/configs/import (the import
# handler is a full overwrite, so a partial-key POST would wipe everything
# else).
#
# Usage:
#   scripts/seed-litellm-connection.sh
#
# After seeding, verify the resulting DB state with:
#   scripts/verify-llm-connections.sh
#
# Overrides:
#   HOST=http://localhost:3333
#   APP_CONTAINER=rm-chatbot
#   DB_CONTAINER=rm-chatbot-db
#   ADMIN_USER_ID=<uuid>             (defaults to first admin row in DB)
#   DEFAULT_MODEL=gemini-2.5-flash-lite

set -euo pipefail

HOST="${HOST:-http://localhost:3333}"
APP_CONTAINER="${APP_CONTAINER:-rm-chatbot}"
DB_CONTAINER="${DB_CONTAINER:-rm-chatbot-db}"
DEFAULT_MODEL="${DEFAULT_MODEL:-gemini-2.5-flash-lite}"

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

# Extract the single LiteLLM key from the container's env. Post-cutover
# OPENAI_API_KEYS holds one value (LITELLM_MASTER_KEY) — same shape, simpler
# parsing than the old 3-provider semicolon-list.
LITELLM_KEY=$(docker exec "$APP_CONTAINER" sh -c 'printf "%s" "$OPENAI_API_KEYS"')
if [ -z "$LITELLM_KEY" ]; then
  echo "OPENAI_API_KEYS missing from container env (expected LITELLM_MASTER_KEY post-cutover)." >&2
  echo "Set LITELLM_MASTER_KEY in .env and recreate the container." >&2
  exit 1
fi

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

# --- 1. Connection ----------------------------------------------------------
# Single LiteLLM connection. Bare model_name strings — these MUST match the
# `model_name` keys in litellm/config.yaml exactly (LiteLLM uses them as the
# routing keys to dispatch to the underlying provider). No `prefix_id` so the
# dropdown shows clean names like `gemini-2.5-flash-lite` rather than
# `litellm.gemini-2.5-flash-lite`.
BODY=$(LITELLM_KEY="$LITELLM_KEY" python3 - <<'PY'
import json, os

litellm_key = os.environ['LITELLM_KEY']

base_urls = ['http://litellm:4000/v1']
keys = [litellm_key]
configs = {
    '0': {
        'enable': True,
        'connection_type': 'external',
        'tags': [{'name': 'LiteLLM'}],
        'model_ids': [
            'claude-opus-4-7',
            'claude-sonnet-4-6',
            'gpt-4.1',
            'gemini-2.5-pro',
            'gemini-2.5-flash',
            'gemini-2.5-flash-lite',
        ],
    },
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

echo "$RESP" | python3 -c "
import json, sys
r = json.load(sys.stdin)
urls = r.get('OPENAI_API_BASE_URLS', [])
cfgs = r.get('OPENAI_API_CONFIGS', {})
models = cfgs.get('0', {}).get('model_ids', [])

if urls != ['http://litellm:4000/v1']:
    print(f'ERROR: expected single litellm URL, got {urls}', file=sys.stderr)
    sys.exit(2)
if len(models) != 6:
    print(f'ERROR: expected 6 LiteLLM models, got {len(models)}', file=sys.stderr)
    sys.exit(2)

print('seeded litellm connection: ' + ', '.join(models))
"

# --- 2. DEFAULT_MODELS ------------------------------------------------------
# /api/v1/configs/import does a full save_config(form_data.config) overwrite,
# so we read-modify-write the whole blob to avoid clobbering everything else
# (banners, branding, MCP tool servers — all in this same JSON document).
EXPORT=$(curl -sS "$HOST/api/v1/configs/export" -H "Authorization: Bearer $TOKEN")

MERGED=$(EXPORT="$EXPORT" DEFAULT_MODEL="$DEFAULT_MODEL" python3 - <<'PY'
import json, os
cfg = json.loads(os.environ['EXPORT'])
cfg.setdefault('ui', {})['default_models'] = os.environ['DEFAULT_MODEL']
print(json.dumps({'config': cfg}))
PY
)

IMPORT_RESP=$(curl -sS -X POST "$HOST/api/v1/configs/import" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "$MERGED")

echo "$IMPORT_RESP" | DEFAULT_MODEL="$DEFAULT_MODEL" python3 -c "
import json, os, sys
r = json.load(sys.stdin)
got = r.get('ui', {}).get('default_models')
want = os.environ['DEFAULT_MODEL']
if got != want:
    print(f'ERROR: default_models is {got!r}, expected {want!r}', file=sys.stderr)
    sys.exit(2)
print(f'reset default_models = {got}')
"
