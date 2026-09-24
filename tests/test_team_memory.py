import json

from yunta.team_memory import dedup_learnings, dedup_memory, sync_report


def test_dedup_learnings_removes_exact_duplicate_lines(tmp_path):
    path = tmp_path / "learnings.md"
    path.write_text(
        "# Lecciones\n\n"
        "- [2026-01-01] tarea A → logrado. Lección: usar tests primero.\n"
        "- [2026-01-02] tarea B → parcial. Lección: revisar edge cases.\n"
        "- [2026-01-01] tarea A → logrado. Lección: usar tests primero.\n",
        encoding="utf-8",
    )
    removed = dedup_learnings(str(path))
    assert removed == 1
    content = path.read_text(encoding="utf-8")
    assert content.count("usar tests primero") == 1
    assert "revisar edge cases" in content


def test_dedup_learnings_no_duplicates_returns_zero(tmp_path):
    path = tmp_path / "learnings.md"
    path.write_text("# Lecciones\n\n- [2026-01-01] a → b. Lección: c.\n", encoding="utf-8")
    assert dedup_learnings(str(path)) == 0


def test_dedup_learnings_missing_file_returns_zero(tmp_path):
    assert dedup_learnings(str(tmp_path / "no-existe.md")) == 0


def test_dedup_memory_removes_duplicates_keeps_first(tmp_path):
    path = tmp_path / "memory.jsonl"
    entries = [
        {"date": "2026-01-01T00:00:00", "kind": "fact", "content": "el proyecto usa python", "tags": []},
        {"date": "2026-01-02T00:00:00", "kind": "decision", "content": "migrar a pytest", "tags": []},
        {"date": "2026-01-03T00:00:00", "kind": "fact", "content": "el proyecto usa python", "tags": ["dup"]},
    ]
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")

    removed = dedup_memory(path)
    assert removed == 1

    remaining = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(remaining) == 2
    assert remaining[0]["date"] == "2026-01-01T00:00:00"  # se conservó la primera aparición


def test_dedup_memory_no_duplicates_returns_zero(tmp_path):
    path = tmp_path / "memory.jsonl"
    path.write_text('{"kind": "fact", "content": "a"}\n{"kind": "fact", "content": "b"}\n', encoding="utf-8")
    assert dedup_memory(path) == 0


def test_sync_report_counts_existing_files(tmp_path):
    yunta_dir = tmp_path / ".yunta"
    yunta_dir.mkdir()
    (yunta_dir / "learnings.md").write_text(
        "# Lecciones\n\n- [2026-01-01] a → b. Lección: c.\n- [2026-01-02] d → e. Lección: f.\n",
        encoding="utf-8",
    )
    (yunta_dir / "memory.json").write_text(
        '{"kind": "fact", "content": "uno"}\n{"kind": "fact", "content": "dos"}\n',
        encoding="utf-8",
    )
    report = sync_report(tmp_path)
    assert report["learnings"]["count"] == 2
    assert report["memory"]["count"] == 2


def test_sync_report_missing_files_returns_none(tmp_path):
    report = sync_report(tmp_path)
    assert report["learnings"] is None
    assert report["memory"] is None
