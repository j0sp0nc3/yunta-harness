"""M-A: el auto-feedback (feedback.summarize) también debe ejecutarse en los
despachos single-shot de cli.main(), no solo al salir del REPL.

Camino 1: `yunta "tarea"` (despacho normal).
Camino 2: `yunta --chunks --yes "tarea"` (despacho por lotes, tras run_chunks).
"""
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, ".")

import yunta.cli as cli_mod
from yunta.api import Block, BlockType, Response, Role, StopReason

LESSON_TEXT = (
    "TAREA: una sola tarea de prueba\n"
    "RESULTADO: logrado\n"
    "LECCION: escribir el test antes del código"
)

PLAIN_TEXT = "hecho"


class FakeProvider:
    """Provider falso: responde el cuestionario de lecciones cuando detecta
    el prompt de auto-evaluación, y un END_TURN plano en cualquier otro caso."""

    def __init__(self):
        self.lesson_calls = 0

    def model(self):
        return "fake/model"

    def send(self, messages, tools, on_text=None):
        if isinstance(messages, str):
            text = messages
        else:
            chunks = []
            for m in messages:
                for b in getattr(m, "content", []) or []:
                    if getattr(b, "type", None) == BlockType.TEXT:
                        chunks.append(b.text)
            text = "\n".join(chunks)
        if "TAREA:" in text and "RESULTADO:" in text and "LECCION:" in text:
            self.lesson_calls += 1
            return Response(
                content=[Block(type=BlockType.TEXT, text=LESSON_TEXT)],
                stop_reason=StopReason.END_TURN,
            )
        return Response(
            content=[Block(type=BlockType.TEXT, text=PLAIN_TEXT)],
            stop_reason=StopReason.END_TURN,
        )


@pytest.fixture
def ss_env(monkeypatch, tmp_path):
    """Aísla cwd, sustituye el provider real por FakeProvider y devuelve la
    lista donde FeedbackStore.summarize registra sus invocaciones."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("yunta.tools.delegate.set_provider", lambda p: None)
    calls = []

    def spy_summarize(self, provider, messages):
        calls.append((provider, list(messages)))

    monkeypatch.setattr(cli_mod.FeedbackStore, "summarize", spy_summarize)

    def no_input(prompt=""):
        raise AssertionError("input() no debe alcanzarse en un despacho single-shot")

    monkeypatch.setattr("builtins.input", no_input)
    return calls


def test_single_shot_calls_summarize(monkeypatch, ss_env):
    fake = FakeProvider()
    monkeypatch.setattr(sys, "argv", ["yunta", "tarea de prueba"])
    monkeypatch.setattr(cli_mod, "LiteLLMProvider", lambda system="": fake)

    cli_mod.main()

    assert len(ss_env) == 1, "summarize debe invocarse exactamente una vez"
    provider, messages = ss_env[0]
    assert provider is fake, "summarize debe recibir el provider del despacho"
    assert messages, "summarize debe recibir el historial del agente"
    has_prompt = any(
        getattr(m, "role", None) == Role.USER
        and any(
            getattr(b, "type", None) == BlockType.TEXT and "tarea de prueba" in b.text
            for b in (getattr(m, "content", None) or [])
        )
        for m in messages
    )
    assert has_prompt, "el historial debe contener el prompt single-shot"


def test_chunks_calls_summarize(monkeypatch, ss_env):
    monkeypatch.setenv("YUNTA_CHUNKS", "1")
    monkeypatch.setattr(sys, "argv", ["yunta", "--chunks", "--yes", "tarea de prueba"])
    fake = FakeProvider()
    monkeypatch.setattr(cli_mod, "LiteLLMProvider", lambda system="": fake)
    # run_chunks exitoso simulado: el punto a testear es que summarize corre
    # después, con el mismo provider, antes del cierre de mcp_clients.
    monkeypatch.setattr(
        "yunta.decompose.decompose_task",
        lambda provider, prompt: [SimpleNamespace(goal="lote único", files=[])],
    )
    monkeypatch.setattr(
        "yunta.decompose.run_chunks",
        lambda provider, subtasks, system, confirm=None: ["ok"],
    )

    cli_mod.main()

    assert len(ss_env) == 1, "summarize debe invocarse exactamente una vez tras run_chunks"
    provider, messages = ss_env[0]
    assert provider is fake, "summarize debe recibir el provider del despacho --chunks"
    assert messages, "summarize debe recibir el historial del agente"
