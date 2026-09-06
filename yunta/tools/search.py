import re
from pathlib import Path

from . import _parse, registry


@registry.register(
    "grep",
    "Busca un patrón regex en los archivos de un directorio (recursivo). "
    "Devuelve 'ruta:linea: texto' por coincidencia, hasta max_results.",
    {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Patrón regex a buscar"},
            "path": {"type": "string", "description": "Directorio base (por defecto '.')"},
            "max_results": {
                "type": "integer",
                "description": "Número máximo de coincidencias a devolver (por defecto 50)",
            },
        },
        "required": ["pattern"],
    },
)
def grep(raw: str) -> str:
    args = _parse(raw)
    pattern = args.get("pattern")
    if not pattern:
        raise ValueError("pattern es obligatorio")
    try:
        rx = re.compile(pattern)
    except re.error as e:
        raise ValueError(f"patrón regex inválido: {e}") from e
    base = Path(args.get("path", "."))
    if not base.is_dir():
        raise FileNotFoundError(f"no existe el directorio: {base}")
    max_results = max(1, int(args.get("max_results", 50)))
    results = []
    for p in sorted(base.rglob("*")):
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if rx.search(line):
                results.append(f"{p.as_posix()}:{lineno}: {line}")
                if len(results) >= max_results:
                    return "\n".join(results)
    return "\n".join(results)


@registry.register(
    "glob",
    "Lista rutas que coinciden con un patrón glob relativo a path (ej. '**/*.py').",
    {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Patrón glob, ej. '**/*.py'"},
            "path": {"type": "string", "description": "Directorio base (por defecto '.')"},
        },
        "required": ["pattern"],
    },
)
def glob(raw: str) -> str:
    args = _parse(raw)
    pattern = args.get("pattern")
    if not pattern:
        raise ValueError("pattern es obligatorio")
    base = Path(args.get("path", "."))
    if not base.is_dir():
        raise FileNotFoundError(f"no existe el directorio: {base}")
    matches = sorted(p.as_posix() for p in base.glob(pattern))
    return "\n".join(matches)
