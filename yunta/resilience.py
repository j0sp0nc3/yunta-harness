"""P7: degradación progresiva ante agotamiento de cuota.

Cuando el proveedor agota su cuota (RateLimitError y afines), el harness
persiste el estado de la tarea pendiente en .yunta/estado-de-tarea.md para
que cualquier sesión posterior (u otro IDE) pueda retomarla, y lanza
QuotaExhausted para cerrar ordenado en vez de morir con traceback."""
from datetime import datetime
from pathlib import Path

STATE_PATH = Path(".yunta") / "estado-de-tarea.md"

_QUOTA_MARKERS = (
    "rate limit",
    "ratelimit",
    "usage limit",
    "quota",
    "insufficient balance",
    "insufficient_quota",
    "resource_exhausted",
    "429",
    "401",
    "403",
    "authenticationerror",
    "invalid_api_key",
    "unauthorized",
    "credit",
    "exceeded your current quota",
)


class QuotaExhausted(RuntimeError):
    """Cuota del proveedor agotada. El estado de la tarea quedó persistido."""


def should_save_state(err: Exception) -> bool:
    """True si el error indica agotamiento de cuota/límite del proveedor."""
    msg = str(err).lower()
    return any(marker in msg for marker in _QUOTA_MARKERS)


def save_task_state(
    last_prompt: str,
    messages_summary: list[dict],
    error: str,
    path: Path | None = None,
) -> Path:
    """Persiste (acumulando) el estado de la tarea interrumpida."""
    f = path or STATE_PATH
    f.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().isoformat(timespec="seconds")
    entry = [
        f"## Sesión interrumpida — {stamp}",
        f"- **Error**: {error}",
        f"- **Última petición del usuario**: {last_prompt or '(sin registrar)'}",
        f"- **Mensajes de contexto**: {len(messages_summary)}",
        "",
    ]
    for m in messages_summary[-10:]:
        role = m.get("role", "?")
        text = m.get("text", "")
        entry.append(f"  - {role}: {text[:200]}")
    entry += [
        "",
        "Para retomar: relanza la sesión y entrega este archivo como contexto,",
        "o usa `yunta --resume`. Ver docs/PLAN.md para la especificación.",
        "",
    ]
    with f.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(entry) + "\n")
    return f
