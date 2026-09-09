"""Tests del REPL: comando /permissions (O1-c, V3-2 permisos persistentes)."""
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, ".")

import yunta.cli as cli_mod
from yunta.agent import SessionPermissions


class FakeProvider:
    def __init__(self, system=""):
        self.system = system
        self.total_usage = None

    def model(self):
        return "fake/model"

    def send(self, messages, tools, on_text=None):
        return SimpleNamespace(content=[], usage=None, stop_reason=None)


class InertFeedback:
    def __init__(self, *a, **k):
        pass

    def preamble(self):
        return ""

    def summarize(self, *a, **k):
        pass


@pytest.fixture
def repl_env(monkeypatch, tmp_path):
    """Aísla cwd en tmp_path, sustituye provider/feedback y devuelve captura de input."""
    monkeypatch.setattr(sys, "argv", ["yunta"])  # evitar dispatch/single-shot bajo pytest
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli_mod, "LiteLLMProvider", FakeProvider)
    monkeypatch.setattr(cli_mod, "FeedbackStore", InertFeedback)
    monkeypatch.setattr("yunta.tools.delegate.set_provider", lambda p: None)


def _run_repl(monkeypatch, agent_capture, lines, shared_perms=None):
    """Ejecuta cli.main() alimentando input() con `lines`; captura el Agent creado.
    shared_perms permite simular la misma sesión compartiendo los permisos."""
    it = iter(lines)

    def fake_input(prompt=""):
        try:
            return next(it)
        except StopIteration:
            raise KeyboardInterrupt  # simula Ctrl+D/Ctrl+C para salir del REPL

    monkeypatch.setattr("builtins.input", fake_input)

    real_agent_cls = cli_mod.Agent

    class SpyAgent(real_agent_cls):
        def __init__(self, *a, **k):
            if shared_perms is not None:
                k.setdefault("session_permissions", shared_perms)
            super().__init__(*a, **k)
            agent_capture.append(self)

    monkeypatch.setattr(cli_mod, "Agent", SpyAgent)
    try:
        cli_mod.main()
    except (KeyboardInterrupt, EOFError):
        pass


def test_permissions_lists_empty_then_registered_pattern(monkeypatch, tmp_path, repl_env, capsys):
    captured = []
    # Secuencia: consultar vacío, salir. Luego un segundo REPL con permiso previo:
    # usamos un solo arranque: primero /permissions (vacío) y, tras inyectar un
    # permiso vía agente de la MISMA sesión, /permissions otra vez.
    def run_with_inputs(inputs):
        it = iter(inputs)

        def fake_input(prompt=""):
            try:
                return next(it)
            except StopIteration:
                raise KeyboardInterrupt

        monkeypatch.setattr("builtins.interaction_input_holder", None, raising=False)
        monkeypatch.setattr("builtins.input", fake_input)

    # Arranque 1: /permissions sin permisos → vacío
    _run_repl(monkeypatch, captured, ["/permissions", "/exit"])
    out1 = capsys.readouterr().out
    assert "no hay permisos persistentes" in out1

    # Arranque 2: misma sesión (permisos compartidos), un permiso otorgado y listar
    assert captured and isinstance(captured[0].session_permissions, SessionPermissions)
    shared = SessionPermissions()
    shared.grant("bash", "rm temporal.txt")
    _run_repl(monkeypatch, captured, ["/permissions", "/exit"], shared_perms=shared)
    out2 = capsys.readouterr().out
    assert "bash: rm*" in out2

    # Arranque 3: /permissions clear revoca y el listado vuelve a vacío
    _run_repl(monkeypatch, captured, ["/permissions clear", "/permissions", "/exit"], shared_perms=shared)
    out3 = capsys.readouterr().out
    assert "permisos de sesión revocados" in out3
    assert "no hay permisos persistentes" in out3
