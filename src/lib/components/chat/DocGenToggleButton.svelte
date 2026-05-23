<script lang="ts">
	// Toggle button for the Document-Generator iframe panel (WI-014).
	//
	// Owns the open/close lifecycle for the DG panel within a chat:
	//   - On open: mints/reads the chat's docId from chat.meta.docgen,
	//     sets the global embed store to point at iframe-embed.html, marks
	//     it `trusted` (so Embeds.svelte passes allowSameOrigin to the
	//     iframe — DG needs same-origin for Clerk localStorage/cookies),
	//     opens showControls+showEmbeds, waits a tick for the iframe DOM,
	//     queries it, and connects an iframeClient via the docGen store
	//     (the active client becomes available to the execute:tool socket
	//     handler in +layout.svelte).
	//   - On close: disconnects the client, clears showEmbeds + embed.

	import { tick, getContext } from 'svelte';
	import { toast } from 'svelte-sonner';

	import {
		chatId,
		embed,
		showControls,
		showEmbeds,
		user,
		type EmbedDescriptor
	} from '$lib/stores';
	import Document from '$lib/components/icons/Document.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';

	import { getOrMintDocIdForChat } from '$lib/integrations/docGen/chatMeta';
	import {
		disconnectDocGenIframe,
		docGenPanelState,
		openDocGenIframe
	} from '$lib/integrations/docGen/store';

	const i18n = getContext<{ t: (k: string) => string }>('i18n');

	// Production override + sensible default for the DG iframe URL. Mirrors
	// the WI-013 iframe-embed.html entry. PUBLIC_RMDG_IFRAME_BASE lets ops
	// point at a non-prod DG without a rebuild.
	const RMDG_IFRAME_BASE =
		(import.meta.env?.VITE_RMDG_IFRAME_BASE as string | undefined) ??
		'https://doc-gen.datameesters.nl';
	const RMDG_IFRAME_ORIGIN = (() => {
		try {
			return new URL(RMDG_IFRAME_BASE).origin;
		} catch {
			return 'https://doc-gen.datameesters.nl';
		}
	})();

	let busy = $state(false);

	async function toggle() {
		if (busy) return;
		busy = true;
		try {
			if ($docGenPanelState.open) {
				closePanel();
				return;
			}
			await openPanel();
		} finally {
			busy = false;
		}
	}

	async function openPanel() {
		if (!$chatId) {
			toast.error(i18n.t('Start een chat voordat je een document opent.'));
			return;
		}
		let docId: string;
		try {
			docId = await getOrMintDocIdForChat(localStorage.token, $chatId);
		} catch (err) {
			console.error('docGen: failed to read/mint docId for chat', err);
			toast.error(i18n.t('Kon de document-id voor deze chat niet ophalen.'));
			return;
		}
		const url = `${RMDG_IFRAME_BASE}/iframe-embed.html?docId=${encodeURIComponent(docId)}`;
		// Open the right-rail Embeds panel via the existing store pattern
		// (matches Citations / ContentRenderer usage).
		const descriptor: EmbedDescriptor = { url, title: 'Document', trusted: true };
		embed.set(descriptor as unknown as null);
		await showControls.set(true);
		await showEmbeds.set(true);
		// Wait for Svelte to mount Embeds.svelte + FullHeightIframe.
		await tick();
		const iframeEl = findEmbedIframe();
		if (!iframeEl) {
			toast.error(i18n.t('Document-paneel kon niet worden gestart.'));
			console.error('docGen: iframe element not found after panel open');
			return;
		}
		openDocGenIframe({ iframe: iframeEl, docId, iframeOrigin: RMDG_IFRAME_ORIGIN });
	}

	function closePanel() {
		disconnectDocGenIframe();
		showEmbeds.set(false);
		embed.set(null);
	}

	function findEmbedIframe(): HTMLIFrameElement | null {
		// FullHeightIframe doesn't expose a binding hook to its consumer
		// (it's used by Citations + others as a generic embed shell). The
		// reliable way to grab the iframe element is a DOM query scoped
		// to the embeds panel; there is exactly one iframe in that pane.
		// If FullHeightIframe later exposes a `bind:iframe`, swap to that.
		return document.querySelector<HTMLIFrameElement>(
			'.docgen-embeds-pane iframe, [data-rmdg-embed-host] iframe, iframe[src*="iframe-embed.html"]'
		);
	}
</script>

{#if $user?.role === 'admin' || ($user?.permissions?.chat?.controls ?? true)}
	<Tooltip content={i18n.t($docGenPanelState.open ? 'Document sluiten' : 'Document openen')}>
		<button
			type="button"
			class="flex cursor-pointer px-2 py-2 rounded-xl transition {$docGenPanelState.open
				? 'bg-gray-100 dark:bg-gray-800 text-blue-600 dark:text-blue-400'
				: 'hover:bg-gray-50 dark:hover:bg-gray-850'}"
			onclick={toggle}
			disabled={busy}
			aria-label={i18n.t($docGenPanelState.open ? 'Document sluiten' : 'Document openen')}
			aria-pressed={$docGenPanelState.open}
		>
			<div class="m-auto self-center">
				<Document className="size-5" strokeWidth="1.5" />
			</div>
		</button>
	</Tooltip>
{/if}
