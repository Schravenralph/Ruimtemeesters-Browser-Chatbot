"""Unit tests for rm-tools/filters/bopa_session_context.py.

Run with:
    pytest rm-tools/tests/test_bopa_inlet_filter.py -v

Tests are pure: the rm-memory MCP HTTP call is patched at requests.post.
"""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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


def _mcp_response(sessions: list[dict]) -> MagicMock:
    """Build a MagicMock that mimics requests.Response for a successful MCP
    tools/call returning the given sessions list."""
    text = json.dumps({'sessions': sessions})
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        'jsonrpc': '2.0',
        'id': 1,
        'result': {
            'content': [{'type': 'text', 'text': text}],
        },
    }
    return resp


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_body(model_id: str = 'rm-assistent') -> dict:
    return {
        'model': model_id,
        'messages': [
            {'role': 'system', 'content': 'Je bent de Ruimtemeesters AI Assistent.'},
            {'role': 'user', 'content': 'hallo'},
        ],
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
    session = {
        'id': '11111111-1111-1111-1111-111111111111',
        'project_id': 42,
        'gemeente_code': 'GM0363',
        'completed_phases': [1],
        'current_phase': 2,
    }
    block = _format_summary(session, others_count=0)
    assert 'ACTIEVE BOPA-SESSIE' in block
    assert 'GM0363' in block
    assert '/bopa-strijdigheid' in block  # next phase = 2
    assert 'Strijdigheid' in block
    assert 'Andere actieve sessies' not in block


def test_format_summary_notes_other_active_sessions():
    session = {
        'id': 'abc',
        'project_id': 1,
        'gemeente_code': 'GM0034',
        'completed_phases': [],
        'current_phase': 1,
    }
    block = _format_summary(session, others_count=2)
    assert 'Andere actieve sessies: 2' in block


def test_format_summary_handles_phase4_blocked_message():
    """Phase 4-6 MCP tools aren't shipped yet — surface a warning rather than
    a fake slash command."""
    session = {
        'id': 'abc',
        'project_id': 1,
        'gemeente_code': 'GM0034',
        'completed_phases': [1, 2, 3],
        'current_phase': 3,
    }
    block = _format_summary(session, others_count=0)
    # Next phase = 4 (Omgevingsaspecten); no slash command exists yet.
    assert 'Omgevingsaspecten' in block
    assert 'MCP-tool nog niet beschikbaar' in block


# --- selection logic via Filter ------------------------------------------


def test_owner_filter_picks_only_matching_user():
    f = Filter()
    f.valves.cache_ttl_s = 0  # no caching across tests
    sessions = [
        {
            'id': 'a',
            'owner_user_id': 'other',
            'status': 'active',
            'updated_at': '2026-04-30T10:00:00Z',
            'completed_phases': [],
            'current_phase': 1,
            'project_id': 1,
            'gemeente_code': 'GM0001',
        },
        {
            'id': 'b',
            'owner_user_id': 'me',
            'status': 'active',
            'updated_at': '2026-04-29T10:00:00Z',
            'completed_phases': [1],
            'current_phase': 2,
            'project_id': 2,
            'gemeente_code': 'GM0002',
        },
    ]
    with patch('filters.bopa_session_context.requests.post', return_value=_mcp_response(sessions)):
        body = _run(f.inlet(_make_body(), __user__={'id': 'me'}, __metadata__={'model_id': 'rm-assistent'}))
    sys_msg = body['messages'][0]['content']
    assert 'GM0002' in sys_msg
    assert 'GM0001' not in sys_msg


def test_picks_most_recent_active_when_user_has_multiple():
    f = Filter()
    f.valves.cache_ttl_s = 0
    sessions = [
        {
            'id': 'older',
            'owner_user_id': 'me',
            'status': 'active',
            'updated_at': '2026-04-20T10:00:00Z',
            'completed_phases': [1],
            'current_phase': 2,
            'project_id': 1,
            'gemeente_code': 'GM-OLDER',
        },
        {
            'id': 'newer',
            'owner_user_id': 'me',
            'status': 'active',
            'updated_at': '2026-04-30T10:00:00Z',
            'completed_phases': [1, 2],
            'current_phase': 3,
            'project_id': 2,
            'gemeente_code': 'GM-NEWER',
        },
    ]
    with patch('filters.bopa_session_context.requests.post', return_value=_mcp_response(sessions)):
        body = _run(f.inlet(_make_body(), __user__={'id': 'me'}, __metadata__={'model_id': 'rm-assistent'}))
    sys_msg = body['messages'][0]['content']
    assert 'GM-NEWER' in sys_msg
    assert 'GM-OLDER' not in sys_msg
    assert 'Andere actieve sessies: 1' in sys_msg


def test_no_active_sessions_is_a_noop():
    f = Filter()
    f.valves.cache_ttl_s = 0
    sessions = [
        {
            'id': 'completed-one',
            'owner_user_id': 'me',
            'status': 'completed',
            'updated_at': '2026-04-30T10:00:00Z',
            'completed_phases': [1, 2, 3, 4, 5, 6],
            'current_phase': None,
            'project_id': 1,
            'gemeente_code': 'GM-DONE',
        },
    ]
    original_body = _make_body()
    with patch('filters.bopa_session_context.requests.post', return_value=_mcp_response(sessions)):
        body = _run(f.inlet(_make_body(), __user__={'id': 'me'}, __metadata__={'model_id': 'rm-assistent'}))
    assert body['messages'][0]['content'] == original_body['messages'][0]['content']
    assert 'ACTIEVE BOPA-SESSIE' not in body['messages'][0]['content']


def test_mcp_502_returns_body_unchanged():
    """If the MCP RPC fails, the chat MUST proceed without injection."""
    import requests as _requests

    f = Filter()
    f.valves.cache_ttl_s = 0
    original_body = _make_body()
    err = _requests.exceptions.HTTPError('502 Bad Gateway')
    failing = MagicMock()
    failing.raise_for_status.side_effect = err
    with patch('filters.bopa_session_context.requests.post', return_value=failing):
        body = _run(f.inlet(_make_body(), __user__={'id': 'me'}, __metadata__={'model_id': 'rm-assistent'}))
    assert body['messages'][0]['content'] == original_body['messages'][0]['content']


def test_mcp_timeout_returns_body_unchanged():
    import requests as _requests

    f = Filter()
    f.valves.cache_ttl_s = 0
    original_body = _make_body()
    with patch(
        'filters.bopa_session_context.requests.post',
        side_effect=_requests.exceptions.Timeout('timed out'),
    ):
        body = _run(f.inlet(_make_body(), __user__={'id': 'me'}, __metadata__={'model_id': 'rm-assistent'}))
    assert body['messages'][0]['content'] == original_body['messages'][0]['content']


def test_user_valves_disabled_short_circuits_mcp_call():
    """When the user has opted out, no RPC is made — saves latency on every
    chat for users who don't want BOPA priming."""
    f = Filter()
    f.valves.cache_ttl_s = 0
    user = {'id': 'me', 'valves': {'enabled': False}}
    with patch('filters.bopa_session_context.requests.post') as mock_post:
        body = _run(f.inlet(_make_body(), __user__=user, __metadata__={'model_id': 'rm-assistent'}))
    mock_post.assert_not_called()
    assert 'ACTIEVE BOPA-SESSIE' not in body['messages'][0]['content']


def test_off_target_model_skips_injection():
    """Switching to rm-demografie-analist must leave the system prompt
    untouched — even if there's an active BOPA session."""
    f = Filter()
    f.valves.cache_ttl_s = 0
    sessions = [
        {
            'id': 'a',
            'owner_user_id': 'me',
            'status': 'active',
            'updated_at': '2026-04-30T10:00:00Z',
            'completed_phases': [],
            'current_phase': 1,
            'project_id': 1,
            'gemeente_code': 'GM0001',
        },
    ]
    with patch('filters.bopa_session_context.requests.post', return_value=_mcp_response(sessions)) as mock_post:
        body = _run(
            f.inlet(
                _make_body('rm-demografie-analist'),
                __user__={'id': 'me'},
                __metadata__={'model_id': 'rm-demografie-analist'},
            )
        )
    mock_post.assert_not_called()
    assert 'ACTIEVE BOPA-SESSIE' not in body['messages'][0]['content']


def test_master_kill_switch_disables_filter():
    f = Filter()
    f.valves.enabled = False
    with patch('filters.bopa_session_context.requests.post') as mock_post:
        body = _run(f.inlet(_make_body(), __user__={'id': 'me'}, __metadata__={'model_id': 'rm-assistent'}))
    mock_post.assert_not_called()
    assert 'ACTIEVE BOPA-SESSIE' not in body['messages'][0]['content']


def test_cache_avoids_second_rpc_within_ttl():
    """Two successive inlets within cache_ttl_s should hit the MCP exactly once."""
    f = Filter()
    f.valves.cache_ttl_s = 60
    sessions = [
        {
            'id': 'a',
            'owner_user_id': 'me',
            'status': 'active',
            'updated_at': '2026-04-30T10:00:00Z',
            'completed_phases': [],
            'current_phase': 1,
            'project_id': 1,
            'gemeente_code': 'GM0001',
        },
    ]
    with patch('filters.bopa_session_context.requests.post', return_value=_mcp_response(sessions)) as mock_post:
        _run(f.inlet(_make_body(), __user__={'id': 'me'}, __metadata__={'model_id': 'rm-assistent'}))
        _run(f.inlet(_make_body(), __user__={'id': 'me'}, __metadata__={'model_id': 'rm-assistent'}))
    assert mock_post.call_count == 1


def test_missing_user_id_skips_injection():
    f = Filter()
    f.valves.cache_ttl_s = 0
    with patch('filters.bopa_session_context.requests.post') as mock_post:
        body = _run(f.inlet(_make_body(), __user__={}, __metadata__={'model_id': 'rm-assistent'}))
    mock_post.assert_not_called()
    assert 'ACTIEVE BOPA-SESSIE' not in body['messages'][0]['content']


def test_inserts_system_message_when_none_present():
    """Body without a system message: filter prepends one rather than crashing."""
    f = Filter()
    f.valves.cache_ttl_s = 0
    sessions = [
        {
            'id': 'a',
            'owner_user_id': 'me',
            'status': 'active',
            'updated_at': '2026-04-30T10:00:00Z',
            'completed_phases': [],
            'current_phase': 1,
            'project_id': 1,
            'gemeente_code': 'GM0001',
        },
    ]
    body_no_system = {
        'model': 'rm-assistent',
        'messages': [{'role': 'user', 'content': 'hi'}],
    }
    with patch('filters.bopa_session_context.requests.post', return_value=_mcp_response(sessions)):
        body = _run(f.inlet(body_no_system, __user__={'id': 'me'}, __metadata__={'model_id': 'rm-assistent'}))
    assert body['messages'][0]['role'] == 'system'
    assert 'ACTIEVE BOPA-SESSIE' in body['messages'][0]['content']
    assert body['messages'][1]['role'] == 'user'


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
