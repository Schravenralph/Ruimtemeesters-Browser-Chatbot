// Tests for dispatchDocGenToolCall (WI-014). Pure dispatch — fakes the
// iframe client and asserts on the result shape OWUI's execute:tool
// callback expects.

import { describe, expect, it, vi } from 'vitest';

import { dispatchDocGenToolCall } from './executeToolDispatch';
import type { DocGenIframeClient } from './iframeClient';

function makeFakeClient(overrides: Partial<DocGenIframeClient> = {}): DocGenIframeClient {
	return {
		ready: Promise.resolve(),
		proposeEdit: vi.fn(async () => ({
			proposalId: 'p1',
			status: 'pending' as const
		})),
		acceptProposal: vi.fn(async () => ({ applied: true as const })),
		rejectProposal: vi.fn(async () => ({ applied: true as const })),
		getState: vi.fn(async () => ({
			documentId: 'doc-1',
			content: { type: 'doc' },
			title: 'Mijn document',
			updatedAt: '2026-05-23T12:00:00Z'
		})),
		call: vi.fn(async () => undefined as unknown) as DocGenIframeClient['call'],
		on: vi.fn(() => () => {}),
		disconnect: vi.fn(),
		...overrides
	};
}

describe('dispatchDocGenToolCall', () => {
	it('returns doc_panel_closed error when client is null', async () => {
		const result = await dispatchDocGenToolCall({
			client: null,
			toolName: 'docgen_proposeEdit',
			params: {}
		});
		expect(result).toMatchObject({ error: expect.stringMatching(/paneel.*niet open/i) });
	});

	it('returns unknown-tool error when toolName is not a docgen_ name', async () => {
		const result = await dispatchDocGenToolCall({
			client: makeFakeClient(),
			toolName: 'something_else',
			params: {}
		});
		expect(result).toMatchObject({ error: expect.stringMatching(/Onbekend gereedschap/) });
	});

	it('proposeEdit dispatches to client.proposeEdit and returns the result', async () => {
		const client = makeFakeClient();
		const proposal = {
			id: 'p1',
			kind: 'insert',
			target: { type: 'document-end' },
			content: { type: 'paragraph', text: 'hello' }
		};
		const result = await dispatchDocGenToolCall({
			client,
			toolName: 'docgen_proposeEdit',
			params: proposal as unknown as Record<string, unknown>
		});
		expect(client.proposeEdit).toHaveBeenCalledWith(proposal);
		expect(result).toEqual({ proposalId: 'p1', status: 'pending' });
	});

	it('proposeEdit unwraps params.proposal when nested', async () => {
		const client = makeFakeClient();
		const proposal = {
			id: 'p2',
			kind: 'insert' as const,
			target: { type: 'document-end' as const },
			content: { type: 'paragraph' as const, text: 'wrapped' }
		};
		await dispatchDocGenToolCall({
			client,
			toolName: 'docgen_proposeEdit',
			params: { proposal }
		});
		expect(client.proposeEdit).toHaveBeenCalledWith(proposal);
	});

	it('proposeEdit returns clear error when proposal arg is missing', async () => {
		const client = makeFakeClient();
		// Empty params + nothing under `proposal` — dispatcher should
		// surface a usable error to the model. Note: the typeof check
		// allows `{}` through (an empty object is still an object), so
		// we pass an explicit non-object to trigger the guard.
		const result = await dispatchDocGenToolCall({
			client,
			toolName: 'docgen_proposeEdit',
			params: { proposal: null } as unknown as Record<string, unknown>
		});
		expect(result).toMatchObject({ error: expect.stringMatching(/ongeldig voorstel/i) });
		expect(client.proposeEdit).not.toHaveBeenCalled();
	});

	it('acceptProposal forwards proposalId', async () => {
		const client = makeFakeClient();
		const result = await dispatchDocGenToolCall({
			client,
			toolName: 'docgen_acceptProposal',
			params: { proposalId: 'p1' }
		});
		expect(client.acceptProposal).toHaveBeenCalledWith('p1');
		expect(result).toEqual({ applied: true });
	});

	it('acceptProposal rejects when proposalId is missing', async () => {
		const client = makeFakeClient();
		const result = await dispatchDocGenToolCall({
			client,
			toolName: 'docgen_acceptProposal',
			params: {}
		});
		expect(result).toMatchObject({ error: expect.stringMatching(/proposalId.*verplicht/) });
		expect(client.acceptProposal).not.toHaveBeenCalled();
	});

	it('getState strips Blob field from the snapshot', async () => {
		const client = makeFakeClient({
			getState: vi.fn(async () => ({
				documentId: 'doc-1',
				content: { type: 'doc' },
				title: 'Mijn',
				updatedAt: '2026-05-23T12:00:00Z',
				// Simulate the bridge returning the real DocumentSnapshot
				// (which has a Blob `docx`) — strip should drop it.
				docx: new Blob(['x'])
			})) as unknown as DocGenIframeClient['getState']
		});
		const result = await dispatchDocGenToolCall({
			client,
			toolName: 'docgen_getState',
			params: {}
		});
		expect(result).toEqual({
			documentId: 'doc-1',
			content: { type: 'doc' },
			title: 'Mijn',
			updatedAt: '2026-05-23T12:00:00Z'
		});
		expect(result).not.toHaveProperty('docx');
	});

	it('wraps client throws into an error result', async () => {
		const client = makeFakeClient({
			acceptProposal: vi.fn(async () => {
				throw new Error('no such proposal');
			})
		});
		const result = await dispatchDocGenToolCall({
			client,
			toolName: 'docgen_acceptProposal',
			params: { proposalId: 'p-missing' }
		});
		expect(result).toMatchObject({ error: expect.stringMatching(/no such proposal/) });
	});
});
