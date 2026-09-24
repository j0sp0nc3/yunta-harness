"""Memoria de Equipo — Parte B: transporte (Feature 4, 2026-09-19).

Higiene de sincronización para `.yunta/learnings.md` (feedback.py, ya
append-only y git-friendly) y `.yunta/memory.json` (memory.py, migrado a
JSONL append-only en esta misma feature). No fuerza sincronización vía
git: solo ofrece deduplicación tras un merge y un reporte de estado.

Tocar `.gitignore` para permitir versionar estos archivos requiere
confirmación explícita del usuario (`yunta memory init-sync`, en cli.py) —
nunca ocurre automáticamente desde este módulo."""
from pathlib import Path

from .feedback import FeedbackStore
from .tools.memory import MEMORY_PATH, _load as _load_memory, _rewrite_as_jsonl


def dedup_learnings(path: str = ".yunta/learnings.md") -> int:
    """Elimina líneas de lección DUPLICADAS EXACTAS (comunes tras un merge
    mal resuelto de dos equipos trabajando en paralelo). Devuelve cuántas
    se eliminaron. Conserva la primera aparición de cada línea."""
    store = FeedbackStore(path)
    if not store.path.exists():
        return 0
    lines = store.path.read_text(encoding="utf-8").splitlines(keepends=True)
    seen: set[str] = set()
    kept = []
    removed = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- "):
            if stripped in seen:
                removed += 1
                continue
            seen.add(stripped)
        kept.append(line)
    if removed:
        store.path.write_text("".join(kept), encoding="utf-8")
    return removed


def dedup_memory(path: Path | str | None = None) -> int:
    """Elimina entradas de memoria duplicadas por (kind, content), sin
    importar tags/fecha. Conserva la más antigua (primera vista). Devuelve
    cuántas se eliminaron."""
    mem_path = Path(path) if path else MEMORY_PATH
    entries = _load_memory(mem_path)
    seen: set[tuple] = set()
    kept = []
    removed = 0
    for e in entries:
        key = (e.get("kind"), e.get("content"))
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        kept.append(e)
    if removed:
        _rewrite_as_jsonl(mem_path, kept)
    return removed


def sync_report(root: Path | str = ".") -> dict:
    """Solo lectura: estado actual de los archivos de memoria de equipo."""
    root = Path(root)
    learnings_path = root / ".yunta" / "learnings.md"
    memory_path = root / ".yunta" / "memory.json"
    report: dict = {"learnings": None, "memory": None}
    if learnings_path.exists():
        store = FeedbackStore(str(learnings_path))
        report["learnings"] = {"path": str(learnings_path), "count": len(store.lessons(limit=10_000))}
    if memory_path.exists():
        entries = _load_memory(memory_path)
        report["memory"] = {"path": str(memory_path), "count": len(entries)}
    return report
