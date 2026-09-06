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
