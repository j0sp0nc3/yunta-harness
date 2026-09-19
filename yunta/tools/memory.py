"""Memoria persistente entre sesiones: tools `remember` y `recall`.

Almacena entradas en formato JSONL (una entrada JSON por línea, por defecto
en `.yunta/memory.json`), configurable vía la variable de entorno
`MEMORY_PATH` o sobrescribiendo el atributo de módulo
`yunta.tools.memory.MEMORY_PATH` (útil en tests). Solo librería estándar.

Feature 4 (2026-09-19, Memoria de Equipo): JSONL en vez de reescribir un
array JSON completo en cada `remember` — mucho más amigable con merges de
git cuando este archivo se comparte entre miembros de un equipo (ver
`yunta/team_memory.py` y `yunta memory init-sync`). El formato viejo
(array JSON completo) se migra automáticamente y una sola vez la primera
vez que se lee o escribe."""

import json
import os
from datetime import datetime
from pathlib import Path

from . import _parse, registry

MEMORY_PATH = Path(os.environ.get("MEMORY_PATH", ".yunta/memory.json"))


def _rewrite_as_jsonl(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(e, ensure_ascii=False) for e in entries]
    path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")


def _load(path: Path) -> list[dict]:
    """Lee memoria en formato JSONL. Si detecta el formato viejo (array JSON
    completo), migra el archivo a JSONL en el mismo paso (una sola vez)."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    stripped = raw.strip()
    if not stripped:
        return []
    if stripped.startswith("["):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        entries = data if isinstance(data, list) else []
        _rewrite_as_jsonl(path, entries)
        return entries
    entries = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def _append(path: Path, entry: dict) -> None:
    """Append-only: una entrada JSON por línea (Feature 4)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _words(text: str) -> list[str]:
    return [w for w in text.lower().split() if w]


@registry.register(
    "remember",
    "Guarda una entrada en la memoria persistente entre sesiones "
    "(.yunta/memory.json). kind: fact/preference/decision (default 'fact').",
    {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "Texto a recordar (requerido)",
            },
            "kind": {
                "type": "string",
                "description": "Tipo de entrada: fact/preference/decision (default 'fact')",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Etiquetas opcionales",
            },
        },
        "required": ["content"],
    },
)
def remember(raw: str) -> str:
    args = _parse(raw)
    content = args.get("content")
    if not content or not isinstance(content, str):
        raise ValueError("content es obligatorio")
    kind = str(args.get("kind") or "fact")
    tags = [str(t) for t in (args.get("tags") or [])]
    entry = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "kind": kind,
        "content": content,
        "tags": tags,
    }
    _load(MEMORY_PATH)  # side-effect: migra formato legacy (array) a JSONL si hace falta
    _append(MEMORY_PATH, entry)
    return f"recordado ({kind}): {content}"


@registry.register(
    "recall",
    "Busca en la memoria persistente las entradas que matcheen la query "
    "(alguna palabra, case-insensitive, en content o tags). "
    "Devuelve como máximo las 10 más recientes.",
    {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Palabras a buscar (requerido)",
            },
        },
        "required": ["query"],
    },
)
def recall(raw: str) -> str:
    query = _parse(raw).get("query")
    if not query or not isinstance(query, str):
        raise ValueError("query es obligatorio")
    words = _words(query)
    matches = []
    for e in _load(MEMORY_PATH):
        haystack = " ".join([str(e.get("content", ""))] + [str(t) for t in e.get("tags", [])])
        if any(w in haystack.lower() for w in words):
            matches.append(e)
    if not matches:
        return "(sin resultados)"
    lines = []
    for e in matches[-10:]:
        tags = e.get("tags") or []
        tags_part = f' [{", ".join(tags)}]' if tags else ""
        lines.append(
            f'[{e.get("date", "")}] ({e.get("kind", "fact")}) {e.get("content", "")}{tags_part}'
        )
    return "\n".join(lines)
