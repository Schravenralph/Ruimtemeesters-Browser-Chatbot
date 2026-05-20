# OpenWebUI Admin Setup — MCP tool servers

One-time setup per environment (staging, prod). The persona seeder
(`scripts/seed_personas.py`) creates persona Models, filters, and slash
prompts — the MCP tool servers themselves are wired via env (per memory
`project_mcp_wiring_strategy`) and the gateway, not via UI registration.

## Personas

Per ADR-0011 the chatbot ships exactly three personas: RO Assistent,
Juridisch Assistent, Commercieel Assistent. Their tool curation lives in
`scripts/personas.yaml` under each persona's `tool_ids` list. Tool IDs use
the `server:mcp:<id>` prefix that OpenWebUI expects.

## Re-seeding after changes

```bash
python3 scripts/seed_personas.py --dry-run
python3 scripts/seed_personas.py
```

The script is idempotent. Re-run any time `personas.yaml` or a filter's
source changes.

## Sanity check

After seeding, the local smoke harness verifies end-to-end wiring:

```bash
bash scripts/smoke/thematic_scan_smoke.sh
```

Expect Stage 1 + 2 + 4 PASS. Soft warnings on Stage 2/3 (skill mandatory
flag, model not calling set_active_project in one-shot) are quality nits,
not wiring failures.

See `product-docs/06-adr/0018-persona-seeding-yaml-manifest.md` for the
seeder design, and the `Ruimtemeesters-MCP-Servers` repo README for the
MCP gateway setup.
