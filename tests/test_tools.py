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

def test_bash_compact_output():
    from yunta.tools.bash import _compact_output

    # Caso pytest exitoso: solo resumen
    pytest_out = "============================= test session starts =============================\nrootdir: /test\ncollected 5 items\n\ntests/test_a.py ..... [100%]\n\n============================= 5 passed in 0.5s =============================\n"
    compacted = _compact_output(pytest_out, 0)
    assert "test session starts" in compacted
    assert "5 passed in 0.5s" in compacted
    assert "tests/test_a.py ....." not in compacted

    # Caso salida genérica larga exitosa: recorta el centro
    long_out = "\n".join([f"linea {i}" for i in range(50)])
    compacted_long = _compact_output(long_out, 0)
    assert "linea 0" in compacted_long
    assert "linea 49" in compacted_long
    assert "omitidas por brevedad" in compacted_long



def test_read_file_size_cap_and_offset_limit(tmp_path):
    import json
    from yunta.tools.files import read_file

    large_file = tmp_path / "large_file.txt"
    lines = [f"linea {i}\n" for i in range(1, 2501)]
    large_file.write_text("".join(lines), encoding="utf-8")

    # Lectura por defecto: cap a 2000 lineas
    res = read_file(json.dumps({"path": str(large_file)}))
    assert "linea 1\n" in res
    assert "linea 2000\n" in res
    assert "linea 2001\n" not in res
    assert "[... truncado: 500 líneas no mostradas" in res

    # Lectura con offset y limit
    res_part2 = read_file(json.dumps({"path": str(large_file), "offset": 2001, "limit": 500}))
    assert "linea 2001\n" in res_part2
    assert "linea 2500\n" in res_part2
    assert "truncado" not in res_part2


def test_list_dir_structure_and_sizes(tmp_path):
    import json
    from yunta.tools.files import list_dir

    sub = tmp_path / "subcarpeta"
    sub.mkdir()
    (sub / "modulo.py").write_text("print('hello')", encoding="utf-8")
    (tmp_path / "archivo.txt").write_text("contenido simple", encoding="utf-8")
    
    # Crear carpeta ignorada (.git)
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("repo", encoding="utf-8")

    tree = list_dir(json.dumps({"path": str(tmp_path)}))
    assert "subcarpeta/" in tree
    assert "modulo.py" in tree
    assert "archivo.txt" in tree
    assert ".git" not in tree


def test_list_dir_max_files_truncation(tmp_path):
    import json
    from yunta.tools.files import list_dir

    for i in range(10):
        (tmp_path / f"archivo_{i}.txt").write_text("x", encoding="utf-8")

    tree = list_dir(json.dumps({"path": str(tmp_path), "max_files": 4}))
    assert "archivo_0.txt" in tree
    assert "truncado" in tree
