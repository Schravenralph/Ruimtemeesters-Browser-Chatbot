---
date: 2026-04-30
status: resolved
severity: high
reporter: user-report
related: chat https://chatbot.datameesters.nl/s/07d2a810-0730-4ab5-bd4e-85df58eda51a
---

# Attach-webpage spinner stuck on `processWeb` failure

**Resolved by:**

- PR #36 — fixed the catch-handler crash (`url` → `fileItem.url`) that masked every web-upload error.
- PR (forge cycle 3, 2026-05-04) — addressed the "Defensive (deferred)" section: inline error chip via `FileItem.svelte` + `AbortSignal.timeout(60_000)` on `processWeb`. Server-side timeout in `get_content_from_url` is still open as a follow-up.

## Reporter quote

> "Hij gaf me in het begin (na enige moeite) goed antwoord maar daarna kon
> ik geen internet link invullen (ook niet met het ''+'' knopje, dan voegde
> hij hem toe maar bleef hij alleen maar laden). Refreshen enzo had geen zin."

Translated: first answer was OK after some effort. After that, couldn't add
an internet URL — neither via paste nor the "+" attach menu. The URL got
added but the spinner stayed forever. Refresh didn't help.

## Diagnosis

`src/lib/components/chat/Chat.svelte:947-950` (function `uploadWeb`):

```js
for (const fileItem of fileItems) {
	try {
		const res = isYoutubeUrl(fileItem.url)
			? await processYoutubeVideo(localStorage.token, fileItem.url)
			: await processWeb(localStorage.token, '', fileItem.url);
		// … set fileItem.status = 'uploaded' on success
	} catch (e) {
		files = files.filter((f) => f.name !== url); // ← `url` is undeclared
		toast.error(`${e}`);
	}
}
```

The catch references `url` — a **variable that doesn't exist in this scope**.
The loop variable is `fileItem`; the function parameter is `urls` (plural).
Svelte's compiled output runs in strict mode (ES modules always are), so
the bare reference throws `ReferenceError: url is not defined`.

That ReferenceError propagates up through `await uploadWeb(data)` (called
from `onUpload` at line 960, which has no try/catch around it). The fileItem
is **never** removed from the `files` array and its `status: 'uploading'`
is **never** flipped — the spinner spins forever. Because `files` is part
of the chat's persisted state, refreshing reloads the same stuck item.

This perfectly matches the reporter's symptom.

## Underlying server-side cause (separate, masked by this bug)

I couldn't read the shared chat (`/share/{id}` requires auth — would need
prod DB access to recover). Common triggers for `processWeb` to throw 4xx:

1. **Auth-token expiry** → 401 from `/api/v1/retrieval/process/web`. Fits
   the "first OK, then stops working" pattern.
2. **Server can't fetch the URL** (Cloudflare-protected, 404, content-type
   reject) → 400 with detail.
3. **Server hangs on slow URL** — `get_content_from_url` doesn't enforce a
   timeout in `backend/open_webui/routers/retrieval.py:1820`. The frontend
   `fetch()` in `processWeb` (`src/lib/apis/retrieval/index.ts:344`) also
   has no `AbortSignal.timeout`.

The catch-handler bug masks all three identically — the user always sees
the same hung spinner, regardless of root cause.

## Provenance

- Introduced upstream in `c96549eaa7` (Tim Baek, 2025-12-21).
- Still present on `open-webui/open-webui:main` as of 2026-04-21
  (line 994 of upstream's Chat.svelte: same broken `f.name !== url`).
- Not specific to our fork — should be sent upstream after we ship locally.

## Fix plan

**Minimum viable**: change `url` → `fileItem.url`. One identifier, restores
the established remove-on-failure pattern. Toast error is already correct.

**Defensive (deferred — separate PR)**:

- Add `AbortSignal.timeout(60_000)` to the `fetch()` in `processWeb` so a
  hanging server still produces a client-side error eventually.
- Consider flipping `status: 'error'` instead of removing the item, so the
  user sees the failure inline instead of a vanishing item + a brief toast.
  (Requires UI work in the file-chip component to render the error state.)
- Server-side: enforce a fetch timeout in `get_content_from_url`.

## Tracking

| Action                                     | PR / Commit | Notes                       |
| ------------------------------------------ | ----------- | --------------------------- |
| Fix the catch-handler crash on this fork   | _(pending)_ |                             |
| Send the same fix upstream to `open-webui` | not yet     | Mirror PR after merge here. |
| Defensive timeouts (client + server)       | not yet     | Follow-up.                  |
