# Ruimtemeesters AI — rm-tools

This directory holds the OpenWebUI filter source code (inlet/outlet handlers)
and unit tests for them. Tools themselves come from MCP servers (see the
`Ruimtemeesters-MCP-Servers` repo).

## Layout

- `filters/` — Python source for OpenWebUI Function rows of type=filter.
  These get uploaded to the OWUI DB by the persona seeder. Edit the `.py`
  here, re-run the seeder to push.
- `functions/` — older / experimental functions.
- `tests/` — pytest coverage for each filter.

## Persona + filter seeding

Seeding is owned by `scripts/seed_personas.py` (per ADR-0018), driven by
`scripts/personas.yaml`. To apply local changes:

```bash
python3 scripts/seed_personas.py --dry-run   # preview
python3 scripts/seed_personas.py             # live
```

See `product-docs/06-adr/0018-persona-seeding-yaml-manifest.md` for the
design.
