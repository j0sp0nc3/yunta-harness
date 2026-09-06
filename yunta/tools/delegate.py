"""Subagente de investigación read-only: tool `delegate_research`.

Crea un `Agent` interno cuyo contexto está restringido a las tools de lectura
(`read_file`, `grep`, `glob`) y le delega la tarea indicada. El provider se
inyecta vía `set_provider(p)` desde `yunta.cli`; si falta, la tool falla con
un error claro (sin proveedores por defecto ni fallbacks ocultos).
"""

from ..agent import Agent
from . import _parse, registry

_provider = None


def set_provider(p) -> None:
    global _provider
    _provider = p


@registry.register(
    "delegate_research",
    "Delega una tarea de investigación a un subagente READ-ONLY (solo puede "
    "leer archivos con read_file, grep y glob) y devuelve sus hallazgos.",
    {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "Tarea de investigación para el subagente (requerida)",
            },
        },
        "required": ["task"],
    },
    requires_approval=False,
)
def delegate_research(raw: str) -> str:
    args = _parse(raw)
    task = args.get("task")
    if not task or not isinstance(task, str):
        raise ValueError("task es obligatorio")
    if _provider is None:
        raise RuntimeError("delegate no configurado: falta set_provider")
    subagent = Agent(
        provider=_provider,
        system=(
            "Eres un subagente de investigación READ-ONLY: usa solo read_file, "
            "grep y glob para investigar y responde con hallazgos concretos y rutas."
        ),
        max_turns=15,
        tools=[
            registry.get("read_file"),
            registry.get("grep"),
            registry.get("glob"),
        ],
    )
    return subagent.send(task)
