import json
import sys
from pathlib import Path

from yunta import cli
from yunta.ide import ide_init


def test_ide_init_crea_archivos(tmp_path):
    created = ide_init(target_dir=tmp_path)
    assert set(created) == {".vscode/mcp.json", ".vscode/tasks.json"}

    mcp = json.loads((tmp_path / ".vscode" / "mcp.json").read_text(encoding="utf-8"))
    assert mcp == {"servers": {"yunta": {"command": "yunta", "args": ["serve-mcp"]}}}


def test_ide_init_tasks_json_valido(tmp_path):
    ide_init(target_dir=tmp_path)
    tasks = json.loads((tmp_path / ".vscode" / "tasks.json").read_text(encoding="utf-8"))
    assert tasks["version"] == "2.0.0"
    labels = [t["label"] for t in tasks["tasks"]]
    assert labels == ["yunta: run", "yunta: check", "yunta: init"]
    commands = [t["command"] for t in tasks["tasks"]]
    assert commands == ["yunta", "yunta check", "yunta init"]
    assert all(t["type"] == "shell" for t in tasks["tasks"])


def test_ide_init_no_sobrescribe_existentes(tmp_path):
    mcp_path = tmp_path / ".vscode" / "mcp.json"
    tasks_path = tmp_path / ".vscode" / "tasks.json"
    mcp_path.parent.mkdir(parents=True)
    mcp_path.write_text('{"servers": {"otro": {"command": "x"}}}', encoding="utf-8")
    tasks_path.write_text('{"version": "2.0.0", "tasks": []}', encoding="utf-8")

    created = ide_init(target_dir=tmp_path)

    assert created == []
    assert json.loads(mcp_path.read_text(encoding="utf-8")) == {
        "servers": {"otro": {"command": "x"}}
    }
    assert json.loads(tasks_path.read_text(encoding="utf-8")) == {"version": "2.0.0", "tasks": []}


def test_ide_init_renuente_por_archivo(tmp_path):
    """Si solo tasks.json existe, se crea mcp.json y se preserva tasks.json."""
    (tmp_path / ".vscode").mkdir()
    (tmp_path / ".vscode" / "tasks.json").write_text("previo", encoding="utf-8")

    created = ide_init(target_dir=tmp_path)

    assert created == [".vscode/mcp.json"]
    assert (tmp_path / ".vscode" / "tasks.json").read_text(encoding="utf-8") == "previo"
    assert json.loads((tmp_path / ".vscode" / "mcp.json").read_text(encoding="utf-8"))


def test_cli_ide_init_dispatch(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["yunta", "ide-init"])

    cli.main()

    assert (tmp_path / ".vscode" / "mcp.json").exists()
    assert (tmp_path / ".vscode" / "tasks.json").exists()
