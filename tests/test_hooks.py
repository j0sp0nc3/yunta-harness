import sys
from pathlib import Path
import pytest

sys.path.insert(0, ".")

from yunta.hooks import install_git_hooks, uninstall_git_hooks


def test_install_git_hooks_fails_without_git_dir(tmp_path):
    res = install_git_hooks(str(tmp_path))
    assert res is False


def test_install_and_uninstall_git_hooks_success(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()

    installed = install_git_hooks(str(tmp_path))
    assert installed is True

    hook_file = git_dir / "hooks" / "pre-commit"
    assert hook_file.exists()
    content = hook_file.read_text(encoding="utf-8")
    assert "yunta.cli check --tests" in content

    uninstalled = uninstall_git_hooks(str(tmp_path))
    assert uninstalled is True
    assert not hook_file.exists()
