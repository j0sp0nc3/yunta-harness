import sys

import pytest

sys.path.insert(0, ".")

import yunta.tools.memory as memory
from yunta.tools.memory import recall, remember


@pytest.fixture()
def storage(tmp_path):
    memory.MEMORY_PATH = tmp_path / "memory.json"
    yield memory.MEMORY_PATH
    memory.MEMORY_PATH = tmp_path / "memory.json"


def test_remember_recall_roundtrip(storage):
    out = remember('{"content": "El proyecto usa Python 3.10+", "kind": "fact", "tags": ["python", "version"]}')
    assert "recordado" in out
    out = recall('{"query": "Python"}')
    assert "(sin resultados)" not in out
    assert "El proyecto usa Python 3.10+" in out
    assert "(fact)" in out
    assert "[python, version]" in out
    assert "[date" in out or "[" in out  # formato '[fecha] (kind) content [tags]'


def test_recall_case_insensitive(storage):
    remember('{"content": "Preferimos commits pequeños y frecuentes", "kind": "preference"}')
    out = recall('{"query": "COMMIT"}')
    assert "Preferimos commits" in out


def test_recall_sin_resultados(storage):
    out = recall('{"query": "zzz_inexistente"}')
    assert out == "(sin resultados)"


def test_entrada_invalida(storage):
    with pytest.raises(ValueError):
        remember('{"kind": "fact"}')  # falta content
    with pytest.raises(ValueError):
        recall('{}')  # falta query


def test_persistencia_entre_llamadas(storage):
    """El storage debe sobrevivir a 'sesiones' (llamadas) distintas."""
    remember('{"content": "decisión: migrar a pytest", "kind": "decision"}')
    entries = memory._load(storage)
    assert len(entries) == 1
    assert entries[0]["kind"] == "decision"
