/**
 * Geoportaal ↔ chatbot postMessage-bridge — implements PRD-0023 from
 * the Geoportaal repo (`docs/07-prd/0023-uc-09-postmessage-bridge-protocol.md`).
 *
 * This is a chatbot-side mirror of Geoportaal's
 * `src/shared/bridge/events.ts`. We can't import from that repo (separate
 * codebase, no shared package yet) so the types are duplicated here.
 * Both sides MUST stay in sync — when Geoportaal evolves the protocol,
 * bump `BRIDGE_PROTOCOL_VERSION` and update this file in lockstep.
 *
 * Distinct from `embedContext.ts` (Databank's `rm:chatbot:context`
 * protocol). Both protocols co-exist on the message channel — they
 * discriminate on `event.data.type` and `event.data.protocolVersion`.
 */

export const BRIDGE_PROTOCOL_VERSION = 1 as const;

export type BridgeEventSource = 'host' | 'iframe';

export interface BridgeEnvelope<TType extends string = string, TPayload = unknown> {
	protocolVersion: typeof BRIDGE_PROTOCOL_VERSION;
	source: BridgeEventSource;
	messageId: string;
	projectId: number;
	variantId: string;
	type: TType;
	payload: TPayload;
}

// ─── HOST → IFRAME events (subset we currently handle) ───────────────────

export interface HostReadyPayload {
	hostVersion: string;
}

export interface HostFeatureClickedPayload {
	feature: { layerKey: string; featureId: string; properties?: Record<string, unknown> };
	lon: number;
	lat: number;
}

export interface HostViewportChangedPayload {
	bbox: [number, number, number, number];
	zoom: number;
}

export interface HostVariantSwitchedPayload {
	variantId: string;
	parentVariantId: string | null;
}

// ─── IFRAME → HOST events (subset we currently emit) ─────────────────────

export interface IframeReadyPayload {
	iframeVersion: string;
}

export interface IframeMapPanToPayload {
	lon: number;
	lat: number;
	zoom?: number;
}

export interface IframeErrorPayload {
	code: string;
	message: string;
}

// Allowed host-origins. Mirror of Geoportaal's `useChatbotBridge.ts`
// `ALLOWED_CHAT_ORIGINS`, but inverted (we accept FROM these origins).
// Per ADR-0021 the production host is geoportaal.datameesters.nl;
// staging + localhost added for dev. Update both sides together when
// the host moves.
const ALLOWED_HOST_ORIGINS = [
	'https://geoportaal.datameesters.nl',
	'https://digitaltwin.datameesters.nl',
	'https://geoportaal-staging.datameesters.nl',
	'http://localhost:3000',
	'http://localhost:5173'
];

export function isAllowedHostOrigin(origin: string): boolean {
	return ALLOWED_HOST_ORIGINS.includes(origin);
}

/**
 * Runtime payload-shape validators for the host events the layout
 * actually consumes. `parseHostEnvelope` only checks the envelope
 * itself; the `payload` is `unknown` and the consumer must narrow it.
 * Without these checks, a malformed `host.variant.switched` payload
 * would set `state.variantId` to `undefined`, which breaks the
 * variant-mismatch guard for every subsequent message (the comparison
 * `env.variantId !== undefined` is always true). Bugbot finding on
 * PR #42.
 */
export function isHostFeatureClickedPayload(p: unknown): p is HostFeatureClickedPayload {
	if (!p || typeof p !== 'object') return false;
	const v = p as Record<string, unknown>;
	if (typeof v.lon !== 'number' || typeof v.lat !== 'number') return false;
	if (!v.feature || typeof v.feature !== 'object') return false;
	const f = v.feature as Record<string, unknown>;
	return typeof f.layerKey === 'string' && typeof f.featureId === 'string';
}

export function isHostVariantSwitchedPayload(p: unknown): p is HostVariantSwitchedPayload {
	if (!p || typeof p !== 'object') return false;
	const v = p as Record<string, unknown>;
	if (typeof v.variantId !== 'string') return false;
	// parentVariantId is `string | null` — present in payload, but the
	// nullable string is the only awkward case.
	return v.parentVariantId === null || typeof v.parentVariantId === 'string';
}

/**
 * Validate an incoming MessageEvent's data as a Geoportaal-PRD-0023
 * envelope from the host side. Returns the parsed envelope or `null`.
 *
 * Distinct from Databank's protocol (`event.data.type === 'rm:chatbot:context'`)
 * — this one looks for the typed envelope shape.
 */
export function parseHostEnvelope(data: unknown): BridgeEnvelope<string, unknown> | null {
	if (!data || typeof data !== 'object' || Array.isArray(data)) return null;
	const e = data as Record<string, unknown>;
	if (e.protocolVersion !== BRIDGE_PROTOCOL_VERSION) return null;
	// Chatbot only accepts host-to-iframe envelopes — never receives an
	// iframe.* type from the host (would be a spoofing attempt).
	if (e.source !== 'host') return null;
	if (typeof e.type !== 'string' || !e.type.startsWith('host.')) return null;
	if (typeof e.messageId !== 'string') return null;
	if (typeof e.projectId !== 'number') return null;
	if (typeof e.variantId !== 'string') return null;
	if (!e.payload || typeof e.payload !== 'object' || Array.isArray(e.payload)) return null;
	return e as unknown as BridgeEnvelope<string, unknown>;
}

/**
 * Build a typed iframe-event envelope for posting to the host parent.
 * The caller supplies the projectId/variantId from the embed-context
 * store (which is populated from the iframe's URL query-params at
 * mount time).
 */
export function buildIframeEnvelope<TType extends string, TPayload>(
	type: TType,
	payload: TPayload,
	ctx: { projectId: number; variantId: string }
): BridgeEnvelope<TType, TPayload> {
	const messageId =
		typeof crypto !== 'undefined' && 'randomUUID' in crypto
			? crypto.randomUUID()
			: `msg-${Date.now()}-${Math.random().toString(36).slice(2)}`;
	return {
		protocolVersion: BRIDGE_PROTOCOL_VERSION,
		source: 'iframe',
		messageId,
		projectId: ctx.projectId,
		variantId: ctx.variantId,
		type,
		payload
	};
}

/**
 * Send an iframe-event to the host parent. Returns `true` on success,
 * `false` if not in iframe context, or if the parent origin is not
 * allowlisted (defensive — if the iframe was misembedded somewhere
 * outside Geoportaal, we shouldn't leak events to whatever loaded us).
 *
 * `targetOrigin` is required for security: postMessage with `'*'`
 * would broadcast to whatever currently controls the parent frame,
 * which is exactly the spoofing vector we're trying to avoid.
 */
export function sendToHost<TType extends string, TPayload>(
	type: TType,
	payload: TPayload,
	ctx: { projectId: number; variantId: string; hostOrigin: string }
): boolean {
	if (typeof window === 'undefined') return false;
	if (!window.parent || window.parent === window) return false;
	if (!isAllowedHostOrigin(ctx.hostOrigin)) return false;
	const envelope = buildIframeEnvelope(type, payload, ctx);
	try {
		window.parent.postMessage(envelope, ctx.hostOrigin);
		return true;
	} catch {
		return false;
	}
}
