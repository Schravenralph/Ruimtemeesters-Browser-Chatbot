"""Unit tests for rm-tools/filters/bopa_session_context.py.

Run with:
    pytest rm-tools/tests/test_bopa_inlet_filter.py -v

Tests are pure: the rm-memory MCP HTTP call is patched at the
`httpx.AsyncClient` constructor so neither the real client nor the
network is touched. Fixture timestamps are computed relative to `now`
so the recency gate (max_age_hours, default 168) doesn't drop them
when test wall-clock drifts.
"""

import asyncio
import datetime as dt
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# Make the filters package importable without requiring an editable install.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from filters.bopa_session_context import (  # noqa: E402
    Filter,
    _compute_dependencies_met,
    _format_summary,
)

# --- helpers --------------------------------------------------------------


def _now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def _hours_ago_iso(hours: float) -> str:
    return (dt.datetime.now(dt.UTC) - dt.timedelta(hours=hours)).isoformat()


def _mcp_response(sessions: list[dict], *, framing: str = 'sse') -> MagicMock:
    """Build a MagicMock that mimics httpx.Response for a successful MCP
    tools/call returning the given sessions list.

    Defaults to SSE framing because the rm-memory MCP's Streamable HTTP
    transport returns `event: message\\ndata: {...}` whenever the request
    accepts both `application/json` and `text/event-stream` (which it
    must — the server enforces that). `framing='json'` is kept for
    coverage of the rare pure-JSON path.
    """
    inner = json.dumps({'sessions': sessions})
    envelope = {
        'jsonrpc': '2.0',
        'id': 1,
        'result': {
            'content': [{'type': 'text', 'text': inner}],
        },
    }
    if framing == 'json':
        body = json.dumps(envelope)
    else:
        body = f'event: message\ndata: {json.dumps(envelope)}\n'
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.text = body
    return resp


def _patch_async_client(response: MagicMock | None = None, *, post_side_effect=None):
    """Patch httpx.AsyncClient so `async with httpx.AsyncClient() as c: await c.post(...)`
    returns our mock. Returns the patcher and the AsyncMock for client.post — the
    test can call .assert_not_called() on the latter to verify short-circuits.
    """
    post_mock = AsyncMock()
    if post_side_effect is not None:
        post_mock.side_effect = post_side_effect
    elif response is not None:
        post_mock.return_value = response

    client_instance = MagicMock()
    client_instance.post = post_mock
    client_instance.__aenter__ = AsyncMock(return_value=client_instance)
    client_instance.__aexit__ = AsyncMock(return_value=None)

    constructor = MagicMock(return_value=client_instance)
    return patch('filters.bopa_session_context.httpx.AsyncClient', constructor), post_mock


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_body(model_id: str = 'rm-assistent') -> dict:
    return {
        'model': model_id,
        'messages': [
            {'role': 'system', 'content': 'Je bent de Ruimtemeesters AI Assistent.'},
            {'role': 'user', 'content': 'hallo'},
        ],
    }


def _session(
    *,
    sid: str = 'a',
    owner: str = 'me',
    status: str = 'active',
    completed: list[int] | None = None,
    current: int | None = 1,
    project_id: int = 1,
    gemeente: str = 'GM0001',
    updated_at: str | None = None,
) -> dict:
    return {
        'id': sid,
        'owner_user_id': owner,
        'status': status,
        'updated_at': updated_at or _now_iso(),
        'completed_phases': completed or [],
        'current_phase': current,
        'project_id': project_id,
        'gemeente_code': gemeente,
    }


# --- pure helpers --------------------------------------------------------


def test_compute_dependencies_met_empty():
    assert _compute_dependencies_met([]) == [1]


def test_compute_dependencies_met_phase1_done_unlocks_2_and_3():
    assert _compute_dependencies_met([1]) == [2, 3]


def test_compute_dependencies_met_phase123_done_unlocks_4_and_5():
    assert _compute_dependencies_met([1, 2, 3]) == [4, 5]


def test_compute_dependencies_met_unlocks_phase6_when_5_done():
    assert _compute_dependencies_met([1, 2, 3, 4, 5]) == [6]


def test_format_summary_includes_phase_label_and_slash_command():
    block = _format_summary(
        _session(sid='11111111-1111-1111-1111-111111111111', completed=[1], current=2, gemeente='GM0363'),
        others_count=0,
    )
    assert 'ACTIEVE BOPA-SESSIE' in block
    assert 'GM0363' in block
    assert '/bopa-strijdigheid' in block  # next phase = 2
    assert 'Strijdigheid' in block
    assert 'Andere actieve sessies' not in block


def test_format_summary_notes_other_active_sessions():
    block = _format_summary(_session(), others_count=2)
    assert 'Andere actieve sessies: 2' in block


def test_format_summary_handles_phase4_blocked_message():
    """Phase 4-6 MCP tools aren't shipped yet — surface a warning rather than
    a fake slash command."""
    block = _format_summary(_session(completed=[1, 2, 3], current=3), others_count=0)
    # Next phase = 4 (Omgevingsaspecten); no slash command exists yet.
    assert 'Omgevingsaspecten' in block
    assert 'MCP-tool nog niet beschikbaar' in block


# --- selection logic via Filter ------------------------------------------


def test_owner_filter_picks_only_matching_user():
    f = Filter()
    f.valves.cache_ttl_s = 0  # no caching across tests
    sessions = [
        _session(sid='a', owner='other', gemeente='GM0001'),
        _session(sid='b', owner='me', completed=[1], current=2, gemeente='GM0002'),
    ]
    patcher, _post = _patch_async_client(_mcp_response(sessions))
    with patcher:
        body = _run(f.inlet(_make_body(), __user__={'id': 'me'}, __metadata__={'model_id': 'rm-assistent'}))
    sys_msg = body['messages'][0]['content']
    assert 'GM0002' in sys_msg
    assert 'GM0001' not in sys_msg


def test_picks_most_recent_active_when_user_has_multiple():
    f = Filter()
    f.valves.cache_ttl_s = 0
    sessions = [
        _session(sid='older', updated_at=_hours_ago_iso(48), gemeente='GM-OLDER', completed=[1], current=2),
        _session(sid='newer', updated_at=_hours_ago_iso(1), gemeente='GM-NEWER', completed=[1, 2], current=3),
    ]
    patcher, _post = _patch_async_client(_mcp_response(sessions))
    with patcher:
        body = _run(f.inlet(_make_body(), __user__={'id': 'me'}, __metadata__={'model_id': 'rm-assistent'}))
    sys_msg = body['messages'][0]['content']
    assert 'GM-NEWER' in sys_msg
    assert 'GM-OLDER' not in sys_msg
    assert 'Andere actieve sessies: 1' in sys_msg


def test_no_active_sessions_is_a_noop():
    f = Filter()
    f.valves.cache_ttl_s = 0
    sessions = [
        _session(
            sid='completed-one', status='completed', completed=[1, 2, 3, 4, 5, 6], current=None, gemeente='GM-DONE'
        )
    ]
    original_body = _make_body()
    patcher, _post = _patch_async_client(_mcp_response(sessions))
    with patcher:
        body = _run(f.inlet(_make_body(), __user__={'id': 'me'}, __metadata__={'model_id': 'rm-assistent'}))
    assert body['messages'][0]['content'] == original_body['messages'][0]['content']
    assert 'ACTIEVE BOPA-SESSIE' not in body['messages'][0]['content']


def test_stale_active_session_is_skipped():
    """A session with status='active' but updated_at older than max_age_hours
    must not auto-load. Guards against forgotten sessions from months ago."""
    f = Filter()
    f.valves.cache_ttl_s = 0
    f.valves.max_age_hours = 24  # tighten the window for this test
    sessions = [_session(updated_at=_hours_ago_iso(72), gemeente='GM-STALE')]  # 3 days old
    patcher, _post = _patch_async_client(_mcp_response(sessions))
    with patcher:
        body = _run(f.inlet(_make_body(), __user__={'id': 'me'}, __metadata__={'model_id': 'rm-assistent'}))
    assert 'GM-STALE' not in body['messages'][0]['content']
    assert 'ACTIEVE BOPA-SESSIE' not in body['messages'][0]['content']


def test_recent_session_within_window_injects():
    """Mirror of the staleness test: 12h-old session with 24h window injects."""
    f = Filter()
    f.valves.cache_ttl_s = 0
    f.valves.max_age_hours = 24
    sessions = [_session(updated_at=_hours_ago_iso(12), gemeente='GM-FRESH')]
    patcher, _post = _patch_async_client(_mcp_response(sessions))
    with patcher:
        body = _run(f.inlet(_make_body(), __user__={'id': 'me'}, __metadata__={'model_id': 'rm-assistent'}))
    assert 'GM-FRESH' in body['messages'][0]['content']


def test_mcp_502_returns_body_unchanged():
    """If the MCP RPC fails, the chat MUST proceed without injection."""
    f = Filter()
    f.valves.cache_ttl_s = 0
    original_body = _make_body()
    failing = MagicMock()
    failing.raise_for_status.side_effect = httpx.HTTPStatusError(
        '502 Bad Gateway', request=MagicMock(), response=MagicMock()
    )
    patcher, _post = _patch_async_client(failing)
    with patcher:
        body = _run(f.inlet(_make_body(), __user__={'id': 'me'}, __metadata__={'model_id': 'rm-assistent'}))
    assert body['messages'][0]['content'] == original_body['messages'][0]['content']


def test_mcp_timeout_returns_body_unchanged():
    f = Filter()
    f.valves.cache_ttl_s = 0
    original_body = _make_body()
    patcher, _post = _patch_async_client(post_side_effect=httpx.TimeoutException('timed out'))
    with patcher:
        body = _run(f.inlet(_make_body(), __user__={'id': 'me'}, __metadata__={'model_id': 'rm-assistent'}))
    assert body['messages'][0]['content'] == original_body['messages'][0]['content']


def test_user_valves_disabled_short_circuits_mcp_call():
    """When the user has opted out, no RPC is made — saves latency on every
    chat for users who don't want BOPA priming."""
    f = Filter()
    f.valves.cache_ttl_s = 0
    user = {'id': 'me', 'valves': {'enabled': False}}
    patcher, post_mock = _patch_async_client(_mcp_response([]))
    with patcher:
        body = _run(f.inlet(_make_body(), __user__=user, __metadata__={'model_id': 'rm-assistent'}))
    post_mock.assert_not_called()
    assert 'ACTIEVE BOPA-SESSIE' not in body['messages'][0]['content']


def test_off_target_model_skips_injection():
    """Switching to rm-demografie-analist must leave the system prompt
    untouched — even if there's an active BOPA session."""
    f = Filter()
    f.valves.cache_ttl_s = 0
    sessions = [_session()]
    patcher, post_mock = _patch_async_client(_mcp_response(sessions))
    with patcher:
        body = _run(
            f.inlet(
                _make_body('rm-demografie-analist'),
                __user__={'id': 'me'},
                __metadata__={'model_id': 'rm-demografie-analist'},
            )
        )
    post_mock.assert_not_called()
    assert 'ACTIEVE BOPA-SESSIE' not in body['messages'][0]['content']


def test_master_kill_switch_disables_filter():
    f = Filter()
    f.valves.enabled = False
    patcher, post_mock = _patch_async_client(_mcp_response([]))
    with patcher:
        body = _run(f.inlet(_make_body(), __user__={'id': 'me'}, __metadata__={'model_id': 'rm-assistent'}))
    post_mock.assert_not_called()
    assert 'ACTIEVE BOPA-SESSIE' not in body['messages'][0]['content']


def test_cache_avoids_second_rpc_within_ttl():
    """Two successive inlets within cache_ttl_s should hit the MCP exactly once."""
    f = Filter()
    f.valves.cache_ttl_s = 60
    sessions = [_session()]
    patcher, post_mock = _patch_async_client(_mcp_response(sessions))
    with patcher:
        _run(f.inlet(_make_body(), __user__={'id': 'me'}, __metadata__={'model_id': 'rm-assistent'}))
        _run(f.inlet(_make_body(), __user__={'id': 'me'}, __metadata__={'model_id': 'rm-assistent'}))
    assert post_mock.call_count == 1


def test_missing_user_id_skips_injection():
    f = Filter()
    f.valves.cache_ttl_s = 0
    patcher, post_mock = _patch_async_client(_mcp_response([]))
    with patcher:
        body = _run(f.inlet(_make_body(), __user__={}, __metadata__={'model_id': 'rm-assistent'}))
    post_mock.assert_not_called()
    assert 'ACTIEVE BOPA-SESSIE' not in body['messages'][0]['content']


def test_inserts_system_message_when_none_present():
    """Body without a system message: filter prepends one rather than crashing."""
    f = Filter()
    f.valves.cache_ttl_s = 0
    sessions = [_session()]
    body_no_system = {
        'model': 'rm-assistent',
        'messages': [{'role': 'user', 'content': 'hi'}],
    }
    patcher, _post = _patch_async_client(_mcp_response(sessions))
    with patcher:
        body = _run(f.inlet(body_no_system, __user__={'id': 'me'}, __metadata__={'model_id': 'rm-assistent'}))
    assert body['messages'][0]['role'] == 'system'
    assert 'ACTIEVE BOPA-SESSIE' in body['messages'][0]['content']
    assert body['messages'][1]['role'] == 'user'


# --- recency helper directly ---------------------------------------------


def test_is_recent_with_timezone_aware_iso():
    f = Filter()
    f.valves.max_age_hours = 24
    assert f._is_recent({'updated_at': _hours_ago_iso(1)}) is True
    assert f._is_recent({'updated_at': _hours_ago_iso(48)}) is False


def test_is_recent_with_naive_iso_treated_as_utc():
    f = Filter()
    f.valves.max_age_hours = 24
    naive = (dt.datetime.now(dt.UTC) - dt.timedelta(hours=1)).replace(tzinfo=None).isoformat()
    assert f._is_recent({'updated_at': naive}) is True


def test_is_recent_missing_or_unparseable_is_stale():
    f = Filter()
    assert f._is_recent({}) is False
    assert f._is_recent({'updated_at': ''}) is False
    assert f._is_recent({'updated_at': 'not-a-date'}) is False


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
