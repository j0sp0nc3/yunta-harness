"""Memoria persistente entre sesiones: tools `remember` y `recall`.

Almacena entradas en un archivo JSON (por defecto `.yunta/memory.json`),
configurable vía la variable de entorno `MEMORY_PATH` o sobrescribiendo el
atributo de módulo `yunta.tools.memory.MEMORY_PATH` (útil en tests).
Solo librería estándar.
"""

import json
import os
from datetime import datetime
from pathlib import Path

from . import _parse, registry

MEMORY_PATH = Path(os.environ.get("MEMORY_PATH", ".yunta/memory.json"))


def _load(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _save(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )


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
    entries = _load(MEMORY_PATH)
    entries.append(entry)
    _save(MEMORY_PATH, entries)
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
