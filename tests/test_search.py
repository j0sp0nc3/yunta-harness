import sys

import pytest

sys.path.insert(0, ".")

from yunta.tools.search import glob, grep


@pytest.fixture()
def tree(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "a.py").write_text("x = 1\nhola = 'mundo'\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("nada que ver aqui\n", encoding="utf-8")
    return tmp_path


def test_grep_encuentra_con_numero_de_linea(tree):
    out = grep('{"pattern": "hola", "path": "%s"}' % tree.as_posix())
    assert out == f"{(tree / 'sub' / 'a.py').as_posix()}:2: hola = 'mundo'"


def test_grep_respeta_max_results(tree):
    out = grep('{"pattern": ".*", "path": "%s", "max_results": 2}' % tree.as_posix())
    assert len(out.splitlines()) == 2


def test_grep_sin_resultados_devuelve_string_vacio(tree):
    out = grep('{"pattern": "zzz_inexistente", "path": "%s"}' % tree.as_posix())
    assert out == ""


def test_glob_encuentra_py_en_subdirectorio(tree):
    out = glob('{"pattern": "**/*.py", "path": "%s"}' % tree.as_posix())
    assert out == (tree / "sub" / "a.py").as_posix()


def test_entrada_invalida():
    with pytest.raises(ValueError):
        grep('{"path": "."}')  # falta pattern
    with pytest.raises(ValueError):
        grep('{"pattern": "["}')  # regex inválido
    with pytest.raises(FileNotFoundError):
        glob('{"pattern": "*.py", "path": "directorio_que_no_existe_xyz"}')
