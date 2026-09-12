"""yunta/tools/symbols.py — Búsqueda semántica de símbolos e inspección de esquemas AST polyglot.

Soporta múltiples lenguajes (Python, JS/TS, Go, Rust, JSON) delegando en el
registro de adaptadores por lenguaje cargados bajo demanda (Lazy-Loading)."""

from pathlib import Path
from typing import List

from . import _parse, registry
from .files import _check_boundary
from ..adapters import registry as adapter_registry


@registry.register(
    "find_symbol",
    "Busca definiciones de clases, funciones, interfaces y métodos en archivos del proyecto (Python, JS/TS, Go, Rust, JSON, etc.).",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Nombre o fragmento del símbolo a buscar"},
            "exact": {"type": "boolean", "description": "Si True, requiere coincidencia exacta (default: False)"},
        },
        "required": ["name"],
    },
)
def find_symbol(raw: str) -> str:
    args = _parse(raw)
    query = args.get("name", "").strip()
    if not query:
        raise ValueError("name es obligatorio")
    exact = bool(args.get("exact", False))

    cwd = Path.cwd().resolve()
    ignored_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist", ".pytest_cache", ".yunta"}
    supported_exts = {
        ".py", ".pyw", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".rs",
        ".java", ".kt", ".kts", ".scala", ".groovy", ".cs", ".fs", ".vb", ".cpp",
        ".cxx", ".cc", ".c", ".h", ".hpp", ".php", ".rb", ".swift", ".sh", ".bash",
        ".zsh", ".ps1", ".sql", ".json"
    }
    results: List[str] = []



    for path in cwd.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in supported_exts:
            continue
        if any(part in ignored_dirs for part in path.parts):
            continue
        try:
            rel_path = path.relative_to(cwd)
            content = path.read_text(encoding="utf-8", errors="replace")
            adapter = adapter_registry.get_adapter(str(rel_path))
            symbols = adapter.find_symbols(content, query=query)
        except Exception:
            continue

        for sym in symbols:
            name = sym.get("name", "")
            match = (name == query) if exact else (query.lower() in name.lower())
            if match:
                kind = sym.get("type", "symbol")
                line = sym.get("line", 1)
                results.append(f"{rel_path}:{line} — {kind} {name}")

    if not results:
        return f"no se encontraron símbolos coincidentes con '{query}'"
    return "\n".join(results[:50])


@registry.register(
    "get_ast_outline",
    "Genera el esquema estructurado (outline) de un archivo del proyecto (Python, JS/TS, Go, Rust, JSON, etc.).",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Ruta relativa o absoluta del archivo a esquematizar"},
        },
        "required": ["path"],
    },
)
def get_ast_outline(raw: str) -> str:
    args = _parse(raw)
    path_str = args.get("path", "")
    if not path_str:
        raise ValueError("path es obligatorio")

    p = _check_boundary(path_str)
    if not p.exists():
        raise FileNotFoundError(f"el archivo '{path_str}' no existe")

    content = p.read_text(encoding="utf-8", errors="replace")
    adapter = adapter_registry.get_adapter(path_str)
    outline = adapter.get_outline(content) or []

    if outline and "error de sintaxis en" in outline[0].lower():
        return f"error de sintaxis en '{path_str}': {outline[0]}"


    header = f"esquema AST de {p.name}:" if p.suffix.lower() == ".py" else f"esquema estructurado de {p.name}:"
    res = [header]
    res.extend(f"  {line}" if not line.startswith("esquema") else line for line in outline)
    return "\n".join(res)

