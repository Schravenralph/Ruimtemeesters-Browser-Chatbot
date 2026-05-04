import { writable } from 'svelte/store';
import type { HostFeatureClickedPayload } from '$lib/bridge/geoportaal';

/**
 * Active state when the chatbot SPA is embedded inside the
 * Ruimtemeesters Geoportaal app via the PRD-0023 postMessage-bridge
 * (distinct from the Databank embed which uses `embedContext`).
 *
 * Populated at mount-time from the iframe URL's query-params
 * (`?projectId=…&variantId=…`) and updated by host events.
 *
 * Components subscribe to this store to render the embed-banner with
 * project context, last-clicked feature, and a "demo: pan map"
 * button that exercises the iframe→host direction of the bridge.
 */
export interface GeoportaalEmbedState {
	/** True when chatbot is loaded as iframe inside Geoportaal. */
	active: boolean;
	/** Project id from URL query-param. NaN until detected. */
	projectId: number;
	/** Variant id from URL query-param. Defaults to 'baseline'. */
	variantId: string;
	/** Origin of the host page — required to send postMessages back. */
	hostOrigin: string;
	/** Bridge handshake state — flips to `'ready'` once host.ready arrives. */
	bridgeState: 'pending' | 'ready';
	/** Last feature the user clicked on the Geoportaal map (host.feature.clicked). */
	lastFeature: HostFeatureClickedPayload | null;
}

export const initialEmbedState: GeoportaalEmbedState = {
	active: false,
	projectId: Number.NaN,
	variantId: 'baseline',
	hostOrigin: '',
	bridgeState: 'pending',
	lastFeature: null
};

export const geoportaalEmbed = writable<GeoportaalEmbedState>(initialEmbedState);
