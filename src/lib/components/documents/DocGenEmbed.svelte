<script lang="ts">
	// Wrapper around the Ruimtemeesters Document-Generator Web Component
	// (WI-006). Loads the bundle from doc-gen.datameesters.nl on first
	// mount, mints a Clerk JWT via docGenAuth, wires it into the
	// <rm-doc-generator>'s `auth-token` attribute, and re-fetches the
	// token on session-changed events.
	//
	// All copy is Dutch, matching the rest of the embed/banner UX.

	import { onMount, onDestroy } from 'svelte';
	import {
		getDocGenAuthToken,
		onDocGenAuthChange,
	} from '$lib/integrations/docGenAuth';

	type Theme = 'light' | 'dark';

	interface Props {
		documentId?: string;
		autoCreate?: boolean;
		theme?: Theme;
		readonly?: boolean;
		apiBase?: string;
		bundleUrl?: string;
		/** Bound back to the parent so it can attach `proposal-pending`
		 *  listeners or call `proposeEdit` from a console session. */
		embedEl?: HTMLElement | null;
	}

	let {
		documentId,
		autoCreate = false,
		theme = 'light',
		readonly = false,
		apiBase = 'https://doc-gen.datameesters.nl/api',
		bundleUrl = 'https://doc-gen.datameesters.nl/rm-doc-generator.js',
		embedEl = $bindable(null),
	}: Props = $props();

	let containerEl: HTMLDivElement | null = $state(null);
	let token = $state<string | null>(null);
	let loadState = $state<'idle' | 'loading' | 'ready' | 'error'>('idle');
	let errorMessage = $state<string | null>(null);
	let unsubscribeAuthChange: (() => void) | null = null;

	// Bundle load — idempotent across multiple mounts. Tracks the active
	// load promise on a global symbol so two simultaneous DocGenEmbed
	// instances don't both inject the script tag.
	const BUNDLE_PROMISE_KEY = '__rmdg_bundle_promise__';

	function loadBundle(url: string): Promise<void> {
		const w = window as unknown as Record<string, unknown>;
		const existing = w[BUNDLE_PROMISE_KEY] as Promise<void> | undefined;
		if (existing) return existing;
		const p = new Promise<void>((resolve, reject) => {
			if (customElements.get('rm-doc-generator')) {
				resolve();
				return;
			}
			const script = document.createElement('script');
			script.src = url;
			script.type = 'module';
			script.async = true;
			script.onload = () => resolve();
			script.onerror = () =>
				reject(new Error(`Kon ${url} niet laden`));
			document.head.appendChild(script);
		});
		w[BUNDLE_PROMISE_KEY] = p;
		return p;
	}

	async function refreshToken() {
		const fresh = await getDocGenAuthToken();
		token = fresh;
		if (!fresh && loadState === 'ready') {
			errorMessage =
				'Aanmelden mislukt: geen Clerk-sessie gevonden. Vernieuw de pagina of meld opnieuw aan.';
		}
	}

	onMount(async () => {
		loadState = 'loading';
		try {
			await loadBundle(bundleUrl);
			await refreshToken();
			if (!token) {
				loadState = 'error';
				errorMessage =
					errorMessage ??
					'Geen geldige aanmelding gevonden voor de Document-Generator. Controleer of PUBLIC_CLERK_PUBLISHABLE_KEY is ingesteld.';
				return;
			}
			unsubscribeAuthChange = await onDocGenAuthChange(() => {
				void refreshToken();
			});
			loadState = 'ready';
		} catch (err) {
			loadState = 'error';
			errorMessage =
				err instanceof Error
					? `Document-Generator kon niet laden: ${err.message}`
					: 'Document-Generator kon niet laden (onbekende fout).';
		}
	});

	onDestroy(() => {
		unsubscribeAuthChange?.();
		unsubscribeAuthChange = null;
	});

	// Capture the live element reference once it's in the DOM, so the
	// parent can drive proposeEdit / acceptProposal / etc. from a console
	// or future LLM-wiring code (WI-008).
	$effect(() => {
		if (!containerEl || loadState !== 'ready') return;
		const el = containerEl.querySelector('rm-doc-generator');
		embedEl = (el as HTMLElement | null) ?? null;
	});
</script>

{#if loadState === 'loading' || loadState === 'idle'}
	<div class="docgen-embed-status">Document-Generator wordt geladen…</div>
{:else if loadState === 'error'}
	<div class="docgen-embed-status docgen-embed-error">
		{errorMessage ?? 'Document-Generator kon niet geladen worden.'}
	</div>
{:else}
	<div
		bind:this={containerEl}
		class="docgen-embed-shell"
		data-testid="docgen-embed-shell"
	>
		<!--
			Custom element attributes match the DG TSD § Attributes. The
			`auth-token` value rotates whenever Clerk hands us a fresh JWT
			(refreshToken is wired to clerk.addListener); the embed's
			attributeChangedCallback re-registers its token provider on
			each change.
		-->
		<!-- svelte-ignore svelte_element_invalid_this -->
		<rm-doc-generator
			document-id={documentId}
			auto-create={autoCreate ? '' : undefined}
			theme={theme}
			readonly={readonly ? '' : undefined}
			api-base={apiBase}
			auth-token={token}
		></rm-doc-generator>
	</div>
{/if}

<style>
	.docgen-embed-shell {
		display: block;
		width: 100%;
		height: 100%;
		min-height: 480px;
	}
	.docgen-embed-status {
		padding: 1rem 1.25rem;
		font-size: 0.95rem;
		color: var(--color-base-content, #4b4f6b);
	}
	.docgen-embed-error {
		color: #b91c1c;
	}
</style>
