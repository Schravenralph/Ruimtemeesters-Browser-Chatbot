"""Unit tests for rm-tools/filters/memory_recall_context.py.

Run with:
    pytest rm-tools/tests/test_memory_recall_inlet_filter.py -v

Tests are pure: the rm-memory MCP HTTP call is patched at the
`httpx.AsyncClient` constructor so neither the real client nor the
network is touched.
"""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest  # noqa: F401  (not used directly but pytest discovers tests)

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from filters.memory_recall_context import (  # noqa: E402
    Filter,
    _format_block,
    _last_user_message,
)


def _mcp_response(matches: list[dict]) -> MagicMock:
    """Build a MagicMock that mimics httpx.Response for a successful MCP
    tools/call returning the given matches list."""
    text = json.dumps({'matches': matches})
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


def _patch_async_client(response: MagicMock | None = None, *, post_side_effect=None):
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
    return patch('filters.memory_recall_context.httpx.AsyncClient', constructor), post_mock


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_body(model_id: str = 'rm-assistent', user_msg: str = 'Wat zijn de bouwhoogtes in Utrecht?') -> dict:
    return {
        'model': model_id,
        'messages': [
            {'role': 'system', 'content': 'Je bent de Ruimtemeesters AI Assistent.'},
            {'role': 'user', 'content': user_msg},
        ],
    }


def _match(
    *,
    name: str = 'utrecht-preference',
    description: str = 'Voor Utrecht altijd Beleidsregels Hoogbouw 2024 raadplegen',
    scope: str = 'user',
    type_: str = 'preference',
) -> dict:
    return {
        'id': f'id-{name}',
        'name': name,
        'type': type_,
        'scope': scope,
        'description': description,
        'snippet': '... <em>Utrecht</em> ...',
        'score': 0.42,
        'owner_user_id': 'me',
        'project_id': None,
    }


# --- pure helpers ---------------------------------------------------------


def test_last_user_message_picks_most_recent_user_turn():
    msgs = [
        {'role': 'system', 'content': 'sys'},
        {'role': 'user', 'content': 'eerste vraag'},
        {'role': 'assistant', 'content': 'antwoord'},
        {'role': 'user', 'content': 'tweede vraag'},
    ]
    assert _last_user_message(msgs) == 'tweede vraag'


def test_last_user_message_handles_content_arrays():
    """OpenAI-style content arrays with text + image parts."""
    msgs = [
        {
            'role': 'user',
            'content': [
                {'type': 'text', 'text': 'wat zie je hier?'},
                {'type': 'image', 'image_url': '...'},
            ],
        }
    ]
    assert _last_user_message(msgs) == 'wat zie je hier?'


def test_last_user_message_returns_empty_when_no_user_turn():
    assert _last_user_message([{'role': 'system', 'content': 'sys'}]) == ''
    assert _last_user_message([]) == ''


def test_format_block_lists_name_description_and_scope():
    block = _format_block([_match(name='foo', description='bar', scope='user')])
    assert 'EERDER OPGESLAGEN MEMORIES' in block
    assert '`foo`' in block
    assert 'bar' in block
    assert '(user)' in block
    assert 'get_memory' in block


def test_format_block_falls_back_to_name_when_description_blank():
    block = _format_block([_match(name='nameonly', description='')])
    assert '`nameonly`' in block
    assert 'nameonly' in block


# --- inlet behaviour -------------------------------------------------------


def test_match_injected_into_system_prompt():
    f = Filter()
    f.valves.cache_ttl_s = 0
    matches = [_match(name='util-pref', description='Voor Utrecht: Beleidsregels Hoogbouw 2024')]
    patcher, _post = _patch_async_client(_mcp_response(matches))
    with patcher:
        body = _run(
            f.inlet(
                _make_body(),
                __user__={'id': 'me'},
                __metadata__={'model_id': 'rm-assistent'},
            )
        )
    sys_msg = body['messages'][0]['content']
    assert 'EERDER OPGESLAGEN MEMORIES' in sys_msg
    assert 'util-pref' in sys_msg
    assert 'Beleidsregels Hoogbouw 2024' in sys_msg


def test_zero_matches_is_a_noop():
    f = Filter()
    f.valves.cache_ttl_s = 0
    original = _make_body()
    patcher, _post = _patch_async_client(_mcp_response([]))
    with patcher:
        body = _run(
            f.inlet(
                _make_body(),
                __user__={'id': 'me'},
                __metadata__={'model_id': 'rm-assistent'},
            )
        )
    assert body['messages'][0]['content'] == original['messages'][0]['content']


def test_short_query_skips_rpc():
    """Below min_query_chars (default 4) the RPC must not fire — guards
    against noisy hits on 'hi' / 'ok' / 'jaja'."""
    f = Filter()
    f.valves.cache_ttl_s = 0
    patcher, post_mock = _patch_async_client(_mcp_response([_match()]))
    with patcher:
        body = _run(
            f.inlet(
                _make_body(user_msg='hoi'),
                __user__={'id': 'me'},
                __metadata__={'model_id': 'rm-assistent'},
            )
        )
    post_mock.assert_not_called()
    assert 'EERDER OPGESLAGEN MEMORIES' not in body['messages'][0]['content']


def test_other_model_is_noop():
    f = Filter()
    patcher, post_mock = _patch_async_client(_mcp_response([_match()]))
    with patcher:
        body = _run(
            f.inlet(
                _make_body(model_id='gpt-4o'),
                __user__={'id': 'me'},
                __metadata__={'model_id': 'gpt-4o'},
            )
        )
    post_mock.assert_not_called()
    assert 'EERDER OPGESLAGEN MEMORIES' not in body['messages'][0]['content']


def test_user_opted_out_is_noop():
    f = Filter()
    patcher, post_mock = _patch_async_client(_mcp_response([_match()]))
    with patcher:
        body = _run(
            f.inlet(
                _make_body(),
                __user__={'id': 'me', 'valves': {'enabled': False}},
                __metadata__={'model_id': 'rm-assistent'},
            )
        )
    post_mock.assert_not_called()
    assert 'EERDER OPGESLAGEN MEMORIES' not in body['messages'][0]['content']


def test_mcp_502_returns_body_unchanged():
    f = Filter()
    f.valves.cache_ttl_s = 0
    original = _make_body()
    failing = MagicMock()
    failing.raise_for_status.side_effect = httpx.HTTPStatusError(
        '502 Bad Gateway', request=MagicMock(), response=MagicMock()
    )
    patcher, _post = _patch_async_client(failing)
    with patcher:
        body = _run(
            f.inlet(
                _make_body(),
                __user__={'id': 'me'},
                __metadata__={'model_id': 'rm-assistent'},
            )
        )
    assert body['messages'][0]['content'] == original['messages'][0]['content']


def test_mcp_timeout_returns_body_unchanged():
    f = Filter()
    f.valves.cache_ttl_s = 0
    patcher, _post = _patch_async_client(post_side_effect=httpx.TimeoutException('timed out'))
    with patcher:
        body = _run(
            f.inlet(
                _make_body(),
                __user__={'id': 'me'},
                __metadata__={'model_id': 'rm-assistent'},
            )
        )
    assert 'EERDER OPGESLAGEN MEMORIES' not in body['messages'][0]['content']


def test_cache_hits_avoid_second_rpc_for_same_query():
    f = Filter()
    f.valves.cache_ttl_s = 60
    patcher, post_mock = _patch_async_client(_mcp_response([_match()]))
    with patcher:
        _run(f.inlet(_make_body(), __user__={'id': 'me'}, __metadata__={'model_id': 'rm-assistent'}))
        _run(f.inlet(_make_body(), __user__={'id': 'me'}, __metadata__={'model_id': 'rm-assistent'}))
    assert post_mock.await_count == 1


def test_disabled_valves_short_circuit():
    f = Filter()
    f.valves.enabled = False
    patcher, post_mock = _patch_async_client(_mcp_response([_match()]))
    with patcher:
        body = _run(
            f.inlet(
                _make_body(),
                __user__={'id': 'me'},
                __metadata__={'model_id': 'rm-assistent'},
            )
        )
    post_mock.assert_not_called()
    assert 'EERDER OPGESLAGEN MEMORIES' not in body['messages'][0]['content']


def test_query_uses_last_user_message_not_first():
    """Multi-turn chat: the FTS query must be the *latest* user message, not
    the original one."""
    f = Filter()
    f.valves.cache_ttl_s = 0
    body_in = {
        'model': 'rm-assistent',
        'messages': [
            {'role': 'system', 'content': 'sys'},
            {'role': 'user', 'content': 'allereerste vraag over Utrecht'},
            {'role': 'assistant', 'content': 'antwoord'},
            {'role': 'user', 'content': 'tweede vraag over Den Haag'},
        ],
    }
    patcher, post_mock = _patch_async_client(_mcp_response([_match()]))
    with patcher:
        _run(
            f.inlet(
                body_in,
                __user__={'id': 'me'},
                __metadata__={'model_id': 'rm-assistent'},
            )
        )
    sent = post_mock.call_args.kwargs.get('json') or post_mock.call_args.args[0]
    args = sent['params']['arguments']
    assert args['query'] == 'tweede vraag over Den Haag'
