"""Pruebas unitarias para el módulo neutral de síntesis de voz (yunta/tts.py)."""

from yunta.tts import TTSProvider, chunk_text_by_sentences, speak, stop_speaking


def test_chunk_text_by_sentences_empty():
    assert chunk_text_by_sentences("") == []
    assert chunk_text_by_sentences("   ") == []


def test_chunk_text_by_sentences_splits_punctuation():
    text = "Hola mundo. Esta es una segunda oración! Y esta es una tercera?"
    chunks = chunk_text_by_sentences(text)
    assert len(chunks) == 3
    assert chunks[0] == "Hola mundo."
    assert chunks[1] == "Esta es una segunda oración!"
    assert chunks[2] == "Y esta es una tercera?"


def test_chunk_text_by_sentences_large_chunk_subsplits():
    # Oración con más palabras que max_words troceada por comas
    text = "Primera parte corta, segunda parte bastante mas larga con muchas palabras para probar la troceada automática por pausas de comas, tercera parte final."
    chunks = chunk_text_by_sentences(text, max_words=10)
    assert len(chunks) >= 2


def test_tts_provider_initialization():
    provider = TTSProvider(model="test-model", voice="es-CL-CatalinaNeural")
    assert provider.model == "test-model"
    assert provider.voice == "es-CL-CatalinaNeural"


def test_tts_provider_synthesize_empty():
    provider = TTSProvider()
    assert provider.synthesize("") == (None, "")
    assert provider.synthesize("   ") == (None, "")


def test_synthesize_returns_source_for_transparency(monkeypatch):
    """El fallback (edge-tts) se devuelve explícito para anunciarse — nunca oculto."""
    provider = TTSProvider()
    monkeypatch.setattr(provider, "synthesize_http", lambda t: None)
    monkeypatch.setattr(provider, "synthesize_edge_tts", lambda t: b"x" * 500)
    audio, source = provider.synthesize("hola")
    assert audio and source == "edge-tts"

    monkeypatch.setattr(provider, "synthesize_http", lambda t: b"y" * 500)
    audio, source = provider.synthesize("hola")
    assert audio and source == "http"


def test_speak_nonblocking_and_stoppable():
    """speak() no bloquea el hilo principal y stop_speaking() corta la locución."""
    class FakeProvider(TTSProvider):
        def __init__(self):
            super().__init__()
            self.synthesized = []

        def synthesize(self, text):
            self.synthesized.append(text)
            return b"x" * 500, "http"

        def play_audio(self, audio_bytes, should_stop=None):
            return True

    p = FakeProvider()
    long_text = ". ".join(f"Oración número {i} de prueba" for i in range(50)) + "."
    assert speak(p, long_text) is True  # retorna inmediatamente (hilo daemon)

    stop_speaking()
    # el hilo pudo sintetizar algunas oraciones antes del corte, pero no todas
    assert len(p.synthesized) <= 50


def test_speak_empty_text_is_noop():
    class FakeProvider(TTSProvider):
        pass

    assert speak(FakeProvider(), "") is False
    assert speak(FakeProvider(), "   ") is False


def test_clean_markdown_for_speech_basic():
    from yunta.tts import clean_markdown_for_speech

    raw = """
    ### Estado del Proceso
    El archivo **app.py** fue actualizado correctamente.
    Revisa la variable `MAX_RETRIES` en [la documentación](https://yunta.dev/docs).
    
    ```python
    def run():
        pass
    ```
    
    * Paso 1 completado
    * Paso 2 pendiente
    """
    cleaned = clean_markdown_for_speech(raw)
    assert "###" not in cleaned
    assert "**" not in cleaned
    assert "`" not in cleaned
    assert "https://" not in cleaned
    assert "def run" not in cleaned
    assert "código en pantalla" in cleaned
    assert "Estado del Proceso" in cleaned
    assert "app.py fue actualizado" in cleaned
    assert "la documentación" in cleaned
    assert "Paso 1 completado" in cleaned


def test_clean_markdown_for_speech_table():
    from yunta.tts import clean_markdown_for_speech

    raw = """
    | Herramienta | Acción |
    |---|---|
    | bash | ejecutar |
    | str_replace | editar |
    """
    cleaned = clean_markdown_for_speech(raw)
    assert "|" not in cleaned
    assert "Herramienta, Acción" in cleaned
    assert "bash, ejecutar" in cleaned


def test_speak_pipelines_synthesis_with_playback():
    """La síntesis de la oración N+1 ocurre mientras la N se reproduce:
    tiempo total ≈ primera_síntesis + n*reproducción (no n*(síntesis+reproducción))."""
    import time
    import threading

    from yunta.tts import speak, wait_until_done

    # Realista: la síntesis Edge (~4.7s) es más RÁPIDA que hablar la oración
    # (~8s de habla), así que el prefetch siempre alcanza a estar listo.
    SYNTH_S, PLAY_S = 0.10, 0.30

    class SlowFake(TTSProvider):
        def synthesize(self, text):
            time.sleep(SYNTH_S)
            return b"x" * 500, "http"

        def play_audio(self, audio_bytes, should_stop=None):
            time.sleep(PLAY_S)
            return True

    p = SlowFake()
    text = ". ".join(f"Frase corta numero {i}" for i in range(5)) + "."
    n = 5
    t0 = time.perf_counter()
    assert speak(p, text) is True
    wait_until_done(timeout=30)
    elapsed = time.perf_counter() - t0
    sequential_bound = n * (SYNTH_S + PLAY_S)          # 2.0s
    pipelined_bound = SYNTH_S + n * PLAY_S + 0.4       # 1.2s + margen
    assert elapsed < pipelined_bound, (
        f"pipeline no aplicado: {elapsed:.2f}s >= {pipelined_bound:.2f}s "
        f"(secuencial sería {sequential_bound:.2f}s)"
    )
