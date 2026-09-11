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


@registry.register(
    "delegate_batch",
    "Ejecuta múltiples subtareas de investigación en paralelo mediante un pool concurrente de subagentes y consolida sus hallazgos.",
    {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "description": "Descripción de la subtarea"},
                    },
                    "required": ["task"],
                },
                "description": "Lista de subtareas a ejecutar concurrentemente",
            },
        },
        "required": ["tasks"],
    },
    requires_approval=False,
)
def delegate_batch(raw: str) -> str:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    args = _parse(raw)
    tasks_list = args.get("tasks")
    if not isinstance(tasks_list, list) or not tasks_list:
        raise ValueError("tasks debe ser una lista no vacía de subtareas")

    if _provider is None:
        raise RuntimeError("delegate no configurado: falta set_provider")

    def _run_single(idx: int, t_info: dict) -> tuple[int, str]:
        t_str = t_info.get("task", "")
        if not t_str:
            return idx, f"[Subtarea {idx+1}] Error: task es obligatorio"
        try:
            res = delegate_research(f'{{"task": "{t_str}"}}')
            return idx, f"[Subtarea {idx+1} — '{t_str}']:\n{res}"
        except Exception as e:
            return idx, f"[Subtarea {idx+1}] Falló: {e}"

    results = [None] * len(tasks_list)
    max_workers = min(len(tasks_list), 5)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_run_single, i, task_info) for i, task_info in enumerate(tasks_list)]
        for future in as_completed(futures):
            idx, res_text = future.result()
            results[idx] = res_text

    return "\n\n---\n\n".join(r for r in results if r is not None)

