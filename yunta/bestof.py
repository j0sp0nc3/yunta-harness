"""Undo como Árbol / Best-of-N (Feature 7, 2026-09-19): el agente prueba N
enfoques distintos para la misma tarea en sandboxes de worktree aislados y
el humano elige el mejor por diff, en vez de aceptar el único intento del
agente o deshacer linealmente con `/undo`.

Decisión de alcance explícita: ejecución SECUENCIAL, no paralela real.
`os.chdir()` es global al proceso — N hilos pisándose entre sandboxes
distintos sería una condición de carrera real, no hipotética. Paralelismo
real (vía subprocesos con su propio cwd, no hilos) queda fuera de este
roadmap."""
import os
import subprocess
from pathlib import Path

from .sandbox import _clean_git_env, cleanup_sandbox, create_sandbox


def _base_commit(sandbox_dir: Path) -> str:
    res = subprocess.run(
        ["git", "-C", str(sandbox_dir), "rev-parse", "HEAD"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=_clean_git_env(),
    )
    return res.stdout.strip()


def _commit_sandbox_changes(branch_name: str) -> None:
    """Compromete cualquier cambio (incluidos archivos nuevos) dentro del
    sandbox ACTUAL (cwd) para que el diff contra el commit base lo capture
    y un merge posterior de la rama lo traiga consigo. `--allow-empty` por
    si el sub-agente no modificó nada."""
    subprocess.run(["git", "add", "-A"], capture_output=True, text=True, env=_clean_git_env())
    subprocess.run(
        ["git", "commit", "-m", f"best-of-n: enfoque en {branch_name}", "--allow-empty"],
        capture_output=True, text=True, env=_clean_git_env(),
    )


def _diff_against_base(sandbox_dir: Path, base_commit: str) -> str:
    """Diff del/los commit(s) del candidato contra el commit del que partió
    (no contra su propio HEAD, que ya los incluye tras `_commit_sandbox_changes`)."""
    res = subprocess.run(
        ["git", "-C", str(sandbox_dir), "diff", base_commit, "HEAD"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=_clean_git_env(),
    )
    return res.stdout if res.returncode == 0 else f"(error al calcular diff: {res.stderr.strip()})"


def run_best_of_n(prompt: str, n: int, provider, system: str, confirm=None, agent_cls=None) -> list[dict]:
    """Crea N sandboxes y ejecuta un sub-agente por rama SECUENCIALMENTE
    (contexto limpio por rama, mismo patrón que `decompose.run_chunks`).
    Devuelve `[{branch, dir, summary, diff}]`."""
    if n < 1:
        raise ValueError("n debe ser >= 1")
    if agent_cls is None:
        from .agent import Agent
        agent_cls = Agent

    candidates = []
    original_cwd = Path.cwd()
    for i in range(n):
        sb_dir, sb_branch = create_sandbox(prefix=f"bestof-{i + 1}")
        base_commit = _base_commit(sb_dir)
        try:
            os.chdir(sb_dir)
            sub = agent_cls(provider=provider, system=system, max_turns=30, confirm=confirm)
            summary = sub.send(prompt)
            _commit_sandbox_changes(sb_branch)
        finally:
            os.chdir(original_cwd)
        diff = _diff_against_base(sb_dir, base_commit)
        candidates.append({"branch": sb_branch, "dir": sb_dir, "summary": summary, "diff": diff})

    return candidates


def choose_and_finalize(candidates: list[dict], chosen_index: int) -> str:
    """Integra (merge) la rama elegida y descarta el resto. `chosen_index`
    es 0-based."""
    if not (0 <= chosen_index < len(candidates)):
        raise ValueError(f"índice fuera de rango: {chosen_index}")
    logs = []
    for i, c in enumerate(candidates):
        merge = i == chosen_index
        msg = cleanup_sandbox(c["dir"], c["branch"], merge=merge)
        tag = "ELEGIDA" if merge else "descartada"
        logs.append(f"[{tag}] {c['branch']}: {msg}")
    return "\n".join(logs)


def discard_all(candidates: list[dict]) -> str:
    """Descarta todas las ramas candidatas sin integrar ninguna."""
    logs = []
    for c in candidates:
        msg = cleanup_sandbox(c["dir"], c["branch"], merge=False)
        logs.append(f"[descartada] {c['branch']}: {msg}")
    return "\n".join(logs)
