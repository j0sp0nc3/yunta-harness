"""Pruebas unitarias para el módulo neutral de síntesis de voz (yunta/tts.py)."""

from yunta.tts import TTSProvider, chunk_text_by_sentences


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
    assert provider.synthesize("") is None
    assert provider.synthesize("   ") is None
