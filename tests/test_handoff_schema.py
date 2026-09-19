"""Valida que un bundle real exportado por handoff.py cumpla la spec pública
publicada en docs/schemas/yunta-session-spec-v1.schema.json — el contrato
que cualquier otro harness necesita para leer/escribir bundles compatibles.
"""
import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

from yunta.agent import SessionPermissions
from yunta.api import Block, BlockType, Message, Role, Usage
from yunta.handoff import export_handoff

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "docs" / "schemas" / "yunta-session-spec-v1.schema.json"


@pytest.fixture()
def schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_schema_file_itself_is_valid_json_schema(schema):
    jsonschema.Draft202012Validator.check_schema(schema)


def test_real_export_validates_against_public_schema(tmp_path, monkeypatch, schema):
    monkeypatch.chdir(tmp_path)
    messages = [
        Message(role=Role.USER, content=[Block(type=BlockType.TEXT, text="hola")]),
        Message(
            role=Role.ASSISTANT,
            content=[
                Block(type=BlockType.TEXT, text="leo"),
                Block(type=BlockType.TOOL_USE, tool_use_id="1", tool_name="read_file", tool_input='{"path":"x"}'),
            ],
        ),
        Message(
            role=Role.USER,
            content=[Block(type=BlockType.TOOL_RESULT, tool_use_id="1", tool_result="contenido", is_error=False)],
        ),
    ]
    usage = Usage(input_tokens=10, output_tokens=5, cached_tokens=2, tool_counts={"read_file": 1}, turns=1)
    sp = SessionPermissions()
    sp.grant_tool("bash")

    out = tmp_path / "bundle.json"
    export_handoff(
        messages, usage, session_permissions=sp,
        active_sandbox={"dir": str(tmp_path / "sb"), "branch": "sandbox-1"},
        model="openai/gpt-4o", path=out,
    )
    bundle = json.loads(out.read_text(encoding="utf-8"))

    jsonschema.validate(instance=bundle, schema=schema)


def test_bundle_without_optional_fields_still_validates(tmp_path, monkeypatch, schema):
    """active_sandbox=None y session_permissions vacíos son válidos: un
    importador sin soporte de sandboxes/permisos debe poder ignorarlos."""
    monkeypatch.chdir(tmp_path)
    messages = [Message(role=Role.USER, content=[Block(type=BlockType.TEXT, text="x")])]
    out = tmp_path / "bundle_min.json"
    export_handoff(messages, Usage(), path=out)
    bundle = json.loads(out.read_text(encoding="utf-8"))

    jsonschema.validate(instance=bundle, schema=schema)


def test_unknown_schema_version_is_rejected_by_schema(schema):
    """El schema exige schema_version == 1 exactamente (const) -- un futuro
    schema_version=2 debe fallar la validación, no pasar silenciosamente."""
    bogus = {
        "schema_version": 2,
        "session_id": "x",
        "created_at": 0,
        "messages": [],
        "usage": {},
    }
    with pytest.raises(jsonschema.exceptions.ValidationError):
        jsonschema.validate(instance=bogus, schema=schema)
