import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, ".")

from yunta.agent import Agent
from yunta.api import Block, BlockType, Response, StopReason
from yunta.tools import bash, files  # noqa: F401


class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.received = []

    def send(self, messages, tools):
        self.received.append((list(messages), tools))
        return self.responses.pop(0)


def tool_use(id, name, input):
    return Block(
        type=BlockType.TOOL_USE, tool_use_id=id, tool_name=name, tool_input=input
    )


def tool_call_blocks(messages):
    return [
        b for m in messages for b in m.content if b.type == BlockType.TOOL_USE
    ]


def test_loop_executes_tool_and_finishes(capsys):
    p = FakeProvider(
        [
            Response(
                content=[tool_use("1", "read_file", '{"path":"README.md"}')],
                stop_reason=StopReason.TOOL_USE,
            ),
            Response(content=[Block(type=BlockType.TEXT, text="listo")], stop_reason=StopReason.END_TURN),
        ]
    )
    a = Agent(provider=p, system="s", confirm=lambda n, d: True)
    out = a.send("lee el readme")
    assert out == "listo"
    assert len(a.messages) == 4  # user, assistant/tool_use, user/tool_result, assistant/text
    results = [b for b in a.messages[2].content if b.type == BlockType.TOOL_RESULT]
    assert results[0].is_error is False
    assert "yunta" in results[0].tool_result


def test_tool_error_returns_to_context():
    p = FakeProvider(
        [
            Response(
                content=[tool_use("1", "read_file", '{"path":"no-existe.txt"}')],
                stop_reason=StopReason.TOOL_USE,
            ),
            Response(content=[Block(type=BlockType.TEXT, text="ok")], stop_reason=StopReason.END_TURN),
        ]
    )
    a = Agent(provider=p, system="s", confirm=lambda n, d: True)
    a.send("lee")
    results = [b for b in a.messages[2].content if b.type == BlockType.TOOL_RESULT]
    assert results[0].is_error is True
    assert "no-existe" in results[0].tool_result or "Error" in results[0].tool_result


def test_denied_tool_call_is_error():
    p = FakeProvider(
        [
            Response(
                content=[tool_use("1", "bash", '{"command":"echo hi"}')],
                stop_reason=StopReason.TOOL_USE,
            ),
            Response(content=[Block(type=BlockType.TEXT, text="ok")], stop_reason=StopReason.END_TURN),
        ]
    )
    a = Agent(provider=p, system="s", confirm=lambda n, d: False)
    a.send("corre echo")
    results = [b for b in a.messages[2].content if b.type == BlockType.TOOL_RESULT]
    assert results[0].is_error is True
    assert "denied" in results[0].tool_result


def test_unknown_tool_is_error():
    p = FakeProvider(
        [
            Response(
                content=[tool_use("1", "no_existe", "{}")],
                stop_reason=StopReason.TOOL_USE,
            ),
            Response(content=[Block(type=BlockType.TEXT, text="ok")], stop_reason=StopReason.END_TURN),
        ]
    )
    a = Agent(provider=p, system="s")
    a.send("x")
    results = [b for b in a.messages[2].content if b.type == BlockType.TOOL_RESULT]
    assert "unknown tool" in results[0].tool_result


def test_write_file_approval_shows_diff():
    p = FakeProvider(
        [
            Response(
                content=[tool_use("1", "write_file", '{"path":"t_diff.txt","content":"nuevo"}')],
                stop_reason=StopReason.TOOL_USE,
            ),
            Response(content=[Block(type=BlockType.TEXT, text="ok")], stop_reason=StopReason.END_TURN),
        ]
    )
    seen = {}

    def confirm(name, detail):
        seen["name"], seen["detail"] = name, detail
        return True

    a = Agent(provider=p, system="s", confirm=confirm)
    try:
        a.send("escribe")
        assert seen["name"] == "write_file"
        assert "+nuevo" in seen["detail"]
        assert "t_diff.txt" in seen["detail"]
    finally:
        import os

        if os.path.exists("t_diff.txt"):
            os.remove("t_diff.txt")


def test_str_replace_approval_shows_diff(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "t_str.txt").write_text("linea vieja\n", encoding="utf-8")
    p = FakeProvider(
        [
            Response(
                content=[
                    tool_use(
                        "1",
                        "str_replace",
                        '{"path":"t_str.txt","old_str":"linea vieja","new_str":"linea nueva"}',
                    )
                ],
                stop_reason=StopReason.TOOL_USE,
            ),
            Response(content=[Block(type=BlockType.TEXT, text="ok")], stop_reason=StopReason.END_TURN),
        ]
    )
    seen = {}

    def confirm(name, detail):
        seen["name"], seen["detail"] = name, detail
        return True

    a = Agent(provider=p, system="s", confirm=confirm)
    a.send("reemplaza")
    assert seen["name"] == "str_replace"
    assert "-linea vieja" in seen["detail"]
    assert "+linea nueva" in seen["detail"]


def test_max_turns_cap():
    resp = Response(
        content=[tool_use("1", "read_file", '{"path":"README.md"}')],
        stop_reason=StopReason.TOOL_USE,
    )
    p = FakeProvider([])
    p.send = lambda m, t: resp
    a = Agent(provider=p, system="s", max_turns=3, confirm=lambda n, d: True)
    a.send("loop")
    # 3 turnos: user + 3x(assistant+toolresult) = 7 mensajes
    assert len(a.messages) == 7


def test_keyboard_interrupt_in_loop_preserves_assistant_message(capsys):
    from yunta.api import Role

    class InterruptProvider:
        def send(self, messages, tools, on_text=None):
            raise KeyboardInterrupt("interrumpido")

    p = InterruptProvider()
    a = Agent(provider=p, system="s")
    out = a.send("haz algo")

    assert "interrumpido" in out
    captured = capsys.readouterr()
    assert "interrumpido" in captured.out
    assert len(a.messages) == 2
    assert a.messages[0].role == Role.USER
    assert a.messages[-1].role == Role.ASSISTANT
    assert a.messages[-1].content[0].text == "[interrumpido por el usuario]"


def test_system_prompt_ontological_boundary():
    from yunta.cli import load_system_prompt

    prompt = load_system_prompt()
    assert "Frontera de rol y entorno de ejecución" in prompt
    assert "banco de herramientas" in prompt
    assert "NO el runtime de la aplicación" in prompt
    assert "NUNCA crees servicios, daemons ni plugins" in prompt


def test_load_system_prompt_custom_override(monkeypatch, tmp_path):
    from pathlib import Path
    from yunta.cli import load_system_prompt

    # 1. Override vía variable de entorno YUNTA_SYSTEM_PROMPT
    monkeypatch.setenv("YUNTA_SYSTEM_PROMPT", "prompt personalizado")
    prompt = load_system_prompt()
    assert prompt.startswith("prompt personalizado")

    # 2. Override vía archivo ~/.yunta/system_prompt.md
    monkeypatch.delenv("YUNTA_SYSTEM_PROMPT", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    dot_yunta = tmp_path / ".yunta"
    dot_yunta.mkdir(parents=True, exist_ok=True)
    (dot_yunta / "system_prompt.md").write_text("prompt archivo", encoding="utf-8")

    prompt_file = load_system_prompt()
    assert prompt_file.startswith("prompt archivo")


def test_spinner_start_and_stop(monkeypatch):
    import time
    from yunta.agent import Spinner

    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)

    spinner = Spinner("Pensando...")
    spinner.start()

    assert spinner._thread is not None
    assert spinner._thread.is_alive()

    time.sleep(0.15)

    spinner.stop()

    assert not spinner._thread.is_alive()


