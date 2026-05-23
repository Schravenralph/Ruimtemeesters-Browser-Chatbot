// ════════════════════════════════════════════════════════════════════════
// SOURCE OF TRUTH lives in the Document-Generator repo:
//   packages/frontend/src/embed/docGenTools.ts
//
// Sync manually on changes (copy with style-reformat). If sync pain
// emerges (touched 2× in a month), promote to a tiny published package
// @ruimtemeesters/docgen-types. For now copy keeps the dependency graph
// flat and avoids npm-package overhead for ~250 LOC of schema.
//
// Last synced: 2026-05-23 (matches DG main @ 95174fe).
//
// ════════════════════════════════════════════════════════════════════════
//
// Tool specs and typed signatures for the LLM-callable surface of the
// Document-Generator embed (WI-014).
//
// Two consumers:
//   1. The OpenAI function specs the model sees in chat completions —
//      passed through OWUI's direct_tool_servers mechanism so backend
//      routes tool calls to the frontend via `execute:tool` socket events
//      (middleware.py:2634, +layout.svelte:497).
//   2. TypeScript types the iframe client uses for end-to-end compile-time
//      safety on tool args + results.
//
// Tool names map 1:1 to `EmbedMethod` in the DG repo's
// iframePostMessageBridge.ts modulo the `docgen_` prefix.
//
// Scope discipline (v0): see DG-side header for the reasoning. Only
// `proposeEdit` / `acceptProposal` / `rejectProposal` / `getState` are
// LLM-callable; `download` / `save` / `updateTitle` / `getVersions` are
// host/user concerns, not model decisions. The `proposeEdit` schema is
// narrower than the bridge's full `EditProposal` union (insert +
// document-end + paragraph only) to match v0 reality.

// ─── Minimal OpenAI tool-spec types ─────────────────────────────────────

export interface OpenAITool {
	type: 'function';
	function: {
		name: string;
		description: string;
		parameters: JSONSchema;
	};
}

export type JSONSchema =
	| {
			type: 'object';
			properties: Record<string, JSONSchema>;
			required?: string[];
			additionalProperties?: boolean;
			description?: string;
	  }
	| {
			type: 'string';
			enum?: string[];
			description?: string;
	  }
	| {
			type: 'number' | 'integer';
			description?: string;
	  }
	| {
			type: 'boolean';
			description?: string;
	  }
	| {
			type: 'array';
			items: JSONSchema;
			description?: string;
	  };

// ─── LLM-callable method names ──────────────────────────────────────────

export const DOC_GEN_TOOL_PREFIX = 'docgen_' as const;

export const DOC_GEN_TOOL_NAMES = [
	'docgen_proposeEdit',
	'docgen_acceptProposal',
	'docgen_rejectProposal',
	'docgen_getState'
] as const;

export type DocGenToolName = (typeof DOC_GEN_TOOL_NAMES)[number];

/** Strip the `docgen_` prefix to get the bridge's method name. */
export function bridgeMethodFor(toolName: DocGenToolName): string {
	return toolName.slice(DOC_GEN_TOOL_PREFIX.length);
}

/** Type guard: is this tool name one of ours? */
export function isDocGenToolName(name: string): name is DocGenToolName {
	return (DOC_GEN_TOOL_NAMES as readonly string[]).includes(name);
}

// ─── Typed args ─────────────────────────────────────────────────────────

export interface DocGenProposalInput {
	id: string;
	kind: 'insert';
	target: { type: 'document-end' };
	content: { type: 'paragraph'; text: string };
	rationale?: string;
	source?: { kind: 'chatbot'; ref?: string };
}

export interface DocGenToolArgs {
	docgen_proposeEdit: [DocGenProposalInput];
	docgen_acceptProposal: [proposalId: string];
	docgen_rejectProposal: [proposalId: string];
	docgen_getState: [];
}

// ─── Typed results ──────────────────────────────────────────────────────

/** `getState` shape the model sees. Strips the original
 *  `DocumentSnapshot.docx` (a Blob — not JSON-serialisable + bytes are
 *  useless to the model). The execute-tool bridge handles the strip at
 *  the boundary. */
export interface DocGenStateForModel {
	documentId: string;
	content: unknown;
	title: string;
	updatedAt: string;
}

export interface DocGenToolResults {
	docgen_proposeEdit: { proposalId: string; status: 'pending' };
	docgen_acceptProposal: { applied: true };
	docgen_rejectProposal: { applied: true };
	docgen_getState: DocGenStateForModel;
}

// ─── JSON Schemas (model-facing) ────────────────────────────────────────

const PROPOSE_EDIT_SCHEMA: JSONSchema = {
	type: 'object',
	description:
		'Een voorgestelde wijziging aan het document. Verschijnt als een banner bovenaan het document waar de gebruiker accepteren of afwijzen kan.',
	properties: {
		id: {
			type: 'string',
			description: 'UUID v4 die je zelf genereert. Eén unieke id per voorstel.'
		},
		kind: {
			type: 'string',
			enum: ['insert'],
			description: "v0 ondersteunt alleen 'insert'."
		},
		target: {
			type: 'object',
			properties: {
				type: {
					type: 'string',
					enum: ['document-end'],
					description: 'v0 voegt uitsluitend toe aan het einde van het document.'
				}
			},
			required: ['type'],
			additionalProperties: false
		},
		content: {
			type: 'object',
			properties: {
				type: {
					type: 'string',
					enum: ['paragraph'],
					description: "v0 ondersteunt alleen platte alinea's."
				},
				text: {
					type: 'string',
					description:
						'Inhoud van de alinea. Platte tekst, geen markdown, geen koppen, geen lijsten.'
				}
			},
			required: ['type', 'text'],
			additionalProperties: false
		},
		rationale: {
			type: 'string',
			description:
				'Optionele korte uitleg waarom je dit voorstelt — getoond naast de Accepteren/Afwijzen knoppen.'
		}
	},
	required: ['id', 'kind', 'target', 'content'],
	additionalProperties: false
};

// ─── Public spec array ──────────────────────────────────────────────────

export const docGenToolSpecs: OpenAITool[] = [
	{
		type: 'function',
		function: {
			name: 'docgen_proposeEdit',
			description:
				'Stel een wijziging voor aan het document dat de gebruiker open heeft. Het voorstel verschijnt als een banner bovenaan het document; de gebruiker accepteert of wijst af. Gebruik dit gereedschap zodra je inhoud wilt schrijven die in het document terecht moet komen — niet wanneer je gewoon antwoordt in de chat.',
			parameters: PROPOSE_EDIT_SCHEMA
		}
	},
	{
		type: 'function',
		function: {
			name: 'docgen_acceptProposal',
			description:
				'Accepteer namens de gebruiker een eerder voorstel. Gebruik dit zelden — meestal accepteert de gebruiker zelf in de banner. Alleen aanroepen als de gebruiker expliciet om bevestiging vraagt.',
			parameters: {
				type: 'object',
				properties: {
					proposalId: {
						type: 'string',
						description: 'De id die je bij proposeEdit hebt meegegeven.'
					}
				},
				required: ['proposalId'],
				additionalProperties: false
			}
		}
	},
	{
		type: 'function',
		function: {
			name: 'docgen_rejectProposal',
			description:
				'Wijs namens de gebruiker een eerder voorstel af. Zelfde voorbehoud als acceptProposal — meestal doet de gebruiker dit zelf.',
			parameters: {
				type: 'object',
				properties: {
					proposalId: {
						type: 'string',
						description: 'De id die je bij proposeEdit hebt meegegeven.'
					}
				},
				required: ['proposalId'],
				additionalProperties: false
			}
		}
	},
	{
		type: 'function',
		function: {
			name: 'docgen_getState',
			description:
				'Lees de huidige status van het document: titel, ProseMirror-JSON van de inhoud, laatst-gewijzigd-tijd. Gebruik dit om te zien wat er al in het document staat voordat je iets toevoegt — voorkomt herhaling.',
			parameters: {
				type: 'object',
				properties: {},
				additionalProperties: false
			}
		}
	}
];

// ─── System prompt injected when doc panel is open ──────────────────────
// Passed to OWUI's middleware as `tool_servers[i].system_prompt` —
// middleware.py:2636 appends it to the system message when the model
// has these tools available.

export const DOC_GEN_SYSTEM_PROMPT = `Een document is geopend in een paneel rechts in beeld. Je kunt het bewerken via de docgen_* gereedschappen. De gebruiker accepteert of wijst voorgestelde wijzigingen af via een banner bovenaan het document — je hoeft niet om bevestiging te vragen voor een proposeEdit.

Gebruik docgen_proposeEdit zodra de gebruiker iets vraagt dat in het document hoort. Antwoord in de chat alleen kort wat je hebt voorgesteld; herhaal de doc-inhoud niet in de chat.`;

// ─── Virtual server URL ─────────────────────────────────────────────────
// Sentinel passed to OWUI's direct_tool_servers as `server.url`. The
// backend doesn't dereference it; the frontend's executeTool handler
// pattern-matches on it to dispatch via the iframe client instead of
// HTTP. Scheme is intentionally non-routable (no DNS) so it would fail
// loudly if it ever leaked into a real HTTP call.

export const DOC_GEN_VIRTUAL_SERVER_URL = 'rmdg-iframe://docgen' as const;
