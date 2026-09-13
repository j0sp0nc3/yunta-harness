"""Paquete de Extractores Locales Universales de Texto (Etapa 1).

Convierte cualquier formato de entrada (Audio, Video, PDF/Documentos, Imágenes OCR)
a Texto Plano localmente sin enviar datos a LLMs. El texto extraído se convierte
en el Prompt Base para la Etapa 2.
"""

from pathlib import Path
from .audio import extract_audio_text
from .video import extract_video_text
from .document import extract_document_text
from .ocr import extract_ocr_text
from .url import extract_url_text


def extract_text_from_file(file_path: str) -> str:
    """Enruta cualquier archivo o URL según su formato al extractor local correspondiente."""
    target = file_path.strip()

    # Si es una URL web o video de YouTube
    if target.startswith("http://") or target.startswith("https://"):
        return extract_url_text(target)

    path = Path(target)
    if not path.exists():
        raise FileNotFoundError(f"Archivo no encontrado: {file_path}")

    ext = path.suffix.lower()

    # Audio
    if ext in (".wav", ".mp3", ".m4a", ".ogg", ".webm", ".flac"):
        return extract_audio_text(str(path))

    # Video
    if ext in (".mp4", ".mkv", ".avi", ".mov", ".wmv"):
        return extract_video_text(str(path))

    # Documentos & PDFs
    if ext in (".pdf", ".docx", ".txt", ".md", ".csv", ".json", ".log"):
        return extract_document_text(str(path))

    # Imágenes & OCR
    if ext in (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff"):
        return extract_ocr_text(str(path))

    # Fallback por defecto: intentar leer como texto plano
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception as err:
        raise ValueError(f"Formato no soportado para extracción de texto: '{ext}' ({err})")
