import os
import subprocess
import pytest
from pathlib import Path
from yunta.sandbox import create_sandbox, cleanup_sandbox


def _clean_env():
    """Sin GIT_* heredadas: el test debe pasar incluso dentro de un hook
    pre-commit (git exporta GIT_INDEX_FILE/GIT_DIR al proceso del hook)."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _git(*args, cwd=None):
    subprocess.run(["git", *args], check=True, capture_output=True,
                   cwd=cwd, env=_clean_env())


def test_create_and_cleanup_sandbox(tmp_path, monkeypatch):
    """Crea un git worktree aislado y verifica su eliminación con cleanup_sandbox."""
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)

    _git("init")
    _git("config", "user.name", "TestUser")
    _git("config", "user.email", "test@example.com")

    (repo / "file.txt").write_text("initial content", encoding="utf-8")
    _git("add", "file.txt")
    _git("commit", "-m", "initial commit")

    # Test create_sandbox
    sb_dir, sb_branch = create_sandbox("test-sb")
    assert sb_dir.exists()
    assert (sb_dir / "file.txt").read_text(encoding="utf-8") == "initial content"
    assert "sandbox-" in sb_branch

    # Make change inside sandbox
    (sb_dir / "sandbox_file.txt").write_text("created in sandbox", encoding="utf-8")
    _git("add", "sandbox_file.txt", cwd=str(sb_dir))
    _git("commit", "-m", "sandbox commit", cwd=str(sb_dir))

    # Test cleanup_sandbox with merge=True
    msg = cleanup_sandbox(sb_dir, sb_branch, merge=True)
    assert "Merge exitoso" in msg or "Worktree" in msg
    assert not sb_dir.exists()
    assert (repo / "sandbox_file.txt").read_text(encoding="utf-8") == "created in sandbox"


def test_sandbox_funciona_bajo_entorno_de_hook(tmp_path, monkeypatch):
    """Regresión P-W: GIT_INDEX_FILE/GIT_DIR (como los exporta un pre-commit)
    no deben romper la creación del sandbox."""
    repo = tmp_path / "repo2"
    repo.mkdir()
    monkeypatch.chdir(repo)
    _git("init")
    _git("config", "user.name", "T")
    _git("config", "user.email", "t@t")
    (repo / "f.txt").write_text("x", encoding="utf-8")
    _git("add", "f.txt")
    _git("commit", "-m", "c")

    monkeypatch.setenv("GIT_INDEX_FILE", str(repo / "index.lock-sim"))
    monkeypatch.setenv("GIT_DIR", str(repo / ".git"))
    sb_dir, sb_branch = create_sandbox("hook-sim")
    assert sb_dir.exists()
    cleanup_sandbox(sb_dir, sb_branch)
    assert not sb_dir.exists()
