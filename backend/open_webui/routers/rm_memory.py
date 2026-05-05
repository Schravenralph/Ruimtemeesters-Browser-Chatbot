"""User-facing BFF for the Ruimtemeesters memory MCP.

Surfaces the MCP's read tools (currently `list_memories`) over HTTP so
the chatbot frontend can render a memory panel without the user
needing direct MCP access. Every request runs under the calling
user's identity: the chatbot forwards `user.email` as
`X-Forwarded-User` and authenticates to the MCP with the gateway
token. The MCP applies its Session 1 read predicate
(user own + global + project), so per-user scoping is enforced
server-side by the MCP — the BFF doesn't try to second-guess it.

Distinct from `admin_memory.py`:
- Auth: gateway token (not admin token).
- Identity: the caller's email is forwarded; no synthetic admin
  identity.
- Gate: `get_verified_user` (any signed-in user).
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from open_webui.utils.auth import get_verified_user
from open_webui.utils.mcp_response import extract_tool_result, parse_mcp_response

log = logging.getLogger(__name__)

router = APIRouter()


DEFAULT_MEMORY_MCP_URL = 'http://rm-mcp-memory:3200/mcp'
MCP_TIMEOUT_S = 10.0

MEMORY_TYPE = Literal['user', 'feedback', 'project', 'reference', 'session-summary']
SCOPE = Literal['user', 'project', 'global']


class MemoryEntry(BaseModel):
    """Mirror of IndexEntry in
    Ruimtemeesters-MCP-Servers/packages/memory/src/tools/listMemories.ts."""

    name: str
    type: str
    scope: str
    description: str
    owner_user_id: str
    project_id: str | None = None
    updated_at: str


class ListMemoriesOutput(BaseModel):
    entries: list[MemoryEntry] = Field(default_factory=list)


def _resolve_gateway_token() -> str:
    token = (os.environ.get('MEMORY_GATEWAY_TOKEN') or '').strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=('MEMORY_GATEWAY_TOKEN not configured — the rm-memory BFF is offline until an operator sets it.'),
        )
    return token


def _resolve_mcp_url() -> str:
    return (os.environ.get('RM_MEMORY_MCP_URL') or DEFAULT_MEMORY_MCP_URL).strip() or DEFAULT_MEMORY_MCP_URL


async def _call_list_memories(
    *,
    user_email: str | None,
    scope: str | None,
    project_id: str | None,
    memory_type: str | None,
    limit: int | None,
) -> dict[str, Any]:
    """Issue the user-scoped tools/call to the memory MCP and return the
    parsed payload. Raises HTTPException on transport / protocol errors."""
    arguments: dict[str, Any] = {}
    if scope is not None:
        arguments['scope'] = scope
    if project_id is not None:
        arguments['project_id'] = project_id
    if memory_type is not None:
        arguments['type'] = memory_type
    if limit is not None:
        arguments['limit'] = limit

    rpc_payload = {
        'jsonrpc': '2.0',
        'id': str(uuid.uuid4()),
        'method': 'tools/call',
        'params': {
            'name': 'list_memories',
            'arguments': arguments,
        },
    }
    headers = {
        'Authorization': f'Bearer {_resolve_gateway_token()}',
        'Accept': 'application/json, text/event-stream',
        'Content-Type': 'application/json',
    }
    if user_email:
        headers['X-Forwarded-User'] = user_email

    url = _resolve_mcp_url()

    try:
        async with httpx.AsyncClient(timeout=MCP_TIMEOUT_S) as client:
            resp = await client.post(url, json=rpc_payload, headers=headers)
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        log.warning(
            'rm-memory MCP returned %s for list_memories',
            e.response.status_code if e.response else '?',
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f'rm-memory MCP returned an error: {e}',
        ) from e
    except httpx.HTTPError as e:
        log.warning('rm-memory MCP transport error for list_memories: %s', e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f'rm-memory MCP unreachable: {e}',
        ) from e

    try:
        envelope = parse_mcp_response(resp.text)
        return extract_tool_result(envelope)
    except ValueError as e:
        log.warning('rm-memory MCP returned malformed response: %s', e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f'rm-memory MCP returned a malformed response: {e}',
        ) from e


@router.get('/list', response_model=ListMemoriesOutput)
async def list_memories_endpoint(
    scope: SCOPE | None = Query(default=None, description='Restrict to one scope.'),
    project_id: str | None = Query(
        default=None,
        max_length=256,
        description='When given, project entries match this project id.',
    ),
    type: MEMORY_TYPE | None = Query(
        default=None,
        description='Restrict to one memory type.',
        alias='type',
    ),
    limit: int | None = Query(default=None, ge=1, le=200, description='Up to 200; default 100 on the MCP side.'),
    user=Depends(get_verified_user),
) -> ListMemoriesOutput:
    """List the calling user's memory entries (user own + global + project).

    Returns the index view: name + description + metadata, no content.
    Use a follow-up `get_memory` call to retrieve content.
    """
    user_email = getattr(user, 'email', None) or None
    payload = await _call_list_memories(
        user_email=user_email,
        scope=scope,
        project_id=project_id,
        memory_type=type,
        limit=limit,
    )
    return ListMemoriesOutput.model_validate(payload)
