import ast
from pathlib import Path
from typing import Any, Dict, List

from . import _parse, registry
from .files import _check_boundary


def _format_args(args: ast.arguments) -> str:
    arg_names = [a.arg for a in args.args]
    if args.vararg:
        arg_names.append(f"*{args.vararg.arg}")
    if args.kwarg:
        arg_names.append(f"**{args.kwarg.arg}")
    return ", ".join(arg_names)


@registry.register(
    "find_symbol",
    "Busca definiciones de clases, funciones y métodos en archivos Python del proyecto usando el analizador estático AST.",
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
    ignored_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist", ".pytest_cache"}
    results: List[str] = []

    for path in cwd.rglob("*.py"):
        if any(part in ignored_dirs for part in path.parts):
            continue
        try:
            rel_path = path.relative_to(cwd)
            content = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content, filename=str(rel_path))
        except Exception:
            continue

        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                match = (node.name == query) if exact else (query.lower() in node.name.lower())
                if match:
                    kind = "class" if isinstance(node, ast.ClassDef) else "func"
                    arg_str = "" if isinstance(node, ast.ClassDef) else f"({_format_args(node.args)})"
                    results.append(f"{rel_path}:{node.lineno} — {kind} {node.name}{arg_str}")

    if not results:
        return f"no se encontraron símbolos coincidentes con '{query}'"
    return "\n".join(results[:50])


@registry.register(
    "get_ast_outline",
    "Genera el esquema estructurado (outline) de un archivo Python mostrando clases, métodos y funciones con sus números de línea.",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Ruta relativa o absoluta del archivo Python a esquematizar"},
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
    try:
        tree = ast.parse(content, filename=str(p))
    except SyntaxError as e:
        return f"error de sintaxis en '{path_str}': línea {e.lineno} — {e.msg}"

    outline: List[str] = [f"esquema AST de {p.name}:"]

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                names = ", ".join(alias.name for alias in node.names)
                outline.append(f"  L{node.lineno}: import {names}")
            else:
                names = ", ".join(alias.name for alias in node.names)
                outline.append(f"  L{node.lineno}: from {node.module or ''} import {names}")
        elif isinstance(node, ast.ClassDef):
            bases = ", ".join(b.id for b in node.bases if isinstance(b, ast.Name))
            base_str = f"({bases})" if bases else ""
            outline.append(f"  L{node.lineno}: class {node.name}{base_str}")
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args_str = _format_args(item.args)
                    outline.append(f"    L{item.lineno}: def {item.name}({args_str})")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args_str = _format_args(node.args)
            outline.append(f"  L{node.lineno}: def {node.name}({args_str})")

    return "\n".join(outline)
