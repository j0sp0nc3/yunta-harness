import base64
from pathlib import Path

from . import _parse, registry
from .files import _check_boundary

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB

MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


@registry.register(
    "read_image",
    "Lee una imagen local (PNG, JPEG, WebP, GIF) de hasta 5MB, valida su formato y retorna su representación Base64 Data URL para inspección con visión.",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Ruta de la imagen a inspeccionar"},
        },
        "required": ["path"],
    },
)
def read_image(raw: str) -> str:
    args = _parse(raw)
    path_str = args.get("path", "")
    if not path_str:
        raise ValueError("path es obligatorio")

    p = _check_boundary(path_str)
    if not p.exists():
        raise FileNotFoundError(f"la imagen '{path_str}' no existe")

    ext = p.suffix.lower()
    if ext not in MIME_TYPES:
        allowed = ", ".join(MIME_TYPES.keys())
        raise ValueError(f"formato no soportado '{ext}'. Formatos válidos: {allowed}")

    size = p.stat().st_size
    if size > MAX_IMAGE_SIZE_BYTES:
        size_mb = size / (1024 * 1024)
        raise ValueError(f"la imagen supera el límite de 5MB ({size_mb:.2f} MB)")

    mime_type = MIME_TYPES[ext]
    data = p.read_bytes()
    b64_str = base64.b64encode(data).decode("utf-8")
    data_url = f"data:{mime_type};base64,{b64_str}"

    size_kb = size / 1024
    return (
        f"imagen cargada con éxito: '{p.name}' ({size_kb:.1f} KB, {mime_type})\n"
        f"[IMAGE_URL: {data_url}]"
    )
