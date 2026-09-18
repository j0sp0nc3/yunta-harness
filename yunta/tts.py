"""Módulo neutral de síntesis de voz (Text-to-Speech / TTS) para Yunta.

Implementa un pipeline de salida de audio de bajo costo ($0 USD) con estrategia de
resiliencia en 2 niveles:
1. Proveedor Primario: HTTP OpenAI-compatible endpoint (/v1/audio/speech)
   configurable vía TTS_API_BASE.
2. Proveedor Secundario / Fallback: Microsoft Edge TTS (edge-tts) con voces
   neuronales en español de alta fidelidad (ej. es-CL-CatalinaNeural).

Soporta troceo por oraciones (sentence chunking) para reducir la latencia de
reproducción a menos de 0.5 segundos.
"""

import asyncio
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request


def chunk_text_by_sentences(text: str, max_words: int = 25) -> list[str]:
    """Trocea un texto extenso en oraciones o bloques cortos para síntesis en streaming."""
    if not text:
        return []
    # Separar por signos de puntuación principales (. ! ? \n)
    raw_chunks = re.split(r'(?<=[.!?\n])\s+', text.strip())
    chunks = []
    for chunk in raw_chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        words = chunk.split()
        if len(words) <= max_words:
            chunks.append(chunk)
        else:
            # Sub-fragmentar por comas o pausas si la oración es muy larga
            sub_parts = re.split(r'(?<=[,;:])\s+', chunk)
            current = []
            for part in sub_parts:
                part_words = part.split()
                if len(current) + len(part_words) <= max_words:
                    current.extend(part_words)
                else:
                    if current:
                        chunks.append(" ".join(current))
                    current = part_words
            if current:
                chunks.append(" ".join(current))
    return chunks


class TTSProvider:
    """Proveedor agnóstico de síntesis de voz (TTS) con fallback transparente."""

    def __init__(
        self,
        model: str | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
        voice: str | None = None,
    ):
        import os
        self.model = model or os.environ.get("TTS_MODEL") or "@cf/meta/mms-tts-spa"
        base = api_base or os.environ.get("TTS_API_BASE") or os.environ.get("VOICE_API_BASE") or "http://localhost:8000/v1"
        self.api_base = base.rstrip("/")
        self.api_key = api_key or os.environ.get("TTS_API_KEY") or os.environ.get("VOICE_API_KEY") or os.environ.get("LLM_API_KEY") or ""
        self.voice = voice or os.environ.get("TTS_VOICE") or "es-CL-CatalinaNeural"

    def synthesize_http(self, text: str) -> bytes | None:
        """Intenta sintetizar audio llamando al endpoint HTTP /v1/audio/speech."""
        endpoint = f"{self.api_base}/audio/speech"
        payload = json.dumps({
            "model": self.model,
            "input": text,
            "voice": self.voice,
            "response_format": "mp3",
        }).encode("utf-8")

        req = urllib.request.Request(endpoint, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "Yunta/2.6.0 Client")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")

        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.read()
        except Exception:
            return None

    def synthesize_edge_tts(self, text: str) -> bytes | None:
        """Sintetiza audio de alta fidelidad neuronal utilizando edge-tts (fallback)."""
        try:
            # Intento 1: usar la librería edge_tts de Python si está disponible
            import edge_tts

            async def _gen() -> bytes:
                communicate = edge_tts.Communicate(text, self.voice)
                audio_bytes = bytearray()
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_bytes.extend(chunk["data"])
                return bytes(audio_bytes)

            return asyncio.run(_gen())
        except Exception:
            pass

        # Intento 2: usar la herramienta de línea de comandos edge-tts si está instalada en el sistema
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = Path(tmp.name)

            cmd = [
                sys.executable, "-m", "edge_tts",
                "--voice", self.voice,
                "--text", text,
                "--write-media", str(tmp_path),
            ]
            res = subprocess.run(cmd, capture_output=True, timeout=10)
            if res.returncode == 0 and tmp_path.exists() and tmp_path.stat().st_size > 0:
                audio_data = tmp_path.read_bytes()
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
                return audio_data
        except Exception:
            pass

        return None

    def synthesize(self, text: str) -> bytes | None:
        """Sintetiza texto a audio retornando bytes en formato MP3 o WAV con fallback."""
        if not text or not text.strip():
            return None

        # 1. Probar proveedor HTTP primario (Cloudflare Worker / OpenAI TTS API)
        audio = self.synthesize_http(text)
        if audio and len(audio) > 100:
            return audio

        # 2. Respaldo secundario: Microsoft Edge TTS (edge-tts neuronal gratis)
        audio = self.synthesize_edge_tts(text)
        if audio and len(audio) > 100:
            return audio

        return None

    def play_audio(self, audio_bytes: bytes) -> bool:
        """Reproduce un bloque de audio en el sistema local sin bloquear la ejecución."""
        if not audio_bytes:
            return False

        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = Path(tmp.name)

            # Intentar reproducción con reproductores comunes de sistema (ffplay, mpv, vlc, powershell)
            if sys.platform == "win32":
                ps_script = (
                    f"$player = New-Object System.Media.SoundPlayer; "
                    f"$player.SoundLocation = '{tmp_path}'; $player.PlaySync()"
                )
                cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script]
                res = subprocess.run(cmd, capture_output=True, timeout=10)
                if res.returncode == 0:
                    try:
                        tmp_path.unlink()
                    except OSError:
                        pass
                    return True

            # Fallback con ffplay si está disponible en PATH
            try:
                subprocess.run(
                    ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(tmp_path)],
                    capture_output=True,
                    timeout=15,
                )
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
                return True
            except Exception:
                pass
        except Exception:
            pass

        return False

    def speak(self, text: str) -> None:
        """Procesa y lee en voz alta una respuesta completa fragmentándola por oraciones."""
        chunks = chunk_text_by_sentences(text)
        if not chunks:
            return

        for chunk in chunks:
            audio = self.synthesize(chunk)
            if audio:
                self.play_audio(audio)
