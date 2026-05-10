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
#   DEFAULT_MODEL=Meester             (codename, must match litellm/config.yaml)

set -euo pipefail

HOST="${HOST:-http://localhost:3333}"
APP_CONTAINER="${APP_CONTAINER:-rm-chatbot}"
DB_CONTAINER="${DB_CONTAINER:-rm-chatbot-db}"
DEFAULT_MODEL="${DEFAULT_MODEL:-Meester}"

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
        'tags': [{'name': 'Ruimtemeesters AI'}],
        # Codenamed model surface — admin-curated, no per-user picker beyond
        # these two. Names must match `model_name` keys in litellm/config.yaml.
        # `Schets` (sketch — fast first-pass) is mapped to gemini-2.5-flash-lite;
        # `Meester` (echoes Ruimtemeester — deliberate work) is mapped to
        # claude-sonnet-4-6.
        'model_ids': ['Schets', 'Meester'],
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

# `--fail-with-body` (curl >= 7.76) makes curl exit non-zero on HTTP 4xx/5xx
# while still printing the response body to stdout — combined with `set -e`
# at the top, this aborts the script before any subsequent step (read,
# mutate, re-import) can act on a broken response. Without this, a 401 from
# an expired token would parse as valid JSON and the next /configs/import
# call would full-overwrite the saved config with garbage.
RESP=$(curl -sS --fail-with-body -X POST "$HOST/openai/config/update" \
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
if len(models) != 2:
    print(f'ERROR: expected 2 codenamed models, got {len(models)}', file=sys.stderr)
    sys.exit(2)

print('seeded litellm connection: ' + ', '.join(models))
"

# --- 2. DEFAULT_MODELS ------------------------------------------------------
# /api/v1/configs/import does a full save_config(form_data.config) overwrite,
# so we read-modify-write the whole blob to avoid clobbering everything else
# (banners, branding, MCP tool servers — all in this same JSON document).
#
# `--fail-with-body` is critical here: a 401/403 on /configs/export would
# otherwise parse as valid JSON `{"detail": "..."}`, get `ui.default_models`
# merged into it, and then /configs/import would replace the real config
# with that two-key blob. Bugbot caught this on f0d07a8.
EXPORT=$(curl -sS --fail-with-body "$HOST/api/v1/configs/export" \
  -H "Authorization: Bearer $TOKEN")

MERGED=$(EXPORT="$EXPORT" DEFAULT_MODEL="$DEFAULT_MODEL" python3 - <<'PY'
import json, os, sys
cfg = json.loads(os.environ['EXPORT'])
# Defense in depth: even after --fail-with-body, refuse to mutate a response
# that doesn't look like an OWUI config. /configs/export should always
# return a dict with `openai` (set up earlier in this script) and `ui`
# (default_models lives here). If neither is present, something's wrong.
if not isinstance(cfg, dict) or ('openai' not in cfg and 'ui' not in cfg):
    print(f'ERROR: /configs/export returned an unexpected shape (top-level keys: {list(cfg)[:10] if isinstance(cfg, dict) else type(cfg).__name__}); refusing to import.', file=sys.stderr)
    sys.exit(2)
cfg.setdefault('ui', {})['default_models'] = os.environ['DEFAULT_MODEL']
# Lock the model surface to the codenamed LiteLLM connection only.
# Without these, an existing DB has `ollama.enable=true` (auto-discovers
# any local Ollama models like qwen) and `evaluation.arena.enable=true`
# (admin A/B-comparison models), both of which would surface in the user
# picker alongside Schets/Meester.
cfg.setdefault('ollama', {})['enable'] = False
cfg.setdefault('evaluation', {}).setdefault('arena', {})['enable'] = False
print(json.dumps({'config': cfg}))
PY
)

IMPORT_RESP=$(curl -sS --fail-with-body -X POST "$HOST/api/v1/configs/import" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "$MERGED")

echo "$IMPORT_RESP" | DEFAULT_MODEL="$DEFAULT_MODEL" python3 -c "
import json, os, sys
r = json.load(sys.stdin)
got = r.get('ui', {}).get('default_models')
want = os.environ['DEFAULT_MODEL']
ollama_enabled = r.get('ollama', {}).get('enable')
arena_enabled = r.get('evaluation', {}).get('arena', {}).get('enable')
ok = True
if got != want:
    print(f'ERROR: default_models is {got!r}, expected {want!r}', file=sys.stderr); ok = False
if ollama_enabled is not False:
    print(f'ERROR: ollama.enable is {ollama_enabled!r}, expected False', file=sys.stderr); ok = False
if arena_enabled is not False:
    print(f'ERROR: evaluation.arena.enable is {arena_enabled!r}, expected False', file=sys.stderr); ok = False
if not ok:
    sys.exit(2)
print(f'reset default_models = {got}')
print('disabled ollama.enable, evaluation.arena.enable')
"
