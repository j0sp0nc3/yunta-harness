from pathlib import Path

from . import _parse, registry


import tempfile


def _check_boundary(path: str) -> Path:
    """W5: workspace boundary — garantiza que la ruta (relativa O absoluta)
    resuelva dentro del directorio del proyecto o el directorio temporal de pruebas.
    Previene path traversal fuera de las fronteras autorizadas."""
    if not path:
        raise ValueError("path es obligatorio")
    cwd = Path.cwd().resolve()
    temp_dir = Path(tempfile.gettempdir()).resolve()
    p = Path(path)
    target = (p if p.is_absolute() else cwd / p).resolve()
    
    try:
        target.relative_to(cwd)
        return target
    except ValueError:
        pass

    if p.is_absolute():
        try:
            target.relative_to(temp_dir)
            return target
        except ValueError:
            pass

    raise ValueError(
        f"acceso denegado por seguridad: la ruta '{path}' resuelve fuera del directorio del proyecto ({cwd})"
    )


def ensure_within_cwd(path: str) -> None:
    """W5: workspace boundary — toda ruta de archivo debe resolver dentro del
    directorio de trabajo o directorio temporal. Evita lecturas/ediciones fuera del proyecto."""
    _check_boundary(path)


@registry.register(
    "read_file",
    "Lee un archivo del proyecto y devuelve su contenido. Soporta offset y limit opcionales para archivos extensos.",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Ruta relativa al proyecto"},
            "offset": {"type": "integer", "description": "Línea inicial (1-indexed, opcional)"},
            "limit": {"type": "integer", "description": "Número máximo de líneas a leer (opcional, por defecto hasta 2000)"},
        },
        "required": ["path"],
    },
)
def read_file(raw: str) -> str:
    args = _parse(raw)
    path = args.get("path", "")
    p = _check_boundary(path)
    content = p.read_text(encoding="utf-8", errors="replace")

    offset = args.get("offset")
    limit = args.get("limit")

    lines = content.splitlines(keepends=True)
    total_lines = len(lines)

    start_idx = max(0, offset - 1) if (offset is not None and isinstance(offset, int) and offset > 0) else 0
    max_lines = limit if (limit is not None and isinstance(limit, int) and limit > 0) else 2000

    if start_idx == 0 and total_lines <= max_lines and limit is None:
        return content

    selected_lines = lines[start_idx : start_idx + max_lines]
    res = "".join(selected_lines)
    if start_idx + max_lines < total_lines:
        remaining = total_lines - (start_idx + max_lines)
        res += f"\n[... truncado: {remaining} líneas no mostradas. Usa offset={start_idx + max_lines + 1} para continuar ...]"
    return res


@registry.register(
    "write_file",
    "Crea o sobrescribe un archivo con el contenido dado. Requiere aprobación del usuario.",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Ruta relativa al proyecto"},
            "content": {"type": "string", "description": "Contenido completo del archivo"},
        },
        "required": ["path", "content"],
    },
    requires_approval=True,
)
def write_file(raw: str) -> str:
    args = _parse(raw)
    path, content = args.get("path", ""), args.get("content", "")
    if not path:
        raise ValueError("path es obligatorio")
    if not isinstance(content, str):
        raise ValueError("content debe ser un string")
    p = _check_boundary(path)
    _validate_content(path, content)

    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp-yunta")
    try:
        tmp.write_text(content, encoding="utf-8")
        written = tmp.read_text(encoding="utf-8")
        if written != content:
            raise ValueError("verificación de escritura falló (bytes inconsistentes)")
        tmp.replace(p)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return f"wrote {len(content)} bytes to {path}"


def _validate_content(path: str, content: str) -> None:
    """P6: validación previa a escribir. Delega en el registro de adaptadores
    por lenguaje cargado bajo demanda."""
    from ..adapters import registry as adapter_registry
    adapter_registry.get_adapter(path).validate(content, path=path)




@registry.register(
    "str_replace",
    "Reemplaza una cadena de texto única en un archivo por un nuevo texto.",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Ruta relativa al archivo"},
            "old_str": {"type": "string", "description": "Texto exacto a buscar (debe ser único)"},
            "new_str": {"type": "string", "description": "Nuevo texto de reemplazo"},
        },
        "required": ["path", "old_str", "new_str"],
    },
    requires_approval=True,
)
def str_replace(raw: str) -> str:
    args = _parse(raw)
    path = args.get("path", "")
    if not path:
        raise ValueError("path es obligatorio")
    if "old_str" not in args or args.get("old_str") is None:
        raise ValueError("old_str es obligatorio")
    if "new_str" not in args or args.get("new_str") is None:
        raise ValueError("new_str es obligatorio")

    old_str = args["old_str"]
    new_str = args["new_str"]

    p = _check_boundary(path)
    if not p.exists():
        raise FileNotFoundError(f"El archivo '{path}' no existe")

    content = p.read_text(encoding="utf-8", errors="replace")
    count = content.count(old_str)
    if count == 0:
        raise ValueError(f"'{old_str}' no fue encontrado en {path}")
    if count > 1:
        raise ValueError(f"'{old_str}' aparece {count} veces en {path}. Proporcione más contexto para evitar ambigüedad.")

    new_content = content.replace(old_str, new_str, 1)
    p.write_text(new_content, encoding="utf-8")
    return f"successfully replaced in {path}"


@registry.register(
    "list_dir",
    "Lista la estructura de un directorio en formato de árbol compacto con tamaños de archivo. Ignora carpetas pesadas (.git, node_modules, etc.).",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Ruta del directorio a inspeccionar (opcional, por defecto '.')"},
            "max_depth": {"type": "integer", "description": "Profundidad máxima de recursión (opcional, por defecto 2)"},
            "max_files": {"type": "integer", "description": "Límite máximo de archivos a listar (opcional, por defecto 80)"},
        },
        "required": [],
    },
)
def list_dir(raw: str) -> str:
    args = _parse(raw)
    base_path = Path(args.get("path") or ".")
    max_depth = int(args.get("max_depth") or 2)
    max_files = int(args.get("max_files") or 80)

    if not base_path.exists():
        raise FileNotFoundError(f"El directorio '{base_path}' no existe")
    if not base_path.is_dir():
        raise NotADirectoryError(f"'{base_path}' no es un directorio")

    ignored_dirs = {
        ".git", "node_modules", "__pycache__", ".pytest_cache",
        ".venv", "venv", "env", "dist", "build", ".idea", ".vscode",
        ".zcode", ".gemini", ".next", ".nuxt", "coverage"
    }

    results = []
    file_count = 0
    truncated = False

    def walk(current_dir: Path, depth: int, prefix: str):
        nonlocal file_count, truncated
        if depth > max_depth or truncated:
            return

        try:
            entries = sorted(current_dir.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            results.append(f"{prefix}[Acceso denegado]")
            return

        for idx, entry in enumerate(entries):
            if file_count >= max_files:
                truncated = True
                return

            name = entry.name
            if name in ignored_dirs or name.startswith(".tmp"):
                continue

            is_last = (idx == len(entries) - 1)
            connector = "\\-- " if is_last else "|-- "
            child_prefix = prefix + ("    " if is_last else "|   ")

            if entry.is_dir():
                results.append(f"{prefix}{connector}{name}/")
                walk(entry, depth + 1, child_prefix)
            else:
                file_count += 1
                size = entry.stat().st_size if entry.exists() else 0
                if size >= 1024 * 1024:
                    size_str = f"{size / (1024*1024):.1f} MB"
                elif size >= 1024:
                    size_str = f"{size / 1024:.1f} KB"
                else:
                    size_str = f"{size} B"
                results.append(f"{prefix}{connector}{name} ({size_str})")

    results.append(f"{base_path.resolve().name}/")
    walk(base_path, 1, "")

    if truncated:
        results.append(f"\n[... truncado: se alcanzó el límite de {max_files} archivos. Usa max_files o path para acotar la búsqueda ...]")

    return "\n".join(results)
