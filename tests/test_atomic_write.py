"""P6: write_file atómico — nunca deja archivos truncados ni rompe el original."""
import sys

sys.path.insert(0, ".")

import pytest

from yunta.tools.files import write_file


def test_write_ok_confirma_bytes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = write_file('{"path":"a.txt","content":"hola"}')
    assert "hola" in out or "bytes" in out
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "hola"


def test_py_invalido_se_rechaza_y_no_toca_original(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "mod.py").write_text("x = 1\n", encoding="utf-8")
    truncado = "def f():\n    return (1, 2"  # paréntesis sin cerrar
    import json as _json
    raw = _json.dumps({"path": "mod.py", "content": truncado})
    with pytest.raises(ValueError, match="sintaxis|balance"):
        write_file(raw)
    assert (tmp_path / "mod.py").read_text(encoding="utf-8") == "x = 1\n"  # intacto


def test_json_truncado_en_el_input_no_alcanza_al_archivo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "t.txt").write_text("original", encoding="utf-8")
    # input JSON cortado a mitad (como cuando la sesión muere escribiendo)
    with pytest.raises(Exception):
        write_file('{"path":"t.txt","content":"nuevo')
    assert (tmp_path / "t.txt").read_text(encoding="utf-8") == "original"


def test_texto_plano_con_comillas_desbalanceadas(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        write_file('{"path":"pares.txt","content":"comilla sin cerrar: \\""}')
    assert not (tmp_path / "pares.txt").exists()


def test_texto_valido_con_caracteres_especiales(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_file('{"path":"ok.txt","content":"ñ áéíóú (paréntesis ok) [ok] {ok}"}')
    assert "ñ" in (tmp_path / "ok.txt").read_text(encoding="utf-8")


def test_no_quedan_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    try:
        write_file('{"path":"mal.py","content":"def broken(:"}')
    except ValueError:
        pass
    leftovers = list(tmp_path.rglob("*.tmp*"))
    assert leftovers == [], f"residuos: {leftovers}"
