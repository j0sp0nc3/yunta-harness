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


def percentile(values: list[float], pct: float) -> float:
    """Percentil por interpolación lineal, sin dependencias (V7-2,
    2026-09-22). `pct` en [0, 100]. 0.0 con lista vacía."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (pct / 100)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


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
    # V7-2 (2026-09-22): desglose de tiempo por fragmento — network_wait
    # (esperando al servidor, dentro de `_post_transcription`) vs processing
    # (todo lo demás en `transcribe_with_meta`, incluido el backoff entre
    # reintentos). Convierte en dato medible si una demora es de red/endpoint
    # o del lado cliente, en vez de solo un tiempo total agregado.
    network_wait_p50: float = 0.0
    network_wait_p95: float = 0.0
    network_wait_max: float = 0.0
    processing_p50: float = 0.0
    processing_p95: float = 0.0
    processing_max: float = 0.0
    workers_used: int = 1
    # V7-6 (2026-09-22): fragmentos descartados enteros por ser una frase de
    # relleno conocida de Whisper (V6-4) — antes no había forma de saber si
    # ese filtro ayudó en una corrida real.
    hallucinations_filtered: int = 0
    # V7-12 (2026-09-25): reintentos de nube, incluidos los que terminaron
    # bien. `errors_handled` solo cuenta fallbacks a Whisper local, así que una
    # corrida real con 7 errores reintentados con éxito registró 0 errores.
    # Snapshots anteriores a este campo leen 0, que para ELLOS significa "no
    # medido", no "no hubo reintentos": en al menos dos corridas previas sí
    # los hubo (se ven como outliers de `processing_max`, porque el sleep del
    # backoff cae fuera de `network_wait`).
    cloud_retries: int = 0


def record_voice_snapshot(
    total_fragments: int,
    cloud_fragments: int,
    local_fragments: int,
    errors_handled: int,
    breaker_trips: int,
    elapsed_secs: float,
    audio_duration_secs: float,
    outcome: str = "",
    network_wait_p50: float = 0.0,
    network_wait_p95: float = 0.0,
    network_wait_max: float = 0.0,
    processing_p50: float = 0.0,
    processing_p95: float = 0.0,
    processing_max: float = 0.0,
    workers_used: int = 1,
    hallucinations_filtered: int = 0,
    cloud_retries: int = 0,
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
        network_wait_p50=network_wait_p50,
        network_wait_p95=network_wait_p95,
        network_wait_max=network_wait_max,
        processing_p50=processing_p50,
        processing_p95=processing_p95,
        processing_max=processing_max,
        workers_used=workers_used,
        hallucinations_filtered=hallucinations_filtered,
        cloud_retries=cloud_retries,
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
    total_hallucinations_filtered = sum(s.get("hallucinations_filtered", 0) for s in snapshots)
    total_cloud_retries = sum(s.get("cloud_retries", 0) for s in snapshots)
    avg_rtf = sum(s.get("rtf", 0.0) for s in snapshots) / n

    cloud_ratio = (total_cloud / total_fragments) if total_fragments else 0.0
    errors_per_fragment = (total_errors / total_fragments) if total_fragments else 0.0
    hallucinations_per_fragment = (total_hallucinations_filtered / total_fragments) if total_fragments else 0.0
    retries_per_fragment = (total_cloud_retries / total_fragments) if total_fragments else 0.0

    # V7-2: promedio entre sesiones de los percentiles ya calculados por
    # sesión (no se guardan los tiempos crudos por fragmento en el JSONL,
    # solo el resumen p50/p95/max de cada corrida) — snapshots viejos sin
    # estos campos aportan 0.0 sin romper el promedio.
    avg_network_wait_p50 = sum(s.get("network_wait_p50", 0.0) for s in snapshots) / n
    avg_network_wait_p95 = sum(s.get("network_wait_p95", 0.0) for s in snapshots) / n
    max_network_wait = max((s.get("network_wait_max", 0.0) for s in snapshots), default=0.0)
    avg_processing_p50 = sum(s.get("processing_p50", 0.0) for s in snapshots) / n
    avg_processing_p95 = sum(s.get("processing_p95", 0.0) for s in snapshots) / n
    max_processing = max((s.get("processing_max", 0.0) for s in snapshots), default=0.0)

    return {
        "sessions": n,
        "total_fragments": total_fragments,
        "total_cloud_fragments": total_cloud,
        "total_local_fragments": total_local,
        "total_errors_handled": total_errors,
        "total_breaker_trips": total_trips,
        "total_hallucinations_filtered": total_hallucinations_filtered,
        "avg_rtf": round(avg_rtf, 3),
        "cloud_ratio": round(cloud_ratio, 4),
        "errors_per_fragment": round(errors_per_fragment, 4),
        "hallucinations_per_fragment": round(hallucinations_per_fragment, 4),
        "avg_network_wait_p50": round(avg_network_wait_p50, 3),
        "avg_network_wait_p95": round(avg_network_wait_p95, 3),
        "max_network_wait": round(max_network_wait, 3),
        "avg_processing_p50": round(avg_processing_p50, 3),
        "avg_processing_p95": round(avg_processing_p95, 3),
        "max_processing": round(max_processing, 3),
        "total_cloud_retries": total_cloud_retries,
        "retries_per_fragment": round(retries_per_fragment, 4),
    }
