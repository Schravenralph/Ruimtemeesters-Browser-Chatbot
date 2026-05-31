"""User-facing BFF for the Ruimtemeesters skills corpus (rm-skills).

Read-only proxy that surfaces the persona's mandatory skill list to the
chatbot frontend so a navbar chip can show "Skills: N" without giving
the frontend the gateway bearer or direct rm-skills access.

Same gateway-token pattern as rm_memory.py: `SKILLS_GATEWAY_TOKEN`
matches an entry in rm-skills's `SKILLS_API_KEYS`. The BFF also
forwards `X-Forwarded-User` so rm-skills can future-extend with
per-user filtering (Phase D in the rm-skills roadmap).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from open_webui.models.functions import Functions
from open_webui.utils.auth import get_verified_user
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

router = APIRouter()


DEFAULT_SKILLS_URL = 'http://rm-skills:4101'
SKILLS_TIMEOUT_S = 5.0
DEFAULT_MAX_SKILLS = 5
SKILLS_CONTEXT_FUNCTION_ID = 'skills_context'

_PERSONA_MAP: dict[str, str] = {
    'rm-assistent': 'ro-assistent',
    'rm-ro-assistent': 'ro-assistent',
    'rm-juridisch-assistent': 'juridisch-assistent',
    'rm-commercieel-assistent': 'commercieel-assistent',
    'ro-assistent': 'ro-assistent',
    'juridisch-assistent': 'juridisch-assistent',
    'commercieel-assistent': 'commercieel-assistent',
}


class ActiveSkill(BaseModel):
    """Subset of rm-skills's IndexEntry — just what the chip renders."""

    name: str
    description: str


class ActiveSkillsOutput(BaseModel):
    persona: str
    skills: list[ActiveSkill] = Field(default_factory=list)


def _resolve_skills_url() -> str:
    return (os.environ.get('SKILLS_API_URL') or DEFAULT_SKILLS_URL).strip() or DEFAULT_SKILLS_URL


def _resolve_gateway_token() -> str:
    token = (os.environ.get('SKILLS_GATEWAY_TOKEN') or '').strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='SKILLS_GATEWAY_TOKEN not configured — the rm-skills BFF is offline until an operator sets it.',
        )
    return token


def _forwarded_user_id(user: Any) -> str | None:
    """Construct the canonical `clerk:<sub>` identifier from the user's
    OAuth profile. Mirror of rm_memory._forwarded_user_id — the BFF
    convention is the same across both services."""
    oauth = getattr(user, 'oauth', None) or {}
    if not isinstance(oauth, dict):
        return None
    oidc_entry = oauth.get('oidc')
    if not isinstance(oidc_entry, dict):
        return None
    sub = oidc_entry.get('sub')
    if not sub or not isinstance(sub, str):
        return None
    return f'clerk:{sub}'


def _user_opted_out(user: Any) -> bool:
    """Check whether the user disabled skills_context via UserValves."""
    user_id = getattr(user, 'id', None)
    if not user_id:
        return False
    try:
        valves = Functions.get_user_valves_by_id_and_user_id(SKILLS_CONTEXT_FUNCTION_ID, user_id)
        if isinstance(valves, dict) and valves.get('enabled') is False:
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _read_admin_valves() -> dict:
    """Read the admin-level valves for the skills_context filter function."""
    try:
        valves = Functions.get_function_valves_by_id(SKILLS_CONTEXT_FUNCTION_ID)
        if isinstance(valves, dict):
            return valves
    except Exception:  # noqa: BLE001
        pass
    return {}


def _resolve_persona(model_id: str) -> str:
    """Resolve persona slug from model id — mirrors the filter's logic.

    Order:
      1. Exact map lookup
      2. Lowercased map lookup
      3. Fall-through: strip `rm-` prefix and return lowercased
    """
    if not model_id:
        return ''
    trimmed = model_id.strip()
    if trimmed in _PERSONA_MAP:
        return _PERSONA_MAP[trimmed]
    lowered = trimmed.lower()
    if lowered in _PERSONA_MAP:
        return _PERSONA_MAP[lowered]
    if lowered.startswith('rm-'):
        return lowered[len('rm-') :]
    return lowered


def _model_in_scope(model_id: str, admin_valves: dict) -> bool:
    """Check if model_id is in the admin-configured target_models set."""
    raw = admin_valves.get('target_models', '')
    if not isinstance(raw, str) or not raw.strip():
        return True
    targets = {m.strip() for m in raw.split(',') if m.strip()}
    if not targets:
        return True
    return model_id.strip() in targets


def _effective_max_skills(admin_valves: dict) -> int:
    """Return the max_skills cap from admin valves, falling back to the default."""
    val = admin_valves.get('max_skills', DEFAULT_MAX_SKILLS)
    if not isinstance(val, int) or val < 1:
        return DEFAULT_MAX_SKILLS
    return val


async def _fetch_verified_skills(persona: str, admin_valves: dict, user: Any) -> list[ActiveSkill]:
    """Fetch mandatory skills from rm-skills and verify each body is accessible."""
    headers: dict[str, str] = {
        'Authorization': f'Bearer {_resolve_gateway_token()}',
        'Accept': 'application/json',
    }
    forwarded = _forwarded_user_id(user)
    if forwarded:
        headers['X-Forwarded-User'] = forwarded

    base_url = _resolve_skills_url().rstrip('/')
    url = f'{base_url}/api/v1/skills'

    async with httpx.AsyncClient(timeout=SKILLS_TIMEOUT_S) as client:
        resp = await client.get(url, params={'persona': persona}, headers=headers)
        resp.raise_for_status()
        payload = resp.json()

        mandatory = _parse_mandatory(payload, _effective_max_skills(admin_valves))

        verified: list[ActiveSkill] = []
        for skill in mandatory:
            body_url = f'{base_url}/api/v1/skills/{skill.name}'
            try:
                body_resp = await client.get(body_url, headers=headers)
                body_resp.raise_for_status()
                body_data = body_resp.json()
                if isinstance(body_data, dict) and body_data.get('skill_md'):
                    verified.append(skill)
            except (httpx.HTTPError, ValueError):
                log.debug('Skipping skill %s — body fetch failed', skill.name)
                continue
    return verified


@router.get('/active', response_model=ActiveSkillsOutput)
async def list_active_skills(
    model_id: str = Query(
        ..., description='Model ID as selected in the chat UI. The BFF resolves the persona and checks admin valves.'
    ),
    user=Depends(get_verified_user),
) -> ActiveSkillsOutput:
    """List the persona's mandatory skills (name + description only).

    The set returned here is exactly the set the `skills_context` inlet
    filter injects into the system prompt — the chip cannot drift from
    what the LLM actually sees.

    Returns an empty list if rm-skills has no mandatory entries for this
    persona; never returns 404. Transport / parser failures map to 502.
    Returns an empty list when the admin kill switch is off, the model is
    not in scope, or the user has opted out of skills_context.
    """
    admin_valves = _read_admin_valves()

    if admin_valves.get('enabled') is False:
        return ActiveSkillsOutput(persona='', skills=[])

    if not _model_in_scope(model_id, admin_valves):
        return ActiveSkillsOutput(persona='', skills=[])

    persona = _resolve_persona(model_id)
    if not persona:
        return ActiveSkillsOutput(persona='', skills=[])

    if _user_opted_out(user):
        return ActiveSkillsOutput(persona=persona, skills=[])

    try:
        verified = await _fetch_verified_skills(persona, admin_valves, user)
    except httpx.HTTPStatusError as e:
        upstream = ''
        if e.response is not None:
            try:
                upstream = (e.response.text or '')[:500]
            except Exception:  # noqa: BLE001 — defensive read
                upstream = ''
        log.warning('rm-skills returned %s for /api/v1/skills', e.response.status_code if e.response else '?')
        suffix = f' — {upstream}' if upstream else ''
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f'rm-skills returned an error: {e}{suffix}',
        ) from e
    except (httpx.HTTPError, ValueError) as e:
        log.warning('rm-skills transport / parse failure: %s', e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f'rm-skills unreachable or returned invalid JSON: {e}',
        ) from e

    return ActiveSkillsOutput(persona=persona, skills=verified)


def _parse_mandatory(payload: Any, max_skills: int = DEFAULT_MAX_SKILLS) -> list[ActiveSkill]:
    """Extract `mandatory: true` entries from rm-skills's list response.

    Accepts either `{skills: [...]}` (canonical) or a bare list (some
    early endpoints). Returns an empty list on any unexpected shape —
    a chip showing 0 is less surprising than a 502.

    Truncates to max_skills to match the skills_context filter's cap.
    """
    raw = payload.get('skills') if isinstance(payload, dict) else payload
    if not isinstance(raw, list):
        log.warning('rm-skills returned unexpected payload shape: %r', type(raw))
        return []
    out: list[ActiveSkill] = []
    for s in raw:
        if not isinstance(s, dict) or not s.get('mandatory'):
            continue
        name = s.get('name')
        if isinstance(name, str) and name:
            out.append(ActiveSkill(name=name, description=s.get('description') or ''))
        if len(out) >= max_skills:
            break
    return out
