"""Tests for scripts/seed_personas.py and scripts/personas.yaml (ADR-0018)."""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / 'scripts'
sys.path.insert(0, str(SCRIPTS_DIR))

from personas_schema import load_manifest  # noqa: E402
from seed_personas import _persona_payload, _read_filter_source, run_dry  # noqa: E402

MANIFEST_PATH = SCRIPTS_DIR / 'personas.yaml'


@pytest.fixture(scope='module')
def manifest():
    return load_manifest(MANIFEST_PATH)


def test_manifest_loads(manifest):
    assert manifest.connection.default_model == 'RO-Assistent'
    assert manifest.connection.base_urls == ['http://litellm:4000/v1']


def test_persona_canon_three(manifest):
    ids = [p.id for p in manifest.personas]
    assert ids == ['RO-Assistent', 'Juridisch-Assistent', 'Commercieel-Assistent']


def test_persona_payload_base_model_is_none(manifest):
    # ADR-0018 §"What this commits to": base_model_id MUST be None so the
    # row hits OpenWebUI's override branch (utils/models.py:150).
    for persona in manifest.personas:
        payload = _persona_payload(persona)
        assert payload['base_model_id'] is None, f'{persona.id} base_model_id must be None'
        assert payload['params']['system'] == persona.system_prompt
        assert payload['meta']['filterIds'] == persona.filter_ids
        assert payload['meta']['toolIds'] == persona.tool_ids


def test_persona_tools_use_mcp_prefix(manifest):
    for persona in manifest.personas:
        for tool in persona.tool_ids:
            assert tool.startswith('server:mcp:'), f'{persona.id}: {tool} missing server:mcp: prefix'


def test_filter_sources_exist(manifest):
    for f in manifest.filters:
        path = REPO_ROOT / f.source_path
        assert path.exists(), f'filter source missing: {f.source_path}'
        # Should be non-empty Python file
        content = _read_filter_source(f)
        assert len(content) > 100, f'filter {f.id} source suspiciously small'


def test_filter_ids_referenced_by_personas_are_installed(manifest):
    installed = {f.id for f in manifest.filters}
    for persona in manifest.personas:
        for fid in persona.filter_ids:
            assert fid in installed, f'{persona.id} references uninstalled filter: {fid}'


def test_prompt_commands_unique(manifest):
    cmds = [p.command for p in manifest.prompts]
    assert len(cmds) == len(set(cmds)), 'duplicate slash-command in prompts'


def test_dry_run_smoke(manifest, capsys):
    rc = run_dry(manifest)
    assert rc == 0
    out = capsys.readouterr().out
    assert 'Filters (5)' in out
    assert 'Personas (3)' in out
    assert 'Prompts (14)' in out
