import json
from pathlib import Path
import re
import urllib.parse
import urllib.request

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


@registry.register(
    "web_search",
    "Busca información pública de referencia en la web (Wikipedia/APIs) y devuelve resúmenes en texto plano.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Término o consulta de búsqueda"},
        },
        "required": ["query"],
    },
)
def web_search(raw: str) -> str:
    args = _parse(raw)
    query = args.get("query", "").strip()
    if not query:
        raise ValueError("query es obligatorio")

    url = (
        "https://es.wikipedia.org/w/api.php?action=query&list=search&srsearch="
        + urllib.parse.quote(query)
        + "&format=json&utf8=1"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Yunta/2.5.0 Client"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("query", {}).get("search", [])
            if not results:
                return f"No se encontraron resultados públicos para '{query}'."
            output = []
            for r in results[:5]:
                title = r.get("title", "")
                snippet = re.sub(r"<[^>]+>", "", r.get("snippet", ""))
                output.append(f"- {title}: {snippet}")
            return "\n".join(output)
    except Exception as e:
        return f"error al consultar búsqueda web: {e}"
