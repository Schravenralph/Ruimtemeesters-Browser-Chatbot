# ADR-0010: LiteLLM proxy for provider routing and cost management

**Date:** 2026-04-17
**Last updated:** 2026-05-09
**Status:** Accepted

## Context

The chatbot connects directly to multiple LLM providers (Ollama, OpenAI, Anthropic, Gemini via OpenAI-compat, OpenRouter). The direct setup works for a single user but loses important properties as soon as more humans or surfaces consume the chatbot:

- No way to track per-user or per-team token spend
- No way to set budget limits per user / per assistant / per model
- No way to route between providers based on rules (e.g. fallback when one rate-limits)
- No unified view of cost across all providers

OpenWebUI supports LiteLLM as a provider natively — it appears as a single OpenAI-compatible endpoint, so swapping in LiteLLM is configuration-shaped rather than code-shaped on the chatbot side.

A 2026-05-09 conversation considered an interim "Claude Max via Code SDK Pipe" path to keep solo-phase Claude costs flat. That path was evaluated and rejected as more engineering effort (CLI auth, streaming, fragility against Claude Code SDK changes) than its near-term cost savings justify, when LiteLLM stand-up is itself a small additive PR.

## Decision

**Adopt LiteLLM as the provider layer.** Run it as an additional Docker Compose service that sits between OpenWebUI and the actual LLM providers:

```
OpenWebUI ──► LiteLLM Proxy ──┬──► Anthropic (Claude)
                               ├──► OpenAI (GPT-4o/4.1)
                               ├──► Gemini (Google AI Studio)
                               ├──► OpenRouter
                               └──► Ollama (local)
```

LiteLLM handles:

- **Provider routing:** Route requests to the correct provider based on model name
- **Per-user spend tracking:** Budget visibility without custom metering code
- **Fallback chains:** If one provider is down or rate-limited, route to another
- **Prompt caching pass-through:** Anthropic's prompt caching works through LiteLLM
- **Single API key surface:** One master key for OpenWebUI to call; provider keys live in LiteLLM only

## Build order

Two-PR rollout to keep blast radius small:

1. **Stand-up (this PR-pair commit).** Add the `litellm` service to `docker-compose.rm.yaml` with a `litellm/config.yaml` listing every provider/model. Spend tracking enabled against the existing `chatbot-db` postgres instance (LiteLLM auto-creates its own tables). LiteLLM listens on `rm-internal` only — never exposed to the host or public internet, per the database-publication security invariant. OpenWebUI still uses its direct provider keys at this point; LiteLLM runs in parallel for validation.

2. **Cutover (follow-up PR).** Replace OpenWebUI's `OPENAI_API_KEYS` / `OPENAI_API_BASE_URLS` and `ANTHROPIC_API_KEY` with a single connection pointing at LiteLLM (`http://litellm:4000/v1`, `LITELLM_MASTER_KEY`). Verify chat works against each provider through the proxy. Drop the now-unused direct env vars.

If anything goes wrong in step 2, revert — step 1's LiteLLM keeps running but is unused, no chat impact.

## Rationale

- OpenWebUI already supports LiteLLM as a provider — configuration change, not code change
- Per-user spend tracking becomes critical when multiple users share API costs (vs. per-seat subscriptions)
- Fallback routing improves reliability without retry logic in the chatbot
- Single place to manage API keys, rate limits, and model aliases
- Cost transparency: know exactly what each user/assistant/model costs

## Consequences

- Two more containers in the Docker Compose stack: `rm-litellm` (the proxy) and `rm-litellm-db-init` (one-shot, exits after `CREATE DATABASE litellm`)
- LiteLLM uses a **dedicated `litellm` logical database** within the shared `chatbot-db` postgres instance — its `LiteLLM_*` tables live there and never touch OpenWebUI's database. See "Postmortem" below for why this isolation is non-negotiable.
- API keys move from OpenWebUI config to LiteLLM config after step 2 of the build order
- OpenWebUI sees LiteLLM as a single OpenAI-compatible endpoint — all provider-specific config lives in LiteLLM
- Adds a network hop (~1ms latency) between OpenWebUI and providers — negligible vs. LLM inference time
- LiteLLM is on `rm-internal` only; no host port, no public surface — same security posture as the postgres DB

## Postmortem — 2026-05-09 OWUI table wipe

A first attempt at build-order step 1 (commit `534e78c` on this PR) pointed LiteLLM's `DATABASE_URL` at the **same** database OpenWebUI uses (`rmchatbot`). On first boot, LiteLLM's prisma migration step generated a "migration diff" between the live schema and its `schema.prisma` and applied it — which **dropped every OpenWebUI table** as "extra". The chatbot at `chatbot.datameesters.nl` began returning HTTP 500 on every request because `relation "user" does not exist`.

Confirmed in LiteLLM's own startup logs:

```
INFO - Generating migration diff between DB and schema.prisma...
INFO - Migration diff created at /tmp/litellm_migration_diff_*/migration.sql
INFO - prisma db execute stdout: Script executed successfully.
INFO - ✅ Migration diff applied successfully
```

The diff was the destructive op.

**Recovery.** `DROP SCHEMA public CASCADE; CREATE SCHEMA public;` followed by `docker restart rm-chatbot`, which let alembic recreate the OWUI schema fresh. No data was lost in practice — the chatbot had no important data on prod yet — but it would have been if there had been.

**Root cause.** LiteLLM is **prisma-managed**. Prisma treats its `schema.prisma` as the source of truth for the database it points at. Sharing such a database with another app is incompatible with the prisma migration model.

**Fix (this PR).** LiteLLM gets a **dedicated `litellm` logical database** within the shared chatbot-db postgres instance:

- `litellm/config.yaml`'s `database_url` and the compose `DATABASE_URL` env var both end in `/litellm` (not `/${POSTGRES_DB}`).
- A new compose service `litellm-db-init` runs `CREATE DATABASE litellm OWNER ${POSTGRES_USER}` idempotently before LiteLLM starts. LiteLLM's `depends_on` requires `litellm-db-init` to exit 0 first.
- Comments in both files call this out explicitly so a future operator does not accidentally repoint the URL at the OWUI database.

**Lessons captured.**

- Never share a prisma-managed (or any ORM-managed-as-source-of-truth) database with another application. Logical isolation costs a single `CREATE DATABASE`; the alternative is a full rebuild.
- Back up the chatbot-db volume independently from the host pg_dumpall pipeline. The 3am pg_dumpall does not reach dockerized postgres instances. (Tracked separately as a follow-up backup-cron PR.)
- `start_period` on healthchecks is mandatory for first-boot prisma migration sweeps (~5 minutes for 116 migrations).

## Related

- **ADR-0012 §2** ("Anthropic-native pipeline — deferred") — still deferred. LiteLLM passes Anthropic-native features (caching, headers) through, so this ADR doesn't change ADR-0012 §2's calculus.
- **ADR-0011** — service-pattern AI surfaces; service-pattern callers will go through OpenWebUI which now goes through LiteLLM, so spend-tracking applies to those surfaces transparently when they ship.
