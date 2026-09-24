"""Protocolo de Portabilidad de Sesión (Handoff) — Feature 1, 2026-09-19.

Empaqueta el estado de una sesión de yunta (mensajes, usage, permisos
persistentes, sandbox activo, contexto de git) en un bundle JSON versionado
que puede reanudarse en otro proceso, máquina o harness/IDE compatible.

No fuerza que otro harness lo lea: publica el schema (schema_version) para
que cualquiera pueda hacerlo. Reutiliza al 100% la serialización de
mensajes/usage de session.py — este módulo solo añade el resto del contexto
de sesión que hoy vive en memoria y se pierde al morir el proceso.

Spec pública versionada: docs/schemas/yunta-session-spec-v1.{md,schema.json}
"""
import json
import time
from pathlib import Path

from .agent import SessionPermissions
from .api import Message, Usage
from .sandbox import _clean_git_env
from .session import (
    deserialize_messages,
    deserialize_usage,
    get_or_create_session_id,
    serialize_messages,
    serialize_usage,
)

SCHEMA_VERSION = 1
DEFAULT_HANDOFF_DIR = Path(".yunta") / "handoff"


def _git_info() -> dict:
    import subprocess

    info = {"git_branch": None, "git_commit": None}
    try:
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, env=_clean_git_env(),
        )
        if branch.returncode == 0:
            info["git_branch"] = branch.stdout.strip() or None
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, env=_clean_git_env(),
        )
        if commit.returncode == 0:
            info["git_commit"] = commit.stdout.strip() or None
    except FileNotFoundError:
        pass
    return info


def export_handoff(
    messages: list[Message],
    usage: Usage,
    session_permissions: SessionPermissions | None = None,
    cwd: str | None = None,
    active_sandbox: dict | None = None,
    model: str = "",
    source_harness: str = "yunta",
    path: Path | str | None = None,
) -> Path:
    """Empaqueta el estado de sesión en un bundle JSON portable. Escritura
    atómica (.tmp + replace), igual que session.save_session."""
    session_id = get_or_create_session_id()
    bundle = {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "created_at": time.time(),
        "source_harness": source_harness,
        "cwd": cwd or str(Path.cwd()),
        "model": model,
        "messages": serialize_messages(messages),
        "usage": serialize_usage(usage),
        "session_permissions": session_permissions.to_list() if session_permissions else [],
        "active_sandbox": (
            {"dir": str(active_sandbox["dir"]), "branch": active_sandbox["branch"]}
            if active_sandbox else None
        ),
    }
    bundle.update(_git_info())

    if path is None:
        DEFAULT_HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
        path = DEFAULT_HANDOFF_DIR / f"{session_id}.json"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(path)
    return path


def import_handoff(path: Path | str) -> dict | None:
    """Lee un bundle de handoff y lo deserializa. `None` si no existe o no
    es JSON válido. Incluye `drift_warning` (no es un error) si el commit
    actual de git difiere del que tenía la sesión al exportarse."""
    path = Path(path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    version = data.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"schema_version {version!r} no soportado (esperado {SCHEMA_VERSION}). "
            "El bundle fue exportado por una versión de yunta incompatible."
        )

    result = {
        "session_id": data.get("session_id"),
        "created_at": data.get("created_at"),
        "source_harness": data.get("source_harness"),
        "cwd": data.get("cwd"),
        "git_branch": data.get("git_branch"),
        "git_commit": data.get("git_commit"),
        "model": data.get("model", ""),
        "messages": deserialize_messages(data.get("messages", [])),
        "usage": deserialize_usage(data.get("usage", {})),
        "session_permissions": SessionPermissions.from_list(data.get("session_permissions")),
        "active_sandbox": data.get("active_sandbox"),
        "drift_warning": None,
    }

    current = _git_info()
    saved_commit = data.get("git_commit")
    if saved_commit and current.get("git_commit") and saved_commit != current["git_commit"]:
        result["drift_warning"] = (
            f"El repo avanzó desde el handoff: commit exportado {saved_commit[:8]}, "
            f"commit actual {current['git_commit'][:8]}."
        )

    return result
