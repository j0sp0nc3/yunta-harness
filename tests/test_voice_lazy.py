"""Pruebas unitarias para la carga perezosa (Lazy-Loading) de adaptadores modales."""

import sys
from yunta.adapters import input_registry


def test_input_registry_lazy_loading():
    # Inicialmente, el módulo de voz no debe estar instanciado en el registro
    assert "AudioTranscriber" not in input_registry.loaded_modalities()
    assert "VisionAdapter" not in input_registry.loaded_modalities()

    # Carga bajo demanda del adaptador de audio
    audio_transcriber = input_registry.get_audio_adapter()
    assert audio_transcriber is not None
    assert "AudioTranscriber" in input_registry.loaded_modalities()

    # Carga bajo demanda del adaptador de visión
    vision_adapter = input_registry.get_vision_adapter()
    assert vision_adapter is not None
    assert "VisionAdapter" in input_registry.loaded_modalities()
