from pathlib import Path

from . import _parse, registry


@registry.register(
    "read_file",
    "Lee un archivo del proyecto y devuelve su contenido completo.",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Ruta relativa al proyecto"}
        },
        "required": ["path"],
    },
)
def read_file(raw: str) -> str:
    path = _parse(raw).get("path", "")
    return Path(path).read_text(encoding="utf-8")


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
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"wrote {len(content)} bytes to {path}"


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

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"El archivo '{path}' no existe")

    content = p.read_text(encoding="utf-8")
    count = content.count(old_str)
    if count == 0:
        raise ValueError(f"'{old_str}' no fue encontrado en {path}")
    if count > 1:
        raise ValueError(f"'{old_str}' aparece {count} veces en {path}. Proporcione más contexto para evitar ambigüedad.")

    new_content = content.replace(old_str, new_str, 1)
    p.write_text(new_content, encoding="utf-8")
    return f"successfully replaced in {path}"
