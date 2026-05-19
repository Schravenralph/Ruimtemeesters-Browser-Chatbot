# ADR-0018: Persona seeding via declarative YAML + Python

**Date:** 2026-05-19
**Status:** Accepted

## Context

The Browser-Chatbot has been seeding OpenWebUI state (connection config, persona Model rows, filter Functions, slash-command Prompts) through two scripts that drifted out of sync:

- `scripts/seed-litellm-connection.sh` — bash + curl + inline Python heredocs. Sets the LiteLLM OpenAI-compat connection, default models, and the three persona Model rows. Single-arg filter binding via positional CSV.
- `rm-tools/register_assistants.py` — Python + `requests`. Seeds filters (with source code, valves, activation toggle), persona Model rows (under a separate `rm-*` prefix pointing at a Gemini base model that isn't connected), and 14 slash-prompts.

Today's smoke verified the wiring concretely: the bash script's `RO-Assistent` row was the one users actually chat with, but it had no `filterIds` attached because the bash script was last run before PR #110 added `skills_context` to its arg list. The Python script's `rm-ro-assistent` row had the full `filterIds` set but pointed at an unreachable base model. So filters were installed (Python's doing) but never fired on real chats (bash's row was unfiltered).

This is the failure mode the user flagged: "two seed scripts overlap but disagree; neither owns the full picture." Bash is hard to test (no dry-run, no schema validation, fragile error handling); both scripts run as out-of-band side effects (no automation, easy to forget).

## Decision

**One Python script driven by one YAML manifest owns all OpenWebUI seeding.** The bash script is retired in full.

### Manifest: `scripts/personas.yaml`

Single source of truth, human-editable. Sections:

- `connection` — OpenAI-compat connection (LiteLLM base URL, key source, default model, disabled providers)
- `filters` — id, name, source path, description, token requirements, optional valve extras
- `personas` — id, name, description, system prompt, tool curation, filter binding, suggestion prompts, profile image
- `prompts` — slash-command catalog (command, name, content)
- `legacy_persona_ids` — IDs to delete on each run (cleanup of retired personas)

System prompts and slash-command contents use YAML block scalars (`|`) so multi-line Dutch prose stays readable without escape hell.

### Seeder: `scripts/seed_personas.py`

- Loads + validates `personas.yaml` via Pydantic models (fail loudly on schema typos)
- Mints an admin JWT in-container (matches the existing `docker exec` pattern)
- Calls OpenWebUI's admin HTTP API for everything — no direct DB writes
- Idempotent (create-or-update; safe to re-run)
- `--dry-run`: prints what would change, no API calls
- `--manifest <path>`: override default path (for tests / staging)
- Required env / flags: `MEMORY_GATEWAY_TOKEN` (warns if missing and any filter needs it), `SKILLS_GATEWAY_TOKEN` (optional today)

Ordering: filters first (so persona Model rows reference live function IDs), then personas, then prompts. Same ordering `register_assistants.py` already enforced.

### What gets deleted

- `scripts/seed-litellm-connection.sh` — fully replaced
- `rm-tools/register_assistants.py` — fully replaced (its `ASSISTANTS`, `FILTERS`, `PROMPTS` lists move into `personas.yaml`)

### What stays the same

- Filter source code remains in `rm-tools/filters/*.py`. The manifest references them by path; the script reads + uploads them. Filter logic is untouched.
- LiteLLM proxy config (`litellm/config.yaml`) is out of scope — that file is consumed by the LiteLLM container, not by OpenWebUI. Different boundary, different cadence.

## Rationale

**Why YAML over hardcoded Python:** the 3 persona system prompts are the most-edited content in this repo (multiple PRs tuning Wel/Niet framing, regels, persona scope). Pulling them into YAML lets non-engineers edit prompts without touching code, lets reviewers see prompt changes as a single readable diff, and decouples "what the personas say" from "how they get installed."

**Why Pydantic validation:** today's bug was structural drift between two scripts. Schema validation catches typos in field names (`filter_ids` vs `filterIds`) at load time, not at API-call time. Costs ~30 lines, prevents a whole class of silent breakage.

**Why retire bash entirely:** the connection-config piece of bash (`/openai/config/update`, `/api/v1/configs/export+import`) is a handful of HTTP calls Python already knows how to make. Keeping bash for "the parts Python doesn't do yet" perpetuates the two-script split this ADR exists to end.

**Why not Alembic-style versioned migrations:** the chatbot has one deploy target (Hetzner) and a handful of dev machines. State reproducibility across time is not yet a felt need. The trigger to revisit is the third independent environment, or the first time someone asks "what did persona X look like on date Y?"

**Why not run via GitHub Actions:** see `feedback_no_github_actions_ci`. Seeding runs locally (dev: `make seed` or direct invocation; prod: SSH + invoke). The script is the contract; orchestration is environment-specific.

## What this commits to concretely

1. `scripts/personas.yaml` — manifest with the current 3 personas, 5 filters, 14 prompts, 4 legacy persona IDs. Exact-content port of the current state; no semantic change.
2. `scripts/seed_personas.py` — replaces both scripts. CLI: `--url`, `--token`, `--dry-run`, `--manifest`, `--memory-token`, `--skills-token`, `--no-connection-config` (run subsets for debugging).
3. `scripts/personas_schema.py` — Pydantic models for manifest validation. One file.
4. `rm-tools/tests/test_seed_personas.py` — unit tests covering manifest parse, dry-run output, idempotency. Replaces no existing test (none existed for the bash flow).
5. Delete `scripts/seed-litellm-connection.sh` and `rm-tools/register_assistants.py`.
6. Update `scripts/README.md` (or create) with the new invocation.

## Out of scope

- **Filter logic changes** — `rm-tools/filters/*.py` is untouched. Same source code, same valves, same behavior.
- **LiteLLM config migration** — `litellm/config.yaml` keeps its own seeding path (it's read by LiteLLM directly, not by this script).
- **GUI for editing** — manifest is hand-edited.
- **Multi-env overlays** — one manifest, one set of values. If staging or per-developer overrides become a felt need, add YAML anchors or a `.local.yaml` overlay layer in a follow-up.
- **State drift detection** — `--check` mode (exit non-zero on drift) is a clean follow-up if pre-deploy verification becomes useful. Not v1.

## Consequences

**Positive:**

- One source of truth ends today's drift class.
- Persona prompts become editable without Python knowledge.
- Schema validation catches typos before API round-trips.
- Bash is gone; testing seed logic moves from "run it and check the DB" to "pytest the script."
- Dry-run shows exactly what will change before any HTTP call.

**Negative:**

- Net new dependency on PyYAML (already transitively available via OWUI deps, but now explicit at the use site).
- One more concept to onboard: contributors editing prompts need to know "edit `personas.yaml` then run the seeder" instead of "edit a `.sh` and re-run."
- The bash script's familiarity (one-shot, no Python env needed) goes away. Devs without a working Python environment will need one — usually fine, OWUI already requires Python for development.

## Triggers to revisit

- A second deploy target appears where state diverges meaningfully → consider per-env overlays or Alembic-style migrations.
- Pre-deploy drift detection becomes valuable → add `--check`.
- The 14 slash-prompts grow past ~30 and editing the manifest becomes unwieldy → split prompts into a sub-directory (`scripts/prompts/*.yaml`) keyed by command name.
- A non-engineer needs to edit prompts without git access → revisit the "GUI for editing" decision.

## Related ADRs

- **ADR-0010** — LiteLLM proxy. This ADR consolidates the OWUI-side connection seeding (replacing `seed-litellm-connection.sh`); the LiteLLM `config.yaml` itself is out of scope and continues to live where it does.
- **ADR-0011** — 3-persona canon. The manifest enforces the canon by being the place where personas are defined; adding a fourth still requires an ADR amendment per ADR-0011 §5.
- **ADR-0016** — Persona-skill bindings. Per-persona `filter_ids` and `tool_ids` in the manifest implement ADR-0016's per-persona curation model.
