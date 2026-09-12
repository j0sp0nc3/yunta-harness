import sys

import pytest

sys.path.insert(0, ".")

import yunta.cli as cli_mod
import yunta.decompose as decompose_mod
from yunta.decompose import Subtask, looks_multi_file


def test_looks_multi_file_true_with_4_distinct_files():
    prompt = (
        "Refactoriza yunta/decompose.py y yunta/cli.py, actualiza "
        "tests/test_mb_autotrigger.py y revisa docs/PLAN.md."
    )
    assert looks_multi_file(prompt) is True
    # Unicidad: repetir el mismo archivo no suma.
    assert looks_multi_file("edita a.py, a.py y a.py") is False


def test_looks_multi_file_false_for_simple_prompt():
    assert looks_multi_file("revisa los tests y corrige el bug del login") is False
    assert looks_multi_file("edita yunta/api.py") is False


def test_main_autotriggers_chunks_for_multi_file_prompt(monkeypatch, capsys):
    monkeypatch.setenv("LLM_MODEL", "openai/test-model")
    monkeypatch.delenv("YUNTA_CHUNKS", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        ["yunta", "Refactoriza yunta/decompose.py, yunta/cli.py, tests/test_x.py y docs/PLAN.md"],
    )

    calls = {"decompose": [], "chunks": []}

    def fake_decompose(provider, spec, max_attempts=2):
        calls["decompose"].append(spec)
        return [
            Subtask(goal="g1", files=["yunta/decompose.py"], verify="pytest"),
            Subtask(goal="g2", files=["yunta/cli.py"], verify="pytest"),
        ]

    def fake_run_chunks(provider, subtasks, system, confirm=None, start_from=0, agent_cls=None):
        calls["chunks"].append([t.goal for t in subtasks])
        return ["ok1", "ok2"]

    monkeypatch.setattr(decompose_mod, "decompose_task", fake_decompose)
    monkeypatch.setattr(decompose_mod, "run_chunks", fake_run_chunks)
    monkeypatch.setattr(cli_mod.FeedbackStore, "summarize", lambda self, provider, messages: None)

    cli_mod.main()
    out = capsys.readouterr().out

    assert len(calls["decompose"]) == 1
    assert len(calls["chunks"]) == 1
    assert "[M-B]" in out
    assert "menciona 4 archivos" in out
