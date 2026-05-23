// Glue between OWUI's `execute:tool` socket event and the typed
// docGenIframeClient (WI-014).
//
// OWUI's middleware routes tool calls from `direct_tool_servers` (with
// `direct: True`) to the frontend via a socket event:
//
//     { type: 'execute:tool', data: { name, params, server: { url }, ... } }
//
// +layout.svelte's existing executeTool handler then dispatches based on
// server.url. For HTTP tool servers it calls executeToolServer (REST).
// For our virtual `rmdg-iframe://docgen` URL it calls this module
// instead — which routes by tool name to the iframe client and returns
// the result for OWUI to inject as a tool-role message in the next turn.
//
// Pure function module: takes the active client + the tool name + params,
// returns the result (or an error result, never throws — the caller
// expects to put `tool_result` into a socket callback shape).

import { isDocGenToolName, type DocGenStateForModel } from './tools';
import type { DocGenIframeClient } from './iframeClient';

/** Shape OWUI expects back in the execute:tool callback. Wide on
 *  purpose: concrete tool results (proposeEdit's `{proposalId,
 *  status:'pending'}`, getState's snapshot, etc.) fit without forcing
 *  callers to add an index signature. Distinguish success vs failure
 *  via the optional `error` field. */
export type ExecuteToolResult = object & { error?: string };

export interface DispatchOptions {
	/** The active iframe client. Null when the doc panel is closed —
	 *  callers should check before invoking (and ideally return a clear
	 *  doc_panel_closed error so the model knows to ask the user to open it). */
	client: DocGenIframeClient | null;
	toolName: string;
	params: Record<string, unknown>;
}

/**
 * Dispatch a single tool call. Always resolves (never throws); on error
 * returns `{error: ...}` which the model treats as a tool failure and
 * recovers from.
 */
export async function dispatchDocGenToolCall(opts: DispatchOptions): Promise<ExecuteToolResult> {
	const { client, toolName, params } = opts;

	if (!isDocGenToolName(toolName)) {
		return { error: `Onbekend gereedschap '${toolName}' — verwacht een docgen_* naam.` };
	}

	if (!client) {
		return {
			error:
				"Het documentpaneel is niet open. Vraag de gebruiker om op de '📄 Document' knop te klikken voordat je het document probeert te bewerken."
		};
	}

	try {
		switch (toolName) {
			case 'docgen_proposeEdit': {
				// The model passes the proposal as a positional arg (per the
				// docgen_proposeEdit JSON Schema). When OWUI's tool dispatch
				// hands us params as a name→value map, the proposal arrives
				// under either the first declared param name or spread as the
				// whole `params` object. Both cases are handled:
				//   - direct: { id, kind, target, content, rationale } → use as-is
				//   - wrapped: { proposal: {...} } → unwrap
				const proposal = (
					params && typeof params === 'object' && 'proposal' in params
						? (params as { proposal: unknown }).proposal
						: params
				) as Parameters<DocGenIframeClient['proposeEdit']>[0];
				if (!proposal || typeof proposal !== 'object') {
					return { error: 'proposeEdit: ontbrekend of ongeldig voorstel-object.' };
				}
				const result = await client.proposeEdit(proposal);
				return result as unknown as ExecuteToolResult;
			}
			case 'docgen_acceptProposal': {
				const proposalId = String(params.proposalId ?? '');
				if (!proposalId) {
					return { error: "acceptProposal: 'proposalId' is verplicht." };
				}
				const result = await client.acceptProposal(proposalId);
				return result as unknown as ExecuteToolResult;
			}
			case 'docgen_rejectProposal': {
				const proposalId = String(params.proposalId ?? '');
				if (!proposalId) {
					return { error: "rejectProposal: 'proposalId' is verplicht." };
				}
				const result = await client.rejectProposal(proposalId);
				return result as unknown as ExecuteToolResult;
			}
			case 'docgen_getState': {
				const snapshot = await client.getState();
				// The bridge's actual `getState` returns a DocumentSnapshot with
				// a `docx` Blob. The DG-side bridge has not stripped it — strip
				// it here at the boundary before handing to the model.
				return stripBlob(snapshot);
			}
		}
	} catch (err) {
		const message = err instanceof Error ? err.message : String(err);
		return { error: `docgen_${toolName.slice('docgen_'.length)} mislukt: ${message}` };
	}
}

function stripBlob(snapshot: unknown): DocGenStateForModel {
	if (!snapshot || typeof snapshot !== 'object') {
		return { documentId: '', content: null, title: '', updatedAt: '' };
	}
	const s = snapshot as Record<string, unknown>;
	return {
		documentId: typeof s.documentId === 'string' ? s.documentId : '',
		content: s.content ?? null,
		title: typeof s.title === 'string' ? s.title : '',
		updatedAt: typeof s.updatedAt === 'string' ? s.updatedAt : ''
	};
}
