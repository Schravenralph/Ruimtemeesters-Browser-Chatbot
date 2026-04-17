# Port 5176 Conflict — Workspace vs Sales Viewer Frontend

**Date:** 2026-04-03
**Severity:** medium
**Service:** Riens-Sales-Viewer (Frontend), Ruimtemeesters-Workspace
**Phase found:** 1

## Description

Both the Ruimtemeesters-Workspace dev server (Vite) and the Sales Viewer frontend (Docker/Nginx) bind to host port 5176. When both are running, the second one to start fails.

## Repro steps

1. Start Workspace: `cd Ruimtemeesters-Workspace && pnpm dev` (binds 5176)
2. Start Sales Viewer frontend: `docker compose up -d frontend` (tries to bind 5176, fails)

## Expected

Both services can run simultaneously.

## Actual

```
Error: failed to bind host port 0.0.0.0:5176/tcp: address already in use
```

## Notes

Fix: remap one of them. Workspace could use 5177, or the Sales Viewer frontend could use a different port. The Sales Viewer frontend port is configurable via `FRONTEND_PORT` or similar in docker-compose.yml.

Non-critical because the Sales Viewer API (port 3001) is what the MCP server needs — the frontend is for direct browser access only.

---

## Resolution

**Status:** RESOLVED on 2026-04-17.

Authoritative fix lives in **[Platform ADR-0003 — Port Allocation](https://github.com/Schravenralph/Ruimtemeesters-Platform/blob/main/adr/ADR-0003-port-allocation.md)**. First-claim rule:

- Riens-Sales-Viewer claimed `5176` first (commit `cdd8797`, 2025-10-07) → keeps it.
- Ruimtemeesters-Workspace claimed later (March 2026) → moves to `5178` (next free slot in the 5176–5179 frontend band).

**Commits:**
- `Ruimtemeesters-Platform@0c543da` — Platform ADR-0003 added
- `Ruimtemeesters-Workspace@4697695` — `VITE_PORT=5176` → `5178`

**Verification:** start both simultaneously — `cd Ruimtemeesters-Workspace && pnpm dev` then `cd Riens-Sales-Viewer && docker compose -f docker-compose.dev.yml up -d frontend`. Both should bind without conflict.

**Register going forward:** Platform ADR-0003 carries the authoritative port table across the fleet; any future port add/move must update it in the same PR.
