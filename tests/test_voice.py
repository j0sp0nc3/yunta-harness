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


@patch("urllib.request.urlopen")
def test_transcribe_with_meta_reports_cloud_source_on_success(mock_urlopen, tmp_path):
    """Fase 0: transcribe() sigue devolviendo solo texto (sin cambio para
    los llamadores existentes); transcribe_with_meta() expone la metadata
    que el circuit breaker de AudioChunker necesita."""
    audio_file = tmp_path / "sample.mp3"
    audio_file.write_bytes(b"dummy audio content")

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"text": "hola"}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    transcriber = AudioTranscriber(api_key="test")
    text, meta = transcriber.transcribe_with_meta(str(audio_file))
    assert text == "hola"
    assert meta == {"source": "cloud", "cloud_attempted": True, "cloud_failed": False}

    # transcribe() público no cambia de comportamiento
    assert transcriber.transcribe(str(audio_file)) == "hola"


def test_retry_after_header_respected_in_backoff(tmp_path, monkeypatch):
    """Fase 2: si el error trae retry_after (header Retry-After), el
    backoff usa ese valor exacto (con tope VOICE_BACKOFF_CAP) en vez de la
    fórmula exponencial."""
    from yunta.voice import _TranscribeError

    audio_file = tmp_path / "sample.mp3"
    audio_file.write_bytes(b"dummy")

    transcriber = AudioTranscriber(api_key="test")
    sleeps = []
    monkeypatch.setattr("yunta.voice.time.sleep", lambda s: sleeps.append(s))

    call_count = {"n": 0}

    def fake_post(path, prompt=""):
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise _TranscribeError("HTTP 429: rate limited", 429, "rate limited", retry_after=2.0)
        return "listo"

    monkeypatch.setattr(transcriber, "_post_transcription", fake_post)

    result = transcriber.transcribe(str(audio_file))
    assert result == "listo"
    assert sleeps == [2.0, 2.0]


def test_backoff_exponential_with_jitter_when_no_retry_after(tmp_path, monkeypatch):
    """Fase 2: sin Retry-After, el backoff es exponencial (creciente por
    intento) en vez del lineal fijo anterior (3s, 6s)."""
    from yunta.voice import _TranscribeError

    audio_file = tmp_path / "sample.mp3"
    audio_file.write_bytes(b"dummy")

    transcriber = AudioTranscriber(api_key="test")
    sleeps = []
    monkeypatch.setattr("yunta.voice.time.sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr("yunta.voice.random.uniform", lambda a, b: 0.0)  # jitter determinista
    monkeypatch.setattr(transcriber, "transcribe_offline_local", lambda p: "")

    def fake_post(path, prompt=""):
        raise _TranscribeError("URLError: timeout", None, "")

    monkeypatch.setattr(transcriber, "_post_transcription", fake_post)

    transcriber.transcribe(str(audio_file))
    assert len(sleeps) == 2
    assert sleeps[1] > sleeps[0]  # monotonía creciente (exponencial)
    assert all(s <= 30 for s in sleeps)


def test_transcribe_error_retry_after_defaults_to_none():
    """Regresión: construir _TranscribeError sin retry_after (como en todos
    los sitios existentes) debe seguir funcionando con retry_after=None."""
    from yunta.voice import _TranscribeError

    err = _TranscribeError("msg", 500, "detail")
    assert err.retry_after is None


def test_transcribe_with_meta_skip_cloud_goes_straight_to_local(tmp_path, monkeypatch):
    audio_file = tmp_path / "sample.mp3"
    audio_file.write_bytes(b"dummy audio content")

    transcriber = AudioTranscriber(api_key="test")
    monkeypatch.setattr(transcriber, "transcribe_offline_local", lambda p: "texto local")

    calls = {"urlopen": 0}
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: calls.__setitem__("urlopen", calls["urlopen"] + 1))

    text, meta = transcriber.transcribe_with_meta(str(audio_file), skip_cloud=True)
    assert text == "texto local"
    assert meta == {"source": "local", "cloud_attempted": False, "cloud_failed": False}
    assert calls["urlopen"] == 0  # nunca tocó la red


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


def test_offload_transcript_suggests_single_read_when_moderate_size(tmp_path, monkeypatch):
    """Motivado por una corrida real: un transcript de ~18K tokens (81 min de
    audio) cabe en una sola lectura, pero el agente lo fragmentó en 6
    llamadas porque el mensaje anterior siempre sugería leer 'por partes'.
    Bajo un umbral generoso, ahora sugiere una sola lectura."""
    from yunta.voice import offload_transcript
    monkeypatch.chdir(tmp_path)
    text = "clase de cardiología. " * 1000  # ~22K chars, ~5500 tokens aprox
    result = offload_transcript(text)
    assert "sin offset/limit" in result
    assert "por partes" not in result


def test_offload_transcript_suggests_chunked_read_when_very_large(tmp_path, monkeypatch):
    """Un transcript genuinamente enorme (>50K tokens aprox) sigue sugiriendo
    lectura fragmentada — no se quita la protección para audios de muchas horas."""
    from yunta.voice import offload_transcript
    monkeypatch.chdir(tmp_path)
    text = "clase muy larga de anatomía. " * 10000  # ~290K chars, ~72K tokens aprox
    result = offload_transcript(text)
    assert "por partes" in result
    assert "sin offset/limit" not in result


def test_offload_transcript_reports_posix_path_not_backslashes(tmp_path, monkeypatch):
    """La ruta se reporta con barras (POSIX), no backslashes de Windows — un
    backslash seguido de una letra como 't' o 'n' es una secuencia de escape
    JSON válida y puede corromperse si el modelo la reproduce en un argumento
    de tool call."""
    from yunta.voice import offload_transcript
    monkeypatch.chdir(tmp_path)
    text = "clase de cardiología. " * 1000
    result = offload_transcript(text)
    assert "\\" not in result.split("guardado en:")[1].split(" — ")[0]


def test_chunker_passes_tail_as_prompt_and_supports_interrupt(tmp_path, monkeypatch):
    """AudioChunker: (1) pasa el final del chunk anterior como prompt de continuidad,
    (2) Ctrl+C interrumpe y devuelve transcripción parcial marcada."""
    monkeypatch.chdir(tmp_path)  # aisla los checkpoints de V6-3 (.yunta/scratch)
    from yunta.voice import AudioChunker, AudioTranscriber

    calls = []

    class FakeTranscriber(AudioTranscriber):
        def transcribe_with_meta(self, file_path, prompt="", skip_cloud=False):
            calls.append(prompt)
            # Interrumpir en el fragmento 3 de 4
            if len(calls) == 3:
                raise KeyboardInterrupt
            text = f"texto del fragmento {len(calls)} con terminología médica"
            return text, {"source": "cloud", "cloud_attempted": True, "cloud_failed": False}

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


def test_stop_keywords_routed():
    for word in ("para", "parar", "stop", "detener", "cancela", "cancelar", "basta"):
        assert route_keyword(word) == "/stop"
    for word in ("callate", "cállate", "silencio"):
        assert route_keyword(word) == "/speak off"


def test_prefix_keywords_routed():
    assert route_keyword("inicializa un clon de snake") == "/init un clon de snake"
    assert route_keyword("inicia proyecto api con fastapi") == "/init api con fastapi"
    assert route_keyword("crear proyecto app móvil") == "/init app móvil"
    assert route_keyword("inicializar") == "/init"


def test_make_voice_approval():
    from yunta.voice import make_voice_approval

    class FakePermissions:
        def __init__(self):
            self.granted = []
        def grant_tool(self, name):
            self.granted.append(name)

    class FakeAgent:
        def __init__(self):
            self.session_permissions = FakePermissions()

    class FakeListener:
        def __init__(self, responses):
            self.responses = list(responses)
            self.resumed = 0
            self.paused = 0

        def resume(self):
            self.resumed += 1

        def pause(self):
            self.paused += 1

        def get(self, timeout=180):
            if self.responses:
                return self.responses.pop(0)
            return None

    agent = FakeAgent()

    # 1. 'si' -> True
    cb = make_voice_approval(agent, FakeListener(["sí"]))
    assert cb("bash") is True

    # 2. 'siempre' -> True + persistencia en session_permissions
    cb = make_voice_approval(agent, FakeListener(["siempre"]))
    assert cb("write_file") is True
    assert "write_file" in agent.session_permissions.granted

    # 3. 'no' -> False
    cb = make_voice_approval(agent, FakeListener(["no"]))
    assert cb("bash") is False

    # 4. Timeout (None) -> False
    cb = make_voice_approval(agent, FakeListener([None]))
    assert cb("bash") is False


def test_workers_ai_uses_500kb_threshold_and_30s_chunks(tmp_path, monkeypatch):
    """Endpoints de Workers AI (workers.dev) fragmentan a partir de 500 KB en bloques de 30s (0.5m)."""
    from unittest.mock import MagicMock
    from yunta.voice import AudioTranscriber

    audio_file = tmp_path / "lecture.m4a"
    # Archivo de 1 MB
    audio_file.write_bytes(b"x" * (1 * 1024 * 1024))

    transcriber = AudioTranscriber(
        model="@cf/openai/whisper",
        api_base="https://my-worker.beroiza.workers.dev/v1",
        api_key="fake-key"
    )

    mock_chunker_instance = MagicMock()
    mock_chunker_instance.transcribe_large_audio.return_value = "transcripcion fragmentada"
    mock_chunker_cls = MagicMock(return_value=mock_chunker_instance)
    monkeypatch.setattr("yunta.voice.AudioChunker", mock_chunker_cls)

    res = transcriber.transcribe(str(audio_file))
    assert res == "transcripcion fragmentada"
    # Verificamos que se instanció con chunk_minutes=0.33 (20 segundos)
    mock_chunker_cls.assert_called_once_with(transcriber, chunk_minutes=0.33)
    mock_chunker_instance.transcribe_large_audio.assert_called_once_with(str(audio_file))


def test_too_large_error_retries_with_smaller_chunks(tmp_path, monkeypatch):
    """Si el endpoint arroja HTTP 413 o too_large, reintenta con fragmentos de 1 minuto."""
    from unittest.mock import MagicMock
    from yunta.voice import AudioTranscriber, _TranscribeError

    audio_file = tmp_path / "chunk.mp3"
    audio_file.write_bytes(b"x" * (1 * 1024 * 1024))

    transcriber = AudioTranscriber(api_base="http://localhost:8000/v1")
    # Simular que _post_transcription falla con error 413
    monkeypatch.setattr(
        transcriber,
        "_post_transcription",
        MagicMock(side_effect=_TranscribeError("HTTP 413: payload too large", 413, "too large"))
    )

    mock_chunker_instance = MagicMock()
    mock_chunker_instance.transcribe_large_audio.return_value = "rescate con fragmentos menores"
    mock_chunker_cls = MagicMock(return_value=mock_chunker_instance)
    monkeypatch.setattr("yunta.voice.AudioChunker", mock_chunker_cls)

    res = transcriber.transcribe(str(audio_file))
    assert res == "rescate con fragmentos menores"
    mock_chunker_instance.transcribe_large_audio.assert_called_once_with(str(audio_file), chunk_minutes=0.33)


def test_estimate_bitrate_bps_reads_mp3_frame_header(tmp_path):
    """Frame MP3 con índice de bitrate 9 (tabla MPEG1 Layer3) = 128 kbps."""
    f = tmp_path / "audio.mp3"
    f.write_bytes(b"\xff\xfb\x90\x00" + b"x" * 512)
    assert AudioChunker._estimate_bitrate_bps(str(f)) == 128000


def test_estimate_bitrate_bps_returns_zero_for_non_mp3(tmp_path):
    f = tmp_path / "audio.wav"
    f.write_bytes(b"\xff\xfb\x90\x00" + b"x" * 512)
    assert AudioChunker._estimate_bitrate_bps(str(f)) == 0


def test_calibrate_chunk_minutes_uses_real_bitrate_within_bounds(tmp_path):
    """Bitrate real (128 kbps) da un valor entre floor y ceiling, distinto del
    0.33 fijo anterior — el caso central que motiva la Fase 4."""
    f = tmp_path / "audio.mp3"
    f.write_bytes(b"\xff\xfb\x90\x00" + b"x" * 512)
    cm = AudioChunker._calibrate_chunk_minutes(str(f), max_bytes=500 * 1024)
    assert 0.33 < cm < 0.5
    assert cm == pytest.approx(0.4533, abs=0.001)


def test_calibrate_chunk_minutes_clamps_to_ceiling_for_low_bitrate(tmp_path):
    """Bitrate bajo (32 kbps) permitiría fragmentos largos bajo el mismo límite
    de bytes, pero el ceiling conservador (30s) no se supera."""
    f = tmp_path / "audio.mp3"
    f.write_bytes(b"\xff\xfb\x10\x00" + b"x" * 512)  # índice de bitrate 1 = 32 kbps
    cm = AudioChunker._calibrate_chunk_minutes(str(f), max_bytes=500 * 1024)
    assert cm == 0.5


def test_calibrate_chunk_minutes_clamps_to_floor_for_high_bitrate(tmp_path):
    """Bitrate alto (320 kbps) no reduce el fragmento por debajo del floor actual."""
    f = tmp_path / "audio.mp3"
    f.write_bytes(b"\xff\xfb\xe0\x00" + b"x" * 512)  # índice de bitrate 14 = 320 kbps
    cm = AudioChunker._calibrate_chunk_minutes(str(f), max_bytes=500 * 1024)
    assert cm == 0.33


def test_calibrate_chunk_minutes_falls_back_to_floor_without_bitrate(tmp_path):
    """Sin bitrate legible (formato no MP3), se mantiene el comportamiento
    previo (0.33 fijo) — sin regresión."""
    f = tmp_path / "audio.m4a"
    f.write_bytes(b"x" * (1024 * 1024))
    assert AudioChunker._calibrate_chunk_minutes(str(f), max_bytes=500 * 1024) == 0.33


def test_workers_ai_calibrates_chunk_minutes_by_real_bitrate_for_mp3(tmp_path, monkeypatch):
    """Para .mp3 contra Workers AI, sin override manual, se usa el bitrate real
    en vez del 0.33 fijo — verifica el cableado en transcribe_with_meta."""
    from unittest.mock import MagicMock
    from yunta.voice import AudioTranscriber

    audio_file = tmp_path / "lecture.mp3"
    audio_file.write_bytes(b"\xff\xfb\x90\x00" + b"x" * (1 * 1024 * 1024))

    transcriber = AudioTranscriber(
        model="@cf/openai/whisper",
        api_base="https://my-worker.beroiza.workers.dev/v1",
        api_key="fake-key",
    )

    mock_chunker_instance = MagicMock()
    mock_chunker_instance.transcribe_large_audio.return_value = "transcripcion fragmentada"
    mock_chunker_cls = MagicMock(return_value=mock_chunker_instance)
    monkeypatch.setattr("yunta.voice.AudioChunker", mock_chunker_cls)

    res = transcriber.transcribe(str(audio_file))
    assert res == "transcripcion fragmentada"
    _, kwargs = mock_chunker_cls.call_args
    assert kwargs["chunk_minutes"] == pytest.approx(0.4533, abs=0.001)


def test_workers_ai_env_override_bypasses_calibration(tmp_path, monkeypatch):
    """VOICE_CHUNK_MINUTES explícito respeta el override manual y no calibra."""
    from unittest.mock import MagicMock
    from yunta.voice import AudioTranscriber

    monkeypatch.setenv("VOICE_CHUNK_MINUTES", "2.0")
    audio_file = tmp_path / "lecture.mp3"
    audio_file.write_bytes(b"\xff\xfb\x90\x00" + b"x" * (1 * 1024 * 1024))

    transcriber = AudioTranscriber(
        model="@cf/openai/whisper",
        api_base="https://my-worker.beroiza.workers.dev/v1",
        api_key="fake-key",
    )

    mock_chunker_instance = MagicMock()
    mock_chunker_instance.transcribe_large_audio.return_value = "ok"
    mock_chunker_cls = MagicMock(return_value=mock_chunker_instance)
    monkeypatch.setattr("yunta.voice.AudioChunker", mock_chunker_cls)

    transcriber.transcribe(str(audio_file))
    mock_chunker_cls.assert_called_once_with(transcriber, chunk_minutes=2.0)



def test_circuit_breaker_skips_cloud_after_consecutive_failures(tmp_path, monkeypatch):
    """Tras N fallos de nube consecutivos, el breaker salta directo a local
    (skip_cloud=True) durante el cooldown, y la nube exitosa resetea el streak."""
    monkeypatch.chdir(tmp_path)  # aisla los checkpoints de V6-3 (.yunta/scratch)
    from yunta.voice import AudioChunker, AudioTranscriber

    calls: list[bool] = []  # valor de skip_cloud por fragmento

    class MetaTranscriber(AudioTranscriber):
        def transcribe_with_meta(self, file_path, prompt="", skip_cloud=False):
            calls.append(skip_cloud)
            n = len(calls)
            if skip_cloud:
                return "local", {"source": "local", "cloud_attempted": False, "cloud_failed": False}
            # fragmentos 1-3: nube falla; 4+: si se intenta nube, ya con cooldown activo
            if n <= 3:
                return "", {"source": "local", "cloud_attempted": True, "cloud_failed": True}
            return "nube", {"source": "cloud", "cloud_attempted": True, "cloud_failed": False}

    chunker = AudioChunker(MetaTranscriber())
    chunker._cb_threshold = 3
    chunker._cb_cooldown = 2

    chunks = []
    for i in range(6):
        f = tmp_path / f"c{i}.mp3"
        f.write_bytes(b"\xff\xfb\x90\x00" + b"a" * 512)
        chunks.append(str(f))
    chunker.split_audio_by_silence
    chunker.split_audio_by_silence = lambda fp, *a, **k: chunks  # type: ignore[assignment]

    result = chunker.transcribe_large_audio("audio.mp3")

    # 3 primeros fragmentos intentaron nube (skip_cloud=False)
    assert calls[:3] == [False, False, False]
    # el breaker se disparó: los siguientes van directo a local
    assert any(calls[3:]), "el breaker debió saltar la nube tras 3 fallos"
    assert chunker._cb_tripped_count == 1
    assert "local" in result


def test_circuit_breaker_disabled_with_threshold_zero(monkeypatch, tmp_path):
    """VOICE_BREAKER_THRESHOLD=0 desactiva el breaker: siempre intenta la nube."""
    monkeypatch.chdir(tmp_path)  # aisla los checkpoints de V6-3 (.yunta/scratch)
    import os as _os
    monkeypatch.setenv("VOICE_BREAKER_THRESHOLD", "0")
    from yunta.voice import AudioChunker, AudioTranscriber

    class MetaTranscriber(AudioTranscriber):
        def transcribe_with_meta(self, file_path, prompt="", skip_cloud=False):
            assert skip_cloud is False, "con breaker desactivado nunca debe saltar la nube"
            return "texto", {"source": "local", "cloud_attempted": True, "cloud_failed": True}

    chunker = AudioChunker(MetaTranscriber())
    fake_chunks = []
    for i in range(2):
        f = tmp_path / f"c{i}.mp3"
        f.write_bytes(b"\xff\xfb\x90\x00" + b"a" * 512)
        fake_chunks.append(str(f))
    chunker.split_audio_by_silence = lambda fp, *a, **k: fake_chunks  # type: ignore[assignment]
    chunker.transcribe_large_audio("audio.mp3")


# ==================== Fase 5: paralelismo acotado (VOICE_PARALLEL_WORKERS) ====================

def test_parallel_workers_reassembles_out_of_order_completions_by_index(monkeypatch, tmp_path):
    """Con VOICE_PARALLEL_WORKERS>1, fragmentos que terminan fuera de orden se
    reensamblan según su índice original, no según orden de llegada."""
    monkeypatch.chdir(tmp_path)  # aisla los checkpoints de V6-3 (.yunta/scratch)
    import time as _time
    monkeypatch.setenv("VOICE_PARALLEL_WORKERS", "4")
    from yunta.voice import AudioChunker, AudioTranscriber

    class SlowFirstTranscriber(AudioTranscriber):
        def transcribe_with_meta(self, file_path, prompt="", skip_cloud=False):
            idx = int(Path(file_path).stem[1:])  # "c0.mp3" -> 0
            # El fragmento 0 tarda más: si el reensamblado fuera por orden de
            # llegada en vez de por índice, terminaría después que los demás.
            _time.sleep(0.05 * (4 - idx) / 100)
            return f"fragmento-{idx}", {"source": "cloud", "cloud_attempted": True, "cloud_failed": False}

    chunker = AudioChunker(SlowFirstTranscriber())
    chunks = [str(tmp_path / f"c{i}.mp3") for i in range(4)]
    for c in chunks:
        Path(c).write_bytes(b"\xff\xfb\x90\x00" + b"x" * 512)
    chunker.split_audio_by_silence = lambda fp, *a, **k: chunks  # type: ignore[assignment]

    result = chunker.transcribe_large_audio("audio.mp3")

    order = [f"fragmento-{i}" for i in range(4)]
    positions = [result.index(o) for o in order]
    assert positions == sorted(positions), f"orden incorrecto en el resultado:\n{result}"


def test_parallel_workers_use_empty_prompt_no_tail_continuity(monkeypatch, tmp_path):
    """Limitación documentada de la Fase 5: sin orden garantizado entre workers,
    no hay continuidad de `tail` — cada fragmento recibe prompt vacío."""
    monkeypatch.chdir(tmp_path)  # aisla los checkpoints de V6-3 (.yunta/scratch)
    monkeypatch.setenv("VOICE_PARALLEL_WORKERS", "3")
    from yunta.voice import AudioChunker, AudioTranscriber

    prompts = []

    class MetaTranscriber(AudioTranscriber):
        def transcribe_with_meta(self, file_path, prompt="", skip_cloud=False):
            prompts.append(prompt)
            return "texto con contenido largo " * 10, {"source": "cloud", "cloud_attempted": True, "cloud_failed": False}

    chunker = AudioChunker(MetaTranscriber())
    chunks = [str(tmp_path / f"c{i}.mp3") for i in range(3)]
    for c in chunks:
        Path(c).write_bytes(b"\xff\xfb\x90\x00" + b"x" * 512)
    chunker.split_audio_by_silence = lambda fp, *a, **k: chunks  # type: ignore[assignment]

    chunker.transcribe_large_audio("audio.mp3")
    assert prompts == ["", "", ""]


def test_parallel_workers_disabled_by_default_keeps_tail_continuity(tmp_path, monkeypatch):
    """Sin VOICE_PARALLEL_WORKERS (o =1), el comportamiento es idéntico al
    secuencial existente: continuidad de tail entre fragmentos."""
    monkeypatch.chdir(tmp_path)  # aisla los checkpoints de V6-3 (.yunta/scratch)
    from yunta.voice import AudioChunker, AudioTranscriber

    prompts = []

    class MetaTranscriber(AudioTranscriber):
        def transcribe_with_meta(self, file_path, prompt="", skip_cloud=False):
            prompts.append(prompt)
            return "cola de continuidad", {"source": "cloud", "cloud_attempted": True, "cloud_failed": False}

    chunker = AudioChunker(MetaTranscriber())
    chunks = [str(tmp_path / f"c{i}.mp3") for i in range(3)]
    for c in chunks:
        Path(c).write_bytes(b"\xff\xfb\x90\x00" + b"x" * 512)
    chunker.split_audio_by_silence = lambda fp, *a, **k: chunks  # type: ignore[assignment]

    chunker.transcribe_large_audio("audio.mp3")
    assert prompts[0] == ""
    assert prompts[1] == "cola de continuidad"


def test_parallel_workers_telemetry_counts_are_order_independent(monkeypatch, tmp_path):
    """Los contadores agregados de telemetría (protegidos por lock) suman
    correctamente sin importar el orden real de finalización de los threads."""
    monkeypatch.chdir(tmp_path)  # aisla los checkpoints de V6-3 (.yunta/scratch)
    monkeypatch.setenv("VOICE_PARALLEL_WORKERS", "5")
    from yunta.voice import AudioChunker, AudioTranscriber

    class MixedTranscriber(AudioTranscriber):
        def transcribe_with_meta(self, file_path, prompt="", skip_cloud=False):
            idx = int(Path(file_path).stem[1:])
            if idx % 2 == 0:
                return "nube", {"source": "cloud", "cloud_attempted": True, "cloud_failed": False}
            return "local", {"source": "local", "cloud_attempted": True, "cloud_failed": True}

    chunker = AudioChunker(MixedTranscriber())
    chunks = [str(tmp_path / f"c{i}.mp3") for i in range(10)]
    for c in chunks:
        Path(c).write_bytes(b"\xff\xfb\x90\x00" + b"x" * 512)
    chunker.split_audio_by_silence = lambda fp, *a, **k: chunks  # type: ignore[assignment]

    chunker.transcribe_large_audio("audio.mp3")

    assert chunker._telem_cloud == 5
    assert chunker._telem_local == 5
    assert chunker._telem_errors == 5


def test_parallel_workers_keyboard_interrupt_returns_partial(monkeypatch, tmp_path):
    """Ctrl+C en modo paralelo cancela los fragmentos pendientes y devuelve
    lo ya transcrito, marcado como parcial."""
    monkeypatch.chdir(tmp_path)  # aisla los checkpoints de V6-3 (.yunta/scratch)
    monkeypatch.setenv("VOICE_PARALLEL_WORKERS", "2")
    from yunta.voice import AudioChunker, AudioTranscriber

    class InterruptingTranscriber(AudioTranscriber):
        def transcribe_with_meta(self, file_path, prompt="", skip_cloud=False):
            idx = int(Path(file_path).stem[1:])
            if idx == 0:
                raise KeyboardInterrupt
            return f"fragmento-{idx}", {"source": "cloud", "cloud_attempted": True, "cloud_failed": False}

    chunker = AudioChunker(InterruptingTranscriber())
    chunks = [str(tmp_path / f"c{i}.mp3") for i in range(4)]
    for c in chunks:
        Path(c).write_bytes(b"\xff\xfb\x90\x00" + b"x" * 512)
    chunker.split_audio_by_silence = lambda fp, *a, **k: chunks  # type: ignore[assignment]

    result = chunker.transcribe_large_audio("audio.mp3")
    assert "transcripción parcial" in result or result == ""


def test_transcribe_large_audio_workers_invalid_value_falls_back_to_sequential(monkeypatch, tmp_path):
    """Un VOICE_PARALLEL_WORKERS no numérico no debe romper la transcripción
    (mismo patrón de tolerancia que VOICE_CHUNK_MINUTES: cae al default 1)."""
    monkeypatch.chdir(tmp_path)  # aisla los checkpoints de V6-3 (.yunta/scratch)
    monkeypatch.setenv("VOICE_PARALLEL_WORKERS", "not-a-number")
    from yunta.voice import AudioChunker, AudioTranscriber

    class MetaTranscriber(AudioTranscriber):
        def transcribe_with_meta(self, file_path, prompt="", skip_cloud=False):
            return "ok", {"source": "cloud", "cloud_attempted": True, "cloud_failed": False}

    chunker = AudioChunker(MetaTranscriber())
    chunks = [str(tmp_path / "c0.mp3")]
    Path(chunks[0]).write_bytes(b"\xff\xfb\x90\x00" + b"x" * 512)
    chunker.split_audio_by_silence = lambda fp, *a, **k: chunks  # type: ignore[assignment]

    result = chunker.transcribe_large_audio("audio.mp3")
    assert "ok" in result


# ==================== Cache del modelo local de faster-whisper ====================

def _install_fake_faster_whisper(monkeypatch, load_calls, text="texto simulado"):
    import sys
    import types

    class FakeSegment:
        def __init__(self, t):
            self.text = t

    class FakeModel:
        def __init__(self, model_size, device, compute_type):
            load_calls.append(model_size)

        def transcribe(self, path, language="es"):
            return [FakeSegment(text)], None

    fake_module = types.SimpleNamespace(WhisperModel=FakeModel)
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_module)


def test_local_whisper_model_loaded_once_and_reused(monkeypatch, tmp_path):
    """El modelo local de faster-whisper se carga una sola vez por proceso y se
    reutiliza entre fragmentos — antes se recargaba en cada llamada (benchmark
    real: ~3.9s de overhead por fragmento, ~17 min extra en 259 fragmentos)."""
    import yunta.voice as voice_module

    monkeypatch.setattr(voice_module, "_local_whisper_model", None)
    monkeypatch.setattr(voice_module, "_local_whisper_model_size", None)
    monkeypatch.setenv("LOCAL_WHISPER_MODEL", "tiny")

    load_calls = []
    _install_fake_faster_whisper(monkeypatch, load_calls)

    transcriber = voice_module.AudioTranscriber(api_base="http://localhost:8000/v1")
    f = tmp_path / "a.mp3"
    f.write_bytes(b"\xff\xfb\x90\x00" + b"x" * 512)

    for _ in range(5):
        text = transcriber.transcribe_offline_local(str(f))
        assert text == "texto simulado"

    assert load_calls == ["tiny"], f"el modelo debió cargarse una sola vez, se cargó {len(load_calls)} veces"


def test_local_whisper_model_reloads_if_size_changes(monkeypatch, tmp_path):
    """Si LOCAL_WHISPER_MODEL cambia entre llamadas, el cache invalida y recarga
    (no queda pegado al primer tamaño de modelo pedido)."""
    import yunta.voice as voice_module

    monkeypatch.setattr(voice_module, "_local_whisper_model", None)
    monkeypatch.setattr(voice_module, "_local_whisper_model_size", None)

    load_calls = []
    _install_fake_faster_whisper(monkeypatch, load_calls)

    transcriber = voice_module.AudioTranscriber(api_base="http://localhost:8000/v1")
    f = tmp_path / "a.mp3"
    f.write_bytes(b"\xff\xfb\x90\x00" + b"x" * 512)

    monkeypatch.setenv("LOCAL_WHISPER_MODEL", "tiny")
    transcriber.transcribe_offline_local(str(f))
    monkeypatch.setenv("LOCAL_WHISPER_MODEL", "small")
    transcriber.transcribe_offline_local(str(f))

    assert load_calls == ["tiny", "small"]


def test_local_whisper_model_shared_across_transcriber_instances(monkeypatch, tmp_path):
    """El cache es de módulo, no de instancia: dos AudioTranscriber distintos
    (como ocurre en el retry por `too_large`) comparten el mismo modelo cargado."""
    import yunta.voice as voice_module

    monkeypatch.setattr(voice_module, "_local_whisper_model", None)
    monkeypatch.setattr(voice_module, "_local_whisper_model_size", None)
    monkeypatch.setenv("LOCAL_WHISPER_MODEL", "tiny")

    load_calls = []
    _install_fake_faster_whisper(monkeypatch, load_calls)

    f = tmp_path / "a.mp3"
    f.write_bytes(b"\xff\xfb\x90\x00" + b"x" * 512)

    voice_module.AudioTranscriber(api_base="http://localhost:8000/v1").transcribe_offline_local(str(f))
    voice_module.AudioTranscriber(api_base="http://localhost:8000/v1").transcribe_offline_local(str(f))

    assert load_calls == ["tiny"]


# ==================== V6-4: filtro de alucinaciones conocidas de Whisper ====================

def test_filter_hallucinations_discards_known_phrases_exact_match():
    from yunta.voice import _filter_whisper_hallucinations

    assert _filter_whisper_hallucinations("Gracias por ver el video.") == ""
    assert _filter_whisper_hallucinations("  suscríbete al canal  ") == ""
    assert _filter_whisper_hallucinations("Subtítulos realizados por la comunidad de Amara.org") == ""
    assert _filter_whisper_hallucinations("THANKS FOR WATCHING!") == ""


def test_filter_hallucinations_keeps_real_content_untouched():
    from yunta.voice import _filter_whisper_hallucinations

    real = "El hipotálamo regula el balance energético mediante señales de leptina."
    assert _filter_whisper_hallucinations(real) == real


def test_filter_hallucinations_does_not_strip_partial_mentions():
    """Si la frase conocida aparece dentro de contenido real (no es TODO el
    fragmento), no se descarta — solo se filtra el caso 'el chunk es puro relleno'."""
    from yunta.voice import _filter_whisper_hallucinations

    mixed = "Como decía, gracias por ver el video no es lo que buscamos explicar hoy."
    assert _filter_whisper_hallucinations(mixed) == mixed


def test_filter_hallucinations_handles_empty_string():
    from yunta.voice import _filter_whisper_hallucinations

    assert _filter_whisper_hallucinations("") == ""


def test_clean_transcription_combines_dedup_and_hallucination_filter():
    from yunta.voice import _clean_transcription

    assert _clean_transcription("Gracias por ver el video") == ""
    repeated = "vale vale vale vale vale vale"
    assert _clean_transcription(repeated) != repeated  # el dedup sigue actuando


def test_transcribe_with_meta_filters_hallucinated_cloud_success(monkeypatch, tmp_path):
    """Un fragmento cuya transcripción de nube es pura alucinación conocida
    vuelve como texto vacío, no como el relleno de YouTube."""
    from yunta.voice import AudioTranscriber

    transcriber = AudioTranscriber(api_base="http://fake-endpoint.test/v1")
    monkeypatch.setattr(transcriber, "_post_transcription", lambda path, prompt="": "Gracias por ver el video.")

    f = tmp_path / "a.mp3"
    f.write_bytes(b"x" * 100)
    text, meta = transcriber.transcribe_with_meta(str(f))

    assert text == ""
    assert meta == {"source": "cloud", "cloud_attempted": True, "cloud_failed": False}


def test_transcribe_with_meta_filters_hallucinated_local_fallback(monkeypatch, tmp_path):
    """El mismo filtro aplica al texto del fallback local, no solo a la nube."""
    from yunta.voice import AudioTranscriber, _TranscribeError

    transcriber = AudioTranscriber(api_base="http://fake-endpoint.test/v1")
    monkeypatch.setattr(
        transcriber, "_post_transcription",
        lambda path, prompt="": (_ for _ in ()).throw(_TranscribeError("fail", 400, "bad request")),
    )
    monkeypatch.setattr(transcriber, "transcribe_offline_local", lambda p: "suscríbete al canal")

    f = tmp_path / "a.mp3"
    f.write_bytes(b"x" * 100)
    text, meta = transcriber.transcribe_with_meta(str(f))

    assert text == ""
    assert meta["source"] == "local"


# ==================== V6-3: checkpoint incremental de transcripción ====================

def test_checkpoint_roundtrip_save_load_clear(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from yunta.voice import _save_checkpoint_fragment, _load_checkpoint, _clear_checkpoint

    _save_checkpoint_fragment("audio.mp3", 3, 0, "[00:00:00]\ntexto uno")
    _save_checkpoint_fragment("audio.mp3", 3, 1, "[00:00:20]\ntexto dos")

    entries = _load_checkpoint("audio.mp3", 3)
    assert entries[0] == "[00:00:00]\ntexto uno"
    assert entries[1] == "[00:00:20]\ntexto dos"
    assert entries[2] is None

    _clear_checkpoint("audio.mp3", 3)
    assert _load_checkpoint("audio.mp3", 3) == [None, None, None]


def test_checkpoint_mismatched_total_does_not_resume(tmp_path, monkeypatch):
    """Si el total de fragmentos cambia entre corridas (p.ej. VOICE_CHUNK_MINUTES
    distinto), los checkpoints viejos no matchean — fallback seguro a
    transcripción completa en vez de desalinear fragmentos."""
    monkeypatch.chdir(tmp_path)
    from yunta.voice import _save_checkpoint_fragment, _load_checkpoint

    _save_checkpoint_fragment("audio.mp3", 3, 0, "[00:00:00]\ntexto")
    assert _load_checkpoint("audio.mp3", 5) == [None] * 5


def test_transcribe_large_audio_resumes_after_interrupt_sequential(tmp_path, monkeypatch):
    """Una interrupción a mitad de camino deja checkpoints en disco; relanzar
    el mismo archivo reanuda desde el último fragmento sin re-llamar a la red
    para los ya transcritos."""
    monkeypatch.chdir(tmp_path)
    from yunta.voice import AudioChunker, AudioTranscriber

    def make_chunks():
        chunks = [str(tmp_path / f"c{i}.mp3") for i in range(4)]
        for c in chunks:
            Path(c).write_bytes(b"\xff\xfb\x90\x00" + b"x" * 512)
        return chunks

    calls = []

    class InterruptingTranscriber(AudioTranscriber):
        def transcribe_with_meta(self, file_path, prompt="", skip_cloud=False):
            calls.append(file_path)
            if len(calls) == 3:
                raise KeyboardInterrupt
            return f"texto {len(calls)}", {"source": "cloud", "cloud_attempted": True, "cloud_failed": False}

    chunker = AudioChunker(InterruptingTranscriber())
    chunker.split_audio_by_silence = lambda fp, *a, **k: make_chunks()

    result1 = chunker.transcribe_large_audio("clase.mp3")
    assert "transcripción parcial" in result1
    assert len(calls) == 3

    # Segunda corrida (mismo nombre y mismo total de fragmentos): reanuda.
    calls.clear()

    class CompletingTranscriber(AudioTranscriber):
        def transcribe_with_meta(self, file_path, prompt="", skip_cloud=False):
            calls.append(file_path)
            return f"resumido {len(calls)}", {"source": "cloud", "cloud_attempted": True, "cloud_failed": False}

    chunker2 = AudioChunker(CompletingTranscriber())
    chunker2.split_audio_by_silence = lambda fp, *a, **k: make_chunks()
    result2 = chunker2.transcribe_large_audio("clase.mp3")

    assert len(calls) == 2, "solo debieron transcribirse los 2 fragmentos pendientes"
    assert "texto 1" in result2 and "texto 2" in result2  # reusados del checkpoint
    assert "resumido 1" in result2 and "resumido 2" in result2  # nuevos
    assert "transcripción parcial" not in result2


def test_transcribe_large_audio_resumes_with_parallel_workers(tmp_path, monkeypatch):
    """El resume de V6-3 también aplica en modo paralelo (Fase 5)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VOICE_PARALLEL_WORKERS", "2")
    from yunta.voice import AudioChunker, AudioTranscriber, _save_checkpoint_fragment

    chunks = [str(tmp_path / f"c{i}.mp3") for i in range(4)]
    for c in chunks:
        Path(c).write_bytes(b"\xff\xfb\x90\x00" + b"x" * 512)

    _save_checkpoint_fragment("clase.mp3", 4, 0, "[00:00:00]\nviejo 1")
    _save_checkpoint_fragment("clase.mp3", 4, 1, "[00:00:20]\nviejo 2")

    calls = []

    class MetaTranscriber(AudioTranscriber):
        def transcribe_with_meta(self, file_path, prompt="", skip_cloud=False):
            calls.append(file_path)
            return "nuevo", {"source": "cloud", "cloud_attempted": True, "cloud_failed": False}

    chunker = AudioChunker(MetaTranscriber())
    chunker.split_audio_by_silence = lambda fp, *a, **k: chunks

    result = chunker.transcribe_large_audio("clase.mp3")

    assert len(calls) == 2, "solo debieron someterse al pool los 2 fragmentos pendientes"
    assert "viejo 1" in result and "viejo 2" in result
    assert result.count("nuevo") == 2


def test_checkpoint_cleared_after_full_completion(tmp_path, monkeypatch):
    """Al completar la transcripción entera (sin interrupción), los
    checkpoints se borran — no quedan archivos huérfanos en .yunta/scratch."""
    monkeypatch.chdir(tmp_path)
    from yunta.voice import AudioChunker, AudioTranscriber, _load_checkpoint

    chunks = [str(tmp_path / f"c{i}.mp3") for i in range(2)]
    for c in chunks:
        Path(c).write_bytes(b"\xff\xfb\x90\x00" + b"x" * 512)

    class MetaTranscriber(AudioTranscriber):
        def transcribe_with_meta(self, file_path, prompt="", skip_cloud=False):
            return "ok", {"source": "cloud", "cloud_attempted": True, "cloud_failed": False}

    chunker = AudioChunker(MetaTranscriber())
    chunker.split_audio_by_silence = lambda fp, *a, **k: chunks
    chunker.transcribe_large_audio("clase2.mp3")

    assert _load_checkpoint("clase2.mp3", 2) == [None, None]


# ==================== V6-1: marcas de tiempo reales por chunk (ffprobe) ====================

def test_ffprobe_duration_secs_parses_output(monkeypatch):
    import yunta.voice as voice_module
    monkeypatch.setattr(voice_module, "_ffprobe_available", None)

    class FakeCompleted:
        stdout = "12.345\n"

    monkeypatch.setattr(voice_module.subprocess, "run", lambda *a, **k: FakeCompleted())
    assert voice_module._ffprobe_duration_secs("chunk.mp3") == 12.345
    assert voice_module._ffprobe_available is True


def test_ffprobe_duration_secs_disables_after_binary_missing(monkeypatch):
    import yunta.voice as voice_module
    monkeypatch.setattr(voice_module, "_ffprobe_available", None)

    calls = []

    def fake_run(*a, **k):
        calls.append(1)
        raise FileNotFoundError("ffprobe no encontrado")

    monkeypatch.setattr(voice_module.subprocess, "run", fake_run)
    assert voice_module._ffprobe_duration_secs("chunk.mp3") == 0.0
    assert voice_module._ffprobe_available is False

    # Segunda llamada: no debe ni intentar invocar el subprocess de nuevo
    assert voice_module._ffprobe_duration_secs("otro.mp3") == 0.0
    assert len(calls) == 1


def test_ffprobe_duration_secs_bad_file_does_not_disable_binary(monkeypatch):
    """Un archivo puntual que ffprobe no puede parsear no debe desactivar
    ffprobe para el resto de los fragmentos (el binario sí funciona)."""
    import yunta.voice as voice_module
    monkeypatch.setattr(voice_module, "_ffprobe_available", True)

    class FakeCompleted:
        stdout = ""  # ffprobe corrió pero no pudo extraer duración

    monkeypatch.setattr(voice_module.subprocess, "run", lambda *a, **k: FakeCompleted())
    assert voice_module._ffprobe_duration_secs("corrupto.mp3") == 0.0
    assert voice_module._ffprobe_available is True


def test_transcribe_large_audio_uses_ffprobe_real_durations_for_offsets(tmp_path, monkeypatch):
    """Si ffprobe da la duración real de cada chunk, los timestamps reflejan
    esa duración real — no bytes proporcionales ni chunk_minutes fijo (los
    3 fragmentos de este test pesan lo mismo en bytes pero duran distinto,
    simulando audio VBR)."""
    monkeypatch.chdir(tmp_path)
    from yunta.voice import AudioChunker, AudioTranscriber

    chunks = [str(tmp_path / f"c{i}.mp3") for i in range(3)]
    for c in chunks:
        Path(c).write_bytes(b"\xff\xfb\x90\x00" + b"x" * 512)

    durations = {chunks[0]: 5.0, chunks[1]: 55.0, chunks[2]: 3.0}
    monkeypatch.setattr("yunta.voice._ffprobe_duration_secs", lambda p: durations[p])

    class MetaTranscriber(AudioTranscriber):
        def transcribe_with_meta(self, file_path, prompt="", skip_cloud=False):
            return "ok", {"source": "cloud", "cloud_attempted": True, "cloud_failed": False}

    chunker = AudioChunker(MetaTranscriber())
    chunker.split_audio_by_silence = lambda fp, *a, **k: chunks
    result = chunker.transcribe_large_audio("audio.mp3")

    assert "[00:00:00]" in result  # chunk 0 arranca en 0
    assert "[00:00:05]" in result  # chunk 1 arranca a los 5s reales
    assert "[00:01:00]" in result  # chunk 2 arranca a los 60s (5+55)


def test_transcribe_large_audio_falls_back_when_ffprobe_unavailable(tmp_path, monkeypatch):
    """Si ffprobe no está disponible o falla para algún chunk, cae a la
    heurística anterior (bytes proporcionales) sin romper la transcripción."""
    monkeypatch.chdir(tmp_path)
    from yunta.voice import AudioChunker, AudioTranscriber

    monkeypatch.setattr("yunta.voice._ffprobe_duration_secs", lambda p: 0.0)

    chunks = [str(tmp_path / f"c{i}.mp3") for i in range(2)]
    for c in chunks:
        Path(c).write_bytes(b"\xff\xfb\x90\x00" + b"x" * 512)

    class MetaTranscriber(AudioTranscriber):
        def transcribe_with_meta(self, file_path, prompt="", skip_cloud=False):
            return "ok", {"source": "cloud", "cloud_attempted": True, "cloud_failed": False}

    chunker = AudioChunker(MetaTranscriber())
    chunker.split_audio_by_silence = lambda fp, *a, **k: chunks
    result = chunker.transcribe_large_audio("audio.mp3")
    assert "[00:00:00]" in result


# ==================== V6-5: corte de chunks en silencios (ffmpeg silencedetect) ====================

def test_detect_silence_intervals_parses_ffmpeg_output(monkeypatch):
    import yunta.voice as voice_module

    fake_stderr = (
        "some ffmpeg banner\n"
        "[silencedetect @ 0x1] silence_start: 10.5\n"
        "[silencedetect @ 0x1] silence_end: 12.25 | silence_duration: 1.75\n"
        "[silencedetect @ 0x1] silence_start: 40.0\n"
        "[silencedetect @ 0x1] silence_end: 41.0 | silence_duration: 1.0\n"
    )

    class FakeResult:
        stderr = fake_stderr

    monkeypatch.setattr(voice_module.subprocess, "run", lambda *a, **k: FakeResult())
    intervals = voice_module._detect_silence_intervals("audio.mp3")
    assert intervals == [(10.5, 12.25), (40.0, 41.0)]


def test_detect_silence_intervals_returns_empty_on_failure(monkeypatch):
    import yunta.voice as voice_module

    def fake_run(*a, **k):
        raise FileNotFoundError("ffmpeg no encontrado")

    monkeypatch.setattr(voice_module.subprocess, "run", fake_run)
    assert voice_module._detect_silence_intervals("audio.mp3") == []


def test_silence_aware_cut_points_snaps_to_nearest_silence_midpoint():
    from yunta.voice import _silence_aware_cut_points

    cuts = _silence_aware_cut_points(total_secs=100, segment_secs=60, silences=[(55, 63)], tolerance=20)
    assert cuts == [59.0]


def test_silence_aware_cut_points_keeps_fixed_target_without_nearby_silence():
    from yunta.voice import _silence_aware_cut_points

    cuts = _silence_aware_cut_points(total_secs=130, segment_secs=60, silences=[(10, 11)], tolerance=5)
    assert cuts == [60.0, 120.0]


def test_silence_aware_cut_points_empty_without_silences():
    from yunta.voice import _silence_aware_cut_points

    assert _silence_aware_cut_points(100, 60, [], tolerance=10) == []


def test_split_audio_uses_segment_times_when_silence_detected(tmp_path, monkeypatch):
    """Cuando ffprobe da duración real y se detectan silencios, el comando de
    ffmpeg usa -segment_times con los cortes ajustados en vez de -segment_time."""
    import os
    import yunta.voice as voice_module
    from yunta.voice import AudioTranscriber

    audio_file = tmp_path / "clase.mp3"
    audio_file.write_bytes(b"\xff\xfb\x90\x00" + b"x" * 2048)

    monkeypatch.setattr(voice_module, "_ffprobe_duration_secs", lambda p: 100.0)
    monkeypatch.setattr(voice_module, "_detect_silence_intervals", lambda p: [(58.0, 60.0), (118.0, 120.0)])

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        out_pattern = cmd[-1]
        d = os.path.dirname(out_pattern)
        Path(os.path.join(d, "chunk_000.mp3")).write_bytes(b"a")
        Path(os.path.join(d, "chunk_001.mp3")).write_bytes(b"b")

    monkeypatch.setattr(voice_module.subprocess, "run", fake_run)

    chunker = voice_module.AudioChunker(AudioTranscriber())
    result = chunker.split_audio_by_silence(str(audio_file), chunk_minutes=1)

    assert "-segment_times" in captured["cmd"]
    idx = captured["cmd"].index("-segment_times")
    assert captured["cmd"][idx + 1] == "59.000"
    assert len(result) == 2


def test_split_audio_falls_back_to_segment_time_without_silence_data(tmp_path, monkeypatch):
    """Sin duración real (ffprobe falla) se mantiene el corte a tiempo fijo
    de siempre — sin regresión cuando ffmpeg/ffprobe no cooperan."""
    import os
    import yunta.voice as voice_module
    from yunta.voice import AudioTranscriber

    audio_file = tmp_path / "clase.mp3"
    audio_file.write_bytes(b"\xff\xfb\x90\x00" + b"x" * 2048)

    monkeypatch.setattr(voice_module, "_ffprobe_duration_secs", lambda p: 0.0)

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        out_pattern = cmd[-1]
        d = os.path.dirname(out_pattern)
        Path(os.path.join(d, "chunk_000.mp3")).write_bytes(b"a")

    monkeypatch.setattr(voice_module.subprocess, "run", fake_run)

    chunker = voice_module.AudioChunker(AudioTranscriber())
    chunker.split_audio_by_silence(str(audio_file), chunk_minutes=1)

    assert "-segment_time" in captured["cmd"]
    assert "-segment_times" not in captured["cmd"]
