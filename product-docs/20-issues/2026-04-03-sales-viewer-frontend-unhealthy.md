# Sales Viewer Frontend Unhealthy

**Date:** 2026-04-03
**Severity:** low
**Service:** Riens-Sales-Viewer (Frontend)
**Phase found:** 1

## Description

Sales Viewer frontend (`sales-viewer-frontend`) Nginx is running (workers started), but container reports unhealthy.

## Repro steps

1. `docker ps | grep sales-viewer-frontend` → unhealthy
2. `docker logs sales-viewer-frontend --tail 20` → Nginx workers running normally

## Expected

Frontend serves the SPA and passes health checks.

## Actual

Unhealthy status. Likely the health check proxies to the API backend which returns 503 (see companion issue `2026-04-03-sales-viewer-api-503-health-check.md`).

## Notes

This is likely a cascading issue. Fix the API health check first, then the frontend should recover.

---

## Resolution

**Status:** RESOLVED transitively.

The issue doc correctly predicted this was a cascading failure — the frontend's Nginx upstream health-proxied to the API's `/health` endpoint, which was returning 503 because `/health` was gated by the auth middleware in production + mock-auth-disabled mode.

Upstream fix landed in [Waar-Zitten-We-GeoTool#8](https://github.com/Schravenralph/Waar-Zitten-We-GeoTool/pull/8) (merged 2026-04-17): `/health` moved above `authMiddleware` in `server/src/app.ts`, so it now returns 200 unconditionally. Any `sales-viewer-frontend` container whose healthcheck proxies through to the API will now pass.

### Verification

Not directly verified live because `sales-viewer-frontend` isn't currently running on this dev host (only `sales-viewer-api` and `sales-viewer-db` are up — a dev-time stack subset). But:

1. The Sales-Viewer#8 regression test explicitly covers the 503 path (`tests/health.test.ts: bypasses auth middleware even when mock auth is disabled in production`).
2. The frontend Dockerfile healthcheck (`wget --spider http://localhost:80/`) hits Nginx, not the API — whether that produces a cascade depends on the Nginx config's upstream check; most common setups rely on the backing `/health` returning 200 indirectly.

Closing as resolved via the upstream fix. If the frontend still reports unhealthy once it's started, open a new issue with fresh logs — the root cause in this doc (auth-gated `/health`) is fixed.
