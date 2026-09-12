"""P9: descomposición de specs grandes — parser, validación, lotes secuenciales
con contexto limpio y reanudación ante muerte de lote."""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

import pytest

from yunta.api import Block, BlockType, Response, Role, StopReason
from yunta.decompose import Subtask, decompose_task, run_chunks, _parse_subtasks, _validate


class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.received = []

    def send(self, messages, tools, on_text=None):
        self.received.append(list(messages))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def text_resp(text):
    return Response(content=[Block(type=BlockType.TEXT, text=text)],
                    stop_reason=StopReason.END_TURN)


# ---------- parser y validación ----------

def test_parse_subtasks_json_valido():
    tasks = _parse_subtasks('intro basura [{"goal":"a","files":["f1.py"],"verify":"t1"}] cola')
    assert len(tasks) == 1
    assert tasks[0].goal == "a" and tasks[0].files == ["f1.py"]


def test_parse_sin_json_lanza():
    with pytest.raises(ValueError):
        _parse_subtasks("no hay array aqui")


def test_validate_rechaza_mas_de_2_archivos():
    with pytest.raises(ValueError, match="archivos"):
        _validate([Subtask("x", ["a", "b", "c"])])


def test_validate_rechaza_solapamiento():
    with pytest.raises(ValueError, match="dos subtareas"):
        _validate([
            Subtask("1", ["a.py", "b.py"]),
            Subtask("2", ["b.py", "c.py"]),
        ])


def test_decompose_un_intento_si_valido():
    plan = json.dumps([
        {"goal": "tool", "files": ["t.py"], "verify": "pytest t"},
        {"goal": "tests", "files": ["test_t.py"], "verify": "pytest"},
    ])
    p = FakeProvider([text_resp(plan)])
    tasks = decompose_task(p, "spec grande")
    assert len(tasks) == 2
    assert p.received[0][0].content[0].text.endswith("spec grande")


def test_decompose_regenera_una_vez_si_invalido():
    plan_malo = json.dumps([
        {"goal": "1", "files": ["a", "b"]},
        {"goal": "2", "files": ["b", "c"]},  # solape
    ])
    plan_bueno = json.dumps([
        {"goal": "1", "files": ["a"]},
        {"goal": "2", "files": ["c"]},
    ])
    p = FakeProvider([text_resp(plan_malo), text_resp(plan_bueno)])
    tasks = decompose_task(p, "spec")
    assert len(tasks) == 2


def test_decompose_falla_tras_dos_intentos():
    p = FakeProvider([text_resp("sin json"), text_resp("tampoco [}")])
    with pytest.raises(ValueError):
        decompose_task(p, "spec")


# ---------- ejecución por lotes ----------

def test_run_chunks_contexto_limpio_y_secuencial(tmp_path, monkeypatch):
    """Cada subagente recibe SOLO su subtarea (no la historia de los otros)."""
    monkeypatch.chdir(tmp_path)
    p = FakeProvider([text_resp("lote1 ok"), text_resp("lote2 ok")])
    subtasks = [Subtask("uno", ["a.py"], "v1"), Subtask("dos", ["b.py"], "v2")]

    class FakeAgent:
        def __init__(self, provider=None, system="", max_turns=0, confirm=None, **k):
            self.provider = provider
            self.messages = []

        def send(self, prompt):
            return text_resp("ok-" + prompt[:12]).content and "ok"

    # inyectar agent que registra su prompt
    prompts = []

    class SpyAgent(FakeAgent):
        def send(self, prompt):
            prompts.append(prompt)
            return "resumen-" + str(len(prompts))

    results = run_chunks(p, subtasks, system="s", agent_cls=SpyAgent)
    assert results == ["resumen-1", "resumen-2"]
    assert "Subtarea 1/2" in prompts[0] and "Subtarea 2/2" in prompts[1]
    assert "uno" in prompts[0] and "dos" in prompts[1]


def test_run_chunks_muerte_persiste_lote_pendiente(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import litellm
    err = litellm.exceptions.RateLimitError(message="quota", llm_provider="t", model="t")
    p = FakeProvider([])

    class DyingAgent:
        def __init__(self, provider=None, system="", max_turns=0, confirm=None, **k):
            self.provider = provider
            self.messages = []

        def send(self, prompt):
            raise err

    subtasks = [Subtask("uno", ["a"]), Subtask("dos", ["b"]), Subtask("tres", ["c"])]
    with pytest.raises(Exception):
        run_chunks(p, subtasks, system="s", agent_cls=DyingAgent, start_from=1)
    f = Path(".yunta/estado-de-tarea.md")
    assert f.exists()
    content = f.read_text(encoding="utf-8")
    assert "lote 2/3" in content
    assert "dos" in content


def test_run_chunks_start_from_salta_lotes():
    p = FakeProvider([])
    prompts = []

    class SpyAgent:
        def __init__(self, provider=None, system="", max_turns=0, confirm=None, **k):
            self.provider = provider
            self.messages = []

        def send(self, prompt):
            prompts.append(prompt)
            return "ok"

    subtasks = [Subtask("uno", ["a"]), Subtask("dos", ["b"])]
    run_chunks(p, subtasks, system="s", agent_cls=SpyAgent, start_from=1)
    assert len(prompts) == 1
    assert "Subtarea 2/2" in prompts[0]
