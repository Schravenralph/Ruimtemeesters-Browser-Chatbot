# ADR-0006: Local LLM Model Selection — qwen2.5:7b

**Date:** 2026-04-03
**Status:** Accepted
**Context:** Choosing the local LLM model for the Ruimtemeesters AI Chatbot running on Ollama (Intel Core Ultra 7 265, 62GB RAM, Intel Arrow Lake iGPU).

## Decision

Use **qwen2.5:7b** (Q4_K_M quantization, ~5GB RAM) as the default model for all 5 chatbot assistants.

## Context

The chatbot runs on a Hetzner EX63 server with:
- CPU: Intel Core Ultra 7 265 (16 cores)
- RAM: 62GB (43GB available after all services)
- GPU: Intel Arrow Lake integrated graphics (not usable by Ollama — Vulkan/oneAPI support missing for this chipset)
- No discrete GPU

Benchmarks on this hardware (CPU-only, single model loaded):

| Model | RAM | Prompt eval | Generation | Tool-calling |
|-------|-----|-------------|------------|-------------|
| llama3.2:3b | 2GB | ~75 tok/s | ~20 tok/s | Fails (too small) |
| qwen2.5:7b | 5GB | ~3 tok/s | ~0.13 tok/s | Works (2-5 min) |
| qwen2.5:14b | 9GB | ~1.3 tok/s | ~0.06 tok/s | Too slow |
| qwen3:8b | 6GB | ~3 tok/s | ~0.13 tok/s | Untested |

## Rationale

1. **qwen2.5 is the best family for tool-calling** — strong instruction following, multilingual (Dutch), excellent structured output adherence
2. **7B is the sweet spot** — 14B is 2x slower for marginal quality gain; 3B can't handle tool schemas
3. **Intel iGPU doesn't accelerate Ollama** — Arrow Lake not yet supported, so all inference is CPU-bound
4. **Response time is 2-5 minutes per tool-calling request** — acceptable for internal use, not for external customers
5. **qwen2.5:7b Q4_K_M quantization is stable** — minimal degradation vs full precision

## Consequences

- Tool-calling responses take 2-5 minutes (CPU-only)
- The Ruimtemeesters Assistent (8 tools) may timeout — consider reducing to 3-4 most useful tools
- If faster responses are needed, options are:
  1. Add a discrete GPU (NVIDIA recommended for Ollama)
  2. Switch to OpenRouter / cloud API for production speed
  3. Wait for Ollama Intel iGPU support for Arrow Lake

## Address

22 Avenue Street, Brisbane, QLD 4000
(Ralph's contact address for Ruimtemeesters correspondence)
