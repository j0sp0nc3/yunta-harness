"""Extractor local de texto desde imágenes usando OCR nativo (Windows.Media.Ocr / tesseract)."""

import os
from pathlib import Path
import subprocess
import sys


def extract_ocr_text(file_path: str) -> str:
    """Extrae texto de imágenes (.png, .jpg, .webp) mediante OCR local determinista."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Imagen no encontrada: {file_path}")

    # 1. OCR Nativo en Windows usando Windows.Media.Ocr vía PowerShell (0 dependencias)
    if sys.platform == "win32":
        try:
            ps_script = (
                f"[void][Windows.Media.Ocr.OcrEngine, Windows.Foundation.UniversalApiContract, ContentType=WindowsRuntime]; "
                f"$file = Get-Item '{path.resolve()}'; "
                f"$stream = [Windows.Storage.Streams.FileRandomAccessStream]::OpenAsync($file.FullName, [Windows.Storage.FileAccessMode]::Read).GetResults(); "
                f"$decoder = [Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream).GetResults(); "
                f"$bmp = $decoder.GetSoftwareBitmapAsync().GetResults(); "
                f"$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguage(); "
                f"$ocrResult = $engine.RecognizeAsync($bmp).GetResults(); "
                f"Write-Host $ocrResult.Text"
            )
            cmd = ["powershell", "-Command", ps_script]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0 and res.stdout.strip():
                return f"### OCR de Imagen ({path.name})\n\n{res.stdout.strip()}"
        except Exception:
            pass

    # 2. Fallback usando pytesseract si está instalado
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(str(path))
        text = pytesseract.image_to_string(img, lang="spa+eng")
        if text.strip():
            return f"### OCR de Imagen ({path.name})\n\n{text.strip()}"
    except Exception:
        pass

    return f"### Imagen {path.name}\n\n(No se detectó texto imprimible en la imagen vía OCR local)"
