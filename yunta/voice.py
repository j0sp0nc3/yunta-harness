"""Módulo de transcripción de voz a texto y procesamiento de cátedras extensas.

Soporta transcripción de voz vía HTTP multipart/form-data nativo hacia endpoints
compatibles con OpenAI Whisper (/v1/audio/transcriptions), fragmentación
inteligente de audios largos por silencios (VAD) y grabación desde micrófono.
"""

from io import BytesIO
import http.client
import json
import mimetypes
import os
from pathlib import Path
import random
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import re
import unicodedata
import uuid
import wave

# Evitar UnicodeEncodeError en consolas Windows (cp1252) al imprimir emojis o caracteres especiales
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

APPROVAL_SYNONYMS = {
    "s", "si", "sí", "yes", "y", "ok", "okay", "okei", "okey", "oki",
    "aprobado", "aprobar", "aprobada", "apruebo", "aprobarlo", "aprobado ok",
    "avanzar", "avanza", "abanza", "abanzau", "abanzado", "adelante", "proceder", "prosiga",
    "dale", "vamos", "ya", "listo", "confirmo", "confirmado", "correcto", "perfecto",
    "acepto", "aceptar", "enviar", "envialo", "de acuerdo", "dale nomas", "dale nomás",
    "aprobau", "abanzar"
}

REJECTION_SYNONYMS = {
    "c", "n", "no", "cancelar", "cancela", "cancelado", "rechazado", "rechazar", "rechazo", "rechazada",
    "alto", "detener", "deten", "stop", "para", "parar", "abortar", "no enviar", "negativo"
}

EDIT_SYNONYMS = {
    "e", "editar", "edita", "edit", "modificar", "modifica", "cambiar", "cambia", "corregir", "corrige",
    "reescribir", "ajustar"
}

ALWAYS_SYNONYMS = {
    "siempre", "always", "para siempre", "siempre si", "siempre aprobar",
    "si a todo", "sí a todo", "aprobado a todo", "aprobar todo", "todo si", "todo sí"
}

FILLERS = {
    "por", "favor", "el", "la", "los", "las", "un", "una", "de", "del", "en", "gracias",
    "nomas", "nomás", "ahi", "ahí", "entonces", "ya", "pues", "texto", "modo"
}


def _clean_response_text(text: str) -> str:
    """Normaliza texto removiendo acentos, signos de puntuación y espacios superfluos."""
    t = text.strip().lower()
    t = "".join(
        c for c in unicodedata.normalize("NFD", t)
        if unicodedata.category(c) != "Mn"
    )
    t = re.sub(r"[^\w\s]", "", t)
    return t.strip()


def _levenshtein(a: str, b: str) -> int:
    """Distancia de edición clásica (DP con una fila) — sin dependencias externas."""
    if a == b:
        return 0
    if not a or not b:
        return max(len(a), len(b))
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = curr
    return prev[-1]


# Sinónimos que NO participan del matching difuso: su forma es tan cercana a una
# palabra común ("reescribir" ≈ "escribir", "apruebo" ≈ "prueba") que aceptarla
# por fuzzy genera falsos positivos. Siguen funcionando por coincidencia exacta.
_FUZZY_EXEMPT = {"reescribir", "apruebo"}


def _fuzzy_in(word: str, candidates: set[str]) -> bool:
    """Tolerancia fonética ante errores de Whisper (V5-3): distancia ≤1 para
    palabras cortas (≤5 chars) y ≤2 para largas, excluyendo _FUZZY_EXEMPT."""
    for cand in candidates:
        if cand in _FUZZY_EXEMPT:
            continue
        max_d = 1 if len(cand) <= 5 else 2
        if abs(len(word) - len(cand)) > max_d:
            continue
        if _levenshtein(word, cand) <= max_d:
            return True
    return False


def normalize_voice_response(text: str) -> str:
    """Normaliza y compara respuestas de voz o texto frecuente para aprobaciones o elecciones.

    Retorna:
    - 's': si coincide con sinónimos de aprobación ("sí", "aprobado", "avanzar", "abanzau", "ok", "dale", etc.)
    - 'c': si coincide con sinónimos de rechazo/cancelación ("no", "rechazado", "cancelar", "alto", "stop", etc.)
    - 'e': si coincide con sinónimos de edición ("editar", "modificar", "cambiar", etc.)
    - 'siempre': si coincide con aprobación permanente ("siempre", "para siempre")
    - El texto original sin modificar si no es una palabra/frase corta de respuesta rápida.
    Frases de una palabra no exactas se comparan con tolerancia fonética (V5-3).
    """
    if not text:
        return text

    cleaned = _clean_response_text(text)
    if not cleaned:
        return text

    # Coincidencia exacta de frase
    if cleaned in ALWAYS_SYNONYMS:
        return "siempre"
    if cleaned in APPROVAL_SYNONYMS:
        return "s"
    if cleaned in REJECTION_SYNONYMS:
        return "c"
    if cleaned in EDIT_SYNONYMS:
        return "e"

    # Fuzzy (V5-3): una sola palabra no exacta contra los sinónimos de cada acción
    if " " not in cleaned:
        if _fuzzy_in(cleaned, ALWAYS_SYNONYMS):
            return "siempre"
        if _fuzzy_in(cleaned, APPROVAL_SYNONYMS):
            return "s"
        if _fuzzy_in(cleaned, REJECTION_SYNONYMS):
            return "c"
        if _fuzzy_in(cleaned, EDIT_SYNONYMS):
            return "e"

    words = cleaned.split()
    if len(words) <= 4:
        meaningful = [w for w in words if w not in FILLERS]
        if not meaningful:
            meaningful = words

        if all(w in ALWAYS_SYNONYMS or w in {"siempre", "si"} for w in meaningful):
            return "siempre"
        if all(w in APPROVAL_SYNONYMS or w in {"ok", "si"} for w in meaningful):
            return "s"
        if all(w in REJECTION_SYNONYMS or w in {"no"} for w in meaningful):
            return "c"
        if all(w in EDIT_SYNONYMS for w in meaningful):
            return "e"

    return text


def trim_initial_noise_and_silence(wav_path: str, noise_gate_ms: int = 150, lead_in_ms: int = 100) -> str:
    """Elimina el ruido inicial de tecla/micrófono y el silencio previo antes de la voz."""
    try:
        path = Path(wav_path)
        if not path.exists() or path.suffix.lower() != ".wav":
            return wav_path

        with wave.open(str(path), "rb") as wf:
            params = wf.getparams()
            sample_rate = params.framerate
            n_channels = params.nchannels
            sample_width = params.sampwidth
            frames = wf.readframes(wf.getnframes())

        if sample_width != 2 or not frames:
            return wav_path

        sample_count = len(frames) // (2 * n_channels)
        total_duration_ms = (sample_count / sample_rate) * 1000.0
        # No recortar si el audio dura menos de 500ms
        if total_duration_ms < 500:
            return wav_path

        fmt = f"<{sample_count * n_channels}h"
        samples = struct.unpack(fmt, frames)

        if n_channels > 1:
            mono_samples = [sum(samples[i:i+n_channels]) // n_channels for i in range(0, len(samples), n_channels)]
        else:
            mono_samples = samples

        window_size = int(sample_rate * 0.02)
        if window_size == 0 or len(mono_samples) < window_size:
            return wav_path

        start_sample = int(sample_rate * (noise_gate_ms / 1000.0))
        speech_start_sample = start_sample
        threshold = 300

        for i in range(start_sample, len(mono_samples) - window_size, window_size):
            chunk = mono_samples[i:i+window_size]
            rms = (sum(s * s for s in chunk) / len(chunk)) ** 0.5
            if rms > threshold:
                speech_start_sample = max(0, i - int(sample_rate * (lead_in_ms / 1000.0)))
                break

        byte_start = speech_start_sample * 2 * n_channels
        trimmed_bytes = frames[byte_start:]

        if trimmed_bytes:
            with wave.open(str(path), "wb") as wf_out:
                wf_out.setparams(params)
                wf_out.writeframes(trimmed_bytes)
    except Exception:
        pass
    return wav_path


def offload_transcript(text: str, preview_chars: int = 500, threshold: int = 8000) -> str:
    """Si el transcript supera el umbral, lo guarda en .yunta/scratch/ y retorna
    un preview + referencia, para no saturar el contexto del agente (V3-3).

    2026-09-20: motivado por una corrida real donde el agente, pese a poder
    leer el archivo completo en una sola llamada (775 líneas, bajo el límite
    de 2000 de `read_file`), lo fragmentó en 6 lecturas "para procesarlo
    mejor" — cada llamada adicional reenvía todo el historial acumulado, y
    eso solo, en ~15 turnos totales, hizo pesar la transcripción entera 172K
    tokens de entrada. Además se detectó path confusion: el agente
    transcribió mal un dígito del nombre de archivo con timestamp y perdió 7
    tool calls explorando el filesystem antes de encontrarlo. Dos mitigaciones:
    (1) sugerir explícitamente una sola lectura cuando el tamaño lo permite
    (bajo un umbral generoso de tokens), en vez de empujar a fragmentar
    siempre; (2) reportar la ruta en formato POSIX (barras, no backslashes)
    para reducir el riesgo de que el modelo la corrompa al reproducirla en un
    argumento JSON (`\\t`, `\\n`, etc. son secuencias de escape válidas que
    pueden aparecer por casualidad en una ruta de Windows).
    """
    if len(text) <= threshold:
        return text
    from datetime import datetime

    scratch_dir = Path(".yunta") / "scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    scratch_file = scratch_dir / f"transcript_{ts}.txt"
    scratch_file.write_text(text, encoding="utf-8")
    posix_path = scratch_file.as_posix()
    preview = text[:preview_chars]
    approx_tokens = len(text) // 4
    if approx_tokens <= 50_000:
        instruction = f'usa read_file con path="{posix_path}" (cabe entero en una sola lectura, sin offset/limit)'
    else:
        instruction = f'usa read_file con path="{posix_path}" y offset/limit para leerlo por partes (muy extenso para una sola lectura)'
    return (
        f"{preview}\n\n[... transcript completo ({len(text)} caracteres, {approx_tokens} tokens aprox) "
        f"guardado en: {posix_path} — {instruction}]"
    )


class _TranscribeError(Exception):
    """Error HTTP o de red al transcribir, con clasificación para retry/fragmentación."""

    def __init__(self, msg: str, code: int | None, detail: str, retry_after: float | None = None):
        super().__init__(msg)
        self.code = code
        self.detail = detail.lower()
        self.too_large = (
            "too large" in self.detail
            or "3006" in self.detail
            or self.code == 413
        )
        self.retryable = (
            self.code is None
            or (self.code is not None and self.code >= 500)
            or self.code == 429
        )
        # Fase 2 (2026-09-20): segundos que el endpoint pide esperar (header
        # Retry-After), si lo manda. Solo formato numérico (segundos); el
        # formato HTTP-date queda fuera de alcance.
        self.retry_after = retry_after


def _dedup_whisper_repetition(text: str) -> str:
    """Elimina bucles patológicos de repetición que Whisper a veces genera en silencios o pausas."""
    if not text:
        return text
    pattern = re.compile(r"(\b[\w\s]{2,30}?[\s,.;]+)\1{2,}", re.IGNORECASE)
    cleaned = pattern.sub(r"\1\1", text)
    return cleaned.strip()


# V6-4 (docs/PLAN.md): frases de relleno típicas que Whisper "alucina" sobre
# silencios/ruido, aprendidas de subtítulos de YouTube en su entrenamiento.
# Lista no exhaustiva, ampliable con el tiempo.
_KNOWN_HALLUCINATION_PHRASES = {
    "gracias por ver el video",
    "gracias por ver el vídeo",
    "gracias por ver este video",
    "gracias por ver este vídeo",
    "suscríbete al canal",
    "suscríbete a mi canal",
    "no olvides suscribirte",
    "no olvides suscribirte al canal",
    "nos vemos en el próximo video",
    "nos vemos en el próximo vídeo",
    "subtítulos realizados por la comunidad de amara.org",
    "subtítulos por la comunidad de amara.org",
    "subtitles by the amara.org community",
    "thanks for watching",
    "thank you for watching",
    "please subscribe to my channel",
    "like, comment and subscribe",
    "like comment and subscribe",
    "see you in the next video",
    "www.youtube.com",
}


def _filter_whisper_hallucinations(text: str) -> str:
    """Descarta un fragmento si su contenido ENTERO (sin puntuación/mayúsculas)
    es una de las frases alucinadas conocidas de arriba — no recorta contenido
    real que las mencione de pasada, solo el caso "el chunk es puro relleno"."""
    if not text:
        return text
    normalized = text.strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = normalized.strip(" .!?¡¿-—")
    if normalized in _KNOWN_HALLUCINATION_PHRASES:
        return ""
    return text


def _clean_transcription(text: str) -> str:
    """Limpieza post-transcripción aplicada a cualquier fuente (nube o local):
    dedup de bucles de repetición + filtro de alucinaciones conocidas (V6-4)."""
    return _filter_whisper_hallucinations(_dedup_whisper_repetition(text))


_local_whisper_model = None
_local_whisper_model_size = None
_local_whisper_lock = threading.Lock()


def _get_local_whisper_model(model_size: str):
    """Carga el modelo local de `faster_whisper` una sola vez por proceso y lo
    reutiliza entre fragmentos (2026-09-20, benchmark real: recargarlo en cada
    llamada costaba ~3.9s de overhead por fragmento — ~17 min extra en una
    transcripción de 259 fragmentos si el fallback local se usa seguido).
    Cache a nivel de módulo (no de instancia) porque `AudioTranscriber`/
    `AudioChunker` a veces se instancian varias veces dentro del mismo proceso
    (p.ej. el retry por `too_large`), y el modelo debe compartirse entre todas.
    """
    global _local_whisper_model, _local_whisper_model_size
    with _local_whisper_lock:
        if _local_whisper_model is None or _local_whisper_model_size != model_size:
            from faster_whisper import WhisperModel
            _local_whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
            _local_whisper_model_size = model_size
        return _local_whisper_model


class AudioTranscriber:
    """Cliente HTTP nativo y agnóstico a proveedores para transcripción de voz (Whisper)."""

    def __init__(self, model: str = None, api_base: str = None, api_key: str = None):
        # 100% Agnóstico: El modelo de voz es whisper-1 o VOICE_MODEL (no hereda LLM_MODEL de texto)
        self.model = model or os.environ.get("VOICE_MODEL") or "whisper-1"
        base = (
            api_base
            or os.environ.get("VOICE_API_BASE")
            or "http://localhost:8000/v1"
        )
        self.api_base = base.rstrip("/")
        self.api_key = (
            api_key
            or os.environ.get("VOICE_API_KEY")
            or os.environ.get("LLM_API_KEY")
            or ""
        )
        self._http_local = threading.local()

    def transcribe(self, file_path: str, prompt: str = "") -> str:
        """Transcribe un archivo de audio (.mp3, .wav, .m4a, .ogg, .webm).

        - Reintenta hasta 3 veces ante errores transitorios (429/5xx) con backoff (V6-2).
        - Si el endpoint rechaza el payload por tamaño (3006/"too large"), reintenta
          automáticamente fragmentando el audio en partes menores (V6-2).
        """
        return self.transcribe_with_meta(file_path, prompt)[0]

    def transcribe_with_meta(self, file_path: str, prompt: str = "", skip_cloud: bool = False) -> tuple[str, dict]:
        """Como `transcribe()`, pero además devuelve metadata de la ejecución:
        `{"source": "cloud"|"local", "cloud_attempted": bool, "cloud_failed": bool}`.

        `AudioChunker` usa esta metadata para implementar un circuit breaker
        entre fragmentos sin duplicar la lógica de reintento/fallback aquí.
        `skip_cloud=True` salta directo al fallback local sin tocar la red
        (usado por el circuit breaker cuando la nube ya se detectó saturada).
        """
        # V7-2 (2026-09-22): `network_wait` mide solo el tiempo dentro de
        # `_post_transcription` (esperando al servidor); todo lo demás del
        # método (incluida la espera de backoff entre reintentos, que es una
        # pausa deliberada del cliente, no del servidor) cae en `total_secs -
        # network_wait` ("processing" a ojos de `AudioChunker`). El objetivo
        # es distinguir "la red/el endpoint es lento" de "algo del lado
        # cliente es lento", no una contabilidad perfecta de cada micro-etapa.
        method_start = time.monotonic()
        network_wait = 0.0

        def _meta(source: str, cloud_attempted: bool, cloud_failed: bool, hallucination_filtered: bool = False) -> dict:
            return {
                "source": source,
                "cloud_attempted": cloud_attempted,
                "cloud_failed": cloud_failed,
                "network_wait_secs": network_wait,
                "total_secs": time.monotonic() - method_start,
                "hallucination_filtered": hallucination_filtered,
            }

        # V7-6 (2026-09-22): detecta si `_clean_transcription` descartó el
        # fragmento entero por ser una frase de relleno conocida (V6-4), para
        # que `AudioChunker` pueda contar cuántos fragmentos reales caen en
        # ese caso — hoy no hay forma de saber si el filtro ayudó en una
        # corrida real. `_dedup_whisper_repetition` nunca reduce texto no
        # vacío a "" (solo colapsa repeticiones), así que "entrada no vacía →
        # salida vacía" solo puede deberse al filtro de alucinaciones.
        def _clean_and_flag(raw: str) -> tuple[str, bool]:
            cleaned = _clean_transcription(raw)
            filtered = bool(raw and raw.strip()) and not cleaned
            return cleaned, filtered

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Archivo de audio no encontrado: {file_path}")

        if skip_cloud:
            raw_local = self.transcribe_offline_local(str(path))
            local_text, filtered = _clean_and_flag(raw_local)
            return local_text, _meta("local", False, False, filtered)

        # Si el archivo supera el límite (25 MB en Whisper API estándar, 500 KB en Workers AI), usar chunker
        max_size = (
            int(os.environ.get("VOICE_MAX_BYTES", 0))
            or (500 * 1024 if "workers.dev" in self.api_base else 25 * 1024 * 1024)
        )
        if path.stat().st_size > max_size:
            env_cm = os.environ.get("VOICE_CHUNK_MINUTES")
            if env_cm:
                cm = float(env_cm)
            elif "workers.dev" in self.api_base:
                # Fase 4: calibrar por bitrate real en vez de asumir siempre
                # el peor caso (0.33 min fijos) — solo si no hay override manual.
                cm = _calibrate_chunk_minutes(str(path), max_size)
            else:
                cm = 10.0
            text = AudioChunker(self, chunk_minutes=cm).transcribe_large_audio(str(path))
            return text, _meta("cloud", True, False)

        last_err = None
        for attempt in range(3):
            t0 = time.monotonic()
            try:
                raw_text = self._post_transcription(path, prompt)
                network_wait += time.monotonic() - t0
                cleaned, filtered = _clean_and_flag(raw_text)
                return cleaned, _meta("cloud", True, False, filtered)
            except _TranscribeError as err:
                network_wait += time.monotonic() - t0
                last_err = err
                if err.too_large:
                    # El endpoint rechaza el tamaño: fragmentar y reintentar con fragmentos menores (20s)
                    if path.stat().st_size <= 128 * 1024:
                        break
                    print(f"⚠️ Endpoint rechazó el audio por límites de tamaño ({err}). Reintentando por fragmentos menores...")
                    text = AudioChunker(self).transcribe_large_audio(str(path), chunk_minutes=0.33)
                    return text, _meta("cloud", True, False)
                if err.retryable and attempt < 2:
                    cap = float(os.environ.get("VOICE_BACKOFF_CAP", "30"))
                    if err.retry_after is not None:
                        wait = min(err.retry_after, cap)
                    else:
                        # Fase 2: exponencial con jitter en vez de lineal fijo
                        # (antes (attempt+1)*3 = 3s, 6s sin importar la señal
                        # real del servidor).
                        base = float(os.environ.get("VOICE_BACKOFF_BASE", "1.0")) * (2 ** attempt)
                        wait = min(base + random.uniform(0, base), cap)
                    print(f"⚠️ {err}. Reintentando en {wait:.1f}s (intento {attempt + 2}/3)...")
                    time.sleep(wait)
                    continue
                break
        if last_err is not None:
            print(f"⚠️ Error de transcripción con {self.api_base}: {last_err}")
        # Fallback: servidor Whisper local (Docker) en localhost:8000, si no era la URL principal
        raw_local = self.transcribe_offline_local(str(path))
        local_text, filtered = _clean_and_flag(raw_local)
        if local_text:
            print("💡 (Transcripción realizada con el servidor Whisper local de resguardo)")
            return local_text, _meta("local", True, True, filtered)
        return "", _meta("local", True, True, filtered)

    def _post_transcription(self, path: Path, prompt: str = "") -> str:
        """Un POST multipart al endpoint de transcripción. Lanza _TranscribeError."""
        endpoint = f"{self.api_base}/audio/transcriptions"
        boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"

        body = BytesIO()

        # Campo: model
        body.write(f"--{boundary}\r\n".encode("utf-8"))
        body.write(b'Content-Disposition: form-data; name="model"\r\n\r\n')
        body.write(f"{self.model}\r\n".encode("utf-8"))

        # Campo: language (por defecto 'es' para evitar alucinaciones en inglés)
        lang = os.environ.get("VOICE_LANGUAGE") or os.environ.get("VOICE_LANG") or "es"
        if lang:
            iso_lang = lang.split("-")[0].split("_")[0]
            body.write(f"--{boundary}\r\n".encode("utf-8"))
            body.write(b'Content-Disposition: form-data; name="language"\r\n\r\n')
            body.write(f"{iso_lang}\r\n".encode("utf-8"))

        # Campo: prompt opcional
        if prompt:
            body.write(f"--{boundary}\r\n".encode("utf-8"))
            body.write(b'Content-Disposition: form-data; name="prompt"\r\n\r\n')
            body.write(f"{prompt}\r\n".encode("utf-8"))

        # Campo: file
        mime_type = mimetypes.guess_type(path.name)[0] or "audio/mpeg"
        body.write(f"--{boundary}\r\n".encode("utf-8"))
        body.write(
            f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'.encode("utf-8")
        )
        body.write(f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"))

        with open(path, "rb") as f:
            body.write(f.read())
        body.write(b"\r\n")

        body.write(f"--{boundary}--\r\n".encode("utf-8"))
        payload = body.getvalue()

        timeout = int(os.environ.get("VOICE_TIMEOUT", "60"))
        reuse_conn = os.environ.get("VOICE_REUSE_CONNECTION", "0").lower() in ("1", "true", "yes")

        if reuse_conn:
            headers = {
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "Yunta/2.5.0 Client",
                "Connection": "keep-alive",
            }
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            resp_body = self._post_multipart_reuse(endpoint, payload, headers, timeout)
            data = json.loads(resp_body)
            text = data.get("text")
            if text is None and isinstance(data.get("result"), dict):
                text = data.get("result", {}).get("text")
            return (text or "").strip()

        req = urllib.request.Request(endpoint, data=payload, method="POST")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        req.add_header("User-Agent", "Yunta/2.5.0 Client")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text = data.get("text")
                if text is None and isinstance(data.get("result"), dict):
                    text = data.get("result", {}).get("text")
                return (text or "").strip()
        except urllib.error.HTTPError as err:
            try:
                detail = err.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                detail = ""
            # Fase 2: respetar Retry-After si el endpoint lo manda (solo
            # formato numérico en segundos — el formato HTTP-date queda
            # fuera de alcance por complejidad no justificada aquí).
            retry_after = None
            try:
                ra = err.headers.get("Retry-After") if err.headers else None
                if ra is not None:
                    retry_after = float(ra)
            except (TypeError, ValueError):
                retry_after = None
            raise _TranscribeError(
                f"HTTP {err.code}: {detail or err.reason}", err.code, detail, retry_after=retry_after
            ) from err
        except Exception as err:
            # Errores de red (timeout, DNS, conexión): reintentables
            raise _TranscribeError(f"{type(err).__name__}: {err}", None, "") from err

    def _get_http_connection(self, endpoint: str, timeout: float) -> http.client.HTTPConnection:
        """Obtiene o crea una conexion HTTP/HTTPS reutilizable por hilo para el endpoint dado."""
        parsed = urllib.parse.urlparse(endpoint)
        is_https = parsed.scheme == "https"
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if is_https else 80)

        conn = getattr(self._http_local, "conn", None)
        conn_target = getattr(self._http_local, "conn_target", None)

        if conn is None or conn_target != (is_https, host, port):
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
            if is_https:
                conn = http.client.HTTPSConnection(host, port, timeout=timeout)
            else:
                conn = http.client.HTTPConnection(host, port, timeout=timeout)
            self._http_local.conn = conn
            self._http_local.conn_target = (is_https, host, port)
        return conn

    def _post_multipart_reuse(
        self, endpoint: str, payload: bytes, headers: dict[str, str], timeout: float
    ) -> str:
        """Envia la peticion multipart reutilizando conexion HTTP persistente (Keep-Alive).

        Si la conexion fue cerrada remotamente por inactividad o error de socket,
        reconecta automaticamente una vez.
        """
        parsed = urllib.parse.urlparse(endpoint)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        for attempt in range(2):
            conn = self._get_http_connection(endpoint, timeout)
            try:
                conn.request("POST", path, body=payload, headers=headers)
                resp = conn.getresponse()
                status = resp.status
                resp_headers = resp.headers
                resp_body = resp.read().decode("utf-8", errors="replace")

                if 200 <= status < 300:
                    return resp_body

                retry_after = None
                try:
                    ra = resp_headers.get("Retry-After") if resp_headers else None
                    if ra is not None:
                        retry_after = float(ra)
                except (TypeError, ValueError):
                    retry_after = None

                detail = resp_body[:200]
                raise _TranscribeError(
                    f"HTTP {status}: {detail}",
                    status,
                    detail,
                    retry_after=retry_after,
                )
            except (
                http.client.CannotSendRequest,
                http.client.RemoteDisconnected,
                http.client.ResponseNotReady,
                BrokenPipeError,
                ConnectionResetError,
            ) as conn_err:
                try:
                    conn.close()
                except Exception:
                    pass
                self._http_local.conn = None
                if attempt == 1:
                    raise _TranscribeError(
                        f"Conexion cerrada tras reintento Keep-Alive: {conn_err}", None, ""
                    ) from conn_err
            except _TranscribeError:
                raise
            except Exception as err:
                try:
                    conn.close()
                except Exception:
                    pass
                self._http_local.conn = None
                raise _TranscribeError(f"{type(err).__name__}: {err}", None, "") from err
        raise _TranscribeError("Fallo inesperado de conexion Keep-Alive", None, "")

    def close(self) -> None:
        """Cierra la conexion HTTP persistente si existe."""
        conn = getattr(self._http_local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            self._http_local.conn = None
            self._http_local.conn_target = None


    def transcribe_offline_local(self, file_path: str) -> str:
        """Transcribe audio localmente mediante contenedor Whisper Docker en localhost:8000 o speech_recognition."""
        path = Path(file_path)
        if not path.exists():
            return ""

        # 1. Intentar llamar al servidor local Whisper Docker en localhost:8000 si no era la URL principal
        if "localhost:8000" not in self.api_base:
            local_endpoint = "http://localhost:8000/v1/audio/transcriptions"
            try:
                mime_type = mimetypes.guess_type(path.name)[0] or "audio/mpeg"
                boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
                body = BytesIO()

                body.write(f"--{boundary}\r\n".encode("utf-8"))
                body.write(b'Content-Disposition: form-data; name="model"\r\n\r\n')
                body.write(f"{self.model}\r\n".encode("utf-8"))

                body.write(f"--{boundary}\r\n".encode("utf-8"))
                body.write(
                    f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'.encode("utf-8")
                )
                body.write(f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"))

                with open(path, "rb") as f:
                    body.write(f.read())
                body.write(b"\r\n")

                body.write(f"--{boundary}--\r\n".encode("utf-8"))
                payload = body.getvalue()

                req = urllib.request.Request(local_endpoint, data=payload, method="POST")
                req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
                req.add_header("User-Agent", "Yunta/2.5.0 Client")

                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    text = data.get("text", "").strip()
                    if text:
                        return text
            except Exception:
                pass

        # 2. Respaldo local offline vía `faster_whisper` (modelo cacheado a nivel
        # de módulo, ver `_get_local_whisper_model` — antes se recargaba en cada
        # llamada, ~3.9s de overhead por fragmento)
        try:
            model_size = os.environ.get("LOCAL_WHISPER_MODEL", "tiny")
            model = _get_local_whisper_model(model_size)
            segments, _ = model.transcribe(str(path), language="es")
            text = " ".join(s.text.strip() for s in segments if s.text.strip()).strip()
            if text:
                return text
        except Exception:
            pass

        return ""


_MP3_BITRATES = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]


def _estimate_bitrate_bps(file_path: str) -> int:
    """Estima el bitrate (bps) de un MP3 leyendo el primer frame válido. 0 si no se puede.

    Función a nivel de módulo (no método de `AudioChunker`) a propósito: se
    llama desde `AudioTranscriber.transcribe_with_meta` antes de instanciar
    `AudioChunker`, y varios tests mockean la clase `AudioChunker` completa
    (`monkeypatch.setattr("yunta.voice.AudioChunker", ...)`) — llamarla como
    `AudioChunker._estimate_bitrate_bps(...)` desde ahí resolvería el mock en
    vez de la lógica real.
    """
    if Path(file_path).suffix.lower() != ".mp3":
        return 0
    try:
        data = Path(file_path).read_bytes()[:8192]
        for i in range(len(data) - 4):
            b = data[i:i + 4]
            if b[0] == 0xFF and (b[1] & 0xE0) == 0xE0:  # sync MP3 frame
                bitrate = _MP3_BITRATES[(b[2] >> 4) & 0x0F] * 1000
                if bitrate:
                    return bitrate
    except Exception:
        pass
    return 0


def _calibrate_chunk_minutes(
    file_path: str, max_bytes: int, safety: float = 0.75, floor: float = 0.33, ceiling: float = 0.42
) -> float:
    """Calcula minutos por fragmento usando el bitrate real del audio en vez
    de asumir siempre el peor caso (Fase 4, 2026-09-20).

    Motivado por una transcripción real de 81 min contra Cloudflare Workers
    AI: 480 errores 503/1102 manejados para solo 259 fragmentos de 20s fijos,
    pese a que el bitrate real del audio permitía fragmentos algo mayores
    bajo el mismo límite de payload (500 KB). `ceiling` es deliberadamente
    conservador (30s por defecto) porque el límite real de Workers AI es
    CPU-por-invocación, no solo tamaño de payload — no se busca maximizar
    el tamaño de fragmento, solo evitar fragmentar más fino de lo necesario.
    Si no se puede leer el bitrate ni por sniffing de frame MP3 ni por
    `ffprobe` (formato desconocido, archivo dañado, `ffprobe` ausente), cae
    al `floor` — comportamiento idéntico al valor fijo previo, sin regresión.

    V7-1 (2026-09-22): `_estimate_bitrate_bps` solo lee bitrate de frames
    MP3 — para cualquier otro contenedor (`.m4a`, `.ogg`, `.wav`) siempre
    daba 0 y esta función jamás calibraba nada, cayendo siempre al `floor`.
    Se agrega `_ffprobe_bitrate_bps` como segundo intento (cualquier
    formato que `ffprobe` entienda) antes de rendirse al `floor`.

    V7-8 (2026-09-24): `safety` 0.85→0.75 y `ceiling` 0.5→0.42, medido
    sobre la corrida real de 81 min. El corte por silencio de V6-5 mueve
    cada límite hasta ±30% del tamaño de fragmento, y como mueve AMBOS
    extremos, un fragmento puede estirarse hasta `chunk + 2×tolerancia` —
    muy por encima de lo que sugiere el `ceiling`. Con los valores viejos
    (objetivo 26.7s) aparecieron fragmentos de hasta 35.7s = ~583 KB, por
    encima del límite de 500 KB, que la rama de archivo sobredimensionado
    re-fragmentaba en silencio (12-14 casos en la corrida real).
    Verificado con el archivo real (130,564 bps → límite duro de 31.37s
    por fragmento): con 0.85/0.5 quedaban **12 fragmentos por encima del
    límite**; con 0.75/0.42 el máximo baja a 30.9s y quedan **cero**.
    """
    bitrate = _estimate_bitrate_bps(file_path) or _ffprobe_bitrate_bps(file_path)
    if not bitrate:
        return floor
    bytes_per_sec = bitrate / 8
    minutes = (max_bytes * safety) / bytes_per_sec / 60
    return max(floor, min(ceiling, minutes))


# V6-3 (docs/PLAN.md): checkpoint incremental de transcripción. Si el proceso
# muere a mitad de una cátedra larga, relanzar el mismo archivo reanuda desde
# el último fragmento en vez de empezar de cero. El `total` de fragmentos va
# en el nombre del archivo a propósito: si `chunk_minutes` cambia entre
# corridas, el conteo de fragmentos cambia y los checkpoints viejos
# simplemente no matchean (fallback seguro a transcripción completa, sin
# desalinear fragmentos de una fragmentación distinta).
def _checkpoint_dir() -> Path:
    d = Path(".yunta") / "scratch"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _checkpoint_path(file_path: str, total: int, idx: int) -> Path:
    stem = re.sub(r"[^\w.-]", "_", Path(file_path).stem)
    return _checkpoint_dir() / f"transcript_{stem}.n{total}.part{idx}.txt"


def _load_checkpoint(file_path: str, total: int) -> list[str | None]:
    entries: list[str | None] = [None] * total
    for idx in range(total):
        p = _checkpoint_path(file_path, total, idx)
        if p.exists():
            try:
                entries[idx] = p.read_text(encoding="utf-8")
            except OSError:
                pass
    return entries


def _save_checkpoint_fragment(file_path: str, total: int, idx: int, entry: str) -> None:
    try:
        _checkpoint_path(file_path, total, idx).write_text(entry, encoding="utf-8")
    except OSError:
        pass


def _clear_checkpoint(file_path: str, total: int) -> None:
    for idx in range(total):
        try:
            _checkpoint_path(file_path, total, idx).unlink()
        except OSError:
            pass


# V6-1 (docs/PLAN.md): marcas de tiempo reales por chunk vía ffprobe, en vez de
# asumir `índice × chunk_minutes` o repartir proporcionalmente por bytes — con
# `-c copy` los fragmentos varían de duración (el último casi siempre es más
# corto) y esas aproximaciones se desincronizan de forma acumulativa a medida
# que avanza el audio.
_ffprobe_available = None


def _ffprobe_duration_secs(file_path: str) -> float:
    """Duración real de un archivo de audio/video vía `ffprobe`. 0.0 si
    `ffprobe` no está en PATH o falla — el caller cae a la heurística
    anterior (bitrate/proporción de bytes), sin regresión."""
    global _ffprobe_available
    if _ffprobe_available is False:
        return 0.0
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", file_path],
            capture_output=True, text=True, timeout=10,
        )
        _ffprobe_available = True
        return float(out.stdout.strip())
    except Exception:
        if _ffprobe_available is None:
            _ffprobe_available = False
        return 0.0


def _ffprobe_bitrate_bps(file_path: str) -> int:
    """Bitrate real (bps) vía `ffprobe`, para cuando `_estimate_bitrate_bps`
    (sniffing de frame MP3, solo `.mp3`) da 0 — p.ej. `.m4a`, `.ogg`, `.wav`
    (V7-1, 2026-09-22: la calibración de chunk por bitrate real nunca tuvo
    efecto en las 3 corridas empíricas de esta sesión porque el archivo de
    prueba era `.m4a`). 0 si `ffprobe` no está disponible o falla — el
    caller cae al `floor` de `_calibrate_chunk_minutes`, sin regresión.
    Comparte el flag `_ffprobe_available` con `_ffprobe_duration_secs`."""
    global _ffprobe_available
    if _ffprobe_available is False:
        return 0
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=bit_rate",
             "-of", "default=noprint_wrappers=1:nokey=1", file_path],
            capture_output=True, text=True, timeout=10,
        )
        _ffprobe_available = True
        return int(float(out.stdout.strip()))
    except Exception:
        if _ffprobe_available is None:
            _ffprobe_available = False
        return 0


# V6-5 (docs/PLAN.md): cortar cada fragmento en la pausa de silencio más
# cercana al límite de `chunk_minutes`, en vez de un corte a tiempo fijo que
# puede partir una palabra a la mitad (técnica estándar en WhisperX/faster-whisper).
def _detect_silence_intervals(file_path: str, noise_db: int = -30, min_silence_secs: float = 0.5) -> list[tuple[float, float]]:
    """Detecta intervalos de silencio con `ffmpeg -af silencedetect`. Devuelve
    una lista de `(inicio, fin)` en segundos; lista vacía si `ffmpeg` no está
    disponible, la detección falla o no hay silencios — el caller cae al
    corte a tiempo fijo anterior, sin regresión."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-i", file_path, "-af",
             f"silencedetect=noise={noise_db}dB:d={min_silence_secs}", "-f", "null", "-"],
            capture_output=True, text=True, timeout=300,
        )
    except Exception:
        return []
    intervals: list[tuple[float, float]] = []
    start = None
    for line in result.stderr.splitlines():
        m = re.search(r"silence_start:\s*([\d.]+)", line)
        if m:
            start = float(m.group(1))
            continue
        m = re.search(r"silence_end:\s*([\d.]+)", line)
        if m and start is not None:
            intervals.append((start, float(m.group(1))))
            start = None
    return intervals


def _silence_aware_cut_points(
    total_secs: float, segment_secs: float, silences: list[tuple[float, float]], tolerance: float
) -> list[float]:
    """Ajusta los cortes fijos (múltiplos de `segment_secs`) al punto medio
    del silencio más cercano dentro de `tolerance` segundos, para no partir
    palabras a la mitad. Si un corte no tiene silencio cerca, se mantiene el
    corte fijo original en vez de descartarlo. Lista vacía si no hay
    silencios detectados (el caller usa eso como señal para no ajustar nada)."""
    if not silences or total_secs <= 0 or segment_secs <= 0:
        return []
    cuts = []
    n = 1
    while n * segment_secs < total_secs:
        target = n * segment_secs
        best, best_dist = None, tolerance
        for s, e in silences:
            mid = (s + e) / 2
            dist = abs(mid - target)
            if dist <= best_dist:
                best, best_dist = mid, dist
        cuts.append(best if best is not None else target)
        n += 1
    return sorted(set(round(c, 3) for c in cuts))


class AudioChunker:
    """Fragmenta audios grandes (>25 MB / cátedras de varias horas) en bloques."""

    def __init__(self, transcriber: AudioTranscriber, chunk_minutes: float | int | None = None):
        self.transcriber = transcriber
        self.default_chunk_minutes = chunk_minutes
        # Circuit breaker (Fase 1, 2026-09-20): tras N fallos de nube
        # CONSECUTIVOS entre fragmentos, deja de intentar la nube por un
        # tramo de fragmentos en vez de que cada uno pelee su propia
        # batalla de reintentos contra un endpoint ya saturado.
        # VOICE_BREAKER_THRESHOLD=0 desactiva el breaker (comportamiento
        # idéntico al actual: siempre intenta la nube).
        self._cb_threshold = int(os.environ.get("VOICE_BREAKER_THRESHOLD", "3"))
        self._cb_cooldown = int(os.environ.get("VOICE_BREAKER_COOLDOWN", "5"))
        self._cb_fail_streak = 0
        self._cb_skip_remaining = 0
        self._cb_tripped_count = 0  # telemetría (Fase 3)
        # Telemetría (Fase 3, 2026-09-20): contadores agregados por
        # transcripción, grabados a .yunta/voice_health.jsonl al terminar
        # (ver yunta/voice_telemetry.py). errors_handled cuenta FRAGMENTOS
        # con al menos un error de nube manejado, no reintentos individuales.
        self._telem_cloud = 0
        self._telem_local = 0
        self._telem_errors = 0
        # V7-2 (2026-09-22): tiempo de espera de red (network_wait, dentro de
        # `_post_transcription`) separado del resto de `transcribe_with_meta`
        # (processing) por fragmento — convierte en dato medible la anomalía
        # sin explicar de la Corrida 2 (¿la demora es de red o de proceso
        # local?) en vez de solo un agregado ciego de tiempo total.
        self._telem_network_wait: list[float] = []
        self._telem_processing: list[float] = []
        # V7-6 (2026-09-22): cuántos fragmentos se descartaron enteros por
        # ser una frase de relleno conocida de Whisper (V6-4) — antes no
        # había forma de saber si ese filtro ayudó en una corrida real.
        self._telem_hallucinations_filtered = 0
        # Fase 5 (2026-09-20): protege las mutaciones de los contadores de
        # arriba cuando `VOICE_PARALLEL_WORKERS > 1` hace que varios workers
        # llamen a `_breaker_should_skip_cloud`/`_breaker_record` a la vez.
        # Sin costo real en el modo secuencial (default): un solo hilo nunca
        # contiende el lock.
        self._state_lock = threading.Lock()
        # V6-1 (corregido 2026-09-20): duraciones reales por chunk ya
        # calculadas por `split_audio_by_silence` a partir de UNA sola
        # medición de `ffprobe` sobre el archivo original + los puntos de
        # corte (silencio o fijos) — evita volver a medir cada fragmento por
        # separado. Antes se llamaba a `ffprobe` una vez POR FRAGMENTO
        # (259 llamadas medidas en ~36.5s de overhead puro para una cátedra
        # de 81 min), redescubriendo algo que ya se sabía de antemano.
        self._last_chunk_durations: list[float] | None = None

    def _breaker_should_skip_cloud(self) -> bool:
        with self._state_lock:
            if self._cb_skip_remaining > 0:
                self._cb_skip_remaining -= 1
                return True
            return False

    def _breaker_record(self, meta: dict) -> None:
        """Actualiza el estado del breaker según la metadata de un fragmento
        ya procesado (ver `AudioTranscriber.transcribe_with_meta`)."""
        with self._state_lock:
            if self._cb_threshold <= 0:
                return
            if meta.get("source") == "cloud":
                self._cb_fail_streak = 0
                return
            if meta.get("cloud_attempted") and meta.get("cloud_failed"):
                self._cb_fail_streak += 1
                if self._cb_fail_streak >= self._cb_threshold and self._cb_skip_remaining == 0:
                    self._cb_skip_remaining = self._cb_cooldown
                    self._cb_tripped_count += 1
                    print(
                        f"🔌 Circuit breaker: {self._cb_fail_streak} fallos de nube seguidos — "
                        f"saltando directo a transcripción local por {self._cb_cooldown} fragmento(s)."
                    )

    def _record_telemetry(self, meta: dict) -> None:
        with self._state_lock:
            if meta.get("source") == "cloud":
                self._telem_cloud += 1
            else:
                self._telem_local += 1
            if meta.get("cloud_attempted") and meta.get("cloud_failed"):
                self._telem_errors += 1
            network_wait = meta.get("network_wait_secs")
            total = meta.get("total_secs")
            if network_wait is not None and total is not None:
                self._telem_network_wait.append(network_wait)
                self._telem_processing.append(max(0.0, total - network_wait))
            if meta.get("hallucination_filtered"):
                self._telem_hallucinations_filtered += 1

    def transcribe_large_audio(self, file_path: str, chunk_minutes: float | int | None = None) -> str:
        """Divide el audio en fragmentos y concatena las transcripciones.

        - Continuidad: el final del fragmento anterior se pasa como 'prompt' de
          Whisper al siguiente, para mantener nombres propios y terminología.
          Con `VOICE_PARALLEL_WORKERS > 1` esta continuidad no se garantiza
          entre fragmentos concurrentes (ver `_transcribe_chunks_parallel`).
        - Ctrl+C: interrumpe la transcripción y devuelve lo transcrito hasta ese
          momento, marcado como parcial.
        """
        if chunk_minutes is None:
            chunk_minutes = self.default_chunk_minutes
        if chunk_minutes is None:
            env_cm = os.environ.get("VOICE_CHUNK_MINUTES")
            if env_cm:
                try:
                    chunk_minutes = float(env_cm)
                except ValueError:
                    chunk_minutes = 10.0
            else:
                chunk_minutes = 10.0

        start_time = time.monotonic()
        chunks = self.split_audio_by_silence(file_path, chunk_minutes)
        # Offset temporal acumulado por índice (no incremental durante el
        # loop) para que sea válido tanto en modo secuencial como paralelo,
        # donde los fragmentos no terminan necesariamente en orden.
        # V6-1: duración real por chunk — mucho más precisa que asumir bytes
        # proporcionales a duración (variable con VBR) o `índice ×
        # chunk_minutes` (el último chunk casi siempre es más corto).
        # Corregido 2026-09-20: usar primero `self._last_chunk_durations`
        # (ya calculado por `split_audio_by_silence` con UNA sola medición de
        # `ffprobe` sobre el archivo original) en vez de volver a medir cada
        # fragmento por separado — eliminaba 259 llamadas a `ffprobe`
        # redundantes (~36.5s de overhead medido) en una transcripción real
        # de 81 min. Solo se re-mide por fragmento si ese dato no está
        # disponible (p.ej. `split_audio_by_silence` fue reemplazado en un test).
        chunk_durations = self._last_chunk_durations
        if not chunk_durations or len(chunk_durations) != len(chunks):
            chunk_durations = [_ffprobe_duration_secs(c) for c in chunks]
        if chunk_durations and all(d > 0 for d in chunk_durations):
            total_secs = sum(chunk_durations)
            offsets = []
            acc = 0.0
            for d in chunk_durations:
                offsets.append(acc)
                acc += d
        else:
            total_size = sum(os.path.getsize(c) for c in chunks) or 1
            total_secs = self._estimate_duration_secs(file_path) or (len(chunks) * float(chunk_minutes) * 60)
            offsets = []
            acc = 0.0
            for c in chunks:
                offsets.append(acc)
                acc += (os.path.getsize(c) / total_size) * total_secs

        resume_entries = _load_checkpoint(file_path, len(chunks))
        if any(e is not None for e in resume_entries):
            n_resumed = sum(1 for e in resume_entries if e is not None)
            print(f"♻️ Reanudando: {n_resumed}/{len(chunks)} fragmentos ya transcritos en un intento anterior.")

        try:
            workers = max(1, int(os.environ.get("VOICE_PARALLEL_WORKERS", "1") or "1"))
        except ValueError:
            workers = 1
        if workers > 1 and len(chunks) > 1:
            transcripts, completed = self._transcribe_chunks_parallel(chunks, offsets, workers, file_path, resume_entries)
            workers_used = workers
        else:
            transcripts, completed = self._transcribe_chunks_sequential(chunks, offsets, file_path, resume_entries)
            workers_used = 1

        outcome = "completed" if completed == len(chunks) else "partial"
        if outcome == "completed":
            _clear_checkpoint(file_path, len(chunks))
        try:
            from .voice_telemetry import percentile, record_voice_snapshot
            record_voice_snapshot(
                total_fragments=len(chunks),
                cloud_fragments=self._telem_cloud,
                local_fragments=self._telem_local,
                errors_handled=self._telem_errors,
                network_wait_p50=percentile(self._telem_network_wait, 50),
                network_wait_p95=percentile(self._telem_network_wait, 95),
                network_wait_max=max(self._telem_network_wait, default=0.0),
                processing_p50=percentile(self._telem_processing, 50),
                processing_p95=percentile(self._telem_processing, 95),
                processing_max=max(self._telem_processing, default=0.0),
                workers_used=workers_used,
                hallucinations_filtered=self._telem_hallucinations_filtered,
                breaker_trips=self._cb_tripped_count,
                elapsed_secs=time.monotonic() - start_time,
                audio_duration_secs=total_secs,
                outcome=outcome,
            )
        except Exception:
            pass

        try:
            self.transcriber.close()
        except Exception:
            pass

        entries = [t for t in transcripts if t is not None]
        if not entries:
            return ""
        result = "\n\n".join(entries)
        if completed and completed < len(chunks):
            result += "\n\n[NOTA: transcripción parcial — el proceso fue detenido por el usuario antes de completar todos los fragmentos.]"
        return result

    def _transcribe_chunks_sequential(
        self, chunks: list[str], offsets: list[float], file_path: str, resume_entries: list[str | None]
    ) -> tuple[list[str | None], int]:
        """Camino por defecto (`VOICE_PARALLEL_WORKERS=1`): un fragmento a la
        vez, con continuidad de `tail` entre fragmentos consecutivos.
        `resume_entries[idx]` no-None significa que ese fragmento ya fue
        transcrito en un intento anterior (V6-3) — se reutiliza sin llamar
        de nuevo a la red."""
        total = len(chunks)
        transcripts: list[str | None] = list(resume_entries)
        tail = ""
        for e in resume_entries:
            if e is not None:
                tail = e.split("\n", 1)[-1][-200:] or tail
        completed = sum(1 for e in resume_entries if e is not None)
        try:
            for idx, chunk_file in enumerate(chunks):
                if resume_entries[idx] is not None:
                    try:
                        os.remove(chunk_file)
                    except OSError:
                        pass
                    continue
                print(f"🎙️ Transcribiendo fragmento {idx + 1}/{total} (Ctrl+C para detener)...")
                h, rem = int(offsets[idx] // 3600), int(offsets[idx] % 3600)
                timestamp = f"[{h:02d}:{rem // 60:02d}:{rem % 60:02d}]"

                skip_cloud = self._breaker_should_skip_cloud()
                text, meta = self.transcriber.transcribe_with_meta(chunk_file, prompt=tail, skip_cloud=skip_cloud)
                text = text.strip()
                self._breaker_record(meta)
                self._record_telemetry(meta)
                entry = f"{timestamp}\n{text}"
                transcripts[idx] = entry
                _save_checkpoint_fragment(file_path, total, idx, entry)
                # Whisper usa ~200 caracteres finales como guía de continuidad
                tail = text[-200:] if text else tail
                completed += 1

                try:
                    os.remove(chunk_file)
                except OSError:
                    pass
        except KeyboardInterrupt:
            print("\n⏹️ Transcripción interrumpida por el usuario. Conservando lo transcrito hasta ahora...")
            for idx in range(total):
                if transcripts[idx] is None:
                    try:
                        os.remove(chunks[idx])
                    except (OSError, IndexError):
                        pass
        return transcripts, completed

    def _transcribe_chunks_parallel(
        self,
        chunks: list[str],
        offsets: list[float],
        workers: int,
        file_path: str,
        resume_entries: list[str | None],
    ) -> tuple[list[str | None], int]:
        """Fase 5 (2026-09-20, opt-in vía `VOICE_PARALLEL_WORKERS > 1`).

        Reensambla por índice (no por orden de llegada) para no desordenar la
        transcripción. Limitación conocida y aceptada: al no haber orden
        garantizado entre workers, no se puede pasar el `tail` del fragmento
        anterior como prompt de continuidad (cada fragmento se transcribe con
        prompt vacío) — trade-off documentado, no un bug.
        `resume_entries[idx]` no-None (V6-3): fragmento ya transcrito en un
        intento anterior, se reutiliza sin someterlo al pool de workers.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        total = len(chunks)
        transcripts: list[str | None] = list(resume_entries)
        completed = 0
        pending = []
        for idx, c in enumerate(chunks):
            if resume_entries[idx] is not None:
                completed += 1
                try:
                    os.remove(c)
                except OSError:
                    pass
            else:
                pending.append(idx)

        def _run(idx: int, chunk_file: str) -> tuple[int, str, str]:
            h, rem = int(offsets[idx] // 3600), int(offsets[idx] % 3600)
            timestamp = f"[{h:02d}:{rem // 60:02d}:{rem % 60:02d}]"
            skip_cloud = self._breaker_should_skip_cloud()
            text, meta = self.transcriber.transcribe_with_meta(chunk_file, prompt="", skip_cloud=skip_cloud)
            text = text.strip()
            self._breaker_record(meta)
            self._record_telemetry(meta)
            return idx, f"{timestamp}\n{text}", chunk_file

        if not pending:
            return transcripts, completed

        print(f"🎙️ Transcribiendo {len(pending)}/{total} fragmentos con {workers} workers en paralelo (Ctrl+C para detener)...")
        executor = ThreadPoolExecutor(max_workers=workers)
        futures = {executor.submit(_run, idx, chunks[idx]): idx for idx in pending}
        try:
            for future in as_completed(futures):
                idx, entry, chunk_file = future.result()
                transcripts[idx] = entry
                _save_checkpoint_fragment(file_path, total, idx, entry)
                completed += 1
                try:
                    os.remove(chunk_file)
                except OSError:
                    pass
            executor.shutdown(wait=True)
        except KeyboardInterrupt:
            # Los fragmentos ya en vuelo (hasta `workers` de ellos) no se
            # pueden interrumpir a mitad de una llamada HTTP; se cancelan los
            # que aún no empezaron y se espera a que terminen los en curso.
            print("\n⏹️ Transcripción interrumpida por el usuario. Cancelando fragmentos pendientes...")
            executor.shutdown(wait=True, cancel_futures=True)
            for idx in pending:
                try:
                    os.remove(chunks[idx])
                except OSError:
                    pass
        return transcripts, completed

    def close(self) -> None:
        """Cierra conexiones persistentes del transcriptor asociado."""
        self.transcriber.close()

    @staticmethod
    def _estimate_bitrate_bps(file_path: str) -> int:
        """Estima el bitrate (bps) de un MP3 leyendo el primer frame válido. 0 si no se puede."""
        return _estimate_bitrate_bps(file_path)

    @staticmethod
    def _estimate_duration_secs(file_path: str) -> float:
        """Estima la duración de un MP3 asumiendo CBR (bitrate del primer frame). 0 si no se puede."""
        bitrate = _estimate_bitrate_bps(file_path)
        if not bitrate:
            return 0.0
        return (os.path.getsize(file_path) * 8) / bitrate

    @staticmethod
    def _calibrate_chunk_minutes(
        file_path: str, max_bytes: int, safety: float = 0.75, floor: float = 0.33, ceiling: float = 0.42
    ) -> float:
        """Calcula minutos por fragmento usando el bitrate real del audio en vez
        de asumir siempre el peor caso (Fase 4, 2026-09-20). Ver `_calibrate_chunk_minutes`
        a nivel de módulo para la lógica completa."""
        return _calibrate_chunk_minutes(file_path, max_bytes, safety=safety, floor=floor, ceiling=ceiling)

    def split_audio_by_silence(self, file_path: str, chunk_minutes: float | int = 10, chunk_bytes: int = 1024 * 1024) -> list[str]:
        """Divide el archivo de audio usando ffmpeg si está disponible.

        Sin ffmpeg: para MP3 se permite el corte por bytes (~1 MB por fragmento)
        porque sus frames son autocontenidos y decodifican desde casi cualquier
        offset; para otros formatos se falla con mensaje claro.
        """
        # Fix chaos-testing 2026-09-19: un archivo de 0 bytes hacía fallar el
        # intento con ffmpeg Y el fallback por bytes (read() de un archivo
        # vacío no genera chunks), cayendo en el RuntimeError genérico de
        # "ffmpeg no está disponible" aunque ffmpeg sí esté instalado — el
        # problema real es que no hay nada que fragmentar.
        if os.path.getsize(file_path) == 0:
            raise RuntimeError(f"el archivo de audio '{file_path}' está vacío (0 bytes) — no hay nada que transcribir.")

        self._last_chunk_durations = None
        temp_dir = tempfile.mkdtemp(prefix="yunta_audio_")
        chunk_files = []

        # Intentar división con ffmpeg si está en PATH
        try:
            ext = Path(file_path).suffix.lower() or ".mp3"
            out_pattern = os.path.join(temp_dir, f"chunk_%03d{ext}")
            segment_secs = max(5, int(float(chunk_minutes) * 60))

            # V6-5: cortar en la pausa de silencio más cercana a cada límite
            # en vez de un tiempo fijo, si se puede medir la duración real y
            # detectar silencios. Tolerancia del 30% del tamaño de fragmento.
            cut_points: list[float] = []
            total_secs = _ffprobe_duration_secs(file_path)
            if total_secs > 0:
                silences = _detect_silence_intervals(file_path)
                if silences:
                    cut_points = _silence_aware_cut_points(
                        total_secs, float(segment_secs), silences, tolerance=segment_secs * 0.3
                    )

            # Boundaries esperados de cada fragmento: o bien los cortes por
            # silencio de arriba, o bien múltiplos exactos de `segment_secs`
            # (así corta `-segment_time`, sample-accurate en audio con
            # `-c copy`, sin el redondeo por keyframe que sí afecta a video).
            # Corregido 2026-09-20: antes esto se recalculaba con UNA llamada
            # a `ffprobe` POR FRAGMENTO ya generado (259 llamadas, ~36.5s de
            # overhead medido) para redescubrir algo que ya se sabe acá con
            # la ÚNICA medición de `total_secs` de arriba.
            expected_boundaries: list[float] = []
            if total_secs > 0:
                if cut_points:
                    expected_boundaries = cut_points + [total_secs]
                else:
                    b = float(segment_secs)
                    while b < total_secs:
                        expected_boundaries.append(b)
                        b += segment_secs
                    expected_boundaries.append(total_secs)

            cmd = ["ffmpeg", "-i", file_path, "-f", "segment"]
            if cut_points:
                cmd += ["-segment_times", ",".join(f"{c:.3f}" for c in cut_points)]
            else:
                cmd += ["-segment_time", str(segment_secs)]
            cmd += ["-c", "copy", out_pattern]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            files = sorted(os.listdir(temp_dir))
            for f in files:
                chunk_files.append(os.path.join(temp_dir, f))
            if chunk_files:
                if expected_boundaries and len(expected_boundaries) == len(chunk_files):
                    prev = 0.0
                    self._last_chunk_durations = []
                    for b in expected_boundaries:
                        self._last_chunk_durations.append(b - prev)
                        prev = b
                return chunk_files
        except Exception:
            pass

        # Fallback por bytes: solo válido para MP3 (frames autocontenidos).
        # Si el archivo ya cabe en un fragmento, dividirlo en 2 mitades de todos
        # modos: garantiza progreso si el endpoint rechaza el tamaño actual.
        if Path(file_path).suffix.lower() == ".mp3":
            size = os.path.getsize(file_path)
            effective = min(chunk_bytes, max(1, size // 2))
            with open(file_path, "rb") as src:
                part = 0
                while True:
                    data = src.read(effective)
                    if not data:
                        break
                    part_file = os.path.join(temp_dir, f"chunk_{part:03d}.mp3")
                    with open(part_file, "wb") as dst:
                        dst.write(data)
                    chunk_files.append(part_file)
                    part += 1
            if chunk_files:
                return chunk_files

        raise RuntimeError(
            f"ffmpeg no está disponible y es necesario para fragmentar '{file_path}' "
            "(formato no MP3 o audio de varias horas). Instálalo: https://ffmpeg.org/download.html"
        )


def record_microphone(duration: int | None = None, output_path: str = None) -> str:
    """Graba audio del micrófono local.
    Si duration es None, graba en vivo indefinidamente hasta que el usuario presione ENTER.
    """
    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".wav", prefix="yunta_mic_")
        os.close(fd)

    # 1. Fallback Nativo en Windows usando ctypes / winmm.dll (0 dependencias pip)
    if sys.platform == "win32":
        try:
            import ctypes
            import time

            winmm = ctypes.windll.winmm
            winmm.mciSendStringW("open new type waveaudio alias yunta_wave", None, 0, 0)
            winmm.mciSendStringW("record yunta_wave", None, 0, 0)

            if duration is None:
                print("🎙️ Grabando micrófono en vivo... Presiona [ENTER] en la terminal cuando termines de hablar.")
                input()
            else:
                time.sleep(duration)

            winmm.mciSendStringW(f'save yunta_wave "{output_path}"', None, 0, 0)
            winmm.mciSendStringW("close yunta_wave", None, 0, 0)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return trim_initial_noise_and_silence(output_path)
        except Exception:
            pass

    # 2. Intentar usar sounddevice / scipy si está disponible
    try:
        import sounddevice as sd
        import numpy as np
        import scipy.io.wavfile as wav

        fs = 16000  # 16kHz adecuado para Whisper/Speech
        if duration is not None:
            recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='int16')
            sd.wait()
            wav.write(output_path, fs, recording)
            return output_path
        else:
            print("🎙️ Grabando micrófono en vivo... Presiona [ENTER] en la terminal cuando termines de hablar.")
            recordings = []
            def callback(indata, frames, time, status):
                recordings.append(indata.copy())

            with sd.InputStream(samplerate=fs, channels=1, dtype='int16', callback=callback):
                input()

            if recordings:
                full_rec = np.concatenate(recordings, axis=0)
                wav.write(output_path, fs, full_rec)
                return output_path
    except Exception:
        pass

    # Fallback si no se pudo grabar
    raise NotImplementedError(
        "No se detectó un micrófono activo o librerías de audio. "
        "Puedes instalar el soporte completo de voz ejecutando: `pip install yunta-harness[voice]`"
    )


# ============================ Escucha continua (V5-1) ============================

# Comandos REPL resolubles por voz sin consultar al LLM (0 tokens).
# Ampliable por el usuario en .yunta/voice_keywords.json sin tocar código.
DEFAULT_VOICE_KEYWORDS: dict[str, str] = {
    "salir": "/exit",
    "terminar": "/exit",
    "terminar sesion": "/exit",
    "cerrar": "/exit",
    "cerrar sesion": "/exit",
    "adios": "/exit",
    "chao": "/exit",
    "exit": "/exit",
    "quit": "/exit",
    "para": "/stop",
    "parar": "/stop",
    "stop": "/stop",
    "detener": "/stop",
    "cancela": "/stop",
    "cancelar": "/stop",
    "basta": "/stop",
    "limpiar": "/clear",
    "borrar conversacion": "/clear",
    "metricas": "/metrics",
    "consumo": "/tokens",
    "presupuesto": "/roi",
    "rentabilidad": "/roi",
    "permisos": "/permissions",
    "reanudar": "/resume",
    "hablar": "/speak on",
    "activar voz": "/speak on",
    "silencio": "/speak off",
    "desactivar voz": "/speak off",
    "callate": "/speak off",
    "cállate": "/speak off",
    "inicializar": "/init",
    "iniciar proyecto": "/init",
    "crear proyecto": "/init",
}

# Intenciones paramétricas por prefijo hablado: mapean a comandos con argumentos (0 consultas LLM)
DEFAULT_PREFIX_VOICE_KEYWORDS: dict[str, str] = {
    "inicializa": "/init",
    "inicializar": "/init",
    "inicia proyecto": "/init",
    "iniciar proyecto": "/init",
    "crea proyecto": "/init",
    "crear proyecto": "/init",
}


def load_voice_keywords() -> dict[str, str]:
    """Carga las palabras clave por defecto + las del usuario (.yunta/voice_keywords.json).

    El archivo es un JSON plano {"frase hablada": "comando REPL"}: las palabras
    clave del usuario persisten entre sesiones y ahorran consultas al LLM."""
    keywords = dict(DEFAULT_VOICE_KEYWORDS)
    path = Path(".yunta") / "voice_keywords.json"
    try:
        if path.exists():
            custom = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(custom, dict):
                keywords.update({k.lower().strip(): v for k, v in custom.items()})
    except Exception:
        pass
    return keywords


def route_keyword(text: str, keywords: dict[str, str] | None = None) -> str | None:
    """Si la frase hablada es una palabra clave conocida, retorna el comando REPL
    equivalente (0 consultas LLM). None si debe ir al modelo."""
    if not text:
        return None
    if keywords is None:
        keywords = load_voice_keywords()
    cleaned = _clean_response_text(text)
    if not cleaned:
        return None
    if cleaned in keywords:
        return keywords[cleaned]
    # Intenciones paramétricas con prefijo (ej: "inicializa mi idea" → "/init mi idea")
    for prefix, cmd in DEFAULT_PREFIX_VOICE_KEYWORDS.items():
        if cleaned == prefix:
            return cmd
        if cleaned.startswith(prefix + " "):
            # Fix chaos-testing 2026-09-19: antes se usaba text.split(maxsplit=
            # prefix_words) sobre el texto CRUDO, contando por posición de
            # palabra. Si el texto tenía un emoji u otro token que _clean_
            # response_text elimina POR COMPLETO (no solo despuntúa), el
            # conteo de palabras entre `cleaned` y `text` se desalineaba y
            # el prefijo terminaba duplicado dentro del argumento (ej. "🚀
            # inicializa X" -> "/init inicializa X" en vez de "/init X").
            # Ahora se consumen palabras crudas una a una, limpiándolas
            # individualmente, hasta reconstruir exactamente `prefix` —
            # preservando mayúsculas/puntuación del resto como argumento.
            raw_words = text.strip().split()
            consumed = 0
            acc_clean = ""
            for w in raw_words:
                consumed += 1
                cw = _clean_response_text(w)
                if cw:
                    acc_clean = (acc_clean + " " + cw).strip()
                if acc_clean == prefix:
                    break
            arg = " ".join(raw_words[consumed:]).strip()
            return f"{cmd} {arg}" if arg else cmd
    # Fuzzy de una sola palabra ("métricas" → "metricas" ya lo maneja el clean;
    # toleramos errores de Whisper también aquí)
    if " " not in cleaned:
        for kw, cmd in keywords.items():
            if " " not in kw and _fuzzy_in(cleaned, {kw}):
                return cmd
    return None


def make_voice_approval(agent, listener):
    """Construye el callback de aprobación de tools por voz para un Agent
    (REPL interactivo, single-shot nacido de voz o sub-agentes de --chunks).
    Reactiva el micrófono (pausado durante la generación), espera
    'sí'/'siempre'/'no' y vuelve a pausarlo; sin respuesta en 180s rechaza."""

    def _voice_approval(name: str, detail: str = "") -> bool:
        if detail:
            print(detail)
        print(f'🗣️ Di "sí", "siempre" o "no" para {name}...')
        listener.resume()
        try:
            while True:
                text = listener.get(timeout=180)
                if text is None:
                    print("⚠️ Sin respuesta de voz: se rechaza por seguridad.")
                    return False
                print(f'🗣️ "{text}"')
                ans = normalize_voice_response(text)
                if ans == "siempre":
                    # Fix chaos-testing 2026-09-19: agent.session_permissions
                    # es None con cualquier objeto que no pase por el
                    # constructor real de Agent (que siempre lo inicializa a
                    # SessionPermissions()) -- degrada con gracia en vez de
                    # AttributeError: la aprobación de este turno igual se
                    # concede, solo no queda persistida para el siguiente.
                    sp = getattr(agent, "session_permissions", None)
                    if sp is not None:
                        sp.grant_tool(name)
                    return True
                if ans == "s":
                    return True
                if ans == "c":
                    return False
                if ans == "e":
                    print("✏️ Edición no soportada por voz en aprobaciones: se rechaza.")
                    return False
                print('(no entendido — di "sí", "siempre" o "no")')
        finally:
            listener.pause()

    return _voice_approval


class VoiceListener:
    """Escucha continua del micrófono con VAD por umbral RMS calibrado (V5-1).

    Hilo daemon: detecta el inicio de voz, acumula el audio hasta 1.5s de
    silencio y deposita la transcripción de cada frase en una cola. Requiere
    `sounddevice` (opcional). `pause()` evita el eco mientras el agente genera
    o el TTS habla.
    """

    SAMPLE_RATE = 16000
    BLOCK_MS = 480  # ~30 muestras de Whisper por bloque, baja latencia

    def __init__(self, transcriber: AudioTranscriber | None = None, silence_ms: int = 1500):
        self.transcriber = transcriber or AudioTranscriber()
        self.silence_ms = silence_ms
        self.threshold = int(os.environ.get("YUNTA_VAD_THRESHOLD", "0")) or None
        self._queue: "queue.Queue[str]" = __import__("queue").Queue()
        self._blocks: "queue.Queue[bytes]" = __import__("queue").Queue()
        self._paused = __import__("threading").Event()
        self._stopped = __import__("threading").Event()
        self._thread = None
        self._stream = None

    # --- ciclo de vida ---
    def start(self) -> None:
        if self._thread is not None:
            return
        try:
            import sounddevice  # dependencia opcional
        except ImportError as err:
            raise NotImplementedError(
                "La escucha continua requiere `sounddevice` (pip install sounddevice)."
            ) from err
        self._calibrate()
        import threading

        self._thread = threading.Thread(target=self._loop, daemon=True, name="yunta-mic")
        self._thread.start()

    def stop(self) -> None:
        self._stopped.set()
        self._paused.clear()
        if self._stream is not None:
            try:
                self._stream.close()
            except Exception:
                pass

    def pause(self) -> None:
        """Silencia el micrófono (eco del TTS o generación del agente)."""
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    # --- consumo de frases ---
    def get(self, timeout: float | None = None) -> str | None:
        try:
            return self._queue.get(timeout=timeout)
        except Exception:
            return None

    # --- internos ---
    def _calibrate(self) -> None:
        """Mide 1s de ruido ambiental y fija el umbral de voz de forma sensible."""
        env_threshold = os.environ.get("YUNTA_VAD_THRESHOLD")
        if env_threshold:
            try:
                self.threshold = int(env_threshold)
                return
            except ValueError:
                pass
        if self.threshold is not None:
            return
        import numpy as np
        import sounddevice as sd

        blocks = []
        frames = int(self.SAMPLE_RATE * 1.0)

        def cb(indata, nframes, time_info, status):
            blocks.append(indata.copy())

        try:
            with sd.InputStream(samplerate=self.SAMPLE_RATE, channels=1, dtype="int16",
                                blocksize=int(self.SAMPLE_RATE * self.BLOCK_MS / 1000), callback=cb):
                import time

                t0 = time.monotonic()
                while sum(len(b) for b in blocks) < frames and time.monotonic() - t0 < 2.0:
                    time.sleep(0.05)
        except Exception:
            pass

        if not blocks:
            self.threshold = 120
            return
        ambient = np.concatenate(blocks)
        ambient_rms = int(np.sqrt(np.mean(ambient.astype(float) ** 2)))
        # Umbral dinámico y sensible: 1.8x el ruido ambiente con piso bajo (90) y techo (450)
        self.threshold = min(max(int(ambient_rms * 1.8), 90), 450)

    def _loop(self) -> None:
        import numpy as np
        import sounddevice as sd

        def cb(indata, nframes, time_info, status):
            if not self._stopped.is_set():
                self._blocks.put(indata.tobytes())

        utterance = bytearray()
        silence_ms_acc = 0
        block_samples = int(self.SAMPLE_RATE * self.BLOCK_MS / 1000)
        vad_debug = bool(os.environ.get("YUNTA_VAD_DEBUG"))
        dbg_count = 0

        try:
            self._stream = sd.InputStream(samplerate=self.SAMPLE_RATE, channels=1,
                                          dtype="int16", blocksize=block_samples, callback=cb)
            self._stream.start()
            import time

            while not self._stopped.is_set():
                try:
                    raw = self._blocks.get(timeout=0.2)
                except Exception:
                    continue
                if self._paused.is_set():
                    utterance.clear()
                    silence_ms_acc = 0
                    continue
                samples = np.frombuffer(raw, dtype="<i2")
                rms = int(np.sqrt(np.mean(samples.astype(float) ** 2)))
                if vad_debug:
                    dbg_count += 1
                    if dbg_count % 4 == 0:  # ~ cada 2s
                        print(f"\r[VAD] rms={rms} umbral={self.threshold} {'🔴 VOZ' if rms >= self.threshold else '🟢 silencio'}   ", flush=True)
                if rms >= self.threshold:
                    if not utterance:
                        print("\n🔴 escuchando... (habla; cierra con 1.5s de silencio)", flush=True)
                    utterance.extend(raw)
                    silence_ms_acc = 0
                elif utterance:
                    silence_ms_acc += self.BLOCK_MS
                    if silence_ms_acc >= self.silence_ms:
                        print("\r🟠 frase cerrada, transcribiendo...          ", flush=True)
                        self._finish_utterance(bytes(utterance))
                        utterance.clear()
                        silence_ms_acc = 0
                    else:
                        # conservar el silencio final natural de la frase
                        utterance.extend(raw)
        except Exception as err:
            if not self._stopped.is_set():
                print(f"\n⚠️ Escucha continua detenida: {err}")
        finally:
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass

    def _finish_utterance(self, audio: bytes) -> None:
        if len(audio) < self.SAMPLE_RATE * 2 * 0.3:  # < 0.3s: ruido espurio
            print("\r🟢 en espera de tu voz...                       ", flush=True)
            return
        import tempfile
        import wave

        try:
            fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="yunta_vad_")
            os.close(fd)
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.SAMPLE_RATE)
                wf.writeframes(audio)
            try:
                text = self.transcriber.transcribe(wav_path).strip()
            finally:
                try:
                    os.remove(wav_path)
                except OSError:
                    pass
            # Filtrar alucinaciones típicas de Whisper sobre silencio o ruido residual
            ignored = {"you", "you.", "thank you", "thank you.", "subtítulos por la comunidad de amara.org"}
            if text and text.lower().strip() not in ignored:
                self._queue.put(text)
            else:
                print("\r🟢 en espera de tu voz...                       ", flush=True)
        except Exception:
            print("\r🟢 en espera de tu voz...                       ", flush=True)
