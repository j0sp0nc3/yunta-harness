"""Pruebas unitarias para yunta/voice.py y yunta/tools/voice.py."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from yunta.voice import AudioTranscriber, AudioChunker, normalize_voice_response
from yunta.tools.voice import transcribe_audio, generate_study_notes


def test_normalize_voice_response_approvals():
    assert normalize_voice_response("si") == "s"
    assert normalize_voice_response("sí") == "s"
    assert normalize_voice_response("aprobado") == "s"
    assert normalize_voice_response("avanzar") == "s"
    assert normalize_voice_response("abanzau ok") == "s"
    assert normalize_voice_response("ok") == "s"
    assert normalize_voice_response("dale nomas") == "s"
    assert normalize_voice_response("proceder por favor") == "s"


def test_normalize_voice_response_rejections():
    assert normalize_voice_response("no") == "c"
    assert normalize_voice_response("rechazado") == "c"
    assert normalize_voice_response("cancelar") == "c"
    assert normalize_voice_response("alto") == "c"
    assert normalize_voice_response("detener") == "c"
    assert normalize_voice_response("stop") == "c"


def test_normalize_voice_response_edits():
    assert normalize_voice_response("editar") == "e"
    assert normalize_voice_response("modificar") == "e"
    assert normalize_voice_response("cambiar") == "e"


def test_normalize_voice_response_always():
    assert normalize_voice_response("siempre") == "siempre"
    assert normalize_voice_response("para siempre") == "siempre"
    assert normalize_voice_response("si a todo") == "siempre"
    assert normalize_voice_response("sí a todo") == "siempre"
    assert normalize_voice_response("aprobado a todo") == "siempre"


def test_normalize_voice_response_full_sentences_unchanged():
    sentence = "Quiero que generes un archivo punto de prueba"
    assert normalize_voice_response(sentence) == sentence

    instruction = "No usaremos System.Speech en producción"
    assert normalize_voice_response(instruction) == instruction



def test_audio_transcriber_initialization():
    transcriber = AudioTranscriber(model="groq/whisper-large-v3", api_base="https://api.groq.com/openai/v1", api_key="sk-test")
    assert transcriber.model == "groq/whisper-large-v3"
    assert transcriber.api_base == "https://api.groq.com/openai/v1"
    assert transcriber.api_key == "sk-test"


@patch("urllib.request.urlopen")
def test_audio_transcribe_success(mock_urlopen, tmp_path):
    audio_file = tmp_path / "sample.mp3"
    audio_file.write_bytes(b"dummy audio content")

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"text": "Hola esta es una clase de fisiologia médica"}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    transcriber = AudioTranscriber(api_key="test")
    result = transcriber.transcribe(str(audio_file))
    assert result == "Hola esta es una clase de fisiologia médica"


def test_transcribe_audio_tool_file_not_found():
    raw_args = json.dumps({"path": "non_existent_audio.mp3"})
    res = transcribe_audio(raw_args)
    assert "error:" in res


def test_generate_study_notes_tool(tmp_path):
    transcript_file = tmp_path / "clase_cardiologia.txt"
    transcript_file.write_text("Transcripción de cátedra de insuficiencia cardíaca congestiva y farmacología de diuréticos.", encoding="utf-8")

    out_file = tmp_path / "guia_estudio.md"
    raw_args = json.dumps({
        "transcript_path": str(transcript_file),
        "output_path": str(out_file)
    })

    res = generate_study_notes(raw_args)
    assert "Guía de estudio generada exitosamente" in res
    assert out_file.exists()

    content = out_file.read_text(encoding="utf-8")
    assert "Guía Maestra de Estudio" in content
    assert "Glosario de Términos Médicos" in content
    assert "Diagrama de Flujo" in content
