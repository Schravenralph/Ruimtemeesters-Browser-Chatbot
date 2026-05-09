# ADR-0010: LiteLLM proxy for provider routing and cost management

**Date:** 2026-04-17
**Last updated:** 2026-05-09
**Status:** Accepted (deferred — see "Phasing" below)

## Context

The chatbot connects directly to multiple LLM providers (Ollama, OpenAI, Anthropic, Gemini via OpenAI-compat, OpenRouter). As long as the chatbot has **one user** (Ralph), the direct-provider setup has no functional gaps — there is no per-user spend to track, no need to budget across teammates, and no fallback complexity worth engineering.

Once the chatbot grows to **multiple users** — colleagues, clients, or external collaborators sharing the same instance — the direct-provider setup loses important properties:

- No way to track per-user or per-team token spend
- No way to set budget limits per user / per assistant / per model
- No way to route between providers based on rules (e.g. fallback when one rate-limits)
- No unified view of cost across all providers

OpenWebUI supports LiteLLM as a provider natively — no code changes needed.

## Decision

**Commit to LiteLLM as the provider layer**, deployed as a proxy between OpenWebUI and the actual LLM providers, **at the moment we onboard non-solo users**. Until then, run direct-provider connections (current state) and treat the migration as a sequenced follow-up rather than blocking work.

```
OpenWebUI ──► LiteLLM Proxy ──┬──► Anthropic (Claude)
                               ├──► OpenAI (GPT-4o/4.1)
                               ├──► Gemini (Google)
                               └──► Ollama (local)
```

LiteLLM handles:

- **Provider routing:** Route requests to the correct provider based on model name
- **Per-user spend tracking:** Budget visibility without custom metering code
- **Fallback chains:** If one provider is down or rate-limited, route to another
- **Prompt caching pass-through:** Anthropic's prompt caching works through LiteLLM

## Phasing

### Phase 1 — Solo-user (now)

Single user (Ralph). Direct provider connections from OpenWebUI as wired in `docker-compose.rm.yaml`:

- `OPENAI_API_KEYS` / `OPENAI_API_BASE_URLS` for OpenAI + Gemini-via-OpenAI-compat + OpenRouter
- `ANTHROPIC_API_KEY` for Anthropic native
- `GEMINI_API_KEY` for native Gemini features (image gen)

For the **Claude provider specifically**, instead of `ANTHROPIC_API_KEY` against `api.anthropic.com`, route through an **OpenWebUI Pipe that uses the user's Claude Max subscription** (Claude Code CLI / SDK — see ADR-0012 §"Anthropic-native pipeline" for the Pipe pattern). Reasoning:

- Claude Max is a flat-rate subscription; for a heavy single-user chat workload it is materially cheaper than per-token API billing
- Single-user operation under the user's own auth is defensible — it is one human's session, not a multi-tenant resale of access
- Loses per-user spend tracking — irrelevant in the solo phase

This Pipe replaces the direct `ANTHROPIC_API_KEY` connection. OpenAI / Gemini / OpenRouter / Ollama stay direct in this phase.

### Phase 2 — Multi-user (when triggered)

Stand up the LiteLLM proxy container. Migrate **all** providers behind it, including Anthropic. The Claude Max CLI Pipe is **retired** at this point — a shared-instance multi-user setup against a personal subscription is no longer defensible (against ToS in spirit, and operationally fragile under concurrent load). Anthropic moves to standard `ANTHROPIC_API_KEY` billing through LiteLLM, with per-user spend tracked and budgets enforceable.

## Triggers to migrate to Phase 2

Any one of these is sufficient:

- A second human user is onboarded to the chatbot (colleague, client, contractor)
- An automated agent or service consumer needs LLM access through the chatbot's API
- The chatbot is exposed to embedded surfaces with their own users (e.g. ADR-0011's service-pattern UIs gain non-Ralph callers)

The first occurrence triggers an explicit migration sprint, not a gradual roll-in. Reason: running LiteLLM "for some providers" while keeping direct connections for others fragments observability and creates two code paths to maintain.

## Rationale

- OpenWebUI already supports LiteLLM as a provider — configuration change, not code change
- Per-user spend tracking becomes critical when multiple users share API costs (vs. per-seat subscriptions)
- Fallback routing improves reliability without retry logic in the chatbot
- Single place to manage API keys, rate limits, and model aliases
- Cost transparency: know exactly what each user/assistant/model costs

The deferral is justified by:

- Solo phase has no spend-tracking need (one wallet, one user)
- Claude Max CLI gives materially lower Claude cost in the solo phase
- LiteLLM container is operational overhead with no offsetting value while solo
- The migration is configuration-shaped (LiteLLM is a drop-in OpenAI-compatible endpoint), so deferring does not accumulate technical debt that compounds

## Consequences

When Phase 2 lands:

- One more container in the Docker Compose stack
- LiteLLM's PostgreSQL can share the existing chatbot DB instance or use its own
- API keys move from OpenWebUI config to LiteLLM config
- OpenWebUI sees LiteLLM as a single OpenAI-compatible endpoint — all provider-specific config lives in LiteLLM
- Adds a network hop (~1ms latency) between OpenWebUI and providers — negligible vs. LLM inference time
- Claude Max CLI Pipe code is removed; rationale captured in this ADR for future readers wondering why it ever existed

## Related

- **ADR-0012 §2** ("Anthropic-native pipeline — deferred") — the OpenWebUI Pipe pattern this ADR's Phase 1 leans on for the Claude Max CLI integration
- **ADR-0011** — service-pattern AI surfaces; if external surfaces gain their own users, that's a Phase 2 trigger
