// Tests for the typed postMessage RPC client (WI-014). Pure-logic — no
// real DOM, no real iframe. Substitutes a fake Window for the listener
// and a fake `contentWindow` for the parent post target.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { connectDocGenIframe, type DocGenIframeClient } from './iframeClient';

// ─── Fake window/iframe plumbing ────────────────────────────────────────

type MessageHandler = (event: MessageEvent) => void;

interface FakeWindow {
	// Loosely typed because vi.fn's narrow inferred Mock<[...], ...> type
	// fights any concrete signature we'd put here. The iframeClient
	// consumes these via the Window interface in production; tests just
	// need add/remove + a `handlers` array as the assertion seam (no
	// spy-based assertions — handlers.length tells us everything we need).
	addEventListener: (...args: unknown[]) => void;
	removeEventListener: (...args: unknown[]) => void;
	/** Synthesise an inbound message — test helper. */
	fire(event: Partial<MessageEvent>): void;
	handlers: MessageHandler[];
}

function makeFakeWindow(): FakeWindow {
	const handlers: MessageHandler[] = [];
	return {
		handlers,
		addEventListener(_name: unknown, h: unknown): void {
			handlers.push(h as MessageHandler);
		},
		removeEventListener(_name: unknown, h: unknown): void {
			const idx = handlers.indexOf(h as MessageHandler);
			if (idx >= 0) handlers.splice(idx, 1);
		},
		fire(event: Partial<MessageEvent>): void {
			for (const h of handlers) h(event as MessageEvent);
		}
	};
}

interface FakeContentWindow {
	posts: Array<{ message: unknown; origin: string }>;
	postMessage: (msg: unknown, targetOrigin: string) => void;
}

function makeFakeContentWindow(): FakeContentWindow {
	const posts: FakeContentWindow['posts'] = [];
	const cw = {
		posts,
		postMessage(msg: unknown, origin: string): void {
			posts.push({ message: msg, origin });
		}
	};
	return cw;
}

function setup(opts: { timeoutMs?: number } = {}): {
	client: DocGenIframeClient;
	win: FakeWindow;
	cw: FakeContentWindow;
	origin: string;
} {
	const win = makeFakeWindow();
	const cw = makeFakeContentWindow();
	const origin = 'https://doc-gen.datameesters.nl';
	const client = connectDocGenIframe({
		iframe: { contentWindow: cw as unknown as Window },
		iframeOrigin: origin,
		timeoutMs: opts.timeoutMs ?? 15_000,
		window: win as unknown as Window,
		warn: () => {}
	});
	// Swallow ready-promise rejection by default — tests that disconnect
	// before ready would otherwise trip the unhandled-rejection guard.
	// The dedicated "rejects ready on disconnect" test attaches its own
	// .catch BEFORE disconnect, which still fires (it's a separate
	// promise chain off the same source).
	client.ready.catch(() => {});
	return { client, win, cw, origin };
}

function lastPostedRequestId(cw: FakeContentWindow): string {
	const last = cw.posts.at(-1);
	if (!last) throw new Error('no posts');
	const msg = last.message as { requestId: string };
	return msg.requestId;
}

beforeEach(() => {
	vi.useFakeTimers();
});

afterEach(() => {
	vi.useRealTimers();
});

// ─── Tests ──────────────────────────────────────────────────────────────

describe('docGenIframeClient', () => {
	it('ready resolves on rmdg:ready from the iframe', async () => {
		const { client, win, cw, origin } = setup();
		// Before ready: the promise is pending. We can't directly assert
		// "pending" without a race; instead we fire ready and assert it resolves.
		win.fire({
			source: cw as unknown as MessageEventSource,
			origin,
			data: { type: 'rmdg:ready' }
		});
		await expect(client.ready).resolves.toBeUndefined();
	});

	it('call posts an rmdg:request and resolves on matching rmdg:response', async () => {
		const { client, win, cw, origin } = setup();
		const promise = client.proposeEdit({
			id: 'p1',
			kind: 'insert',
			target: { type: 'document-end' },
			content: { type: 'paragraph', text: 'hello' }
		});
		// One post happened — the request.
		expect(cw.posts).toHaveLength(1);
		const post = cw.posts[0].message as {
			type: string;
			method: string;
			args: unknown[];
			requestId: string;
		};
		expect(post.type).toBe('rmdg:request');
		expect(post.method).toBe('proposeEdit');
		expect(post.args).toEqual([
			{
				id: 'p1',
				kind: 'insert',
				target: { type: 'document-end' },
				content: { type: 'paragraph', text: 'hello' }
			}
		]);
		// Reply.
		win.fire({
			source: cw as unknown as MessageEventSource,
			origin,
			data: {
				type: 'rmdg:response',
				requestId: post.requestId,
				success: true,
				value: { proposalId: 'p1', status: 'pending' }
			}
		});
		await expect(promise).resolves.toEqual({ proposalId: 'p1', status: 'pending' });
	});

	it('rmdg:response with success:false rejects with named error', async () => {
		const { client, win, cw, origin } = setup();
		const promise = client.acceptProposal('p1');
		const requestId = lastPostedRequestId(cw);
		win.fire({
			source: cw as unknown as MessageEventSource,
			origin,
			data: {
				type: 'rmdg:response',
				requestId,
				success: false,
				error: { name: 'BridgeError', message: 'no such proposal' }
			}
		});
		await expect(promise).rejects.toMatchObject({
			name: 'BridgeError',
			message: 'no such proposal'
		});
	});

	it('rejects with timeout when no response arrives', async () => {
		const { client } = setup({ timeoutMs: 1000 });
		const promise = client.getState();
		// Trap unhandled-rejection noise: subscribe before advancing time.
		const settled = promise.catch((e) => e);
		await vi.advanceTimersByTimeAsync(1500);
		const err = await settled;
		expect(err).toBeInstanceOf(Error);
		expect((err as Error).message).toMatch(/timed out after 1000ms/);
	});

	it('drops responses from wrong origin', async () => {
		const { client, win, cw } = setup();
		const promise = client.getState();
		const requestId = lastPostedRequestId(cw);
		// Wrong origin: dropped silently. The pending call stays pending.
		win.fire({
			source: cw as unknown as MessageEventSource,
			origin: 'https://evil.example.com',
			data: {
				type: 'rmdg:response',
				requestId,
				success: true,
				value: { documentId: 'leaked' }
			}
		});
		// Advance to timeout to prove the response was indeed dropped.
		const settled = promise.catch((e) => e);
		await vi.advanceTimersByTimeAsync(20_000);
		const err = await settled;
		expect((err as Error).message).toMatch(/timed out/);
	});

	it('drops responses from wrong source (sibling iframe)', async () => {
		const { client, win, origin, cw } = setup();
		const promise = client.getState();
		const requestId = lastPostedRequestId(cw);
		const otherWindow = makeFakeContentWindow();
		// Spoofed: correct origin but source isn't our iframe.
		win.fire({
			source: otherWindow as unknown as MessageEventSource,
			origin,
			data: {
				type: 'rmdg:response',
				requestId,
				success: true,
				value: { documentId: 'leaked' }
			}
		});
		const settled = promise.catch((e) => e);
		await vi.advanceTimersByTimeAsync(20_000);
		const err = await settled;
		expect((err as Error).message).toMatch(/timed out/);
	});

	it('on() subscribes to events and returns an unsubscribe', () => {
		const { client, win, cw, origin } = setup();
		const handler = vi.fn();
		const off = client.on('proposal-accepted', handler);
		win.fire({
			source: cw as unknown as MessageEventSource,
			origin,
			data: {
				type: 'rmdg:event',
				name: 'proposal-accepted',
				detail: { proposalId: 'p1' }
			}
		});
		expect(handler).toHaveBeenCalledWith({ proposalId: 'p1' });
		off();
		win.fire({
			source: cw as unknown as MessageEventSource,
			origin,
			data: {
				type: 'rmdg:event',
				name: 'proposal-accepted',
				detail: { proposalId: 'p2' }
			}
		});
		expect(handler).toHaveBeenCalledTimes(1);
	});

	it('disconnect rejects pending calls and removes the listener', async () => {
		const { client, win, cw } = setup();
		const promise = client.getState();
		expect(cw.posts).toHaveLength(1);
		// Sanity: a listener is registered.
		expect(win.handlers).toHaveLength(1);
		const settled = promise.catch((e) => e);
		client.disconnect();
		const err = await settled;
		expect((err as Error).message).toMatch(/disconnected/);
		expect(win.handlers).toHaveLength(0);
	});

	it('disconnect rejects the ready promise if not yet resolved', async () => {
		const { client } = setup();
		const readyResult = client.ready.catch((e) => e);
		client.disconnect();
		const err = await readyResult;
		expect((err as Error).message).toMatch(/disconnected before ready/);
	});

	it('disconnect is idempotent', () => {
		const { client, win } = setup();
		expect(win.handlers).toHaveLength(1);
		client.disconnect();
		expect(win.handlers).toHaveLength(0);
		expect(() => client.disconnect()).not.toThrow();
		// Still 0 — second disconnect is a no-op, not a removeListener
		// on an already-empty listener set.
		expect(win.handlers).toHaveLength(0);
	});

	it('escape-hatch call() routes to arbitrary bridge methods', async () => {
		const { client, win, cw, origin } = setup();
		const promise = client.call<Blob>('download');
		const requestId = lastPostedRequestId(cw);
		const post = cw.posts[0].message as { method: string };
		expect(post.method).toBe('download');
		const fakeBlob = new Blob(['x']);
		win.fire({
			source: cw as unknown as MessageEventSource,
			origin,
			data: { type: 'rmdg:response', requestId, success: true, value: fakeBlob }
		});
		await expect(promise).resolves.toBe(fakeBlob);
	});
});
