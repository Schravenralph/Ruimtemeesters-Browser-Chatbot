<script lang="ts">
	// Documents list view (WI-006 Tier 1). For v0 this is intentionally
	// minimal — a heading + "Nieuw document" button that navigates to
	// /documents/<freshly-minted-id>. The DG embed's `auto-create`
	// attribute mints the backend row on first mount; we just pre-generate
	// the UUID client-side so the URL is stable from the moment we
	// navigate.
	//
	// A future iteration (WI-008+) can render a real list pulled from
	// `GET /documents` on the DG backend, but for the Tier 1 proof we
	// avoid touching that endpoint until the auth path is validated by
	// the /documents/[id] mount.

	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	let loaded = $state(false);

	onMount(() => {
		loaded = true;
	});

	function newDocument() {
		const id = crypto.randomUUID();
		goto(`/documents/${id}`);
	}
</script>

{#if loaded}
	<div class="docgen-list-shell">
		<header class="docgen-list-header">
			<h1>Documenten</h1>
			<p>
				Open een document of begin een nieuw concept. De inhoud wordt
				automatisch opgeslagen in de Document-Generator backend van
				Ruimtemeesters.
			</p>
		</header>
		<div class="docgen-list-actions">
			<button type="button" class="docgen-btn-primary" onclick={newDocument}>
				Nieuw document
			</button>
		</div>
		<p class="docgen-list-hint">
			Plak een document-ID in de URL <code>/documents/&lt;id&gt;</code>
			om een bestaand document te openen.
		</p>
	</div>
{/if}

<style>
	.docgen-list-shell {
		max-width: 720px;
		margin: 3rem auto;
		padding: 0 1.5rem;
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
	}
	.docgen-list-header h1 {
		font-size: 1.75rem;
		font-weight: 600;
		margin: 0 0 0.5rem;
	}
	.docgen-list-header p {
		color: var(--color-base-content, #4b4f6b);
		margin: 0;
		line-height: 1.5;
	}
	.docgen-list-actions {
		display: flex;
		gap: 0.75rem;
	}
	.docgen-btn-primary {
		background: #2563eb;
		color: #fff;
		border: 1px solid #2563eb;
		border-radius: 0.375rem;
		padding: 0.55rem 1rem;
		font: inherit;
		cursor: pointer;
	}
	.docgen-btn-primary:hover {
		background: #1d4ed8;
	}
	.docgen-list-hint {
		font-size: 0.875rem;
		color: var(--color-base-content, #4b4f6b);
	}
	.docgen-list-hint code {
		background: rgba(0, 0, 0, 0.06);
		padding: 0.1rem 0.35rem;
		border-radius: 0.25rem;
	}
</style>
