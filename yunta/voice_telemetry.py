"""Telemetría persistente del pipeline de transcripción de voz (Fase 3,
2026-09-20): reemplaza el script ad-hoc que grepeaba logs para medir una
transcripción real (259 fragmentos, RTF, errores 503/1102 manejados) por
un registro estructurado consultable con `yunta health --voice`.

Módulo separado de `yunta/health.py` a propósito: su `health_score` es una
heurística específica de agente LLM (tasa de error de tools, doom-loops)
que no tiene sentido para un pipeline de audio. Clona el mismo patrón
(JSONL append-only, `mkdir`, `try/except: pass` del llamador) sin heredar
ese acoplamiento."""
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_VOICE_HEALTH_PATH = Path(".yunta") / "voice_health.jsonl"


@dataclass
class VoiceSnapshot:
    timestamp: float
    total_fragments: int
    cloud_fragments: int
    local_fragments: int
    errors_handled: int
    breaker_trips: int
    elapsed_secs: float
    audio_duration_secs: float
    rtf: float  # audio_duration_secs / elapsed_secs (>1 = más rápido que tiempo real)
    outcome: str = ""


def record_voice_snapshot(
    total_fragments: int,
    cloud_fragments: int,
    local_fragments: int,
    errors_handled: int,
    breaker_trips: int,
    elapsed_secs: float,
    audio_duration_secs: float,
    outcome: str = "",
    path: Path | str = DEFAULT_VOICE_HEALTH_PATH,
) -> None:
    """Append-only: una snapshot JSON por transcripción de audio grande."""
    rtf = (audio_duration_secs / elapsed_secs) if elapsed_secs > 0 else 0.0
    snap = VoiceSnapshot(
        timestamp=time.time(),
        total_fragments=total_fragments,
        cloud_fragments=cloud_fragments,
        local_fragments=local_fragments,
        errors_handled=errors_handled,
        breaker_trips=breaker_trips,
        elapsed_secs=elapsed_secs,
        audio_duration_secs=audio_duration_secs,
        rtf=rtf,
        outcome=outcome,
    )
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(snap), ensure_ascii=False) + "\n")


def _load_voice_snapshots(path: Path | str = DEFAULT_VOICE_HEALTH_PATH, limit: int | None = None) -> list[dict]:
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


def aggregate_voice(path: Path | str = DEFAULT_VOICE_HEALTH_PATH, limit: int | None = None) -> dict:
    """Agrega snapshots de transcripción: promedios de RTF, proporción
    nube/local y errores por fragmento — el dato que hoy requiere un script
    ad-hoc grepeando logs."""
    snapshots = _load_voice_snapshots(path, limit)
    if not snapshots:
        return {"sessions": 0}

    n = len(snapshots)
    total_fragments = sum(s.get("total_fragments", 0) for s in snapshots)
    total_cloud = sum(s.get("cloud_fragments", 0) for s in snapshots)
    total_local = sum(s.get("local_fragments", 0) for s in snapshots)
    total_errors = sum(s.get("errors_handled", 0) for s in snapshots)
    total_trips = sum(s.get("breaker_trips", 0) for s in snapshots)
    avg_rtf = sum(s.get("rtf", 0.0) for s in snapshots) / n

    cloud_ratio = (total_cloud / total_fragments) if total_fragments else 0.0
    errors_per_fragment = (total_errors / total_fragments) if total_fragments else 0.0

    return {
        "sessions": n,
        "total_fragments": total_fragments,
        "total_cloud_fragments": total_cloud,
        "total_local_fragments": total_local,
        "total_errors_handled": total_errors,
        "total_breaker_trips": total_trips,
        "avg_rtf": round(avg_rtf, 3),
        "cloud_ratio": round(cloud_ratio, 4),
        "errors_per_fragment": round(errors_per_fragment, 4),
    }
