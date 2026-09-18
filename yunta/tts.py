"""Módulo neutral de síntesis de voz (Text-to-Speech / TTS) para Yunta.

Cadena de resiliencia en 2 niveles:
1. Proveedor Primario: HTTP OpenAI-compatible (/v1/audio/speech) configurable
   vía TTS_API_BASE.
2. Respaldo: Microsoft Edge TTS (edge-tts) con voces neuronales en español
   (ej. es-CL-CatalinaNeural). El respaldo se anuncia en terminal, nunca es
   silencioso (regla de yunta: sin fallbacks ocultos).

Reproducción sin dependencias: en Windows usa MCI vía ctypes/winmm.dll (igual
que la grabación de micrófono en voice.py); en otros sistemas, ffplay/mpv si
están en PATH. La síntesis y reproducción corren en un hilo daemon: el REPL
nunca se bloquea y una respuesta nueva corta la locución anterior.
"""

import asyncio
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
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
    """Proveedor agnóstico de síntesis de voz (TTS) con fallback anunciado."""

    def __init__(
        self,
        model: str | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
        voice: str | None = None,
    ):
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
        req.add_header("User-Agent", "Yunta/2.5.1 Client")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")

        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.read()
        except Exception:
            return None

    def synthesize_edge_tts(self, text: str) -> bytes | None:
        """Sintetiza audio neuronal con edge-tts: librería Python y, si no, su CLI."""
        try:
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

    def synthesize(self, text: str) -> tuple[bytes | None, str]:
        """Sintetiza texto a MP3. Retorna (audio, proveedor_usado) — el respaldo
        se devuelve explícito para que el llamador lo anuncie (sin fallback oculto)."""
        if not text or not text.strip():
            return None, ""

        audio = self.synthesize_http(text)
        if audio and len(audio) > 100:
            return audio, "http"

        audio = self.synthesize_edge_tts(text)
        if audio and len(audio) > 100:
            return audio, "edge-tts"

        return None, ""

    @staticmethod
    def _play_mci_win32(path: Path, max_seconds: float = 60.0, should_stop=None) -> bool:
        """Reproduce MP3/WAV con MCI (winmm.dll) vía ctypes — 0 dependencias, Windows."""
        import ctypes
        import time

        winmm = ctypes.windll.winmm
        alias = "yunta_tts"
        ok = winmm.mciSendStringW(f'open "{path}" type mpegvideo alias {alias}', None, 0, 0)
        if ok != 0:
            return False
        try:
            winmm.mciSendStringW(f"play {alias}", None, 0, 0)
            deadline = time.monotonic() + max_seconds
            status = ctypes.create_unicode_buffer(32)
            while time.monotonic() < deadline:
                if should_stop is not None and should_stop():
                    break
                winmm.mciSendStringW(f"status {alias} mode", status, 32, 0)
                if status.value != "playing":
                    break
                time.sleep(0.05)
            winmm.mciSendStringW(f"stop {alias}", None, 0, 0)
            return True
        finally:
            winmm.mciSendStringW(f"close {alias}", None, 0, 0)

    def play_audio(self, audio_bytes: bytes, should_stop=None) -> bool:
        """Reproduce un bloque de audio MP3 y retorna si lo logró."""
        if not audio_bytes:
            return False

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = Path(tmp.name)

        played = False
        try:
            if sys.platform == "win32":
                played = self._play_mci_win32(tmp_path, should_stop=should_stop)
            if not played:
                # Linux/macOS: ffplay o mpv si están en PATH
                for player in (["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"],
                               ["mpv", "--no-video", "--really-quiet"]):
                    try:
                        res = subprocess.run(player + [str(tmp_path)], capture_output=True, timeout=60)
                        if res.returncode == 0:
                            played = True
                            break
                    except Exception:
                        continue
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass
        return played


# --- Locución no-bloqueante: un solo hilo daemon, la respuesta nueva corta la anterior ---

_speak_thread: threading.Thread | None = None
_speak_stop = threading.Event()
_playback_lock = threading.Lock()


def speak(provider: TTSProvider, text: str) -> bool:
    """Lee texto en voz alta en segundo plano (hilo daemon). No bloquea el REPL.
    Retorna True si la locución inició. Una llamada nueva corta la anterior."""
    global _speak_thread

    if not text or not text.strip():
        return False
    stop_speaking()
    _speak_stop.clear()

    def _worker():
        announced_edge = False
        for chunk in chunk_text_by_sentences(text):
            if _speak_stop.is_set():
                break
            audio, source = provider.synthesize(chunk)
            if not audio:
                continue
            if source == "edge-tts" and not announced_edge:
                print("\n💡 (voz: Edge TTS — respaldo del endpoint TTS principal)")
                announced_edge = True
            with _playback_lock:
                if _speak_stop.is_set():
                    break
                provider.play_audio(audio, should_stop=lambda: _speak_stop.is_set())

    _speak_thread = threading.Thread(target=_worker, daemon=True, name="yunta-tts")
    _speak_thread.start()
    return True


def stop_speaking() -> None:
    """Corta la locución en curso (bloquea hasta liberar la reproducción actual)."""
    global _speak_thread
    _speak_stop.set()
    with _playback_lock:
        pass
    if _speak_thread is not None and _speak_thread.is_alive():
        _speak_thread.join(timeout=1.0)
    _speak_thread = None


def wait_until_done(timeout: float = 300.0) -> None:
    """Espera (bloqueante) a que termine la locución en curso — usado por el
    gate de eco para no reabrir el micrófono mientras el TTS habla."""
    t = _speak_thread
    if t is not None and t.is_alive():
        t.join(timeout=timeout)
