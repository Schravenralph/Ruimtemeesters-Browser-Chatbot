<script lang="ts">
	// Single-document view (WI-006 Tier 1). Mounts <rm-doc-generator>
	// with `auto-create` so a never-seen-before id mints a backend row
	// on first save. The DocGenEmbed wrapper handles bundle load, Clerk
	// token wiring, and refresh-on-rotate.
	//
	// Console-driven testing: the embed element is bound to
	// `window.__rmdgEmbedEl__` so a developer can run e.g.
	//   await window.__rmdgEmbedEl__.getState()
	//   window.__rmdgEmbedEl__.proposeEdit({ ... })
	// while we don't have the LLM-wiring layer yet (WI-008).

	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import DocGenEmbed from '$lib/components/documents/DocGenEmbed.svelte';

	let documentId = $derived($page.params.id);
	let embedEl = $state<HTMLElement | null>(null);
	let toastMessage = $state<string | null>(null);

	// Surface proposal events as toasts so the developer sees the
	// integration is alive even without explicit DevTools listeners.
	function handleEmbedEvent(eventName: string, detail: unknown) {
		toastMessage = `${eventName}: ${JSON.stringify(detail).slice(0, 120)}`;
		setTimeout(() => {
			toastMessage = null;
		}, 4000);
	}

	$effect(() => {
		if (!embedEl) return;
		const events = [
			'ready',
			'proposal-pending',
			'proposal-accepted',
			'proposal-rejected',
			'proposal-rejected-overlap',
			'title-change'
		];
		const handlers = events.map((name) => {
			const h = (e: Event) => {
				const detail = (e as CustomEvent).detail ?? {};
				handleEmbedEvent(name, detail);
			};
			embedEl!.addEventListener(name, h);
			return [name, h] as const;
		});
		// Stash on window for console-driven testing. Cleaned up via the
		// return below so a SPA navigation away clears the reference.
		(window as unknown as { __rmdgEmbedEl__?: HTMLElement }).__rmdgEmbedEl__ = embedEl;
		return () => {
			for (const [name, h] of handlers) embedEl?.removeEventListener(name, h);
			delete (window as unknown as { __rmdgEmbedEl__?: HTMLElement }).__rmdgEmbedEl__;
		};
	});

	function downloadNow() {
		const el = embedEl as unknown as {
			download?: (filename?: string) => Promise<Blob>;
		};
		void el?.download?.();
	}

	let loaded = $state(false);
	onMount(() => {
		loaded = true;
	});
</script>

{#if loaded}
	<div class="docgen-view-shell">
		<header class="docgen-view-header">
			<h1>Document</h1>
			<div class="docgen-view-toolbar">
				<button
					type="button"
					class="docgen-btn-secondary"
					onclick={downloadNow}
					disabled={!embedEl}
				>
					Download .docx
				</button>
				<a class="docgen-view-link" href="/documents">Terug naar lijst</a>
			</div>
		</header>
		<div class="docgen-view-meta">
			<span>Document-ID: <code>{documentId}</code></span>
			<span class="docgen-view-hint">
				Console: <code>window.__rmdgEmbedEl__</code>
			</span>
		</div>
		<div class="docgen-view-embed">
			<DocGenEmbed {documentId} autoCreate theme="light" bind:embedEl />
		</div>
		{#if toastMessage}
			<div class="docgen-view-toast">{toastMessage}</div>
		{/if}
	</div>
{/if}

<style>
	.docgen-view-shell {
		display: flex;
		flex-direction: column;
		height: 100vh;
		max-height: 100dvh;
	}
	.docgen-view-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.75rem 1.5rem 0.5rem;
		border-bottom: 1px solid rgba(0, 0, 0, 0.08);
	}
	.docgen-view-header h1 {
		font-size: 1.25rem;
		font-weight: 600;
		margin: 0;
	}
	.docgen-view-toolbar {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}
	.docgen-btn-secondary {
		background: transparent;
		color: var(--color-base-content, #0a0d2c);
		border: 1px solid rgba(0, 0, 0, 0.2);
		border-radius: 0.375rem;
		padding: 0.4rem 0.8rem;
		font: inherit;
		cursor: pointer;
	}
	.docgen-btn-secondary:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.docgen-view-link {
		color: #2563eb;
		text-decoration: none;
		font-size: 0.9rem;
	}
	.docgen-view-link:hover {
		text-decoration: underline;
	}
	.docgen-view-meta {
		display: flex;
		justify-content: space-between;
		padding: 0.25rem 1.5rem 0.5rem;
		font-size: 0.8rem;
		color: var(--color-base-content, #4b4f6b);
	}
	.docgen-view-meta code {
		background: rgba(0, 0, 0, 0.06);
		padding: 0.1rem 0.35rem;
		border-radius: 0.2rem;
	}
	.docgen-view-embed {
		flex: 1;
		min-height: 0;
		display: flex;
	}
	.docgen-view-toast {
		position: fixed;
		bottom: 1rem;
		right: 1rem;
		max-width: 360px;
		padding: 0.6rem 0.9rem;
		background: #111827;
		color: #f9fafb;
		border-radius: 0.4rem;
		font-size: 0.8rem;
		opacity: 0.95;
		z-index: 50;
		font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
	}
</style>
