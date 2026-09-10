"""P8: presupuesto de sesión visible — umbrales 70%/90% y cierre ordenado."""
import sys
from pathlib import Path

sys.path.insert(0, ".")

import pytest

from yunta.budget import SessionBudget, check_budget


def test_budget_empieza_sano():
    b = SessionBudget(max_session_tokens=100_000)
    assert b.level() == "ok"
    assert b.warn_at_70() is False


def test_aviso_al_70():
    b = SessionBudget(max_session_tokens=100_000)
    b.add(69_999)
    assert b.warn_at_70() is False
    b.add(1)
    assert b.warn_at_70() is True
    assert b.level() == "warn"


def test_cierre_ordenado_al_90():
    b = SessionBudget(max_session_tokens=100_000)
    b.add(90_000)
    assert b.level() == "critical"
    assert b.warn_at_70() is True


def test_check_budget_avisa_una_vez(capsys):
    b = SessionBudget(max_session_tokens=100)
    b.add(75)
    check_budget(b)  # primera vez: avisa
    out1 = capsys.readouterr().out
    assert "70%" in out1
    check_budget(b)  # segunda vez: no repite
    out2 = capsys.readouterr().out
    assert out2 == ""


def test_check_budget_critico_guarda_estado(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".yunta").mkdir(parents=True, exist_ok=True)
    b = SessionBudget(max_session_tokens=100)
    b.add(95)
    def _save():
        Path(".yunta").mkdir(exist_ok=True)
        Path(".yunta/estado-de-tarea.md").write_text("x", encoding="utf-8")
    check_budget(b, save_state=_save)
    assert Path(".yunta/estado-de-tarea.md").exists()
    assert "90%" in capsys.readouterr().out


def test_check_budget_sano_silencioso(capsys):
    b = SessionBudget(max_session_tokens=100)
    b.add(10)
    check_budget(b)
    assert capsys.readouterr().out == ""
