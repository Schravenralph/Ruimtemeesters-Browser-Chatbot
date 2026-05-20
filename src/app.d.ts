// See https://kit.svelte.dev/docs/types#app
// for information about these interfaces
declare global {
	namespace App {
		// interface Error {}
		// interface Locals {}
		// interface PageData {}
		// interface Platform {}
	}

	// WI-006: Custom-element JSX/Svelte typing for the Ruimtemeesters
	// Document-Generator embed. Svelte's TS checker needs an explicit
	// declaration before it lets us use a hyphenated tag with arbitrary
	// attributes — without this, `<rm-doc-generator document-id="…">`
	// trips "no overload matches this call" on every attribute.
	namespace svelteHTML {
		interface IntrinsicElements {
			'rm-doc-generator': {
				'document-id'?: string | null;
				'auto-create'?: string;
				theme?: 'light' | 'dark';
				readonly?: string;
				'api-base'?: string;
				'auth-token'?: string | null;
			};
		}
	}
}

export {};
