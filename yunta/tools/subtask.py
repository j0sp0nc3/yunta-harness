"""Subagente de modificación acotada a subtareas (P9): tool `delegate_subtask`.

Descompone especificaciones complejas en subtareas enfocadas en máximo 1-2 archivos,
ejecutando un `Agent` con contexto limpio y acotado.
"""

from ..agent import Agent
from . import _parse, registry

_provider = None


def set_provider(p) -> None:
    global _provider
    _provider = p


@registry.register(
    "delegate_subtask",
    "Delega una subtarea de edición/modificación enfocada en 1 o máximo 2 archivos a un "
    "subagente con contexto limpio para evitar la saturación del historial principal.",
    {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "Descripción detallada de la subtarea a ejecutar (requerida)",
            },
            "target_files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Lista de rutas de los archivos objetivo a modificar (máximo 2 archivos)",
            },
        },
        "required": ["task", "target_files"],
    },
    requires_approval=True,
)
def delegate_subtask(raw: str) -> str:
    args = _parse(raw)
    task = args.get("task")
    target_files = args.get("target_files", [])

    if not task or not isinstance(task, str):
        raise ValueError("task es obligatorio y debe ser un string")
    if not isinstance(target_files, list) or len(target_files) == 0:
        raise ValueError("target_files debe ser una lista con al menos 1 archivo")
    if len(target_files) > 2:
        raise ValueError("delegate_subtask acepta como máximo 2 archivos por subtarea para mantener el contexto enfocado")

    if _provider is None:
        raise RuntimeError("delegate_subtask no configurado: falta set_provider")

    files_str = ", ".join(str(f) for f in target_files)
    system_prompt = (
        f"Eres un subagente especializado de edición acotada. Tu objetivo es cumplir la siguiente subtarea "
        f"enfocándote exclusivamente en los archivos objetivo: {files_str}.\n"
        f"Usa read_file, write_file, str_replace y bash según corresponda. Sé preciso y realiza solo los cambios solicitados."
    )

    allowed_tools = []
    for tool_name in ["read_file", "write_file", "str_replace", "list_dir", "grep", "glob", "bash"]:
        tool_obj = registry.get(tool_name)
        if tool_obj:
            allowed_tools.append(tool_obj)

    subagent = Agent(
        provider=_provider,
        system=system_prompt,
        max_turns=15,
        tools=allowed_tools,
    )

    prompt = f"Subtarea: {task}\nArchivos objetivo: {files_str}"
    return subagent.send(prompt)
