"""Telemetría de llamadas al LLM (Fase 10, V7-5, 2026-09-22): registra por
cada llamada a `LiteLLMProvider.send()` el `finish_reason` CRUDO del
proveedor, tokens y tiempo de pared — para confirmar o descartar si una
demora se debe a truncamiento por límite de tokens de salida.

Motivado por un dato concreto de dos corridas reales del pipeline de voz:
generaron EXACTAMENTE 9,402 tokens de salida con contenido de entrada
completamente distinto (72K vs 73K caracteres de transcript, resúmenes con
estructura diferente) — coincidencia estadísticamente rara si ambas
generaciones terminaron "naturalmente". El `StopReason` que ya expone
`yunta/api.py` colapsa `"length"` (el motivo estándar de truncamiento por
`max_tokens`) en `OTHER`, indistinguible de cualquier otro final.

Módulo separado de `yunta/api.py::Usage` a propósito: `Usage` es
superficie pública congelada (`docs/PLAN.md`, ítem E2), reexportada en
`yunta/__init__.py` — no se le agregan campos nuevos ni se modifica
`StopReason` para no arriesgar esa superficie estable. Clona el mismo
patrón JSONL append-only de `voice_telemetry.py`."""
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_LLM_CALLS_PATH = Path(".yunta") / "llm_calls.jsonl"


@dataclass
class LLMCallSnapshot:
    timestamp: float
    model: str
    input_tokens: int
    output_tokens: int
    elapsed_secs: float
    finish_reason_raw: str
    streaming: bool
    tool_calls: int = 0
    # V7-9 (2026-09-24): las llamadas que fallan (cuota agotada, rate
    # limit, timeout) también dejan rastro. Antes solo se registraba el
    # camino de éxito, así que un incidente de cuota que abortó una
    # transcripción real quedó completamente invisible: 0 entradas pese a
    # varios intentos. `error` vacío = la llamada tuvo éxito.
    error: str = ""


def record_llm_call(
    model: str,
    input_tokens: int,
    output_tokens: int,
    elapsed_secs: float,
    finish_reason_raw: str,
    streaming: bool = False,
    tool_calls: int = 0,
    error: str = "",
    path: Path | str = DEFAULT_LLM_CALLS_PATH,
) -> None:
    """Append-only: una entrada JSON por llamada a `send()`, exitosa o no."""
    snap = LLMCallSnapshot(
        timestamp=time.time(),
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        elapsed_secs=elapsed_secs,
        finish_reason_raw=finish_reason_raw,
        streaming=streaming,
        tool_calls=tool_calls,
        error=error,
    )
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(snap), ensure_ascii=False) + "\n")


def _load_llm_calls(path: Path | str = DEFAULT_LLM_CALLS_PATH, limit: int | None = None) -> list[dict]:
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


def aggregate_llm_calls(path: Path | str = DEFAULT_LLM_CALLS_PATH, limit: int | None = None) -> dict:
    """Agrega llamadas: tokens/seg promedio y cuántas terminaron por
    `"length"` (truncadas por `max_tokens`) — responde directamente si el
    truncamiento explica una demora, en vez de conjeturarlo."""
    calls = _load_llm_calls(path, limit)
    if not calls:
        return {"calls": 0}
    n = len(calls)
    # V7-9: las llamadas fallidas no aportan tokens ni velocidad de
    # generación — se cuentan aparte para no ensuciar el promedio de
    # tokens/seg con ceros de intentos que nunca produjeron texto.
    failed = [c for c in calls if c.get("error")]
    ok = [c for c in calls if not c.get("error")]
    total_out = sum(c.get("output_tokens", 0) for c in ok)
    total_secs = sum(c.get("elapsed_secs", 0.0) for c in ok)
    length_truncated = sum(1 for c in ok if c.get("finish_reason_raw") == "length")
    tokens_per_sec = (total_out / total_secs) if total_secs > 0 else 0.0
    errores = {}
    for c in failed:
        tipo = str(c.get("error", "")).split(":")[0]
        errores[tipo] = errores.get(tipo, 0) + 1
    return {
        "calls": n,
        "successful_calls": len(ok),
        "failed_calls": len(failed),
        "failure_ratio": round(len(failed) / n, 4),
        "errors_by_type": errores,
        "total_output_tokens": total_out,
        "avg_tokens_per_sec": round(tokens_per_sec, 2),
        "length_truncated_calls": length_truncated,
        "length_truncated_ratio": round(length_truncated / len(ok), 4) if ok else 0.0,
    }
