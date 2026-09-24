"""Extractor local de texto desde enlaces web (URLs) y videos de YouTube (Etapa 1)."""

import os
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path


def extract_url_text(url: str) -> str:
    """Extrae el texto plano de una URL de página web o video de YouTube."""
    url = url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError(f"URL inválida: {url}")

    # 1. Caso especial: Video de YouTube
    if "youtube.com" in url or "youtu.be" in url:
        return _extract_youtube_text(url)

    # 2. Caso general: Página Web (HTML -> Texto Plano)
    return _extract_webpage_text(url)


def _extract_webpage_text(url: str) -> str:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # Limpieza básica de HTML a texto plano
        html = re.sub(r"<script.*?>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style.*?>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
        
        # Convertir tags de bloque a saltos de línea
        html = re.sub(r"<(p|h[1-6]|div|li|br|tr)\b.*?>", "\n", html, flags=re.IGNORECASE)
        
        # Eliminar todas las etiquetas HTML restantes
        text = re.sub(r"<.*?>", "", html)
        
        # Limpiar espacios en blanco excesivos
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        clean_text = "\n".join(lines)

        return f"### Contenido Web ({url})\n\n{clean_text[:10000]}"
    except Exception as err:
        return f"### Error al acceder a la URL ({url})\n\nNo se pudo extraer el contenido: {err}"


def _extract_youtube_text(url: str) -> str:
    try:
        temp_dir = tempfile.mkdtemp(prefix="yunta_yt_")
        temp_audio = os.path.join(temp_dir, "yt_audio.wav")

        # Intentar extraer subtítulos con yt-dlp si está instalado
        cmd_sub = [
            "yt-dlp", "--skip-download", "--write-auto-sub", "--sub-lang", "es,en",
            "--output", os.path.join(temp_dir, "sub"), url
        ]
        subprocess.run(cmd_sub, capture_output=True, text=True, timeout=15)
        
        # Buscar archivos de subtítulos descargados (.vtt o .srt)
        for sub_file in Path(temp_dir).glob("*.vtt"):
            content = sub_file.read_text(encoding="utf-8", errors="ignore")
            lines = [line for line in content.splitlines() if "-->" not in line and not line.isdigit() and line.strip()]
            sub_text = "\n".join(dict.fromkeys(lines))
            if sub_text.strip():
                return f"### Subtítulos de YouTube ({url})\n\n{sub_text[:10000]}"
        
        # Intentar extraer audio con yt-dlp
        cmd_audio = [
            "yt-dlp", "-x", "--audio-format", "wav",
            "-o", temp_audio, url
        ]
        subprocess.run(cmd_audio, capture_output=True, text=True, timeout=30)
        if os.path.exists(temp_audio):
            from .audio import extract_audio_text
            text = extract_audio_text(temp_audio)
            return f"### Transcripción de Audio YouTube ({url})\n\n{text}"
    except Exception:
        pass

    return (
        f"### Video de YouTube ({url})\n\n"
        f"Nota: Para la extracción automática de subtítulos o audio de enlaces de YouTube se recomienda tener 'yt-dlp' y 'ffmpeg' instalados.\n"
        f"Puedes analizarlo pasando directamente el texto o archivo descargado."
    )
