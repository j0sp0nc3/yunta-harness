"""Extractor local de texto desde archivos de audio."""

from ..voice import AudioTranscriber


def extract_audio_text(file_path: str) -> str:
    """Extrae el texto plano de un archivo de audio (.wav, .mp3, .m4a, .ogg)."""
    transcriber = AudioTranscriber()
    return transcriber.transcribe(file_path)
