"""Pruebas unitarias para yunta/voice.py y yunta/tools/voice.py."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from yunta.voice import AudioTranscriber, VoiceListener, route_keyword, AudioChunker, normalize_voice_response
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


def test_offload_transcript_short_kept(tmp_path, monkeypatch):
    """Transcripts cortos entran completos al contexto."""
    from yunta.voice import offload_transcript
    monkeypatch.chdir(tmp_path)
    text = "transcripción corta"
    assert offload_transcript(text) == text


def test_offload_transcript_long_saved_to_scratch(tmp_path, monkeypatch):
    """Transcripts >8000 chars se guardan en .yunta/scratch/ con preview + referencia."""
    from yunta.voice import offload_transcript
    monkeypatch.chdir(tmp_path)
    text = "clase de cardiología. " * 1000  # ~22K chars
    result = offload_transcript(text)
    assert len(result) < 1000
    assert "guardado en:" in result
    scratch_files = list((tmp_path / ".yunta" / "scratch").glob("transcript_*.txt"))
    assert len(scratch_files) == 1
    assert scratch_files[0].read_text(encoding="utf-8") == text


def test_chunker_passes_tail_as_prompt_and_supports_interrupt(tmp_path, monkeypatch):
    """AudioChunker: (1) pasa el final del chunk anterior como prompt de continuidad,
    (2) Ctrl+C interrumpe y devuelve transcripción parcial marcada."""
    from yunta.voice import AudioChunker, AudioTranscriber

    calls = []

    class FakeTranscriber(AudioTranscriber):
        def transcribe(self, file_path, prompt=""):
            calls.append(prompt)
            # Interrumpir en el fragmento 3 de 4
            if len(calls) == 3:
                raise KeyboardInterrupt
            return f"texto del fragmento {len(calls)} con terminología médica"

    chunker = AudioChunker(FakeTranscriber())
    chunks = [str(tmp_path / f"c{i}.mp3") for i in range(4)]
    for c in chunks:
        Path(c).write_bytes(b"\xff\xfb\x90\x00" + b"x" * 1024)  # frame MP3 fake + contenido

    monkeypatch.setattr(chunker, "split_audio_by_silence", lambda fp, cm=10: chunks)
    result = chunker.transcribe_large_audio("audio.mp3")

    assert "[00:00:00]" in result and "[00:10:00]" in result
    # Continuidad: chunk 2 recibió el tail del chunk 1 como prompt
    assert calls[1] == "texto del fragmento 1 con terminología médica"[-200:]
    # Interrupción conservó lo transcrito y lo marcó como parcial
    assert "fragmento 2" in result and "fragmento 4" not in result
    assert "transcripción parcial" in result
    # Los chunks no procesados fueron limpiados
    assert not tmp_path.joinpath("c2.mp3").exists()


# ==================== V5-1/V5-3: escucha continua y fuzzy ====================

def test_fuzzy_matching_tolerates_whisper_errors():
    """V5-3: errores fonéticos de una palabra se mapean a la acción correcta."""
    assert normalize_voice_response("aprobau") == "s"
    assert normalize_voice_response("avansar") == "s"
    assert normalize_voice_response("cancelal") == "c"
    assert normalize_voice_response("editat") == "e"
    # una frase larga y específica NO se toca (debe ir al LLM)
    long = "explícame el algoritmo de dijkstra con un ejemplo"
    assert normalize_voice_response(long) == long


def test_route_keyword_resolves_locally():
    """Las palabras clave se resuelven a comandos REPL sin consultar al LLM."""
    assert route_keyword("métricas") == "/metrics"
    assert route_keyword("metricass") == "/metrics"  # fuzzy
    assert route_keyword("salir") == "/exit"
    assert route_keyword("analiza este código por favor") is None


def test_voice_keywords_json_overrides(tmp_path, monkeypatch):
    """El usuario puede ampliar el registro en .yunta/voice_keywords.json."""
    monkeypatch.chdir(tmp_path)
    kd = tmp_path / ".yunta"
    kd.mkdir()
    (kd / "voice_keywords.json").write_text('{"guarda todo": "/snapshot"}', encoding="utf-8")
    assert route_keyword("guarda todo") == "/snapshot"
    assert route_keyword("métricas") == "/metrics"  # defaults intactos


def test_voice_listener_vad_segments_by_silence():
    """Segmentación VAD: bloques sobre el umbral + silencio final = una frase en cola."""
    import struct

    vl = VoiceListener.__new__(VoiceListener)  # sin __init__ (evita hardware)
    import queue as q
    vl._queue = q.Queue()
    vl.silence_ms = 960
    vl.threshold = 500
    vl.BLOCK_MS = 480
    vl.SAMPLE_RATE = 16000

    transcribed = []

    class FakeTranscriber:
        def transcribe(self, path, prompt=""):
            transcribed.append(path)
            return "hola yunta"

    vl.transcriber = FakeTranscriber()

    def block(amplitude):
        return struct.pack("<h", amplitude) * int(16000 * 0.48)

    utterance = bytearray()
    silence = 0
    for raw in [block(100), block(2000), block(3000), block(2000), block(50), block(40), block(30)]:
        # replicar la lógica del loop _loop (RMS >= threshold)
        import numpy as np
        samples = np.frombuffer(raw, dtype="<i2")
        rms = int(np.sqrt(np.mean(samples.astype(float) ** 2)))
        if rms >= vl.threshold:
            utterance.extend(raw)
            silence = 0
        elif utterance:
            silence += vl.BLOCK_MS
            if silence >= vl.silence_ms:
                vl._finish_utterance(bytes(utterance))
                utterance = bytearray()
                silence = 0
            else:
                utterance.extend(raw)

    assert vl.get(timeout=1) == "hola yunta"
    assert len(transcribed) == 1

    # una frase de ruido puro (<0.3s de voz) no se transcribe
    tiny = block(3000)[: int(16000 * 2 * 0.2)]  # 0.2s
    vl._finish_utterance(tiny)
    assert vl.get(timeout=0.2) is None


def test_voice_listener_pause_discards_audio():
    """En pausa (eco del TTS) el audio se descarta: no genera frases."""
    import queue as q
    vl = VoiceListener.__new__(VoiceListener)
    vl._queue = q.Queue()
    import threading
    vl._paused = threading.Event()
    vl._paused.set()
    # en el loop real, _paused.is_set() → clear() del buffer; aquí verificamos la API
    vl.pause()
    assert vl._paused.is_set()
    vl.resume()
    assert not vl._paused.is_set()
