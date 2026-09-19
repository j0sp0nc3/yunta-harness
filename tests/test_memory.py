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


def test_remember_appends_as_jsonl_not_array(storage):
    """Feature 4: cada remember() debe escribir UNA línea JSON nueva, sin
    reescribir el archivo completo (formato amigable con merges de git)."""
    remember('{"content": "uno", "kind": "fact"}')
    remember('{"content": "dos", "kind": "fact"}')
    raw = storage.read_text(encoding="utf-8")
    lines = [l for l in raw.splitlines() if l.strip()]
    assert len(lines) == 2
    assert not raw.strip().startswith("[")
    for line in lines:
        import json as _json
        _json.loads(line)  # cada línea es JSON válido por sí sola


def test_legacy_array_format_migrates_to_jsonl_on_first_load(storage):
    """Feature 4: el formato viejo (array JSON completo) se migra
    automáticamente y una sola vez al leerlo."""
    import json as _json
    legacy = [
        {"date": "2026-01-01T00:00:00", "kind": "fact", "content": "vieja 1", "tags": []},
        {"date": "2026-01-02T00:00:00", "kind": "decision", "content": "vieja 2", "tags": ["x"]},
    ]
    storage.parent.mkdir(parents=True, exist_ok=True)
    storage.write_text(_json.dumps(legacy, indent=2), encoding="utf-8")

    entries = memory._load(storage)
    assert len(entries) == 2
    assert entries[0]["content"] == "vieja 1"

    # El archivo en disco ya quedó reescrito como JSONL
    raw = storage.read_text(encoding="utf-8")
    assert not raw.strip().startswith("[")
    assert len(raw.strip().splitlines()) == 2

    # Un remember() posterior debe APPEND-ear sin corromper lo migrado
    remember('{"content": "nueva", "kind": "fact"}')
    entries_after = memory._load(storage)
    assert len(entries_after) == 3
    assert entries_after[-1]["content"] == "nueva"


def test_empty_memory_file_returns_empty_list(storage):
    storage.parent.mkdir(parents=True, exist_ok=True)
    storage.write_text("", encoding="utf-8")
    assert memory._load(storage) == []


def test_corrupted_jsonl_line_is_skipped_not_fatal(storage):
    storage.parent.mkdir(parents=True, exist_ok=True)
    storage.write_text('{"content": "ok", "kind": "fact"}\nesto no es json\n', encoding="utf-8")
    entries = memory._load(storage)
    assert len(entries) == 1
    assert entries[0]["content"] == "ok"
