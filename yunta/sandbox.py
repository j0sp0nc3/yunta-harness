"""Módulo de aislamiento en Git Worktree para tareas experimentales o destructivas (V3-9)."""

import os
import subprocess
import time
from pathlib import Path


def _clean_git_env() -> dict:
    """Entorno sin variables GIT_* heredadas: evita que operaciones dentro de
    un hook de git (pre-commit exporta GIT_INDEX_FILE, GIT_DIR, etc.)
    contaminen la creación/limpieza de worktrees del sandbox."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def create_sandbox(prefix: str = "yunta-sandbox") -> tuple[Path, str]:
    """Crea un git worktree aislado bajo .yunta/sandboxes/ y retorna (path, branch_name)."""
    ts = int(time.time())
    branch_name = f"sandbox-{ts}"
    sandbox_dir = Path(".yunta") / "sandboxes" / f"{prefix}-{ts}"
    sandbox_dir.parent.mkdir(parents=True, exist_ok=True)

    cmd = ["git", "worktree", "add", "-b", branch_name, str(sandbox_dir), "HEAD"]
    res = subprocess.run(cmd, capture_output=True, text=True, env=_clean_git_env())
    if res.returncode != 0:
        raise RuntimeError(f"Error al crear git worktree: {res.stderr.strip()}")

    return sandbox_dir, branch_name


def cleanup_sandbox(sandbox_dir: Path | str, branch_name: str, merge: bool = False) -> str:
    """Elimina el git worktree y opcionalmente realiza merge de la rama aislada antes de eliminarla."""
    path_str = str(sandbox_dir)
    log = []

    if merge:
        res = subprocess.run(["git", "merge", branch_name], capture_output=True, text=True, env=_clean_git_env())
        if res.returncode == 0:
            log.append(f"Merge exitoso de la rama {branch_name}")
        else:
            log.append(f"Advertencia: conflicto al hacer merge de {branch_name}: {res.stderr.strip()}")

    res_rem = subprocess.run(["git", "worktree", "remove", "--force", path_str], capture_output=True, text=True, env=_clean_git_env())
    if res_rem.returncode == 0:
        log.append(f"Worktree {path_str} eliminado")
    else:
        log.append(f"Aviso al eliminar worktree: {res_rem.stderr.strip()}")

    subprocess.run(["git", "branch", "-D", branch_name], capture_output=True, text=True, env=_clean_git_env())
    log.append(f"Rama {branch_name} eliminada")

    return "\n".join(log)
