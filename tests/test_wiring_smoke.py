"""Tests de 'wiring' (B4, blindaje 2026-09-19).

La causa raíz de B1 (LLM_FAST_MODEL roto) fue que los tests existentes de
delegate_research mockeaban el provider a un nivel tan bajo que nunca
ejercitaban la construcción REAL de LiteLLMProvider con los kwargs reales
que usa producción -- por eso 264 tests en verde no detectaron un TypeError
silencioso durante 6 versiones. Estos tests instancian las clases reales con
las firmas exactas que el código de producción usa, sin red (sin llamar
.send()), y solo verifican que no truene por firmas desalineadas.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yunta.provider import LiteLLMProvider


def test_provider_accepts_model_kwarg_como_delegate_research():
    """Firma exacta usada en yunta/tools/delegate.py::delegate_research."""
    os.environ["LLM_MODEL"] = "openai/gpt-4o"  # no debería leerse si hay model=
    p = LiteLLMProvider(model="openai/gpt-4o-mini", system="system de prueba")
    assert p.model() == "openai/gpt-4o-mini"


def test_provider_acepta_solo_system_como_bootstrap_cli():
    """Firma usada en yunta/cli.py (bootstrap del REPL y single-shot) y en
    scripts/prueba_glm.py, scripts/prueba_proveedor.py."""
    os.environ["LLM_MODEL"] = "openai/gpt-4o"
    p = LiteLLMProvider(system="system de prueba")
    assert p.model() == "openai/gpt-4o"


def test_provider_sin_argumentos_lee_entorno_como_json_server():
    """Firma usada en yunta/json_server.py: LiteLLMProvider() sin kwargs."""
    os.environ["LLM_MODEL"] = "openai/gpt-4o"
    p = LiteLLMProvider()
    assert p.model() == "openai/gpt-4o"
