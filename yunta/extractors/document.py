"""Extractor local de texto desde documentos y PDFs (.pdf, .docx, .txt, .md)."""

from pathlib import Path


def extract_document_text(file_path: str) -> str:
    """Extrae el texto plano de documentos (.pdf, .docx, .txt, .md) localmente sin LLMs."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Documento no encontrado: {file_path}")

    ext = path.suffix.lower()

    # Documentos de texto / Markdown / JSON / Log / CSV
    if ext in (".txt", ".md", ".csv", ".json", ".log"):
        return path.read_text(encoding="utf-8", errors="ignore")

    # Archivos PDF
    if ext == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            pages_text = [page.extract_text() or "" for page in reader.pages]
            return f"### Documento PDF ({path.name})\n\n" + "\n\n".join(pages_text)
        except ImportError:
            pass

        # Fallback sin pypdf: extracción simple de streams de texto
        try:
            content = path.read_bytes()
            # Extraer caracteres imprimibles básicos del PDF
            import re
            text_blocks = re.findall(b"\\(([^)]+)\\)", content)
            text = " ".join([b.decode("utf-8", errors="ignore") for b in text_blocks if len(b) > 3])
            if text.strip():
                return f"### Documento PDF ({path.name})\n\n{text}"
        except Exception:
            pass

        return f"### Documento PDF ({path.name})\n\n(Instala 'pypdf' con `pip install pypdf` para mejor extracción de texto PDF)"

    # Documentos Word (.docx)
    if ext == ".docx":
        try:
            import docx
            doc = docx.Document(str(path))
            full_text = [p.text for p in doc.paragraphs if p.text]
            return f"### Documento Word ({path.name})\n\n" + "\n".join(full_text)
        except ImportError:
            return f"### Documento Word ({path.name})\n\n(Instala 'python-docx' con `pip install python-docx` para extracción Word)"

    return path.read_text(encoding="utf-8", errors="ignore")
