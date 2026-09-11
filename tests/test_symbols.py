import json
import pytest
from yunta.tools.symbols import find_symbol, get_ast_outline


def test_find_symbol_exact_and_partial(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code = """
class Calculator:
    def add(self, a, b):
        return a + b

def calculate_total(items):
    return sum(items)
"""
    py_file = tmp_path / "calc.py"
    py_file.write_text(code, encoding="utf-8")

    # Partial match
    res_partial = find_symbol(json.dumps({"name": "calc"}))
    assert "calc.py" in res_partial
    assert "Calculator" in res_partial
    assert "calculate_total" in res_partial

    # Exact match
    res_exact = find_symbol(json.dumps({"name": "Calculator", "exact": True}))
    assert "Calculator" in res_exact
    assert "calculate_total" not in res_exact


def test_find_symbol_no_match(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = find_symbol(json.dumps({"name": "NonExistentSymbol"}))
    assert "no se encontraron símbolos coincidentes" in res


def test_get_ast_outline(tmp_path):
    code = """
import os
from pathlib import Path

class UserStore:
    def get_user(self, user_id):
        pass

def format_name(name):
    return name.title()
"""
    py_file = tmp_path / "store.py"
    py_file.write_text(code, encoding="utf-8")

    res = get_ast_outline(json.dumps({"path": str(py_file)}))
    assert "esquema AST de store.py" in res
    assert "import os" in res
    assert "from pathlib import Path" in res
    assert "class UserStore" in res
    assert "def get_user(self, user_id)" in res
    assert "def format_name(name)" in res


def test_get_ast_outline_syntax_error(tmp_path):
    bad_code = "def broken_func(: pass"
    py_file = tmp_path / "bad.py"
    py_file.write_text(bad_code, encoding="utf-8")

    res = get_ast_outline(json.dumps({"path": str(py_file)}))
    assert "error de sintaxis en" in res
