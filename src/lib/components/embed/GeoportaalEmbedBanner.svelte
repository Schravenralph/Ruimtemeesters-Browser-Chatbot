<script lang="ts">
	import { geoportaalEmbed } from '$lib/stores/geoportaalEmbed';
	import { sendToHost } from '$lib/bridge/geoportaal';

	// Demo coordinates — Den Bosch Markt — used by the "pan kaart"-button
	// to exercise the iframe→host direction of the bridge. When wired
	// into a real chatbot-flow, these would come from LLM output (e.g.
	// the assistant suggesting a location, the iframe extracting coords
	// from the response).
	const DEMO_PAN_LAT = 51.6906;
	const DEMO_PAN_LON = 5.3056;
	const DEMO_PAN_ZOOM = 17;

	function panMapToDemo() {
		const state = $geoportaalEmbed;
		if (!state.active) return;
		sendToHost(
			'iframe.map.panTo',
			{ lat: DEMO_PAN_LAT, lon: DEMO_PAN_LON, zoom: DEMO_PAN_ZOOM },
			{
				projectId: state.projectId,
				variantId: state.variantId,
				hostOrigin: state.hostOrigin
			}
		);
	}

	function clearLastFeature() {
		geoportaalEmbed.update((s) => ({ ...s, lastFeature: null }));
	}
</script>

{#if $geoportaalEmbed.active}
	<div class="geoportaal-embed-banner" role="region" aria-label="Geoportaal embed-context">
		<div class="row">
			<span class="label">
				🗺️ Geoportaal embed
				<span class="muted"
					>— project {$geoportaalEmbed.projectId}, variant {$geoportaalEmbed.variantId}</span
				>
			</span>
			<span class="state state-{$geoportaalEmbed.bridgeState}">
				{#if $geoportaalEmbed.bridgeState === 'ready'}
					● bridge ready
				{:else}
					○ wachten op host…
				{/if}
			</span>
			<button
				type="button"
				class="demo-btn"
				on:click={panMapToDemo}
				disabled={$geoportaalEmbed.bridgeState !== 'ready'}
				title="Demo: stuur iframe.map.panTo naar de host"
			>
				Pan kaart (demo)
			</button>
		</div>

		{#if $geoportaalEmbed.lastFeature}
			<div class="feature">
				<span>
					📍 Laatste klik op kaart:
					<strong>{$geoportaalEmbed.lastFeature.feature.layerKey}</strong>
					/ {$geoportaalEmbed.lastFeature.feature.featureId}
					<span class="muted">
						({$geoportaalEmbed.lastFeature.lat.toFixed(4)},
						{$geoportaalEmbed.lastFeature.lon.toFixed(4)})
					</span>
				</span>
				<button
					type="button"
					class="dismiss"
					aria-label="Sluit feature-info"
					on:click={clearLastFeature}
				>
					×
				</button>
			</div>
		{/if}
	</div>
{/if}

<style>
	.geoportaal-embed-banner {
		background: #f0f7ff;
		border-bottom: 1px solid #cfdcef;
		padding: 0.5rem 0.75rem;
		font-size: 0.8125rem;
		color: #1f2a44;
	}
	.row {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex-wrap: wrap;
	}
	.label {
		font-weight: 500;
	}
	.muted {
		color: #5b6478;
		font-weight: normal;
	}
	.state {
		font-size: 0.75rem;
		padding: 0.125rem 0.5rem;
		border-radius: 999px;
	}
	.state-ready {
		background: #d6f3df;
		color: #105a2b;
	}
	.state-pending {
		background: #fff1d6;
		color: #6b4a00;
	}
	.demo-btn {
		margin-left: auto;
		background: #3b82f6;
		color: white;
		border: none;
		padding: 0.25rem 0.625rem;
		border-radius: 0.25rem;
		font-size: 0.75rem;
		cursor: pointer;
	}
	.demo-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.demo-btn:not(:disabled):hover {
		background: #2563eb;
	}
	.feature {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		margin-top: 0.375rem;
		padding: 0.25rem 0.5rem;
		background: white;
		border: 1px solid #d6e0ee;
		border-radius: 0.25rem;
	}
	.dismiss {
		background: transparent;
		border: none;
		font-size: 1rem;
		line-height: 1;
		cursor: pointer;
		color: #5b6478;
		padding: 0 0.25rem;
	}
	.dismiss:hover {
		color: #1f2a44;
	}
</style>
