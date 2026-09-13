"""Pruebas unitarias para el paquete yunta/extractors."""

import pytest
from pathlib import Path
from yunta.extractors import extract_text_from_file
from yunta.extractors.audio import extract_audio_text
from yunta.extractors.document import extract_document_text
from yunta.extractors.video import extract_video_text
from yunta.extractors.ocr import extract_ocr_text


def test_extract_document_text(tmp_path):
    doc = tmp_path / "test_doc.md"
    doc.write_text("# Título\nEste es un documento de prueba.", encoding="utf-8")
    res = extract_text_from_file(str(doc))
    assert "Este es un documento de prueba" in res


def test_extract_file_not_found():
    with pytest.raises(FileNotFoundError):
        extract_text_from_file("non_existent_file.pdf")


def test_extract_video_graceful(tmp_path):
    vid = tmp_path / "sample.mp4"
    vid.write_bytes(b"dummy video header")
    res = extract_video_text(str(vid))
    assert "Video sample.mp4" in res


def test_extract_ocr_graceful(tmp_path):
    img = tmp_path / "sample.png"
    img.write_bytes(b"dummy png data")
    res = extract_ocr_text(str(img))
    assert "sample.png" in res


def test_extract_url_graceful():
    res = extract_text_from_file("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert "YouTube" in res

