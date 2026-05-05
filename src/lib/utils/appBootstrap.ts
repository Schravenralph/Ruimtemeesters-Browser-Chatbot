import { get } from 'svelte/store';

import {
	banners,
	config,
	models,
	settings,
	terminalServers,
	tools,
	toolServers
} from '$lib/stores';
import { getModels, getToolServersData } from '$lib/apis';
import { getBanners } from '$lib/apis/configs';
import { getTerminalServers } from '$lib/apis/terminal';
import { getTools } from '$lib/apis/tools';
import { getUserSettings } from '$lib/apis/users';
import { WEBUI_API_BASE_URL } from '$lib/constants';

export interface BootstrapHooks {
	onToolServerError?: (url: string | undefined) => void;
	onTerminalServerError?: (url: string | undefined) => void;
}

export async function loadUserSettings(token: string): Promise<void> {
	let userSettings = await getUserSettings(token).catch((error) => {
		console.error(error);
		return null;
	});

	if (!userSettings) {
		try {
			userSettings = JSON.parse(localStorage.getItem('settings') ?? '{}');
		} catch (e: unknown) {
			console.error('Failed to parse settings from localStorage', e);
			userSettings = {};
		}
	}

	if (userSettings?.ui) {
		settings.set(userSettings.ui);
	}
}

export async function loadModels(token: string): Promise<void> {
	const cfg = get(config) as any;
	const s = get(settings) as any;
	models.set(
		await getModels(
			token,
			cfg?.features?.enable_direct_connections ? (s?.directConnections ?? null) : null
		)
	);
}

export async function loadToolServers(token: string, hooks: BootstrapHooks = {}): Promise<void> {
	const s = get(settings) as any;

	let toolServersData = await getToolServersData(s?.toolServers ?? []);
	toolServersData = toolServersData.filter((data: any) => {
		if (!data || data.error) {
			hooks.onToolServerError?.(data?.url);
			return false;
		}
		return true;
	});
	(toolServers as any).set(toolServersData);

	const enabledTerminals = (s?.terminalServers ?? []).filter((t: any) => t.enabled);
	if (enabledTerminals.length > 0) {
		let terminalServersData = await getToolServersData(
			enabledTerminals.map((t: any) => ({
				url: t.url,
				auth_type: t.auth_type ?? 'bearer',
				key: t.key ?? '',
				path: t.path ?? '/openapi.json',
				config: { enable: true }
			}))
		);
		terminalServersData = terminalServersData
			.filter((data: any) => {
				if (!data || data.error) {
					hooks.onTerminalServerError?.(data?.url);
					return false;
				}
				return true;
			})
			.map((data: any, i: number) => ({
				...data,
				key: enabledTerminals[i]?.key ?? ''
			}));

		(terminalServers as any).set(terminalServersData);
	} else {
		terminalServers.set([]);
	}

	const systemTerminals = await getTerminalServers(token);
	if (systemTerminals.length > 0) {
		const terminalEntries = systemTerminals.map((t: any) => ({
			id: t.id,
			url: `${WEBUI_API_BASE_URL}/terminals/${t.id}`,
			name: t.name,
			key: token
		}));
		(terminalServers as any).update((existing: any[]) => [...existing, ...terminalEntries]);
	}
}

export async function loadBanners(token: string): Promise<void> {
	const bannersData = await getBanners(token);
	banners.set(bannersData);
}

export async function loadTools(token: string): Promise<void> {
	const toolsData = await getTools(token);
	tools.set(toolsData);
}

/**
 * Load every store Chat.svelte reads from. Settings must resolve before models
 * and tool-servers — both branch on `$settings?.directConnections` and
 * `$settings?.toolServers`. Used by `(app)/+layout.svelte` and
 * `embed/+layout.svelte` so the embed surface gets identical data.
 */
export async function loadChatBootstrap(token: string, hooks: BootstrapHooks = {}): Promise<void> {
	await Promise.all([
		loadBanners(token).catch((e) => console.error('Failed to load banners:', e)),
		loadTools(token).catch((e) => console.error('Failed to load tools:', e)),
		(async () => {
			await loadUserSettings(token).catch((e) => console.error('Failed to load user settings:', e));
			await Promise.all([
				loadModels(token).catch((e) => console.error('Failed to load models:', e)),
				loadToolServers(token, hooks).catch((e) => console.error('Failed to load tool servers:', e))
			]);
		})()
	]);
}
