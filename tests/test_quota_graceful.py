"""P7: degradación progresiva ante agotamiento de cuota (RateLimitError).

Al capturar el error, el harness persiste .yunta/estado-de-tarea.md con el
último prompt del usuario y el estado de la conversación, y cierra ordenado
en vez de morir con traceback."""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

import pytest

from yunta.agent import Agent
from yunta.api import Block, BlockType, Response, Role, StopReason
from yunta.resilience import save_task_state, should_save_state, QuotaExhausted


class FakeProvider:
    def __init__(self, fail_with=None):
        self.fail_with = fail_with
        self.total_usage = None

    def model(self):
        return "fake/model"

    def send(self, messages, tools, on_text=None):
        if self.fail_with:
            raise self.fail_with
        return Response(
            content=[Block(type=BlockType.TEXT, text="ok")],
            stop_reason=StopReason.END_TURN,
        )


def test_rate_limit_se_convierte_en_quota_exhausted():
    import litellm

    err = litellm.exceptions.RateLimitError(
        message="Usage limit reached for 5 hour",
        llm_provider="test",
        model="test",
    )
    assert should_save_state(err) is True


def test_error_generico_no_dispara_estado(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert should_save_state(ValueError("otra cosa")) is False


def test_save_task_state_persiste_prompt_y_historial(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    msgs = [
        {"role": "user", "text": "implementa P7 con tests primero"},
        {"role": "assistant", "text": "voy: leí los archivos"},
    ]
    save_task_state(
        last_prompt="implementa P7 con tests primero",
        messages_summary=msgs,
        error="RateLimitError: Usage limit reached",
    )
    f = Path(".yunta/estado-de-tarea.md")
    assert f.exists()
    content = f.read_text(encoding="utf-8")
    assert "implementa P7" in content
    assert "RateLimitError" in content
    assert "reanuda" in content.lower() or "retomar" in content.lower()


def test_agent_send_con_quota_lanza_quota_exhausted_y_persiste(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import litellm

    p = FakeProvider(
        fail_with=litellm.exceptions.RateLimitError(
            message="limit reached", llm_provider="t", model="t"
        )
    )
    agent = Agent(provider=p, system="s")
    with pytest.raises(QuotaExhausted):
        agent.send("tarea importante a medias")
    f = Path(".yunta/estado-de-tarea.md")
    assert f.exists()
    assert "tarea importante" in f.read_text(encoding="utf-8")


def test_estado_acumula_si_ya_existia(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    save_task_state("tarea 1", [], "err1")
    save_task_state("tarea 2", [], "err2")
    content = Path(".yunta/estado-de-tarea.md").read_text(encoding="utf-8")
    assert "tarea 1" in content and "tarea 2" in content
