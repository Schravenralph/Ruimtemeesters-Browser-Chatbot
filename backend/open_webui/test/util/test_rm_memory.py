"""Unit tests for backend/open_webui/routers/rm_memory.py.

Exercises `_call_list_memories` directly and mocks `httpx.AsyncClient`.
No FastAPI test client, no DB.

Run with:
    pytest backend/open_webui/test/util/test_rm_memory.py -v
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

from open_webui.routers.rm_memory import (
    ListMemoriesOutput,
    _call_list_memories,
    _resolve_gateway_token,
)


SAMPLE_OUTPUT = {
    'entries': [
        {
            'name': 'identity',
            'type': 'user',
            'scope': 'user',
            'description': 'sole admin, never use other RM emails',
            'owner_user_id': 'clerk:ralph',
            'project_id': None,
            'updated_at': '2026-05-01T12:00:00.000Z',
        },
        {
            'name': 'project_brief',
            'type': 'project',
            'scope': 'project',
            'description': 'BOPA Markt 1, Den Bosch',
            'owner_user_id': 'clerk:ralph',
            'project_id': '7',
            'updated_at': '2026-05-05T08:00:00.000Z',
        },
    ],
}


def _sse_response(payload: dict, *, framing: str = 'sse') -> MagicMock:
    inner = json.dumps(payload)
    envelope = {
        'jsonrpc': '2.0',
        'id': 'rpc-id',
        'result': {'content': [{'type': 'text', 'text': inner}]},
    }
    body = json.dumps(envelope) if framing == 'json' else f'event: message\ndata: {json.dumps(envelope)}\n'
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.text = body
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
    return (
        patch(
            'open_webui.routers.rm_memory.httpx.AsyncClient',
            MagicMock(return_value=client_instance),
        ),
        post_mock,
    )


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# --- gateway token ---------------------------------------------------------


def test_missing_gateway_token_returns_503(monkeypatch):
    monkeypatch.delenv('MEMORY_GATEWAY_TOKEN', raising=False)
    with pytest.raises(HTTPException) as exc:
        _resolve_gateway_token()
    assert exc.value.status_code == 503
    assert 'MEMORY_GATEWAY_TOKEN' in exc.value.detail


def test_blank_gateway_token_returns_503(monkeypatch):
    monkeypatch.setenv('MEMORY_GATEWAY_TOKEN', '   ')
    with pytest.raises(HTTPException) as exc:
        _resolve_gateway_token()
    assert exc.value.status_code == 503


# --- happy path ------------------------------------------------------------


def test_happy_path_returns_typed_payload(monkeypatch):
    monkeypatch.setenv('MEMORY_GATEWAY_TOKEN', 'gateway-secret')
    monkeypatch.setenv('RM_MEMORY_MCP_URL', 'http://test-memory:3200/mcp')

    patcher, post_mock = _patch_async_client(_sse_response(SAMPLE_OUTPUT))
    with patcher:
        payload = _run(
            _call_list_memories(
                user_email='ralph@example.org',
                scope=None,
                project_id=None,
                memory_type=None,
                limit=None,
            )
        )

    typed = ListMemoriesOutput.model_validate(payload)
    assert len(typed.entries) == 2
    assert typed.entries[0].name == 'identity'
    assert typed.entries[1].project_id == '7'

    call = post_mock.call_args
    assert call.args[0] == 'http://test-memory:3200/mcp'
    body = call.kwargs['json']
    assert body['method'] == 'tools/call'
    assert body['params']['name'] == 'list_memories'
    # No optional args passed → empty arguments object.
    assert body['params']['arguments'] == {}

    headers = call.kwargs['headers']
    assert headers['Authorization'] == 'Bearer gateway-secret'
    assert headers['X-Forwarded-User'] == 'ralph@example.org', (
        'User-facing endpoint must forward identity so MCP can apply per-user scoping.'
    )
    assert 'application/json' in headers['Accept']
    assert 'text/event-stream' in headers['Accept']


def test_optional_args_pass_through(monkeypatch):
    monkeypatch.setenv('MEMORY_GATEWAY_TOKEN', 'gateway-secret')

    patcher, post_mock = _patch_async_client(_sse_response(SAMPLE_OUTPUT))
    with patcher:
        _run(
            _call_list_memories(
                user_email='ralph@example.org',
                scope='project',
                project_id='42',
                memory_type='feedback',
                limit=10,
            )
        )

    args = post_mock.call_args.kwargs['json']['params']['arguments']
    assert args == {
        'scope': 'project',
        'project_id': '42',
        'type': 'feedback',
        'limit': 10,
    }


def test_missing_email_omits_x_forwarded_user(monkeypatch):
    """If user.email is None, the BFF must NOT fabricate the header. The
    MCP will then 401 — that surfaces as 502 to the caller, which is the
    correct behavior (matches bopa_session_context)."""
    monkeypatch.setenv('MEMORY_GATEWAY_TOKEN', 'gateway-secret')

    patcher, post_mock = _patch_async_client(_sse_response(SAMPLE_OUTPUT))
    with patcher:
        _run(
            _call_list_memories(
                user_email=None,
                scope=None,
                project_id=None,
                memory_type=None,
                limit=None,
            )
        )

    headers = post_mock.call_args.kwargs['headers']
    assert 'X-Forwarded-User' not in headers


def test_pure_json_framing_also_parses(monkeypatch):
    monkeypatch.setenv('MEMORY_GATEWAY_TOKEN', 'gateway-secret')
    patcher, _ = _patch_async_client(_sse_response(SAMPLE_OUTPUT, framing='json'))
    with patcher:
        payload = _run(
            _call_list_memories(
                user_email='ralph@example.org',
                scope=None,
                project_id=None,
                memory_type=None,
                limit=None,
            )
        )
    assert len(payload['entries']) == 2


# --- failure modes ---------------------------------------------------------


def test_mcp_502_propagates_as_502(monkeypatch):
    monkeypatch.setenv('MEMORY_GATEWAY_TOKEN', 'gateway-secret')
    failing = MagicMock()
    failing.raise_for_status.side_effect = httpx.HTTPStatusError(
        '502 Bad Gateway', request=MagicMock(), response=MagicMock(status_code=502)
    )
    patcher, _ = _patch_async_client(failing)
    with patcher:
        with pytest.raises(HTTPException) as exc:
            _run(
                _call_list_memories(
                    user_email='ralph@example.org',
                    scope=None,
                    project_id=None,
                    memory_type=None,
                    limit=None,
                )
            )
    assert exc.value.status_code == 502


def test_mcp_timeout_propagates_as_502(monkeypatch):
    monkeypatch.setenv('MEMORY_GATEWAY_TOKEN', 'gateway-secret')
    patcher, _ = _patch_async_client(post_side_effect=httpx.TimeoutException('timed out'))
    with patcher:
        with pytest.raises(HTTPException) as exc:
            _run(
                _call_list_memories(
                    user_email='ralph@example.org',
                    scope=None,
                    project_id=None,
                    memory_type=None,
                    limit=None,
                )
            )
    assert exc.value.status_code == 502


def test_malformed_response_propagates_as_502(monkeypatch):
    monkeypatch.setenv('MEMORY_GATEWAY_TOKEN', 'gateway-secret')
    bad = MagicMock()
    bad.raise_for_status = MagicMock()
    bad.text = 'event: ping\ndata: not-json\n\n'
    patcher, _ = _patch_async_client(bad)
    with patcher:
        with pytest.raises(HTTPException) as exc:
            _run(
                _call_list_memories(
                    user_email='ralph@example.org',
                    scope=None,
                    project_id=None,
                    memory_type=None,
                    limit=None,
                )
            )
    assert exc.value.status_code == 502


def test_validation_error_propagates_as_502(monkeypatch):
    """Bugbot finding on PR #58: when the MCP returns a payload that
    doesn't match ListMemoriesOutput, the endpoint must surface a 502
    (gateway-level fault), not let the Pydantic ValidationError leak
    as a 500. Mirrors the same guard on admin_memory.py."""
    monkeypatch.setenv('MEMORY_GATEWAY_TOKEN', 'gateway-secret')

    from fastapi.testclient import TestClient

    from open_webui.main import app  # noqa: PLC0415
    from open_webui.utils.auth import get_verified_user

    bad_payload = {'entries': [{'name': 'x'}]}  # missing required type/scope/etc
    patcher, _ = _patch_async_client(_sse_response(bad_payload))

    app.dependency_overrides[get_verified_user] = lambda: type('U', (), {'id': 'u', 'email': 'a@x'})()
    try:
        with patcher:
            client = TestClient(app)
            res = client.get('/api/v1/rm-memory/list')
        assert res.status_code == 502, f'expected 502, got {res.status_code}: {res.text}'
        assert 'unexpected payload shape' in res.text.lower()
    finally:
        app.dependency_overrides.pop(get_verified_user, None)


def test_mcp_error_envelope_propagates_as_502(monkeypatch):
    monkeypatch.setenv('MEMORY_GATEWAY_TOKEN', 'gateway-secret')
    err_envelope = {
        'jsonrpc': '2.0',
        'id': 'x',
        'error': {'code': -32602, 'message': 'Invalid arguments: scope'},
    }
    bad = MagicMock()
    bad.raise_for_status = MagicMock()
    bad.text = f'event: message\ndata: {json.dumps(err_envelope)}\n'
    patcher, _ = _patch_async_client(bad)
    with patcher:
        with pytest.raises(HTTPException) as exc:
            _run(
                _call_list_memories(
                    user_email='ralph@example.org',
                    scope=None,
                    project_id=None,
                    memory_type=None,
                    limit=None,
                )
            )
    assert exc.value.status_code == 502
    assert 'invalid' in exc.value.detail.lower()
