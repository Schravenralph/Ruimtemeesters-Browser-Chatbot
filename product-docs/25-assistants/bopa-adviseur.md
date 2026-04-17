# BOPA Adviseur

**OpenWebUI model id:** `rm-bopa-adviseur`

De BOPA Adviseur begeleidt adviseurs door het **Buitenplanse Omgevingsplan­activiteit** evaluatieproces. Dit is het enige assistant-profiel dat sessie-state heeft — alle andere RM-assistants zijn stateless. Het procesmodel en de dataflow staan in ADR-024 van de Ruimtemeesters-Databank repo.

## Tools

| MCP server | Welke calls | Waar |
|---|---|---|
| `rm-memory` | `create_bopa_session`, `get_bopa_session`, `update_bopa_session`, `list_bopa_sessions` | [Ruimtemeesters-MCP-Servers/packages/memory](https://github.com/Schravenralph/Ruimtemeesters-MCP-Servers/tree/main/packages/memory) |
| `rm-databank` | `search_policy`, `get_document`, `list_municipalities`, `browse_knowledge_graph`, `get_databank_stats` | Databank remote MCP |
| `rm-geoportaal` | `activities_at_point`, `check_bouwvlak_hoogte`, `ruimtelijke_toets`, `evaluate_rules` (en meer) | Geoportaal MCP |

Geen cross-system aggregator — BOPA-tools orchestreren zelf.

## Systeem-prompt

De prompt komt één-op-één uit [`Ruimtemeesters-MCP-Servers/packages/memory/skills/bopa.md`](https://github.com/Schravenralph/Ruimtemeesters-MCP-Servers/tree/main/packages/memory/skills/bopa.md). De registrar (`rm-tools/register_assistants.py`) kopieert hem verbatim in `params.system`. Claude Code gebruikers krijgen hem via `~/.claude/skills/bopa/SKILL.md` (zie `.claude/skills/bopa/SKILL.md` in deze repo).

Als de canonieke bron verandert, herstart:

```
python rm-tools/register_assistants.py --url https://chat.datameesters.nl --token <admin-jwt>
```

## Fase-afhankelijkheden

De `memory` MCP dwingt af:
- Fase 1: geen afhankelijkheid
- Fase 2, 3, 4: vereisen Fase 1
- Fase 5: vereist Fasen 2 + 3 + 4
- Fase 6: vereist Fase 5

Bij overtreding: `update_bopa_session` retourneert een MCP `isError` met de missende fases in de message. De agent gebruikt dit om de adviseur terug te sturen naar de juiste fase.

## Suggestie-prompts (op de assistant-kaart)

1. "Is een BOPA mogelijk op Linkensweg 64 in Oss voor een appartementengebouw van 20m?"
2. "Open mijn lopende BOPA sessie voor project 1042"
3. "Doorloop de strijdigheidsanalyse voor mijn huidige BOPA sessie"

## Slash-prompts

| Commando | Beschrijving |
|---|---|
| `/bopa-haalbaarheid` | Fase 1 — locatie + BKL 8.0b check |
| `/bopa-strijdigheid` | Fase 2 — ruimtelijke toets + regel-evaluatie |
| `/bopa-beleid` | Fase 3 — beleidstoets per bestuurslaag |

Fase 4-6 slash-prompts volgen zodra die MCP-tools landen (zie memory follow-up specs).

## Nog niet gebouwd

- Upload van specialistenrapporten (`upload_research_report`)
- Sectie-generatie (`save_onderbouwing_section`)
- Eindscore (`score_onderbouwing`)
- Export naar Word/PDF (`export_onderbouwing`)
- OpenWebUI inlet filter voor auto-injectie sessie samenvatting
