"""Extractor local de texto desde archivos de video (.mp4, .mkv, .avi)."""

import os
from pathlib import Path
import subprocess
import tempfile
from .audio import extract_audio_text


def extract_video_text(file_path: str) -> str:
    """Extrae la pista de audio de un video (.mp4, .mkv) y la convierte a texto plano."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Archivo de video no encontrado: {file_path}")

    temp_wav = tempfile.mktemp(suffix=".wav", prefix="yunta_video_audio_")

    # Intentar extraer audio del video usando ffmpeg si está disponible
    try:
        cmd = [
            "ffmpeg", "-i", str(path), "-vn", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1", temp_wav, "-y"
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if os.path.exists(temp_wav) and os.path.getsize(temp_wav) > 0:
            text = extract_audio_text(temp_wav)
            try:
                os.remove(temp_wav)
            except OSError:
                pass
            return f"### Transcripción de Video ({path.name})\n\n{text}"
    except Exception:
        pass

    # Si ffmpeg no está instalado, devolver aviso informativo
    return (
        f"### Video {path.name}\n\n"
        f"Nota: Para la extracción automática de audio de videos .mp4/.mkv se requiere 'ffmpeg' en el PATH del sistema."
    )
