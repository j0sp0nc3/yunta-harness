"""P9: descomposición de specs grandes en subtareas ejecutables por lotes.

Una spec que exige más de ~2 archivos degrada y mata la sesión (evidencia:
dogfooding v0.7 streaming, O1-c, ronda W). Este módulo parte la spec en
subtareas de ≤2 archivos sin solapamiento y las ejecuta SECUENCIALMENTE con
subagentes de contexto limpio. Ante cuota agotada, persiste el lote exacto
en .yunta/estado-de-tarea.md (P7) para reanudar sin repetir trabajo."""
import json
from dataclasses import dataclass, field

from .api import Block, BlockType, Message, Role
from .resilience import save_task_state

MAX_FILES_PER_CHUNK = 2

DECOMPOSE_PROMPT = """Eres un planificador de tareas de código. Divide la siguiente especificación
en subtareas EJECUTABLES INDEPENDIENTEMENTE, respondiendo SOLO un array JSON:

[{"goal": "<objetivo concreto de la subtarea>",
  "files": ["<archivo1>", "<archivo2>"],
  "verify": "<criterio de verificación: test o comando>"}

Reglas:
- Máximo MAXF archivos por subtarea (crea los archivos nuevos que haga falta).
- Un archivo NO puede aparecer en dos subtareas (sin solapamiento).
- Ordena por dependencia: primero lo que no depende de nada.
- Cada subtarea debe poder verificarse sola (test propio o comando).
- Sin texto fuera del array JSON.

Especificación:
"""


@dataclass
class Subtask:
    goal: str
    files: list[str] = field(default_factory=list)
    verify: str = ""


def _parse_subtasks(text: str) -> list[Subtask]:
    """Extrae el array JSON de la respuesta; lanza ValueError si es inválido."""
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        raise ValueError("respuesta sin array JSON")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, list) or not data:
        raise ValueError("array vacío o no es lista")
    tasks = []
    for item in data:
        if not isinstance(item, dict) or "goal" not in item or "files" not in item:
            raise ValueError("subtarea sin goal/files")
        files = [str(f) for f in item["files"]]
        tasks.append(Subtask(goal=str(item["goal"]), files=files, verify=str(item.get("verify", ""))))
    return tasks


def _validate(tasks: list[Subtask]) -> None:
    """Reglas duras: ≤MAX archivos por lote y sin solapamiento."""
    seen: set[str] = set()
    for t in tasks:
        if not (1 <= len(t.files) <= MAX_FILES_PER_CHUNK):
            raise ValueError(f"subtarea con {len(t.files)} archivos (máx {MAX_FILES_PER_CHUNK}): {t.goal[:40]}")
        for f in t.files:
            if f in seen:
                raise ValueError(f"archivo en dos subtareas: {f}")
            seen.add(f)


def decompose_task(provider, spec: str, max_attempts: int = 2) -> list[Subtask]:
    """Pide al modelo el plan de subtareas y lo valida. Una regeneración
    si el plan viola las reglas; luego falla con error claro."""
    last_err = None
    for _ in range(max_attempts):
        resp = provider.send(
            [Message(role=Role.USER, content=[Block(
                type=BlockType.TEXT,
                text=DECOMPOSE_PROMPT.replace("MAXF", str(MAX_FILES_PER_CHUNK)) + spec,
            )])],
            [],
        )
        text = "".join(b.text for b in resp.content if b.type == BlockType.TEXT)
        try:
            tasks = _parse_subtasks(text)
            _validate(tasks)
            return tasks
        except (ValueError, json.JSONDecodeError) as e:
            last_err = e
    raise ValueError(f"no se pudo obtener un plan de subtareas válido: {last_err}")


def run_chunks(provider, subtasks: list[Subtask], system: str,
               confirm=None, start_from: int = 0, agent_cls=None) -> list[str]:
    """Ejecuta las subtareas SECUENCIALMENTE con un subagente de contexto limpio
    por lote. Ante error de cuota persiste el lote pendiente (P7) y relanza.
    Devuelve los resúmenes de cada lote completado."""
    from .agent import Agent

    results = []
    total = len(subtasks)
    for i in range(start_from, total):
        t = subtasks[i]
        sub = (agent_cls or Agent)(
            provider=provider,
            system=system,
            max_turns=15,
            confirm=confirm,
        )
        prompt = (
            f"Subtarea {i + 1}/{total} — UNA tarea acotada, no la spec completa.\n"
            f"Objetivo: {t.goal}\n"
            f"Archivos permitidos (SOLO estos): {', '.join(t.files)}\n"
            f"Verificación al terminar: {t.verify or 'python -m pytest tests/ -q'}\n"
            f"Verifica antes de declarar terminado."
        )
        try:
            results.append(sub.send(prompt))
        except Exception as e:
            save_task_state(
                f"[P9 lote {i + 1}/{total}] {t.goal}",
                [{"role": "assistant", "text": r[:200]} for r in results],
                f"{type(e).__name__}: {e}",
            )
            raise
    return results
