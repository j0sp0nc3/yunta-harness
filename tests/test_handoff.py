import os
import subprocess

import pytest

from yunta.agent import SessionPermissions
from yunta.api import Block, BlockType, Message, Role, Usage
from yunta.handoff import export_handoff, import_handoff


def _clean_env():
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _git(*args, cwd=None):
    subprocess.run(["git", *args], check=True, capture_output=True, cwd=cwd, env=_clean_env())


def _init_repo(repo):
    repo.mkdir()
    _git("init", cwd=str(repo))
    _git("config", "user.name", "T", cwd=str(repo))
    _git("config", "user.email", "t@t", cwd=str(repo))
    (repo / "f.txt").write_text("x", encoding="utf-8")
    _git("add", "f.txt", cwd=str(repo))
    _git("commit", "-m", "c1", cwd=str(repo))


MSGS = [
    Message(role=Role.USER, content=[Block(type=BlockType.TEXT, text="hola")]),
    Message(role=Role.ASSISTANT, content=[Block(type=BlockType.TEXT, text="listo")]),
]
USAGE = Usage(input_tokens=10, output_tokens=5, turns=1)


def test_session_permissions_to_list_from_list_roundtrip():
    sp = SessionPermissions()
    sp.grant("bash", "git status")
    sp.grant_tool("read_file")
    data = sp.to_list()
    restored = SessionPermissions.from_list(data)
    assert restored.allowed("bash", "git status")
    assert restored.allowed("read_file", "cualquier cosa")
    assert not restored.allowed("write_file", "x")


def test_export_import_roundtrip_preserves_messages_and_usage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("YUNTA_SESSION_ID", raising=False)
    sp = SessionPermissions()
    sp.grant_tool("bash")

    out = tmp_path / "bundle.json"
    path = export_handoff(MSGS, USAGE, session_permissions=sp, model="openai/gpt-4o", path=out)
    assert path == out
    assert path.exists()

    result = import_handoff(path)
    assert result is not None
    assert result["model"] == "openai/gpt-4o"
    assert len(result["messages"]) == 2
    assert result["messages"][0].content[0].text == "hola"
    assert result["usage"].input_tokens == 10
    assert result["session_permissions"].allowed("bash", "cualquier comando")
    assert result["drift_warning"] is None


def test_export_default_path_uses_session_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("YUNTA_SESSION_ID", "yunta_sess_test123")
    path = export_handoff(MSGS, USAGE)
    assert path.name == "yunta_sess_test123.json"
    assert (tmp_path / ".yunta" / "handoff").exists()


def test_export_includes_git_commit_when_in_repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    _init_repo(repo)
    monkeypatch.chdir(repo)

    out = repo / "bundle.json"
    export_handoff(MSGS, USAGE, path=out)
    result = import_handoff(out)
    assert result["git_branch"]
    assert result["git_commit"]


def test_import_detects_drift_when_repo_advances(tmp_path, monkeypatch):
    repo = tmp_path / "repo2"
    _init_repo(repo)
    monkeypatch.chdir(repo)

    out = repo / "bundle.json"
    export_handoff(MSGS, USAGE, path=out)

    (repo / "f2.txt").write_text("y", encoding="utf-8")
    _git("add", "f2.txt", cwd=str(repo))
    _git("commit", "-m", "c2", cwd=str(repo))

    result = import_handoff(out)
    assert result["drift_warning"] is not None
    assert "avanzó" in result["drift_warning"]


def test_import_missing_file_returns_none(tmp_path):
    assert import_handoff(tmp_path / "no-existe.json") is None


def test_import_unknown_schema_version_raises(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema_version": 999, "messages": [], "usage": {}}', encoding="utf-8")
    with pytest.raises(ValueError, match="schema_version"):
        import_handoff(bad)
