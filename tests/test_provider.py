import os
import subprocess
import sys
from types import SimpleNamespace

import litellm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yunta.tools.bash  # noqa: F401,E402
import yunta.tools.files  # noqa: F401,E402
from yunta.api import Block, BlockType, Message, Role  # noqa: E402
from yunta.provider import LiteLLMProvider  # noqa: E402
from yunta.tools import registry  # noqa: E402

captured = {}


def fake_completion(**kwargs):
    captured.clear()
    captured.update(kwargs)
    choice = SimpleNamespace(
        message=SimpleNamespace(content="ok", tool_calls=None), finish_reason="stop"
    )
    return SimpleNamespace(
        choices=[choice], usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5)
    )


def setup_function(_):
    litellm.completion = fake_completion


MSGS = [
    Message(role=Role.USER, content=[Block(type=BlockType.TEXT, text="hola")]),
    Message(
        role=Role.ASSISTANT,
        content=[
            Block(type=BlockType.TEXT, text="leo"),
            Block(
                type=BlockType.TOOL_USE,
                tool_use_id="t1",
                tool_name="read_file",
                tool_input='{"path":"x"}',
            ),
        ],
    ),
    Message(
        role=Role.USER,
        content=[Block(type=BlockType.TOOL_RESULT, tool_use_id="t1", tool_result="contenido")],
    ),
]


def test_openai_translation():
    os.environ.update(LLM_MODEL="openai/gpt-4o", OPENAI_API_KEY="sk-x")
    p = LiteLLMProvider(system="sys")
    r = p.send(MSGS, tools=registry.definitions())
    lm = captured["messages"]
    assert lm[0] == {"role": "system", "content": "sys"}
    assert lm[1] == {"role": "user", "content": "hola"}
    assert lm[2]["tool_calls"][0]["function"]["name"] == "read_file"
    assert lm[3] == {"role": "tool", "tool_call_id": "t1", "content": "contenido"}
    assert captured["tools"][0]["function"]["name"] == "bash"
    assert r.usage.input_tokens == 10
    assert p.total_usage.output_tokens == 5


def test_anthropic_same_core():
    os.environ["LLM_MODEL"] = "anthropic/claude-sonnet-4-5"
    p = LiteLLMProvider(system="sys")
    p.send(MSGS, tools=[])
    assert captured["model"] == "anthropic/claude-sonnet-4-5"
    assert "tools" not in captured


def test_custom_base_url():
    os.environ.update(LLM_MODEL="openai/llama3", LLM_API_BASE="http://localhost:11434/v1")
    p = LiteLLMProvider(system="sys")
    p.send(MSGS[:1], tools=[])
    assert captured["api_base"] == "http://localhost:11434/v1"


def test_missing_model_fails_clearly():
    r = subprocess.run(
        [sys.executable, "-c", "from yunta.provider import LiteLLMProvider; LiteLLMProvider(system='s')"],
        capture_output=True,
        text=True,
        env={k: v for k, v in os.environ.items() if k != "LLM_MODEL"},
    )
    assert r.returncode != 0
    assert "LLM_MODEL" in r.stderr


def test_streaming_text():
    os.environ["LLM_MODEL"] = "openai/gpt-4o"
    stream_chunks = [
        SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="Hola ", tool_calls=None), finish_reason=None)],
            usage=None,
        ),
        SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="mundo", tool_calls=None), finish_reason=None)],
            usage=None,
        ),
        SimpleNamespace(
            choices=[SimpleNamespace(delta=None, finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=8, completion_tokens=4),
        ),
    ]

    litellm.completion = lambda **kwargs: stream_chunks
    p = LiteLLMProvider(system="sys")
    streamed = []
    r = p.send(MSGS[:1], tools=[], on_text=streamed.append)

    assert "".join(streamed) == "Hola mundo"
    assert len(r.content) == 1
    assert r.content[0].text == "Hola mundo"
    assert r.stop_reason.value == "end_turn"
    assert r.usage.input_tokens == 8
    assert p.total_usage.output_tokens == 4


def test_streaming_tool_call_fragmented():
    os.environ["LLM_MODEL"] = "openai/gpt-4o"
    stream_chunks = [
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content=None,
                        tool_calls=[
                            SimpleNamespace(
                                index=0,
                                id="call_abc",
                                function=SimpleNamespace(name="read_file", arguments='{"pa'),
                            )
                        ],
                    ),
                    finish_reason=None,
                )
            ],
            usage=None,
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content=None,
                        tool_calls=[
                            SimpleNamespace(
                                index=0,
                                id=None,
                                function=SimpleNamespace(name=None, arguments='th": "foo.py"}'),
                            )
                        ],
                    ),
                    finish_reason=None,
                )
            ],
            usage=None,
        ),
        SimpleNamespace(
            choices=[SimpleNamespace(delta=None, finish_reason="tool_calls")],
            usage=SimpleNamespace(prompt_tokens=15, completion_tokens=10),
        ),
    ]

    litellm.completion = lambda **kwargs: stream_chunks
    p = LiteLLMProvider(system="sys")
    r = p.send(MSGS[:1], tools=registry.definitions(), on_text=lambda t: None)

    assert len(r.content) == 1
    call = r.content[0]
    assert call.type.value == "tool_use"
    assert call.tool_name == "read_file"
    assert call.tool_use_id == "call_abc"
    assert call.tool_input == '{"path": "foo.py"}'
    assert r.stop_reason.value == "tool_use"
    assert r.usage.input_tokens == 15
    assert p.total_usage.output_tokens == 10
