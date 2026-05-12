# Forge Spec: product-docs/25-assistants/ persona canon cleanup

**Cycle:** 1 | **Clock:** 0h elapsed | **Size:** small

## What

Reduce `product-docs/25-assistants/` from 5 stale persona docs (beleidsadviseur, demografie-analist, ruimtelijk-adviseur, ruimtemeesters-assistent, sales-adviseur) to 3 canon docs (ro-assistent, juridisch-assistent, commercieel-assistent). Cleanup item explicitly called out in ADR-0016 §Consequences and Platform ADR-0011 cleanup list.

## Why

Persona-canon coherence: every other surface (LiteLLM model_list, docker-compose DEFAULT_MODELS, seed-litellm-connection.sh seed_persona calls, ADR-0016 skill catalog) already names the three canon personas. Only the docs directory still references the 5-persona pre-canon layout — readers and future contributors land on wrong personas.

## Success criteria

1. Five stale files removed: beleidsadviseur.md, demografie-analist.md, ruimtelijk-adviseur.md, ruimtemeesters-assistent.md, sales-adviseur.md
2. Three canon files present: ro-assistent.md, juridisch-assistent.md, commercieel-assistent.md
3. Each canon doc matches the seed script (display name, description, system prompt verbatim) and ADR-0016 tool curation
4. No broken internal links into `25-assistants/` from elsewhere in product-docs

## Approach

- Single source of truth for content: `scripts/seed-litellm-connection.sh` (display name, persona description, system prompt) + ADR-0016 §"Per-persona tool curation" table (curated MCP tools per persona)
- Each canon doc carries: model routing key (hyphenated, from litellm config), display name, system prompt block (Nederlands, verbatim), curated tools list, suggested prompts
- Delete the 5 stale files in same commit

## Not doing

- Touching seed-litellm-connection.sh, litellm config, or compose — those are already canon
- Refactoring/refining the system prompts themselves — verbatim copy from seed script
- Updating historical references in `superpowers/specs/` or `forge-report-2026-05-04.md` (historical record, not active surface)
- Updating `30-tools/bopa-inlet-filter.md` references unless they are actively misleading
