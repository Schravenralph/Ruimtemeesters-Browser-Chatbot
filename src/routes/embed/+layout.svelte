<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { onMount, tick, getContext } from 'svelte';

	import { goto } from '$app/navigation';

	import { settings, showSettings, showSidebar, user } from '$lib/stores';
	import { loadChatBootstrap } from '$lib/utils/appBootstrap';
	import { setTextScale } from '$lib/utils/text-scale';

	import SettingsModal from '$lib/components/chat/SettingsModal.svelte';
	import AccountPending from '$lib/components/layout/Overlay/AccountPending.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';

	const i18n = getContext('i18n');

	let loaded = false;

	onMount(async () => {
		if ($user === undefined || $user === null) {
			await goto('/auth');
			return;
		}
		if (!['user', 'admin'].includes($user?.role)) {
			return;
		}

		// Sidebar would consume ~260px of a 400px iframe panel and Chat
		// computes its own width from `$showSidebar`, so force-close it
		// before Chat mounts.
		showSidebar.set(false);

		await loadChatBootstrap(localStorage.token, {
			onToolServerError: (url) =>
				toast.error($i18n.t(`Failed to connect to {{URL}} OpenAPI tool server`, { URL: url })),
			onTerminalServerError: (url) =>
				toast.error($i18n.t(`Failed to connect to {{URL}} terminal server`, { URL: url }))
		});

		setTextScale($settings?.textScale ?? 1);

		await tick();
		loaded = true;
	});
</script>

<SettingsModal bind:show={$showSettings} />

{#if $user}
	<div class="embed relative">
		<div
			class="text-gray-700 dark:text-gray-100 bg-white dark:bg-gray-900 h-screen max-h-[100dvh] overflow-auto flex flex-row justify-end"
		>
			{#if !['user', 'admin'].includes($user?.role)}
				<AccountPending />
			{:else if loaded}
				<slot />
			{:else}
				<div class="w-full flex-1 h-full flex items-center justify-center">
					<Spinner className="size-5" />
				</div>
			{/if}
		</div>
	</div>
{/if}
