<script lang="ts">
	// "Vraag de AI" modal for the Document-Generator surface (WI-008,
	// Tier 2 of the cross-repo integration). User enters a prompt; we
	// POST to OWUI's /api/chat/completions (non-streaming); the response
	// text is handed back to the parent (/documents/[id]) which calls
	// embedEl.proposeEdit(...) — surfacing the draft as a pending
	// proposal in the WI-003 banner.
	//
	// Out of scope (intentional): streaming responses, multi-turn chat,
	// markdown rendering. Tier 2.5 / WI-008-followup if needed.

	import { models } from '$lib/stores';
	import { generateOpenAIChatCompletion } from '$lib/apis/openai';
	import { WEBUI_BASE_URL } from '$lib/constants';

	interface Props {
		open: boolean;
		onSubmit: (text: string, model: string) => void | Promise<void>;
		onClose: () => void;
	}

	let { open = $bindable(), onSubmit, onClose }: Props = $props();

	// System prompt nudges the LLM toward plain-paragraph output since
	// the embed v0 only accepts kind:'insert' + content:'paragraph'
	// (WI-002). Markdown / headings / lists would still be inserted as
	// raw text, just not rendered semantically.
	const SYSTEM_PROMPT =
		'Je schrijft één korte, neutrale alinea in het Nederlands. ' +
		'Geen koppen, geen lijsten, geen markdown — uitsluitend platte tekst.';

	let prompt = $state('');
	let busy = $state(false);
	let errorMessage = $state<string | null>(null);
	let selectedModel = $state<string>('');

	// Initialise model from last-used or first available; tracked in a
	// $effect so subsequent renders don't reset the user's choice.
	$effect(() => {
		if (!open) return;
		if (selectedModel) return;
		const last =
			typeof localStorage !== 'undefined' ? localStorage.getItem('lastSelectedModel') || '' : '';
		const available = $models.map((m) => m.id);
		if (last && available.includes(last)) {
			selectedModel = last;
		} else if (available.length > 0) {
			selectedModel = available[0];
		}
	});

	async function submit() {
		const trimmed = prompt.trim();
		if (!trimmed) {
			errorMessage = 'Geef eerst een prompt op.';
			return;
		}
		if (!selectedModel) {
			errorMessage = 'Kies een model. Geen modellen beschikbaar? Check de modelinstellingen.';
			return;
		}
		busy = true;
		errorMessage = null;
		try {
			const token = (typeof localStorage !== 'undefined' && localStorage.token) || '';
			const res = await generateOpenAIChatCompletion(
				token,
				{
					model: selectedModel,
					messages: [
						{ role: 'system', content: SYSTEM_PROMPT },
						{ role: 'user', content: trimmed }
					],
					stream: false
				},
				`${WEBUI_BASE_URL}/api`
			);
			const text = (res?.choices?.[0]?.message?.content ?? '').trim();
			if (!text) {
				errorMessage =
					'Het model leverde geen tekst op. Probeer een andere prompt of een ander model.';
				busy = false;
				return;
			}
			await onSubmit(text, selectedModel);
			// Parent closes the modal on success; we reset local state for
			// the next open. The `open=$bindable` lets the parent flip it.
			prompt = '';
			busy = false;
		} catch (err) {
			busy = false;
			errorMessage = humanCompletionError(err);
		}
	}

	function cancel() {
		if (busy) return;
		errorMessage = null;
		prompt = '';
		onClose();
	}

	function humanCompletionError(err: unknown): string {
		if (err && typeof err === 'object' && 'detail' in err) {
			const detail = (err as { detail?: string }).detail;
			if (typeof detail === 'string') return `Vraag mislukt: ${detail}`;
		}
		if (err instanceof Error) return `Vraag mislukt: ${err.message}`;
		return 'Vraag mislukt: onbekende fout.';
	}
</script>

{#if open}
	<div class="askai-backdrop" role="dialog" aria-modal="true" aria-labelledby="askai-title">
		<div class="askai-modal">
			<header class="askai-header">
				<h2 id="askai-title">Vraag de AI om een paragraaf te schrijven</h2>
			</header>
			<label class="askai-field">
				<span>Prompt</span>
				<textarea
					rows="5"
					bind:value={prompt}
					placeholder="Bijv. 'Schrijf een korte alinea over de juridische status van de BOPA in deze locatie.'"
					disabled={busy}
				></textarea>
			</label>
			<label class="askai-field">
				<span>Model</span>
				<select bind:value={selectedModel} disabled={busy}>
					{#each $models as model (model.id)}
						<option value={model.id}>{model.name ?? model.id}</option>
					{/each}
				</select>
			</label>
			{#if errorMessage}
				<div class="askai-error" role="alert">{errorMessage}</div>
			{/if}
			<footer class="askai-actions">
				<button type="button" class="askai-btn-secondary" onclick={cancel} disabled={busy}
					>Annuleren</button
				>
				<button type="button" class="askai-btn-primary" onclick={submit} disabled={busy}
					>{busy ? 'Bezig…' : 'Versturen'}</button
				>
			</footer>
		</div>
	</div>
{/if}

<style>
	.askai-backdrop {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.45);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 100;
	}
	.askai-modal {
		background: var(--color-base-100, #fff);
		color: var(--color-base-content, #0a0d2c);
		border-radius: 0.5rem;
		padding: 1.25rem 1.5rem;
		max-width: 560px;
		width: 92vw;
		display: flex;
		flex-direction: column;
		gap: 0.85rem;
		box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
	}
	.askai-header h2 {
		margin: 0;
		font-size: 1.05rem;
		font-weight: 600;
	}
	.askai-field {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		font-size: 0.9rem;
	}
	.askai-field span {
		font-weight: 500;
	}
	.askai-field textarea,
	.askai-field select {
		font: inherit;
		padding: 0.5rem 0.65rem;
		border: 1px solid rgba(0, 0, 0, 0.2);
		border-radius: 0.35rem;
		background: var(--color-base-200, #f4f4f8);
		color: inherit;
		resize: vertical;
	}
	.askai-field textarea:disabled,
	.askai-field select:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}
	.askai-error {
		color: #b91c1c;
		font-size: 0.85rem;
	}
	.askai-actions {
		display: flex;
		gap: 0.6rem;
		justify-content: flex-end;
	}
	.askai-btn-primary,
	.askai-btn-secondary {
		font: inherit;
		padding: 0.45rem 0.95rem;
		border-radius: 0.35rem;
		cursor: pointer;
		border: 1px solid transparent;
	}
	.askai-btn-primary {
		background: #2563eb;
		color: #fff;
		border-color: #2563eb;
	}
	.askai-btn-primary:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}
	.askai-btn-secondary {
		background: transparent;
		color: inherit;
		border-color: rgba(0, 0, 0, 0.2);
	}
	.askai-btn-secondary:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}
</style>
