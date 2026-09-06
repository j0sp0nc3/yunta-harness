import sys

sys.path.insert(0, ".")

from yunta.tools.bash import bash
from yunta.tools.files import read_file, str_replace, write_file


def test_bash_stdout():
    out = bash('{"command": "echo hola"}')
    assert "hola" in out


def test_bash_error_returned_as_output():
    out = bash('{"command": "exit 3"}')
    assert "[exit 3]" in out


def test_bash_missing_command():
    try:
        bash("{}")
        assert False, "debio fallar"
    except ValueError as e:
        assert "command" in str(e)


def test_write_then_read(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_file('{"path":"sub/a.txt","content":"contenido"}')
    assert read_file('{"path":"sub/a.txt"}') == "contenido"


def test_read_missing_file():
    try:
        read_file('{"path":"definitivamente_no_existe.txt"}')
        assert False, "debio fallar"
    except FileNotFoundError:
        pass


def test_str_replace_success(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_file('{"path":"file.txt","content":"linea 1\\nlinea 2\\nlinea 3"}')
    res = str_replace('{"path":"file.txt","old_str":"linea 2","new_str":"linea dos"}')
    assert "successfully replaced" in res or "replaced" in res
    assert read_file('{"path":"file.txt"}') == "linea 1\nlinea dos\nlinea 3"


def test_str_replace_not_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_file('{"path":"file.txt","content":"hola mundo"}')
    try:
        str_replace('{"path":"file.txt","old_str":"chau","new_str":"adios"}')
        assert False, "debio fallar"
    except ValueError as e:
        assert "no fue encontrado" in str(e)


def test_str_replace_ambiguous(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_file('{"path":"file.txt","content":"hola\\nhola\\nhola"}')
    try:
        str_replace('{"path":"file.txt","old_str":"hola","new_str":"chau"}')
        assert False, "debio fallar"
    except ValueError as e:
        assert "veces" in str(e) or "ambigüedad" in str(e)


def test_str_replace_missing_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    try:
        str_replace('{"path":"no_existe.txt","old_str":"a","new_str":"b"}')
        assert False, "debio fallar"
    except FileNotFoundError:
        pass
