"""Agent Health Score (Feature 5, 2026-09-19): persiste métricas agregadas
por repo entre sesiones, en vez de perderlas al morir el proceso.

Reutiliza la convención JSONL append-only establecida en la Feature 4
(`team_memory.py`) y los campos ya calculados en `Usage` (`api.py`) — cero
instrumentación nueva salvo el contador de doom-loops (`agent.py`,
`self._doom_loop_triggers`)."""
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .api import Usage

DEFAULT_HEALTH_PATH = Path(".yunta") / "health.jsonl"


@dataclass
class HealthSnapshot:
    timestamp: float
    model: str
    turns: int
    tool_errors: int
    total_tool_calls: int
    doom_loop_triggers: int
    cache_rate: float
    outcome: str = ""


def record_snapshot(
    usage: Usage,
    doom_loop_triggers: int = 0,
    model: str = "",
    outcome: str = "",
    path: Path | str = DEFAULT_HEALTH_PATH,
) -> None:
    """Append-only: una snapshot JSON por sesión (misma convención de la
    Feature 4)."""
    snap = HealthSnapshot(
        timestamp=time.time(),
        model=model,
        turns=usage.turns,
        tool_errors=usage.tool_errors,
        total_tool_calls=usage.total_tool_calls,
        doom_loop_triggers=doom_loop_triggers,
        cache_rate=usage.cache_rate,
        outcome=outcome,
    )
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(snap), ensure_ascii=False) + "\n")


def _load_snapshots(path: Path | str = DEFAULT_HEALTH_PATH, limit: int | None = None) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    entries = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if limit:
        entries = entries[-limit:]
    return entries


def aggregate(path: Path | str = DEFAULT_HEALTH_PATH, limit: int | None = None) -> dict:
    """Agrega snapshots en un resumen. `health_score` es una heurística
    simple v1 (no científica, documentada como punto de partida): penaliza
    tasa de error de tools y frecuencia de doom-loops."""
    snapshots = _load_snapshots(path, limit)
    if not snapshots:
        return {"sessions": 0}

    n = len(snapshots)
    total_turns = sum(s.get("turns", 0) for s in snapshots)
    total_tool_calls = sum(s.get("total_tool_calls", 0) for s in snapshots)
    total_errors = sum(s.get("tool_errors", 0) for s in snapshots)
    total_doom = sum(s.get("doom_loop_triggers", 0) for s in snapshots)
    avg_cache_rate = sum(s.get("cache_rate", 0.0) for s in snapshots) / n

    error_rate = (total_errors / total_tool_calls) if total_tool_calls else 0.0
    doom_rate = total_doom / n

    score = 100.0
    score -= min(50.0, error_rate * 100)
    score -= min(30.0, doom_rate * 20)
    score = max(0.0, round(score, 1))

    return {
        "sessions": n,
        "total_turns": total_turns,
        "total_tool_calls": total_tool_calls,
        "total_tool_errors": total_errors,
        "total_doom_loop_triggers": total_doom,
        "avg_cache_rate": round(avg_cache_rate, 1),
        "error_rate": round(error_rate, 4),
        "health_score": score,
    }
