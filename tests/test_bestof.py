import os
import subprocess
from pathlib import Path

import pytest

from yunta.bestof import _base_commit, _diff_against_base, choose_and_finalize, discard_all, run_best_of_n


def _clean_env():
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _git(*args, cwd=None):
    subprocess.run(["git", *args], check=True, capture_output=True, cwd=cwd, env=_clean_env())


def _init_repo(repo):
    repo.mkdir()
    _git("init", cwd=str(repo))
    _git("config", "user.name", "T", cwd=str(repo))
    _git("config", "user.email", "t@t", cwd=str(repo))
    (repo / "base.txt").write_text("base", encoding="utf-8")
    _git("add", "base.txt", cwd=str(repo))
    _git("commit", "-m", "base", cwd=str(repo))


class FakeAgentWritesDistinctFile:
    """Sustituto de Agent para tests: en vez de llamar a un LLM real, escribe
    un archivo cuyo contenido depende del cwd (el sandbox actual), simulando
    N enfoques distintos para la misma tarea."""

    def __init__(self, provider, system, max_turns=30, confirm=None):
        self.provider = provider
        self.system = system

    def send(self, prompt: str) -> str:
        marker = Path.cwd().name
        Path("output.txt").write_text(f"enfoque generado en {marker} para: {prompt}", encoding="utf-8")
        return f"listo ({marker})"


def test_run_best_of_n_creates_n_sandboxes_with_distinct_diffs(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    _init_repo(repo)
    monkeypatch.chdir(repo)

    candidates = run_best_of_n(
        "implementa la función X", n=3, provider=None, system="s",
        agent_cls=FakeAgentWritesDistinctFile,
    )

    assert len(candidates) == 3
    branches = {c["branch"] for c in candidates}
    assert len(branches) == 3  # sin colisiones (B3)

    for c in candidates:
        assert c["summary"].startswith("listo (")
        assert "output.txt" in c["diff"]
        assert "implementa la función X" in c["diff"]

    # El cwd del proceso vuelve al original tras cada rama (nunca queda pisado)
    assert Path.cwd().resolve() == repo.resolve()

    discard_all(candidates)


def test_choose_and_finalize_merges_only_the_chosen_branch(tmp_path, monkeypatch):
    repo = tmp_path / "repo2"
    _init_repo(repo)
    monkeypatch.chdir(repo)

    candidates = run_best_of_n(
        "tarea", n=2, provider=None, system="s", agent_cls=FakeAgentWritesDistinctFile,
    )

    log = choose_and_finalize(candidates, chosen_index=0)
    assert "ELEGIDA" in log
    assert "descartada" in log

    # El archivo de la rama elegida terminó integrado en el repo base
    assert (repo / "output.txt").exists()
    content = (repo / "output.txt").read_text(encoding="utf-8")
    assert candidates[0]["branch"].split("sandbox-")[-1] in content or "enfoque generado en" in content

    # Ninguno de los dos worktrees queda huérfano
    for c in candidates:
        assert not Path(c["dir"]).exists()


def test_choose_and_finalize_invalid_index_raises(tmp_path, monkeypatch):
    repo = tmp_path / "repo3"
    _init_repo(repo)
    monkeypatch.chdir(repo)
    candidates = run_best_of_n("tarea", n=2, provider=None, system="s", agent_cls=FakeAgentWritesDistinctFile)
    with pytest.raises(ValueError, match="índice fuera de rango"):
        choose_and_finalize(candidates, chosen_index=5)
    discard_all(candidates)


def test_run_best_of_n_rejects_n_below_one():
    with pytest.raises(ValueError, match="n debe ser"):
        run_best_of_n("tarea", n=0, provider=None, system="s")


def test_diff_against_base_includes_new_untracked_files_once_committed(tmp_path, monkeypatch):
    repo = tmp_path / "repo4"
    _init_repo(repo)
    base = _base_commit(repo)
    (repo / "nuevo.txt").write_text("contenido nuevo", encoding="utf-8")
    _git("add", "-A", cwd=str(repo))
    _git("commit", "-m", "agrega nuevo.txt", cwd=str(repo))

    diff = _diff_against_base(repo, base)
    assert "contenido nuevo" in diff
    assert "nuevo.txt" in diff
