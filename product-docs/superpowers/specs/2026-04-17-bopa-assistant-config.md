# Spec — OpenWebUI BOPA Assistant config

**Date:** 2026-04-17
**Status:** Approved (proactive-brainstorm cycle, single item)
**Repo:** `Ruimtemeesters-Browser-Chatbot`
**Depends on:** Ruimtemeesters-MCP-Servers PR #4 (`@rm-mcp/memory`) + PR #5 (gateway route) — merged.

## 1. Goal

Add a **BOPA Adviseur** assistant to this OpenWebUI fork, wired to the now-merged `@rm-mcp/memory` MCP + the existing `@rm-mcp/databank` + `@rm-mcp/geoportaal`. Ship the Dutch BOPA workflow as its system prompt, plus discoverability via 3 suggestion prompts and 3 slash prompts.

End-to-end unlock: an advisor logs into `chat.datameesters.nl`, picks **BOPA Adviseur**, types an address or resumes a session, and the agent uses memory for session state + databank for policy docs + geoportaal for spatial checks.

## 2. Non-goals (deferred)

- Registering the MCP external-tool-servers programmatically (OpenWebUI's admin API is undocumented; admin UI setup documented instead)
- Phase 5/6 BOPA tools — blocked on follow-up PR to memory package
- Geoportaal as remote MCP — geoportaal is already registered as an MCP server in the monorepo, this spec assumes it remains reachable

## 3. Changes

### A. `rm-tools/register_assistants.py`

Add one new entry to the `ASSISTANTS` list:

```python
{
    "id": "rm-bopa-adviseur",
    "name": "BOPA Adviseur",
    "base_model_id": BASE_MODEL,
    "meta": {
        "profile_image_url": "/brand-assets/icon-blue.png",
        "description": "Begeleidt adviseurs door het BOPA-evaluatieproces. Beheert sessies, zoekt beleidsdocumenten, controleert ruimtelijke regels, en bouwt de onderbouwing op. Zes fasen: haalbaarheid → strijdigheid → beleid → omgevingsaspecten → onderbouwing → toetsing.",
        "suggestion_prompts": [
            {"content": "Is een BOPA mogelijk op Linkensweg 64 in Oss voor een appartementengebouw van 20m?", "title": ["BOPA haalbaarheid", "Linkensweg 64 Oss"]},
            {"content": "Open mijn lopende BOPA sessie voor project 1042", "title": ["Sessie hervatten", "project 1042"]},
            {"content": "Doorloop de strijdigheidsanalyse voor mijn huidige BOPA sessie", "title": ["Strijdigheidsanalyse", "fase 2"]},
        ],
        "toolIds": ["server:mcp:rm-memory", "server:mcp:rm-databank", "server:mcp:rm-geoportaal"],
    },
    "params": {
        "system": "<COPY FROM packages/memory/skills/bopa.md in Ruimtemeesters-MCP-Servers>"
    },
}
```

Also update `rm-assistent` (general assistant) `toolIds` to include `"server:mcp:rm-memory"` so the general surface can read session state too.

Do NOT add memory to `rm-beleidsadviseur` (ad-hoc research, not workflow).

### B. `rm-tools/register_assistants.py` — `PROMPTS` array

Add 3 new slash prompts:

```python
{
    "command": "bopa-haalbaarheid",
    "name": "BOPA Haalbaarheid",
    "content": "Beoordeel de haalbaarheid van een BOPA op {{adres}} voor {{plan_omschrijving}}. Begin met geocoden, dan `activities_at_point`, `check_bouwvlak_hoogte`, en `check_bkl_8_0b`. Sla het resultaat op in een nieuwe BOPA sessie via `create_bopa_session` en `update_bopa_session(phase=1, ...)`.",
},
{
    "command": "bopa-strijdigheid",
    "name": "BOPA Strijdigheid",
    "content": "Voer de strijdigheidsanalyse uit voor BOPA sessie {{session_id}}. Roep `ruimtelijke_toets` en `evaluate_rules` aan, en schrijf het resultaat met `update_bopa_session(phase=2, ...)`. Zorg dat Fase 1 eerst is voltooid.",
},
{
    "command": "bopa-beleid",
    "name": "BOPA Beleidstoets",
    "content": "Doe een beleidstoets per bestuurslaag voor BOPA sessie {{session_id}}. Rijk: BKL artikelen + NOVI. Provincie: verordening + omgevingsvisie. Gemeente: omgevingsvisie + sectorbeleid. Gebruik `search_policy` per laag en sla op met `update_bopa_session(phase=3, ...)`.",
},
```

### C. `product-docs/25-assistants/bopa-adviseur.md`

New one-page description following the pattern of the 5 sibling files. Lists the assistant's tools, system prompt, and sample queries.

### D. `rm-tools/ADMIN_SETUP.md` (NEW)

Documentation for the admin-UI steps to register the 9 MCP servers as OpenWebUI External Tools. One-time setup per environment (staging / prod). Lists:

- `rm-memory` → `https://mcp.datameesters.nl/memory/mcp`
- `rm-databank` → `https://mcp.datameesters.nl/databank/mcp`
- `rm-geoportaal` → `https://mcp.datameesters.nl/geoportaal/mcp`
- ... the other 6

For each: Type = MCP (Streamable HTTP), Auth = Bearer, Key = (user's own Clerk-issued token for that user's scope, OR a service-account token).

### E. `.claude/skills/bopa/SKILL.md` (NEW)

Pointer file for Claude Code users: the same workflow is available via Claude Code by adding the MCP servers to `~/.claude/.mcp.json`. Copies the content of the canonical skill file (with a note that the source of truth is `Ruimtemeesters-MCP-Servers/packages/memory/skills/bopa.md`).

## 4. System prompt

Lifted verbatim from `Ruimtemeesters-MCP-Servers/packages/memory/skills/bopa.md`. Content structured around:
- Session management protocol (`list_bopa_sessions` first, then create or get)
- Phase dependency graph (computed `dependencies_met` from `get_bopa_session`)
- Per-phase tool sequence + which MCP server owns each tool
- Behavioral rules: Dutch, cite sources, don't force sequence, escalate to human on missing data

## 5. Success criteria

| Criterion | Threshold | How measured |
|---|---|---|
| `rm-bopa-adviseur` appears in OpenWebUI model list after registrar run | exists | API: `GET /api/v1/models` |
| All 3 tool servers (`rm-memory`, `rm-databank`, `rm-geoportaal`) attached to the assistant | yes | API: `GET /api/v1/models/rm-bopa-adviseur` |
| 3 BOPA suggestion prompts visible on the assistant card | yes | manual UI check |
| 3 slash prompts (`/bopa-haalbaarheid`, `/bopa-strijdigheid`, `/bopa-beleid`) registered | yes | API: `GET /api/v1/prompts` |
| `rm-assistent` general assistant includes `rm-memory` in toolIds | yes | diff inspection + API check |
| `product-docs/25-assistants/bopa-adviseur.md` exists and mirrors the system prompt | yes | file exists + lint |
| `ADMIN_SETUP.md` lists 9 MCP servers with URLs + auth type | yes | file exists, grep for each server |
| Registrar run is idempotent (running twice → second run reports "Updated" not errors) | pass | `python register_assistants.py ... && python register_assistants.py ...` |
| Registrar runs against a fresh OpenWebUI instance | pass | staging smoke |
| End-to-end: "Is BOPA mogelijk op Linkensweg 64 Oss?" in BOPA assistant → agent makes an MCP tool call to memory | manual smoke | staging chat |

## 6. Validation

Since the registrar is a one-shot imperative script with no local test harness, validation is manual-driven:

1. **Lint check:** `python -m py_compile rm-tools/register_assistants.py` — no syntax errors.
2. **Dry-run inspection:** add a `--dry-run` flag to the registrar that prints the payload JSON without calling the API. Run it; verify the BOPA assistant payload is well-formed.
3. **Staging integration:**
   - Deploy host rebuilds `mcp-memory` container (after MCP-Servers PRs #4+#5 merge — already done)
   - Admin runs `register_assistants.py --url https://chat.datameesters.nl --token <admin-jwt>`
   - Admin registers the 3 new external tool servers per `ADMIN_SETUP.md`
   - Smoke: pick BOPA Adviseur in UI, type "Is BOPA mogelijk op Linkensweg 64 Oss voor een appartementengebouw van 20m?", expect the agent to call `create_bopa_session` via the memory MCP and return a session_id.
4. **SQL check after smoke:** `SELECT count(*) FROM memory.bopa_sessions WHERE created_by LIKE 'gateway:%';` should be ≥ 1.

## 7. Rollout

1. Merge PR on main.
2. Admin on staging: run the registrar + add external tool servers via UI per `ADMIN_SETUP.md`.
3. Smoke test (step 6.3 above). If pass → promote to prod.
4. On prod: same sequence.

## 8. Effort

- Registrar edit (1 assistant + 3 prompts): 30 min
- `product-docs/25-assistants/bopa-adviseur.md`: 30 min
- `ADMIN_SETUP.md`: 30 min
- `.claude/skills/bopa/SKILL.md`: 15 min
- `--dry-run` flag on registrar: 30 min
- Spec + PR description: 30 min
- **Total: ~3 hours**

## 9. Out of scope, follow-ups

1. **Programmatic External Tools registration** — needs reverse-engineering OpenWebUI's admin API. Separate slice.
2. **`/bopa-omgevingsaspecten`, `/bopa-onderbouwing`, `/bopa-toetsing`** slash prompts — ship when those MCP tools land.
3. **OpenWebUI inlet filter** for auto-injecting active BOPA session summary — ADR-024 §"OpenWebUI Inlet Filter (Enhancement, Not Required)".
4. **Geoportaal as streamable-HTTP remote MCP** — currently it's listed as `mcp-geoportaal` on the monorepo gateway; needs verification it exposes Streamable HTTP, not stdio-only.
