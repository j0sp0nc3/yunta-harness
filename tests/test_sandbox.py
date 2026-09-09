import subprocess
import pytest
from pathlib import Path
from yunta.sandbox import create_sandbox, cleanup_sandbox


def test_create_and_cleanup_sandbox(tmp_path, monkeypatch):
    """Crea un git worktree aislado y verifica su eliminación con cleanup_sandbox."""
    # Setup temporary git repo
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)

    subprocess.run(["git", "init"], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "TestUser"], check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)

    (repo / "file.txt").write_text("initial content", encoding="utf-8")
    subprocess.run(["git", "add", "file.txt"], check=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], check=True)

    # Test create_sandbox
    sb_dir, sb_branch = create_sandbox("test-sb")
    assert sb_dir.exists()
    assert (sb_dir / "file.txt").read_text(encoding="utf-8") == "initial content"
    assert "sandbox-" in sb_branch

    # Make change inside sandbox
    (sb_dir / "sandbox_file.txt").write_text("created in sandbox", encoding="utf-8")
    subprocess.run(["git", "-C", str(sb_dir), "add", "sandbox_file.txt"], check=True)
    subprocess.run(["git", "-C", str(sb_dir), "commit", "-m", "sandbox commit"], check=True)

    # Test cleanup_sandbox with merge=True
    msg = cleanup_sandbox(sb_dir, sb_branch, merge=True)
    assert "Merge exitoso" in msg or "Worktree" in msg
    assert not sb_dir.exists()
    assert (repo / "sandbox_file.txt").read_text(encoding="utf-8") == "created in sandbox"
