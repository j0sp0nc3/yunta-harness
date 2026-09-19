"""Módulo de transcripción de voz a texto y procesamiento de cátedras extensas.

Soporta transcripción de voz vía HTTP multipart/form-data nativo hacia endpoints
compatibles con OpenAI Whisper (/v1/audio/transcriptions), fragmentación
inteligente de audios largos por silencios (VAD) y grabación desde micrófono.
"""

from io import BytesIO
import json
import mimetypes
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import re
import unicodedata
import uuid
import wave

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
    un preview + referencia, para no saturar el contexto del agente (V3-3)."""
    if len(text) <= threshold:
        return text
    from datetime import datetime

    scratch_dir = Path(".yunta") / "scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    scratch_file = scratch_dir / f"transcript_{ts}.txt"
    scratch_file.write_text(text, encoding="utf-8")
    preview = text[:preview_chars]
    return (
        f"{preview}\n\n[... transcript completo ({len(text)} caracteres, {len(text)//4} tokens aprox) "
        f"guardado en: {scratch_file} — usa read_file con offset/limit para leerlo por partes]"
    )


class _TranscribeError(Exception):
    """Error HTTP o de red al transcribir, con clasificación para retry/fragmentación."""

    def __init__(self, msg: str, code: int | None, detail: str):
        super().__init__(msg)
        self.code = code
        self.detail = detail.lower()
        self.too_large = "too large" in self.detail or "3006" in self.detail or self.code == 413
        self.retryable = (
            self.code is None
            or (self.code is not None and self.code >= 500)
            or self.code == 429
        )


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

    def transcribe(self, file_path: str, prompt: str = "") -> str:
        """Transcribe un archivo de audio (.mp3, .wav, .m4a, .ogg, .webm).

        - Reintenta hasta 3 veces ante errores transitorios (429/5xx) con backoff (V6-2).
        - Si el endpoint rechaza el payload por tamaño (3006/"too large"), reintenta
          automáticamente fragmentando el audio en partes menores (V6-2).
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Archivo de audio no encontrado: {file_path}")

        # Si el archivo supera los 25 MB (límite Whisper API), usar chunker
        if path.stat().st_size > 25 * 1024 * 1024:
            return AudioChunker(self).transcribe_large_audio(str(path))

        last_err = None
        for attempt in range(3):
            try:
                return self._post_transcription(path, prompt)
            except _TranscribeError as err:
                last_err = err
                if err.too_large:
                    # El endpoint rechaza el tamaño: fragmentar y reintentar.
                    # Guard: bajo ~256 KB ya no tiene sentido seguir dividiendo.
                    if path.stat().st_size <= 256 * 1024:
                        break
                    print(f"⚠️ Endpoint rechazó el audio por tamaño ({err}). Reintentando por fragmentos...")
                    return AudioChunker(self).transcribe_large_audio(str(path))
                if err.retryable and attempt < 2:
                    wait = (attempt + 1) * 3
                    print(f"⚠️ {err}. Reintentando en {wait}s (intento {attempt + 2}/3)...")
                    import time

                    time.sleep(wait)
                    continue
                break
        if last_err is not None:
            print(f"⚠️ Error de transcripción con {self.api_base}: {last_err}")
        # Fallback: servidor Whisper local (Docker) en localhost:8000, si no era la URL principal
        local_text = self.transcribe_offline_local(str(path))
        if local_text:
            print("💡 (Transcripción realizada con el servidor Whisper local de resguardo)")
            return local_text
        return ""

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

        req = urllib.request.Request(endpoint, data=payload, method="POST")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        req.add_header("User-Agent", "Yunta/2.5.0 Client")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("text", "")
        except urllib.error.HTTPError as err:
            try:
                detail = err.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                detail = ""
            raise _TranscribeError(f"HTTP {err.code}: {detail or err.reason}", err.code, detail) from err
        except Exception as err:
            # Errores de red (timeout, DNS, conexión): reintentables
            raise _TranscribeError(f"{type(err).__name__}: {err}", None, "") from err

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

        # 2. Respaldo local offline vía `faster_whisper` (Lazy Loading) si está instalado
        try:
            from faster_whisper import WhisperModel
            model_size = os.environ.get("LOCAL_WHISPER_MODEL", "tiny")
            model = WhisperModel(model_size, device="cpu", compute_type="int8")
            segments, _ = model.transcribe(str(path), language="es")
            text = " ".join(s.text.strip() for s in segments if s.text.strip()).strip()
            if text:
                return text
        except Exception:
            pass

        return ""


class AudioChunker:
    """Fragmenta audios grandes (>25 MB / cátedras de varias horas) en bloques."""

    def __init__(self, transcriber: AudioTranscriber):
        self.transcriber = transcriber

    def transcribe_large_audio(self, file_path: str) -> str:
        """Divide el audio en fragmentos de 10 minutos y concatena las transcripciones.

        - Continuidad: el final del fragmento anterior se pasa como 'prompt' de
          Whisper al siguiente, para mantener nombres propios y terminología.
        - Ctrl+C: interrumpe la transcripción y devuelve lo transcrito hasta ese
          momento, marcado como parcial.
        """
        chunks = self.split_audio_by_silence(file_path)
        transcripts = []
        tail = ""
        # Offset temporal acumulado: proporcional a bytes (corte binario) o minutos (ffmpeg)
        total_size = sum(os.path.getsize(c) for c in chunks) or 1
        total_secs = self._estimate_duration_secs(file_path) or (len(chunks) * 600)
        offset_secs = 0.0

        try:
            for idx, chunk_file in enumerate(chunks):
                print(f"🎙️ Transcribiendo fragmento {idx + 1}/{len(chunks)} (Ctrl+C para detener)...")
                h, rem = int(offset_secs // 3600), int(offset_secs % 3600)
                timestamp = f"[{h:02d}:{rem // 60:02d}:{rem % 60:02d}]"

                text = self.transcriber.transcribe(chunk_file, prompt=tail).strip()
                transcripts.append(f"{timestamp}\n{text}")
                # Whisper usa ~200 caracteres finales como guía de continuidad
                tail = text[-200:] if text else tail
                offset_secs += (os.path.getsize(chunk_file) / total_size) * total_secs

                # Limpiar archivo temporal de fragmento
                try:
                    os.remove(chunk_file)
                except OSError:
                    pass
        except KeyboardInterrupt:
            print("\n⏹️ Transcripción interrumpida por el usuario. Conservando lo transcrito hasta ahora...")
            for chunk_file in chunks[idx:]:
                try:
                    os.remove(chunk_file)
                except (OSError, NameError):
                    pass

        if not transcripts:
            return ""
        result = "\n\n".join(transcripts)
        if tail and len(transcripts) < len(chunks):
            result += "\n\n[NOTA: transcripción parcial — el proceso fue detenido por el usuario antes de completar todos los fragmentos.]"
        return result

    @staticmethod
    def _estimate_duration_secs(file_path: str) -> float:
        """Estima la duración de un MP3 asumiendo CBR (bitrate del primer frame). 0 si no se puede."""
        if Path(file_path).suffix.lower() != ".mp3":
            return 0.0
        _BITRATES = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
        try:
            data = Path(file_path).read_bytes()[:8192]
            for i in range(len(data) - 4):
                b = data[i:i + 4]
                if b[0] == 0xFF and (b[1] & 0xE0) == 0xE0:  # sync MP3 frame
                    bitrate = _BITRATES[(b[2] >> 4) & 0x0F] * 1000
                    if bitrate:
                        return (os.path.getsize(file_path) * 8) / bitrate
        except Exception:
            pass
        return 0.0

    def split_audio_by_silence(self, file_path: str, chunk_minutes: int = 10, chunk_bytes: int = 1024 * 1024) -> list[str]:
        """Divide el archivo de audio usando ffmpeg si está disponible.

        Sin ffmpeg: para MP3 se permite el corte por bytes (~1 MB por fragmento)
        porque sus frames son autocontenidos y decodifican desde casi cualquier
        offset; para otros formatos se falla con mensaje claro.
        """
        temp_dir = tempfile.mkdtemp(prefix="yunta_audio_")
        chunk_files = []

        # Intentar división con ffmpeg si está en PATH
        try:
            out_pattern = os.path.join(temp_dir, "chunk_%03d.mp3")
            cmd = [
                "ffmpeg", "-i", file_path, "-f", "segment",
                "-segment_time", str(chunk_minutes * 60), "-c", "copy", out_pattern
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            files = sorted(os.listdir(temp_dir))
            for f in files:
                chunk_files.append(os.path.join(temp_dir, f))
            if chunk_files:
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
    # Fuzzy de una sola palabra ("métricas" → "metricas" ya lo maneja el clean;
    # toleramos errores de Whisper también aquí)
    if " " not in cleaned:
        for kw, cmd in keywords.items():
            if " " not in kw and _fuzzy_in(cleaned, {kw}):
                return cmd
    return None


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
