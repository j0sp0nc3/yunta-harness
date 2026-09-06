import sys

sys.path.insert(0, ".")

from yunta.tools.bash import bash
from yunta.tools.files import read_file, write_file


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
