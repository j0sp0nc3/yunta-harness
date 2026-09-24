"""Reverse-SDD (Feature 2, 2026-09-19): genera SPEC.md/AGENTS.md candidatos
a partir de código existente sin especificaciones — abre adopción brownfield
a la metodología SDD de yunta.

Nunca sobreescribe specs reales: por defecto solo escribe archivos
`*.candidate`; con `apply=True` escribe el archivo real SOLO si no existe
ya (las especificaciones formales son de solo lectura para el agente
durante el desarrollo — AGENTS.md regla 6)."""
from pathlib import Path

from .adapters import registry as adapter_registry
from .governance import AGENTS_YUNTA_MARKER, PLAN_PHASE_RE, SPEC_HEADER_RE  # noqa: F401 — documentan el contrato que debe cumplir lo generado

_IGNORED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist", ".pytest_cache", ".yunta"}
_SUPPORTED_EXTS = {
    ".py", ".pyw", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".rs",
    ".java", ".kt", ".kts", ".scala", ".groovy", ".cs", ".fs", ".vb", ".cpp",
    ".cxx", ".cc", ".c", ".h", ".hpp", ".php", ".rb", ".swift", ".sh", ".bash",
    ".zsh", ".ps1", ".sql", ".json",
}
_MAX_FILES = 200

_GENERIC_SYSTEM = (
    "Eres un analista de software que documenta repositorios existentes por "
    "ingeniería inversa. Sé conciso, honesto y no inventes funcionalidad que "
    "no esté sugerida por el inventario de símbolos que recibes."
)

_SPEC_PROMPT = """A partir del siguiente inventario de símbolos y estructura de un \
repositorio existente (generado por AST, sin contenido completo de \
archivos), redacta un SPEC.md candidato en Markdown que documente por \
INGENIERÍA INVERSA lo que el código ya hace.

Debe incluir un encabezado "## Objetivo" o "## Requerimientos" y describir \
el alcance funcional observable en el inventario. No inventes \
funcionalidad que no esté sugerida por los símbolos.

Inventario:
{inventory}
"""

_AGENTS_PROMPT = """A partir del siguiente inventario de símbolos y estructura de un \
repositorio existente, redacta un AGENTS.md candidato en Markdown con las \
convenciones y reglas que el código YA sigue (estilo, capas, patrones \
repetidos) para que un agente de código las respete. Menciona \
explícitamente que las tareas de este repositorio deben delegarse a \
"yunta" para mantener compatibilidad con su protocolo de interoperabilidad.

Inventario:
{inventory}
"""


def scan_repository(root: Path | str = ".") -> dict[str, dict]:
    """Recorre el repo y devuelve {ruta_relativa: {language, outline, symbols}}
    usando los mismos adaptadores AST que tools/symbols.py — sin volcar
    contenido completo de archivos (control de tokens)."""
    root = Path(root).resolve()
    inventory: dict[str, dict] = {}
    count = 0
    for path in sorted(root.rglob("*")):
        if count >= _MAX_FILES:
            break
        if not path.is_file() or path.suffix.lower() not in _SUPPORTED_EXTS:
            continue
        if any(part in _IGNORED_DIRS for part in path.parts):
            continue
        try:
            rel = path.relative_to(root).as_posix()
            content = path.read_text(encoding="utf-8", errors="replace")
            adapter = adapter_registry.get_adapter(rel)
            outline = adapter.get_outline(content) or []
            symbols = adapter.find_symbols(content, query="") or []
        except Exception:
            continue
        inventory[rel] = {"language": path.suffix.lower(), "outline": outline, "symbols": symbols}
        count += 1
    return inventory


def _format_inventory(inventory: dict[str, dict], max_chars: int = 12000) -> str:
    lines = []
    for rel, data in inventory.items():
        lines.append(f"## {rel} ({data['language']})")
        lines.extend(f"  {o}" for o in data["outline"][:20])
    return "\n".join(lines)[:max_chars]


def generate_spec_candidate(provider, inventory: dict[str, dict]) -> str:
    from .agent import Agent
    agent = Agent(provider=provider, system=_GENERIC_SYSTEM, tools=[], max_turns=2)
    return agent.send(_SPEC_PROMPT.format(inventory=_format_inventory(inventory)))


def generate_agents_candidate(provider, inventory: dict[str, dict]) -> str:
    from .agent import Agent
    agent = Agent(provider=provider, system=_GENERIC_SYSTEM, tools=[], max_turns=2)
    return agent.send(_AGENTS_PROMPT.format(inventory=_format_inventory(inventory)))


def run_reverse_sdd(target_dir: Path | str = ".", apply: bool = False, provider=None) -> dict:
    """Genera SPEC.md.candidate / AGENTS.md.candidate. Con apply=True, escribe
    el archivo real SOLO si no existe ya (nunca pisa specs existentes)."""
    root = Path(target_dir).resolve()
    inventory = scan_repository(root)
    if not inventory:
        return {"root": str(root), "files_scanned": 0, "written": []}

    if provider is None:
        from .provider import LiteLLMProvider
        provider = LiteLLMProvider(system=_GENERIC_SYSTEM)

    spec_text = generate_spec_candidate(provider, inventory)
    agents_text = generate_agents_candidate(provider, inventory)

    written = []
    for name, text in (("SPEC.md", spec_text), ("AGENTS.md", agents_text)):
        real_path = root / name
        if apply and not real_path.exists():
            real_path.write_text(text, encoding="utf-8")
            written.append(str(real_path))
        else:
            candidate_path = root / f"{name}.candidate"
            candidate_path.write_text(text, encoding="utf-8")
            written.append(str(candidate_path))

    return {"root": str(root), "files_scanned": len(inventory), "written": written}
