# BOPA Session Context — Inlet Filter

**Function ID:** `bopa_session_context`
**Type:** OpenWebUI inlet filter
**Source:** [`rm-tools/filters/bopa_session_context.py`](../../rm-tools/filters/bopa_session_context.py)
**Spec:** [`docs/superpowers/specs/forge-2026-05-01-001-bopa-inlet-filter.md`](../../docs/superpowers/specs/forge-2026-05-01-001-bopa-inlet-filter.md)

## What it does

Before the LLM call on every chat with `rm-assistent`, this filter checks
whether the signed-in user has an active BOPA evaluation in progress and,
if so, appends a short summary block to the system prompt. The advisor
opens a fresh chat and the assistant already knows which project, gemeente,
and phase they were working on — no `/bopa-status` step required.

## When it injects

All of the following must be true:

- The chat is targeted at `rm-assistent` (configurable via the
  `target_models` Valve — comma-separated list).
- The signed-in user has at least one row in `memory.bopa_sessions` with
  `status = 'active'` AND `owner_user_id = <their user id>`.
- The user has not opted out via `UserValves.enabled = False`.
- The admin has not flipped the master kill switch (`Valves.enabled = False`).
- The rm-memory MCP server replied within 800ms (configurable via
  `Valves.timeout_ms`).

If any of those fail, the filter is a no-op — the request body passes
through unchanged and the chat proceeds normally.

## What gets injected

When multiple active sessions exist for the user, the filter picks the
most-recently-updated one. The block looks like this in Dutch (matches the
assistant's response language per system prompt richtlijnen):

```
---
ACTIEVE BOPA-SESSIE (automatisch ingeladen)
Sessie: 11111111-... (project 42 — gemeente GM0363)
Status: fase 2/6 actief; afgeronde fasen: 1
Volgende stap: fase 2 (Strijdigheid) — gebruik `/bopa-strijdigheid` of `/bopa-status` voor het overzicht.
Andere actieve sessies: 1 — gebruik `/bopa-status` om te schakelen.
```

The "next step" line uses the same dependencies-met logic the rm-memory
`get_bopa_session` tool exposes — Phase 2 and 3 unlock once Phase 1 is
done; Phase 4 and 5 unlock once 1+2+3 are done; Phase 6 unlocks once
1–5 are done. For Phase 4–6, the slash commands aren't shipped yet
(MCP tools blocked in `Ruimtemeesters-MCP-Servers/packages/memory`),
so the filter surfaces a "MCP-tool nog niet beschikbaar" hint instead
of a fake command.

## How it relates to `/bopa-status`

| Trigger | Mechanism |
|---------|-----------|
| Every chat with `rm-assistent` | This filter (automatic, silent) |
| Explicit query for full overview | `/bopa-status` slash prompt (calls `list_bopa_sessions` via the agent) |

The filter pre-loads context so the agent doesn't need to call
`list_bopa_sessions` on every turn. `/bopa-status` is still useful when
the advisor wants the full multi-session table (the filter only injects
the most-recent one).

## How it talks to rm-memory

Direct JSON-RPC over HTTP POST to `${mcp_url}` (default
`http://rm-mcp-memory:3200/mcp` — the compose-internal hostname). Auth
header `Authorization: Bearer ${mcp_token}` matching `MEMORY_GATEWAY_TOKEN`
in `docker-compose.rm.yaml`. Single tool call: `list_bopa_sessions` with
empty arguments. Client-side filter on `owner_user_id == __user__.id`
because BOPA sessions are project-scoped on read per
[memory-scoping-model](../../docs/superpowers/specs/) §9 — the MCP returns
all sessions, the filter narrows to the caller's.

A 30-second per-user in-memory cache (configurable via
`Valves.cache_ttl_s`) prevents one chat with three rapid turns from
hammering the MCP three times.

## Configuration

### Admin Valves (set per-deployment, not per-user)

| Valve | Default | Purpose |
|-------|---------|---------|
| `priority` | `10` | Filter execution order (lower = earlier) |
| `mcp_url` | `http://rm-mcp-memory:3200/mcp` | rm-memory JSON-RPC endpoint |
| `mcp_token` | `""` | Bearer token (matches `MEMORY_GATEWAY_TOKEN`) |
| `timeout_ms` | `800` | RPC timeout — no-op on miss |
| `cache_ttl_s` | `30` | Per-user cache window |
| `target_models` | `rm-assistent` | Comma-separated models to gate on |
| `enabled` | `true` | Master kill switch |

### Per-user UserValves

| Valve | Default | Purpose |
|-------|---------|---------|
| `enabled` | `true` | Per-user opt-out (settings → personalization → filters) |

A user who flips `enabled = false` saves one MCP RPC per chat turn and
keeps their BOPA state out of the system prompt — useful for screen-share
sessions where unrelated project context shouldn't leak.

## Failure modes

| Failure | Behavior |
|---------|----------|
| MCP timeout / 5xx / connection refused | Log warning; return body unchanged. Chat works. |
| Empty user (anonymous) | No injection. |
| `__user__` missing entirely | No injection (defensive). |
| Malformed MCP response | Log warning; no injection. |
| User has zero active sessions | No injection. |
| Different model selected (e.g. `rm-demografie-analist`) | No injection — and no MCP call (gated before RPC). |

The filter wraps its inlet handler in a top-level try/except — any
unexpected error is logged and the body is returned unchanged. **The chat
must never break because BOPA priming failed.**

## Installation

```bash
python rm-tools/register_assistants.py --url http://localhost:3333 --token <admin-jwt>
```

The registrar registers the filter via `/api/v1/functions/create`
(falling back to `/id/<id>/update` if it already exists), then ensures
`is_active = true` via the toggle endpoint. After install, the filter
shows up in **Admin → Functions** with name "BOPA Session Context".

To verify attachment: open `rm-assistent` in **Admin → Models**, look for
`bopa_session_context` in the filter list. To verify injection: open a
fresh chat with `rm-assistent`, send any message, and inspect the OpenAI
request body in OpenWebUI's request log for the `ACTIEVE BOPA-SESSIE`
block.

## Disabling

- **Per user**: settings → filters → BOPA Session Context → toggle off.
- **Per deployment**: Admin → Functions → bopa_session_context → toggle
  off, OR set `Valves.enabled = false` for runtime override without
  changing active state.
- **Per assistant**: remove `bopa_session_context` from the assistant's
  `meta.filterIds` in `rm-tools/register_assistants.py` and re-run the
  registrar.

## Tests

```bash
.venv/bin/pytest rm-tools/tests/test_bopa_inlet_filter.py -v
```

18 unit tests cover: phase-dependency math, owner-filter selection,
most-recent-active selection, MCP failure paths (timeout, 5xx),
UserValves opt-out, master kill switch, target-model gating, caching,
empty-user defensive path, and message-list shapes (with/without an
existing system message). MCP transport is mocked at `requests.post`.
