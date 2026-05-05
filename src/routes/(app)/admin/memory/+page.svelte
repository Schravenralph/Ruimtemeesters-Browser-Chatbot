<script lang="ts">
	import { getContext, onMount } from 'svelte';

	import { user } from '$lib/stores';
	import { getAdoptionStats, type AdoptionStats } from '$lib/apis/admin/memory';

	import Spinner from '$lib/components/common/Spinner.svelte';

	const i18n = getContext('i18n') as any;

	let stats: AdoptionStats | null = null;
	let loading = true;
	let errorMsg: string | null = null;
	let sinceDays = 7;

	const TOP_USERS = 10;

	const refresh = async () => {
		loading = true;
		errorMsg = null;
		try {
			stats = await getAdoptionStats(localStorage.token, sinceDays);
		} catch (e: any) {
			errorMsg = typeof e === 'string' ? e : (e?.detail ?? String(e));
			stats = null;
		} finally {
			loading = false;
		}
	};

	onMount(() => {
		if ($user?.role !== 'admin') return;
		refresh();
	});

	const recallHitRate = (s: AdoptionStats): number => {
		const calls = s.session_events.recall.calls;
		if (calls === 0) return 0;
		return s.session_events.recall.with_hits / calls;
	};

	const formatPct = (n: number): string => `${(n * 100).toFixed(1)}%`;
	const formatTimestamp = (iso: string): string => {
		try {
			return new Date(iso).toLocaleString();
		} catch {
			return iso;
		}
	};
</script>

<svelte:head>
	<title>Memory adoption · Admin</title>
</svelte:head>

<div class="px-4 py-3 max-w-5xl mx-auto w-full">
	<div class="flex items-center justify-between mb-4">
		<div>
			<h2 class="text-lg font-semibold">Memory adoption</h2>
			<p class="text-xs text-gray-500 dark:text-gray-400">
				Cross-user counts from <code>get_adoption_stats</code>. Admin only.
			</p>
		</div>

		<div class="flex items-center gap-2 text-sm">
			<label for="since-days" class="text-gray-500">Window</label>
			<select
				id="since-days"
				bind:value={sinceDays}
				on:change={refresh}
				class="rounded-sm bg-transparent border border-gray-200 dark:border-gray-700 px-1 py-0.5"
			>
				<option value={1}>1d</option>
				<option value={7}>7d</option>
				<option value={30}>30d</option>
				<option value={90}>90d</option>
			</select>
			<button
				type="button"
				class="px-2 py-0.5 rounded-sm border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-850"
				on:click={refresh}
				disabled={loading}
			>
				Refresh
			</button>
		</div>
	</div>

	{#if loading}
		<div class="flex items-center justify-center py-10">
			<Spinner className="size-5" />
		</div>
	{:else if errorMsg}
		<div
			class="rounded-md border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/40 px-3 py-2 text-sm text-red-800 dark:text-red-200"
		>
			<div class="font-medium">Couldn't load memory stats</div>
			<div class="text-xs mt-0.5">{errorMsg}</div>
			{#if errorMsg.toLowerCase().includes('memory_admin_token')}
				<div class="text-xs mt-1 opacity-75">
					Set <code>MEMORY_ADMIN_TOKEN</code> in the chatbot env (matches the value in MCP-Servers compose)
					and restart the backend.
				</div>
			{/if}
		</div>
	{:else if stats}
		<div class="text-xs text-gray-500 mb-3">
			Snapshot at {formatTimestamp(stats.measured_at)} · window {stats.session_events.window_days}d
		</div>

		<div class="grid grid-cols-1 md:grid-cols-2 gap-3">
			<!-- Entries card -->
			<section
				class="rounded-md border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-3"
			>
				<header class="flex items-baseline justify-between mb-2">
					<h3 class="text-sm font-semibold">Entries</h3>
					<span class="text-2xl font-semibold">{stats.entries.total}</span>
				</header>
				{#if stats.entries.by_scope_and_type.length === 0}
					<p class="text-xs text-gray-500">
						No entries yet — the assistant will save them as users chat.
					</p>
				{:else}
					<table class="w-full text-xs">
						<thead class="text-gray-500">
							<tr>
								<th class="text-left font-normal py-1">scope</th>
								<th class="text-left font-normal py-1">type</th>
								<th class="text-right font-normal py-1">count</th>
							</tr>
						</thead>
						<tbody>
							{#each stats.entries.by_scope_and_type as row}
								<tr class="border-t border-gray-100 dark:border-gray-800">
									<td class="py-1 font-mono">{row.scope}</td>
									<td class="py-1 font-mono">{row.type}</td>
									<td class="py-1 text-right">{row.count}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				{/if}
				<div class="mt-2 text-xs text-gray-500">
					{stats.users} users · {stats.projects} projects
				</div>
			</section>

			<!-- BOPA sessions card -->
			<section
				class="rounded-md border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-3"
			>
				<header class="flex items-baseline justify-between mb-2">
					<h3 class="text-sm font-semibold">BOPA sessions</h3>
					<span class="text-2xl font-semibold">{stats.bopa_sessions.total}</span>
				</header>
				<div class="text-sm">
					<span class="font-medium text-emerald-700 dark:text-emerald-400"
						>{stats.bopa_sessions.active}</span
					>
					<span class="text-gray-500"> active</span>
					<span class="text-gray-400"> · </span>
					<span class="font-medium">{stats.bopa_sessions.total - stats.bopa_sessions.active}</span>
					<span class="text-gray-500"> archived/completed</span>
				</div>
				{#if stats.bopa_sessions.total === 0}
					<p class="text-xs text-gray-500 mt-2">
						No BOPA sessions yet. Try <code>/bopa-haalbaarheid &lt;adres&gt;</code> in chat.
					</p>
				{/if}
			</section>

			<!-- Recent activity card -->
			<section
				class="rounded-md border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-3 md:col-span-2"
			>
				<header class="flex items-baseline justify-between mb-2">
					<h3 class="text-sm font-semibold">
						Recent activity <span class="text-gray-500 font-normal text-xs"
							>(last {stats.session_events.window_days}d)</span
						>
					</h3>
					<span class="text-2xl font-semibold">{stats.session_events.total}</span>
				</header>
				<div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
					<div>
						<div class="text-xs text-gray-500">Recall calls</div>
						<div class="font-medium">{stats.session_events.recall.calls}</div>
					</div>
					<div>
						<div class="text-xs text-gray-500">Recall hit rate</div>
						<div class="font-medium">
							{stats.session_events.recall.calls === 0 ? '—' : formatPct(recallHitRate(stats))}
						</div>
					</div>
					<div>
						<div class="text-xs text-gray-500">Save calls</div>
						<div class="font-medium">{stats.session_events.save.calls}</div>
					</div>
					<div>
						<div class="text-xs text-gray-500">Notes</div>
						<div class="font-medium">{stats.session_events.notes}</div>
					</div>
				</div>
				{#if stats.session_events.by_tool.length > 0}
					<table class="w-full text-xs mt-3">
						<thead class="text-gray-500">
							<tr>
								<th class="text-left font-normal py-1">tool</th>
								<th class="text-right font-normal py-1">calls</th>
								<th class="text-right font-normal py-1">errors</th>
								<th class="text-right font-normal py-1">err rate</th>
							</tr>
						</thead>
						<tbody>
							{#each stats.session_events.by_tool as row}
								<tr class="border-t border-gray-100 dark:border-gray-800">
									<td class="py-1 font-mono">{row.tool}</td>
									<td class="py-1 text-right">{row.calls}</td>
									<td
										class="py-1 text-right {row.errors > 0 ? 'text-red-700 dark:text-red-400' : ''}"
									>
										{row.errors}
									</td>
									<td class="py-1 text-right text-gray-500">
										{row.calls === 0 ? '—' : formatPct(row.errors / row.calls)}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				{/if}
			</section>

			<!-- Per-user breakdown card -->
			<section
				class="rounded-md border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-3 md:col-span-2"
			>
				<header class="flex items-baseline justify-between mb-2">
					<h3 class="text-sm font-semibold">
						Top users <span class="text-gray-500 font-normal text-xs"
							>(by entry count, top {TOP_USERS})</span
						>
					</h3>
				</header>
				{#if stats.entries.by_user.length === 0}
					<p class="text-xs text-gray-500">No per-user activity yet.</p>
				{:else}
					<table class="w-full text-xs">
						<thead class="text-gray-500">
							<tr>
								<th class="text-left font-normal py-1">owner_user_id</th>
								<th class="text-right font-normal py-1">entries</th>
							</tr>
						</thead>
						<tbody>
							{#each stats.entries.by_user.slice(0, TOP_USERS) as row}
								<tr class="border-t border-gray-100 dark:border-gray-800">
									<td class="py-1 font-mono break-all">{row.owner_user_id}</td>
									<td class="py-1 text-right">{row.count}</td>
								</tr>
							{/each}
						</tbody>
					</table>
					{#if stats.entries.by_user.length > TOP_USERS}
						<div class="text-xs text-gray-500 mt-1">
							… and {stats.entries.by_user.length - TOP_USERS} more
						</div>
					{/if}
				{/if}
			</section>
		</div>
	{/if}
</div>
