"""Streamable-HTTP MCP response parser shared by admin BFFs.

The MCP servers we talk to (rm-memory, rm-databank, …) reply over the
Streamable HTTP transport which can frame results as either pure JSON
(`{...}`) or as Server-Sent Events (`event: message\\ndata: {...}`).
The server picks SSE whenever the request advertises both
`application/json` and `text/event-stream` in Accept (which the spec
requires), so any well-formed client must handle both shapes.

Mirrored in `rm-tools/filters/bopa_session_context._parse_mcp_response`
because OpenWebUI's filter loader runs each filter as a self-contained
module — the duplication is intentional. This copy serves the chatbot
backend (FastAPI app context, regular import path).
"""

from __future__ import annotations

import json


def parse_mcp_response(text: str) -> dict:
    """Parse an MCP HTTP response body and return the JSON-RPC envelope.

    Accepts either pure JSON or SSE-framed `event: message\\ndata: {...}`.
    Non-JSON data events (notifications, keep-alives) are skipped.

    SSE selection rule: prefer the FIRST envelope that carries `result`
    or `error` (the spec-defined response shapes for our request).
    Server-sent JSON-RPC notifications that arrive after the response
    must NOT overwrite it — without this guard a late notification
    would make a successful response look malformed (Bugbot finding on
    PR #56). Fall back to the last otherwise-valid envelope when no
    result/error event appears, so legitimate but unrecognised
    responses still parse.

    Raises ValueError on empty bodies or SSE bodies with no parseable
    data event.
    """
    if not text:
        raise ValueError('empty response body')
    stripped = text.lstrip()
    if stripped.startswith('{'):
        return json.loads(stripped)

    response_payload: dict | None = None  # first event with result/error
    fallback_payload: dict | None = None  # last otherwise-valid dict

    def _try_consume(buf: list[str]) -> None:
        nonlocal response_payload, fallback_payload
        joined = '\n'.join(buf).strip()
        if not joined:
            return
        try:
            parsed = json.loads(joined)
        except ValueError:
            return
        if not isinstance(parsed, dict):
            return
        if response_payload is None and ('result' in parsed or 'error' in parsed):
            response_payload = parsed
            return
        fallback_payload = parsed

    data_buf: list[str] = []
    for line in text.splitlines():
        if line.startswith('data:'):
            data_buf.append(line[5:].lstrip())
        elif line == '' and data_buf:
            _try_consume(data_buf)
            data_buf = []
    if data_buf:
        _try_consume(data_buf)
    chosen = response_payload if response_payload is not None else fallback_payload
    if chosen is None:
        raise ValueError('SSE body had no JSON data event')
    return chosen


def extract_tool_result(envelope: dict) -> dict:
    """Pull the tool's structured payload out of a JSON-RPC envelope.

    The MCP server wraps tool output as
    `{"result": {"content": [{"type": "text", "text": "<json>"}]}}`.
    The text payload is itself a JSON-encoded object — we decode and
    return that. Errors (`{"error": {...}}`) raise ValueError so the
    caller can map them to an HTTP response.
    """
    if 'error' in envelope:
        err = envelope['error'] or {}
        msg = err.get('message') or 'MCP returned an error'
        raise ValueError(f'MCP error: {msg}')
    result = envelope.get('result')
    if not isinstance(result, dict):
        raise ValueError('MCP envelope missing result')
    content = result.get('content')
    if not isinstance(content, list) or not content:
        raise ValueError('MCP result.content empty or malformed')
    first = content[0]
    if not isinstance(first, dict) or first.get('type') != 'text':
        raise ValueError('MCP result.content[0] is not a text part')
    text = first.get('text')
    if not isinstance(text, str) or not text:
        raise ValueError('MCP text part empty')
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError('MCP text payload is not a JSON object')
    return parsed
