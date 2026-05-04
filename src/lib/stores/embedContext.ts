import { writable } from 'svelte/store';

export interface EmbedDocContext {
	documentId: string;
	source?: string | null;
	documentType?: string | null;
	publisher?: string | null;
	title?: string | null;
}

/**
 * When this chatbot SPA is embedded as an iframe inside the Ruimtemeesters
 * Databank app, the parent posts the user's currently-viewed document via
 * window.postMessage on the `rm:chatbot:context` channel. We mirror that into
 * a Svelte store so any chat page can read it (e.g. to seed a system prompt
 * or render a "you're asking about X" banner).
 */
export const embedContext = writable<EmbedDocContext | null>(null);
