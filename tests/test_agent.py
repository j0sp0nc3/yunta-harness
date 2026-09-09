import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, ".")

from yunta.agent import Agent
from yunta.api import Block, BlockType, Response, Role, StopReason
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




def test_agent_undo_file_creation(tmp_path):
    import json
    from yunta.agent import Agent
    from types import SimpleNamespace

    mock_provider = SimpleNamespace(
        send=lambda msgs, tools, on_text=None: None,
        total_usage=SimpleNamespace(),
        model=lambda: "test-model"
    )
    agent = Agent(provider=mock_provider, system='', confirm=lambda name, detail: True)

    test_file = tmp_path / "created_by_yunta.txt"
    assert not test_file.exists()

    res, err = agent._execute_tool("write_file", json.dumps({"path": str(test_file), "content": "contenido inicial"}))
    assert not err
    assert test_file.exists()
    assert test_file.read_text(encoding="utf-8") == "contenido inicial"

    # Deshacer operacion (E13)
    restored = agent.undo()
    assert len(restored) == 1
    assert "eliminado" in restored[0]
    assert not test_file.exists()


def test_agent_undo_file_modification(tmp_path):
    import json
    from yunta.agent import Agent
    from types import SimpleNamespace

    mock_provider = SimpleNamespace(
        send=lambda msgs, tools, on_text=None: None,
        total_usage=SimpleNamespace(),
        model=lambda: "test-model"
    )
    agent = Agent(provider=mock_provider, system='', confirm=lambda name, detail: True)

    test_file = tmp_path / "existing_file.txt"
    test_file.write_text("linea 1\nlinea original\nlinea 3", encoding="utf-8")

    res, err = agent._execute_tool("str_replace", json.dumps({
        "path": str(test_file),
        "old_str": "linea original",
        "new_str": "linea modificada"
    }))
    assert not err
    assert "linea modificada" in test_file.read_text(encoding="utf-8")

    # Deshacer modificacion (E13)
    restored = agent.undo()
    assert len(restored) == 1
    assert "restaurado" in restored[0]
    assert "linea original" in test_file.read_text(encoding="utf-8")


def test_agent_ctrl_c_no_orphan_tool_use():
    from yunta.agent import Agent
    from yunta.api import Block, BlockType, Message, Response, Role, StopReason
    from types import SimpleNamespace

    # Simulamos que el modelo retorna 2 llamadas a herramientas
    resp = Response(
        stop_reason=StopReason.TOOL_USE,
        content=[
            Block(type=BlockType.TOOL_USE, tool_use_id="call_1", tool_name="tool_a", tool_input="{}"),
            Block(type=BlockType.TOOL_USE, tool_use_id="call_2", tool_name="tool_b", tool_input="{}"),
        ]
    )
    mock_provider = SimpleNamespace(
        send=lambda msgs, tools, on_text=None: resp,
        total_usage=SimpleNamespace(),
        model=lambda: "test-model"
    )
    agent = Agent(provider=mock_provider, system="")

    # Simulamos que al ejecutar la primera herramienta se presiona Ctrl+C
    def interrupt_tool(name, raw_input):
        raise KeyboardInterrupt()

    agent._execute_tool = interrupt_tool

    res = agent.send("ejecuta tareas")
    assert "[interrumpido por el usuario]" in res

    # VERIFICACION CRITICA P1:
    # El ultimo mensaje debe ser de Role.USER cerrando AMBAS tool_use_ids
    assert len(agent.messages) >= 3
    last_msg = agent.messages[-1]
    assert last_msg.role == Role.USER

    tool_results = [b for b in last_msg.content if b.type == BlockType.TOOL_RESULT]
    assert len(tool_results) == 2
    assert tool_results[0].tool_use_id == "call_1"
    assert tool_results[1].tool_use_id == "call_2"
    assert "cancelada" in tool_results[0].tool_result
    assert "cancelada" in tool_results[1].tool_result


# ---------------------------------------------------------------------------
# O1-c) V3-2: Permisos persistentes de sesión (solo en memoria)
# ---------------------------------------------------------------------------

def _approval_scenario(monkeypatch, answers):
    """Construye un agent con bash tool_use y respuestas de input programadas.

    Devuelve (agent, prompts) donde prompts acumula lo preguntado al usuario.
    """
    prompts = []
    it = iter(answers)

    def fake_input(prompt=""):
        prompts.append(prompt)
        try:
            return next(it)
        except StopIteration:
            return "n"

    monkeypatch.setattr("builtins.input", fake_input)

    p = FakeProvider(
        [
            Response(
                content=[tool_use("1", "bash", '{"command":"rm temporal.txt"}')],
                stop_reason=StopReason.TOOL_USE,
            ),
            Response(content=[Block(type=BlockType.TEXT, text="ok")], stop_reason=StopReason.END_TURN),
        ]
    )
    agent = Agent(provider=p, system="s", auto_save=False)
    agent.send("borra el archivo")
    return agent, prompts


def test_session_permissions_always_skips_same_pattern(monkeypatch):
    """Tras responder 'siempre', el mismo patrón (bash + primer token) no vuelve a preguntar."""
    agent, prompts = _approval_scenario(monkeypatch, ["siempre"])
    assert prompts, "debió preguntar la primera vez"
    assert agent.session_permissions.allowed("bash", "rm temporal.txt")

    # Un segundo agent (simulando nueva llamada en la MISMA sesión: memoria compartida
    # ocurre vía el mismo objeto; aquí verificamos el cambio de estado en el agente)
    p2 = FakeProvider(
        [
            Response(
                content=[tool_use("2", "bash", '{"command":"rm temporal.txt"}')],
                stop_reason=StopReason.TOOL_USE,
            ),
            Response(content=[Block(type=BlockType.TEXT, text="ok")], stop_reason=StopReason.END_TURN),
        ]
    )
    agent2 = Agent(provider=p2, system="s", auto_save=False,
                   session_permissions=agent.session_permissions)
    prompts2 = []
    monkeypatch.setattr(
        "builtins.input",
        lambda _p="": (prompts2.append(_p), "n")[1],
    )
    agent2.send("borra el archivo otra vez")
    assert prompts2 == [], "no debió volver a preguntar para el mismo patrón"


def test_session_permissions_pattern_is_per_first_token(monkeypatch):
    """Un comando distinto (otro primer token) SÍ vuelve a preguntar."""
    agent, _ = _approval_scenario(monkeypatch, ["siempre"])
    assert agent.session_permissions.allowed("bash", "rm temporal.txt")

    p = FakeProvider(
        [
            Response(
                content=[tool_use("2", "bash", '{"command":"curl http://x"}')],
                stop_reason=StopReason.TOOL_USE,
            ),
            Response(content=[Block(type=BlockType.TEXT, text="ok")], stop_reason=StopReason.END_TURN),
        ]
    )
    prompts = []
    monkeypatch.setattr("builtins.input", lambda _p="": (prompts.append(_p), "s")[1])
    p2_agent = Agent(provider=p, system="s", auto_save=False, session_permissions=agent.session_permissions)
    p2_agent.send("usa curl")
    assert prompts, "patrón distinto (curl) debió volver a preguntar"


def test_session_permissions_grant_via_s_also_stores_pattern(monkeypatch):
    """'s' confirma solo esa vez; 'siempre' registra. Ambos caminos exponen el estado."""
    agent, prompts = _approval_scenario(monkeypatch, ["s"])
    assert prompts
    assert not agent.session_permissions.allowed("bash", "rm temporal.txt"), "'s' no debe persistir permiso"

    agent_b, _ = _approval_scenario(monkeypatch, ["siempre"])
    assert agent_b.session_permissions.allowed("bash", "rm temporal.txt")


def test_session_permissions_write_path_pattern(monkeypatch):
    """Para tools de archivos el patrón usa el path (primer token del path)."""
    monkeypatch.setattr("builtins.input", lambda _p="": "siempre")
    p = FakeProvider(
        [
            Response(
                content=[tool_use("3", "write_file", '{"path":"docs/guia.md","content":"x"}')],
                stop_reason=StopReason.TOOL_USE,
            ),
            Response(content=[Block(type=BlockType.TEXT, text="ok")], stop_reason=StopReason.END_TURN),
        ]
    )
    agent = Agent(provider=p, system="s", auto_save=False)
    agent.send("escribe guia")
    assert agent.session_permissions.allowed("write_file", '{"path":"docs/guia.md","content":"x"}')


def test_session_permissions_clear_restores_question(monkeypatch):
    """/permissions clear (SessionPermissions.revoke_all) restaura la pregunta."""
    agent, _ = _approval_scenario(monkeypatch, ["siempre"])
    assert agent.session_permissions.allowed("bash", "rm temporal.txt")

    agent.session_permissions.revoke_all()
    assert not agent.session_permissions.allowed("bash", "rm temporal.txt")


def test_session_permissions_is_memory_only(tmp_path, monkeypatch):
    """El store NO debe escribir nada a disco."""
    monkeypatch.chdir(tmp_path)
    agent, _ = _approval_scenario(monkeypatch, ["siempre"])
    agent.session_permissions.revoke_all()
    assert list(tmp_path.rglob("*")) == [], "no debe persistir nada en disco"


def test_session_permissions_listing_has_entries(monkeypatch):
    """items() expone la lista para /permissions."""
    agent, _ = _approval_scenario(monkeypatch, ["siempre"])
    items = agent.session_permissions.items()
    assert ("bash", "rm") in items


def test_long_output_offloaded_to_scratch_file(tmp_path, monkeypatch):
    """Resultados de tools > 8000 chars se guardan en .yunta/scratch/ con preview de 500 chars."""
    from yunta.tools import registry

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(registry._tools["bash"], "fn", lambda raw: "A" * 500 + "B" * 9500)

    p = FakeProvider(
        [
            Response(
                content=[tool_use("1", "bash", '{"command":"echo largo"}')],
                stop_reason=StopReason.TOOL_USE,
            ),
            Response(content=[Block(type=BlockType.TEXT, text="listo")], stop_reason=StopReason.END_TURN),
        ]
    )

    a = Agent(provider=p, system="s", auto_save=False, confirm=lambda n, d: True)
    a.send("ejecuta tool larga")

    tool_results = [b for b in a.messages[2].content if b.type == BlockType.TOOL_RESULT]
    assert len(tool_results) == 1
    res_text = tool_results[0].tool_result
    assert len(res_text) < 1000
    assert res_text.startswith("A" * 500)
    assert "scratch file: .yunta/scratch/output_" in res_text

    scratch_files = list((tmp_path / ".yunta" / "scratch").glob("output_*.txt"))
    assert len(scratch_files) == 1
    content_on_disk = scratch_files[0].read_text(encoding="utf-8")
    assert len(content_on_disk) == 10000
    assert content_on_disk.startswith("A" * 500)
    assert content_on_disk.endswith("B" * 9500)


def test_doom_loop_detection_warning(tmp_path, monkeypatch):
    """3 repeticiones del mismo (tool, args) inyectan advertencia en tool_result."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "test.txt").write_text("hola", encoding="utf-8")

    responses = [
        Response(content=[tool_use("1", "read_file", '{"path":"test.txt"}')], stop_reason=StopReason.TOOL_USE),
        Response(content=[tool_use("2", "read_file", '{"path":"test.txt"}')], stop_reason=StopReason.TOOL_USE),
        Response(content=[tool_use("3", "read_file", '{"path":"test.txt"}')], stop_reason=StopReason.TOOL_USE),
        Response(content=[Block(type=BlockType.TEXT, text="listo")], stop_reason=StopReason.END_TURN),
    ]
    p = FakeProvider(responses)
    a = Agent(provider=p, system="s", auto_save=False, confirm=lambda n, d: True)
    out = a.send("revisa")
    assert out == "listo"

    # Verificar el 3er tool_result
    results = [b for m in a.messages for b in m.content if b.type == BlockType.TOOL_RESULT]
    assert len(results) == 3
    assert "[ADVERTENCIA DOOM-LOOP" in results[2].tool_result
    assert "se ha ejecutado 3 veces" in results[2].tool_result


def test_doom_loop_detection_pause(tmp_path, monkeypatch):
    """5 repeticiones fuerzan pausa con confirmación que incluye [PAUSA DOOM-LOOP]."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "test.txt").write_text("hola", encoding="utf-8")

    confirm_calls = []

    def custom_confirm(name, detail):
        confirm_calls.append((name, detail))
        return False  # Denegar la confirmación forzada de pausa por doom-loop

    responses = [
        Response(content=[tool_use(str(i), "read_file", '{"path":"test.txt"}')], stop_reason=StopReason.TOOL_USE)
        for i in range(1, 6)
    ]
    responses.append(Response(content=[Block(type=BlockType.TEXT, text="detenido")], stop_reason=StopReason.END_TURN))

    p = FakeProvider(responses)
    a = Agent(provider=p, system="s", auto_save=False, confirm=custom_confirm)
    out = a.send("loop test")

    # read_file no requiere aprobación en llamadas 1-4, solo en la 5ta por force_prompt
    assert len(confirm_calls) == 1
    name_5, detail_5 = confirm_calls[0]
    assert "[PAUSA DOOM-LOOP: repetición x5 de read_file]" in detail_5

    # El 5to tool_result debe ser de error por denegación
    results = [b for m in a.messages for b in m.content if b.type == BlockType.TOOL_RESULT]
    assert len(results) == 5
    assert results[4].is_error is True
    assert "user denied this tool call (doom-loop pause: 5 repeats)" in results[4].tool_result


def test_decision_point_reminder_injected_after_15_calls(tmp_path, monkeypatch):
    """Tras 15 ejecuciones de herramientas se inyecta un bloque TEXT de recordatorio en los mensajes del usuario (V3-5)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "test.txt").write_text("ok", encoding="utf-8")

    responses = [
        Response(content=[tool_use(str(i), "read_file", f'{{"path":"test.txt","i":{i}}}')], stop_reason=StopReason.TOOL_USE)
        for i in range(1, 16)
    ]
    responses.append(Response(content=[Block(type=BlockType.TEXT, text="fin")], stop_reason=StopReason.END_TURN))

    p = FakeProvider(responses)
    a = Agent(provider=p, system="s", auto_save=False, confirm=lambda n, d: True)
    out = a.send("ejecuta 15 tools")
    assert out == "fin"

    user_msgs = [m for m in a.messages if m.role == Role.USER]
    last_user_blocks = user_msgs[-1].content
    text_blocks = [b for b in last_user_blocks if b.type == BlockType.TEXT]
    assert len(text_blocks) == 1
    assert "[RECORDATORIO DE SISTEMA: Han transcurrido 15 ejecuciones de herramientas." in text_blocks[0].text





