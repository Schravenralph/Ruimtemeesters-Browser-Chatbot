import { WEBUI_API_BASE_URL } from '$lib/constants';

export interface CountedScopeType {
	scope: string;
	type: string;
	count: number;
}

export interface CountedUser {
	owner_user_id: string;
	count: number;
}

export interface CountedTool {
	tool: string;
	calls: number;
	errors: number;
}

export interface AdoptionStats {
	measured_at: string;
	entries: {
		total: number;
		by_scope_and_type: CountedScopeType[];
		by_user: CountedUser[];
	};
	session_events: {
		window_days: number;
		total: number;
		by_tool: CountedTool[];
		recall: { calls: number; with_hits: number };
		save: { calls: number };
		notes: number;
	};
	bopa_sessions: { total: number; active: number };
	projects: number;
	users: number;
}

/** GET /api/v1/admin/memory/stats — admin-only memory adoption snapshot. */
export const getAdoptionStats = async (
	token: string,
	sinceDays?: number
): Promise<AdoptionStats> => {
	// `error` and `caught` together: an empty-string detail is still an error
	// (a truthy-only check would let `null` leak as AdoptionStats — Bugbot
	// finding on PR #57).
	let error: { detail?: string } | string | null = null;
	let caught = false;

	const params = new URLSearchParams();
	if (sinceDays !== undefined) {
		params.set('since_days', String(sinceDays));
	}
	const qs = params.toString();
	const url = `${WEBUI_API_BASE_URL}/admin/memory/stats${qs ? `?${qs}` : ''}`;

	const res = await fetch(url, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			Authorization: `Bearer ${token}`
		}
	})
		.then(async (r) => {
			if (!r.ok) throw await r.json();
			return r.json();
		})
		.catch((err) => {
			console.error(err);
			error = err?.detail ?? err;
			caught = true;
			return null;
		});

	if (caught) {
		// Use truthy check so an empty-string `detail` doesn't throw "" —
		// an empty string would hit the page's `{:else if errorMsg}` as
		// falsy and blank the whole panel (Bugbot finding on PR #59).
		throw error || 'request failed';
	}
	return res as AdoptionStats;
};
