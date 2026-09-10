"""Subagente de investigación read-only: tool `delegate_research`.

Crea un `Agent` interno cuyo contexto está restringido a las tools de lectura
(`read_file`, `grep`, `glob`) y le delega la tarea indicada.
Soporta `LLM_FAST_MODEL` en entorno para usar un modelo ultrarrápido/económico en investigaciones.
"""

import os
from ..agent import Agent
from ..provider import LiteLLMProvider
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

    system_prompt = (
        "Eres un subagente de investigación READ-ONLY: usa solo read_file, "
        "grep y glob para investigar y responde con hallazgos concretos y rutas."
    )

    fast_model = os.environ.get("LLM_FAST_MODEL")
    if fast_model:
        try:
            sub_provider = LiteLLMProvider(model=fast_model, system=system_prompt)
        except Exception:
            sub_provider = _provider
    else:
        sub_provider = _provider

    subagent = Agent(
        provider=sub_provider,
        system=system_prompt,
        max_turns=15,
        tools=[
            registry.get("read_file"),
            registry.get("grep"),
            registry.get("glob"),
        ],
    )
    return subagent.send(task)
