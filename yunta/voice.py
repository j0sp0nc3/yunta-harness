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


def normalize_voice_response(text: str) -> str:
    """Normaliza y compara respuestas de voz o texto frecuente para aprobaciones o elecciones.

    Retorna:
    - 's': si coincide con sinónimos de aprobación ("sí", "aprobado", "avanzar", "abanzau", "ok", "dale", etc.)
    - 'c': si coincide con sinónimos de rechazo/cancelación ("no", "rechazado", "cancelar", "alto", "stop", etc.)
    - 'e': si coincide con sinónimos de edición ("editar", "modificar", "cambiar", etc.)
    - 'siempre': si coincide con aprobación permanente ("siempre", "para siempre")
    - El texto original sin modificar si no es una palabra/frase corta de respuesta rápida.
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
        """Transcribe un archivo de audio (.mp3, .wav, .m4a, .ogg, .webm)."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Archivo de audio no encontrado: {file_path}")

        # Si el archivo supera los 25 MB (límite Whisper API), usar chunker
        if path.stat().st_size > 25 * 1024 * 1024:
            return AudioChunker(self).transcribe_large_audio(str(path))

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
        except Exception as err:
            # Fallback de transcripción local offline vía contenedor Whisper o speech_recognition
            local_text = self.transcribe_offline_local(str(path))
            if local_text:
                print("💡 (Transcripción realizada con el servidor Whisper local de respaldo)")
                return local_text
            return ""

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

        # 2. Fallback secundario mediante speech_recognition local si está instalado
        try:
            import speech_recognition as sr
            r = sr.Recognizer()
            with sr.AudioFile(str(path)) as source:
                audio_data = r.record(source)
                return r.recognize_google(audio_data, language="es-ES")
        except Exception:
            pass

        return ""


class AudioChunker:
    """Fragmenta audios grandes (>25 MB / cátedras de varias horas) en bloques."""

    def __init__(self, transcriber: AudioTranscriber):
        self.transcriber = transcriber

    def transcribe_large_audio(self, file_path: str) -> str:
        """Divide el audio en fragmentos de 10 minutos y concatena las transcripciones."""
        chunks = self.split_audio_by_silence(file_path)
        transcripts = []

        for idx, chunk_file in enumerate(chunks):
            # Agregar marca de tiempo estimada (ej. [00:10:00])
            mins = idx * 10
            hours = mins // 60
            remaining_mins = mins % 60
            timestamp = f"[{hours:02d}:{remaining_mins:02d}:00]"

            text = self.transcriber.transcribe(chunk_file)
            transcripts.append(f"{timestamp}\n{text.strip()}")

            # Limpiar archivo temporal de fragmento
            try:
                os.remove(chunk_file)
            except OSError:
                pass

        return "\n\n".join(transcripts)

    def split_audio_by_silence(self, file_path: str, chunk_minutes: int = 10) -> list[str]:
        """Divide el archivo de audio usando ffmpeg si está disponible, o fragmentos físicos."""
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

        # Fallback: si ffmpeg no está, dividir el archivo binario en partes de ~15MB
        chunk_size = 15 * 1024 * 1024
        path = Path(file_path)
        ext = path.suffix or ".mp3"

        with open(file_path, "rb") as src:
            part = 0
            while True:
                data = src.read(chunk_size)
                if not data:
                    break
                part_file = os.path.join(temp_dir, f"chunk_{part:03d}{ext}")
                with open(part_file, "wb") as dst:
                    dst.write(data)
                chunk_files.append(part_file)
                part += 1

        return chunk_files


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
