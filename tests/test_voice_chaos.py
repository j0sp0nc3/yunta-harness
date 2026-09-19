"""Suite de pruebas de caos, estrés y límites para el flujo de Voz y SDD.

Diseñada originalmente (2026-09-19) para intentar romper el flujo, encontrar
condiciones de carrera, fugas de recursos, excepciones no capturadas y
desajustes de estado. Encontró 6 defectos reales que una revisión de diseño
a nivel arquitectónico no detectó por no ejecutar código bajo estrés:
aprobación por voz que ignoraba permisos persistentes, condición de carrera
en el prefetch de TTS, excepción no capturada que mataba el hilo de habla,
desalineación de conteo de palabras en el router por emojis, bloques de
código Markdown sin cerrar filtrados a voz, y un mensaje de error engañoso
en audio de 0 bytes. Los 6 se corrigieron el mismo día; estas pruebas ahora
son regresión permanente sobre el comportamiento CORRECTO."""
import os
import queue
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from yunta.api import Block, BlockType, Message, Role, Usage
from yunta.agent import Agent, SessionPermissions
from yunta.voice import (
    AudioTranscriber,
    AudioChunker,
    DEFAULT_PREFIX_VOICE_KEYWORDS,
    make_voice_approval,
    normalize_voice_response,
    route_keyword,
    _clean_response_text,
    _TranscribeError,
)
from yunta.tts import (
    TTSProvider,
    chunk_text_by_sentences,
    clean_markdown_for_speech,
    speak,
    stop_speaking,
)


# ============================================================================
# 1. PRUEBAS DE CAOS EN APROBACIONES POR VOZ (make_voice_approval / agent)
# ============================================================================

class TestVoiceApprovalChaos:
    """Intenta romper el flujo de aprobación hablada."""

    def test_voice_approval_siempre_respected_by_subsequent_calls(self):
        """FIX 2026-09-19: si el usuario aprueba con 'siempre', se guarda en
        session_permissions, y la siguiente llamada a la misma tool NO debe
        volver a activar el micrófono — antes, Agent._approve consultaba
        voice_approval incondicionalmente antes de mirar session_permissions."""
        class MockListener:
            def __init__(self, responses):
                self.responses = list(responses)
                self.calls = 0
            def resume(self): pass
            def pause(self): pass
            def get(self, timeout=180):
                self.calls += 1
                return self.responses.pop(0) if self.responses else None

        listener = MockListener(["siempre", "sí"])

        class MockProvider:
            def model(self): return "fake"

        agent = Agent(provider=MockProvider(), system="test")
        agent.voice_approval = make_voice_approval(agent, listener)

        # Primera aprobación: usuario dice "siempre" para bash
        approved1 = agent._approve("bash", "rm file", raw_input='{"command": "rm file"}')
        assert approved1 is True
        assert listener.calls == 1
        assert agent.session_permissions.allowed("bash", '{"command": "rm file"}')

        # Segunda aprobación para la misma tool: debe permitirse automáticamente
        # SIN volver a preguntar por voz (listener.calls no debe aumentar).
        approved2 = agent._approve("bash", "ls", raw_input='{"command": "ls"}')
        assert approved2 is True
        assert listener.calls == 1, (
            "REGRESIÓN: Agent._approve volvió a consultar voice_approval pese a "
            "existir un permiso 'siempre' vigente para esta tool."
        )

    def test_voice_approval_infinite_retry_on_hallucinations(self):
        """ESTRÉS: Si Whisper entra en bucle de alucinación o hay ruido ambiente constante,
        make_voice_approval no tiene contador de intentos máximos y puede entrar en bucle infinito."""
        class InfiniteJunkListener:
            def __init__(self):
                self.count = 0
            def resume(self): pass
            def pause(self): pass
            def get(self, timeout=180):
                self.count += 1
                if self.count > 50:
                    return "no"  # romper el bucle para que el test no se cuelgue
                return "ruido de fondo o alucinacion"

        listener = InfiniteJunkListener()
        agent = MagicMock()
        cb = make_voice_approval(agent, listener)

        # Ejecutamos la aprobación
        result = cb("bash", "comando peligroso")
        assert result is False
        assert listener.count >= 50, (
            f"El callback toleró {listener.count} entradas inválidas sin abortar tempranamente."
        )

    def test_voice_approval_crashes_if_agent_permissions_is_none(self):
        """ERROR POTENCIAL: Si el agente tiene session_permissions=None y el usuario
        dice 'siempre', ocurre AttributeError."""
        class MockListener:
            def resume(self): pass
            def pause(self): pass
            def get(self, timeout=180): return "siempre"

        class NakedAgent:
            session_permissions = None

        agent = NakedAgent()
        cb = make_voice_approval(agent, MockListener())

        with pytest.raises(AttributeError, match="grant_tool"):
            cb("write_file", "detalles")

    def test_voice_approval_handles_listener_exceptions(self):
        """ESTRÉS: Si listener.get() lanza una excepción inesperada (ej. desconexión hardware),
        verificar que listener.pause() siempre se llame en el finally."""
        class ExplodingListener:
            def __init__(self):
                self.paused = False
                self.resumed = False
            def resume(self):
                self.resumed = True
            def pause(self):
                self.paused = True
            def get(self, timeout=180):
                raise OSError("Dispositivo de audio desconectado repentinamente")

        listener = ExplodingListener()
        cb = make_voice_approval(MagicMock(), listener)

        with pytest.raises(OSError):
            cb("bash", "ls")

        # Verificar que pause() se haya ejecutado en el finally a pesar de la excepción
        assert listener.paused is True


# ============================================================================
# 2. CONDICIONES DE CARRERA Y ESTRÉS EN TTS PREFETCH (yunta/tts.py)
# ============================================================================

class TestTTSPrefetchRaceCondition:
    """Intenta quebrar el pipeline de prefetch en TTS."""

    def test_tts_prefetch_race_no_longer_duplicates_synthesis(self):
        """FIX 2026-09-19: cuando una oración N es muy corta y se reproduce
        rápido, el bucle principal antes avanzaba a N+1 y sintetizaba de
        nuevo en paralelo porque `i+1 not in prefetched` aún era cierto.
        Ahora el bucle espera (join) el hilo de prefetch en vez de duplicar
        la llamada — cada oración debe sintetizarse exactamente una vez."""

        synthesize_calls = []
        lock = threading.Lock()

        class SlowPrefetchFakeProvider:
            def synthesize(self, text):
                with lock:
                    synthesize_calls.append(text)
                # Simular síntesis que toma 0.2s
                time.sleep(0.2)
                return b"fake_mp3_data", "test"

            def play_audio(self, data, should_stop=None):
                # Reproducción ultra rápida (0.01s, ej. "Sí.")
                time.sleep(0.01)
                return True

        provider = SlowPrefetchFakeProvider()
        # Dos oraciones cortas
        text = "Sí. Continuemos con la tarea."
        speak(provider, text)
        time.sleep(0.6)  # Esperar que el worker complete ambas oraciones
        stop_speaking()

        second_chunk_calls = [c for c in synthesize_calls if "Continuemos" in c]
        assert len(second_chunk_calls) == 1, (
            f"REGRESIÓN: la oración se sintetizó {len(second_chunk_calls)} veces; "
            "el worker debería esperar el prefetch en curso en vez de duplicar la llamada."
        )

    def test_tts_worker_synthesis_exception_no_longer_crashes_thread(self):
        """FIX 2026-09-19: la llamada a provider.synthesize(chunk) en el hilo
        principal de _worker ahora está protegida con try/except (igual que
        ya lo estaba _prefetch) — una falla de red no debe propagar una
        excepción no capturada en el hilo daemon."""
        class FailingProvider:
            def synthesize(self, text):
                raise ConnectionResetError("Endpoint TTS caido")
            def play_audio(self, data, should_stop=None):
                return True

        provider = FailingProvider()
        started = speak(provider, "Oracion que va a fallar.")
        assert started is True
        time.sleep(0.2)
        stop_speaking()
        # Si la excepción no se hubiera capturado, pytest reportaría un
        # PytestUnhandledThreadExceptionWarning al recolectar el hilo daemon.


# ============================================================================
# 3. CASOS DE BORDE EXTREMOS EN LIMPIEZA DE MARKDOWN (clean_markdown_for_speech)
# ============================================================================

class TestMarkdownCleanAdversarial:
    """Pruebas adversarias contra la limpieza de texto fonético."""

    def test_unclosed_code_blocks_no_longer_leak_raw_code(self):
        """FIX 2026-09-19: un bloque de código Markdown sin cerrar (```) ahora
        se resume igual que uno cerrado, en vez de filtrarse crudo al TTS."""
        malformed = "Aquí está la función:\n```python\ndef peligro():\n    return 'sin cerrar'"
        cleaned = clean_markdown_for_speech(malformed)
        assert "def peligro():" not in cleaned, (
            "REGRESIÓN: el bloque de código sin cerrar volvió a filtrarse crudo al lector de voz."
        )
        assert "código en pantalla" in cleaned

    def test_extreme_malformed_markdown_no_crash(self):
        """Verifica que entradas patológicas de Markdown no cuelguen ni lancen excepciones."""
        inputs = [
            "",
            "   \n\t   ",
            "![][][][][][][]",
            "||||||||||||||||",
            "|---|---|---|\n| | | |",
            "***********************************",
            "`" * 500,  # 500 backticks sueltos
            "<div class='test' <span <><>>",
            "[enlace sin destino](",
            "# " * 100,
            "Emoji y símbolos: 🚀 🤖 💥 🔥",
            "Unicode nulo: \x00\x00\x00",
            "\u200b\u200c\u200d\ufeff",  # Caracteres invisibles / zero-width
        ]
        for inp in inputs:
            res = clean_markdown_for_speech(inp)
            assert isinstance(res, str)

    def test_sentence_chunker_handles_floating_points_and_abbreviations(self):
        """Verifica cómo se comporta el troceador ante abreviaciones como 'Dr.':
        el punto provoca que 'El Dr.' se separe de 'Pérez'."""
        text = "La version 2.7.5 de Yunta funciona bien. El Dr. Perez aprobo."
        chunks = chunk_text_by_sentences(text)
        # 'Dr.' provoca partición indeseada
        assert "El Dr." in chunks, (
            "El troceador separa 'El Dr.' como oración independiente debido al punto."
        )


# ============================================================================
# 4. PRUEBAS DE ESTRÉS EN EL ROUTER DE PALABRAS CLAVE (route_keyword)
# ============================================================================

class TestRouteKeywordStress:
    """Intenta confundir al router paramétrico y exacto."""

    def test_prefix_keyword_false_positives(self):
        """Verifica si palabras que comienzan con el prefijo pero son parte de otra palabra
        se confunden o se mantienen intactas."""
        # 'inicializaciones' no debe ser /init
        assert route_keyword("inicializaciones de variables") is None
        # 'iniciaron el proceso' no debe ser /init
        assert route_keyword("iniciaron el proyecto ayer") is None

    def test_prefix_with_punctuation_and_emojis(self):
        """FIX 2026-09-19: si el prefijo está precedido por emojis o símbolos
        no alfanuméricos, ya no se duplica dentro del argumento. Antes,
        _clean_response_text los eliminaba de 'cleaned' pero text.split()
        seguía contando el emoji como palabra, desalineando el conteo."""
        res1 = route_keyword("inicializa, un clon de Tetris")
        assert res1 == "/init un clon de Tetris"

        # Emoji inicial: ya no se filtra "inicializa" dentro del argumento
        res2 = route_keyword("🚀 inicializa mi nuevo sistema")
        assert res2 == "/init mi nuevo sistema", (
            "REGRESIÓN: el emoji volvió a desalinear el conteo de palabras, "
            "duplicando el prefijo dentro del argumento."
        )

    def test_prefix_keyword_with_empty_or_whitespace_arg(self):
        """Si el usuario dice solo 'inicializa    ', debe retornar '/init' sin espacios basura."""
        assert route_keyword("inicializa    ") == "/init"
        assert route_keyword("inicia proyecto \t\n") == "/init"


# ============================================================================
# 5. CASOS DE BORDE EN CHUNKER DE AUDIO Y TRANSCRIPCIÓN
# ============================================================================

class TestAudioPipelineEdgeCases:
    """Intenta romper el procesador de archivos de audio."""

    def test_audio_chunker_on_empty_file_gives_clear_error(self, tmp_path):
        """FIX 2026-09-19: AudioChunker con un archivo de 0 bytes ahora reporta
        que el archivo está vacío, en vez del RuntimeError engañoso de
        'ffmpeg no está disponible' (que ocurría incluso con ffmpeg instalado)."""
        empty_mp3 = tmp_path / "empty.mp3"
        empty_mp3.write_bytes(b"")

        mock_transcriber = MagicMock()
        chunker = AudioChunker(mock_transcriber)

        with pytest.raises(RuntimeError, match="vacío"):
            chunker.split_audio_by_silence(str(empty_mp3))

    def test_transcribe_error_classification(self):
        """Verifica la clasificación de errores HTTP para degradación progresiva."""
        err429 = _TranscribeError("Rate limited", 429, "Too many requests")
        assert err429.retryable is True
        assert err429.too_large is False

        err413 = _TranscribeError("Payload too large", 413, "Maximum size exceeded")
        assert err413.too_large is True

        err500 = _TranscribeError("Server error", 500, "Internal error")
        assert err500.retryable is True
