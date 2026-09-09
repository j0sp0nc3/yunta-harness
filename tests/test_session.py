import json
from pathlib import Path

from yunta.api import Block, BlockType, Message, Role, Usage
from yunta.session import (
    clear_session,
    deserialize_messages,
    deserialize_usage,
    load_session,
    save_session,
    serialize_messages,
    serialize_usage,
)


def test_serialize_and_deserialize_messages():
    messages = [
        Message(role=Role.USER, content=[Block(type=BlockType.TEXT, text="hola")]),
        Message(
            role=Role.ASSISTANT,
            content=[
                Block(type=BlockType.TEXT, text="voy a usar una tool"),
                Block(
                    type=BlockType.TOOL_USE,
                    tool_use_id="tool_1",
                    tool_name="read_file",
                    tool_input='{"path": "foo.py"}',
                ),
            ],
        ),
        Message(
            role=Role.USER,
            content=[
                Block(
                    type=BlockType.TOOL_RESULT,
                    tool_use_id="tool_1",
                    tool_result="def foo(): pass",
                    is_error=False,
                )
            ],
        ),
    ]

    serialized = serialize_messages(messages)
    assert len(serialized) == 3
    assert serialized[0]["role"] == "user"
    assert serialized[1]["content"][1]["tool_name"] == "read_file"

    restored = deserialize_messages(serialized)
    assert len(restored) == 3
    assert restored[0].role == Role.USER
    assert restored[0].content[0].text == "hola"
    assert restored[1].role == Role.ASSISTANT
    assert restored[1].content[1].type == BlockType.TOOL_USE
    assert restored[1].content[1].tool_name == "read_file"
    assert restored[2].content[0].type == BlockType.TOOL_RESULT
    assert restored[2].content[0].tool_result == "def foo(): pass"


def test_serialize_and_deserialize_usage():
    usage = Usage(
        input_tokens=100,
        output_tokens=50,
        cached_tokens=25,
        tool_counts={"read_file": 2, "bash": 1},
        tool_errors=0,
        turns=3,
    )
    data = serialize_usage(usage)
    assert data["input_tokens"] == 100
    assert data["tool_counts"]["read_file"] == 2

    restored = deserialize_usage(data)
    assert restored.input_tokens == 100
    assert restored.output_tokens == 50
    assert restored.cached_tokens == 25
    assert restored.tool_counts == {"read_file": 2, "bash": 1}
    assert restored.turns == 3


def test_save_and_load_session(tmp_path):
    session_file = tmp_path / "session_state.json"
    messages = [
        Message(role=Role.USER, content=[Block(type=BlockType.TEXT, text="test prompt")]),
        Message(role=Role.ASSISTANT, content=[Block(type=BlockType.TEXT, text="test response")]),
    ]
    usage = Usage(input_tokens=50, output_tokens=20, turns=1)

    # 1. Guardar sesión
    save_session(messages, usage, model="test-model", session_file=session_file)
    assert session_file.exists()

    # 2. Cargar sesión
    loaded = load_session(session_file=session_file)
    assert loaded is not None
    assert loaded["model"] == "test-model"
    assert len(loaded["messages"]) == 2
    assert loaded["messages"][0].content[0].text == "test prompt"
    assert loaded["usage"].turns == 1

    # 3. Limpiar sesión
    cleared = clear_session(session_file=session_file)
    assert cleared is True
    assert not session_file.exists()
    assert load_session(session_file=session_file) is None


def test_load_corrupted_session(tmp_path):
    session_file = tmp_path / "corrupt.json"
    session_file.write_text("{bad json...", encoding="utf-8")
    assert load_session(session_file=session_file) is None
