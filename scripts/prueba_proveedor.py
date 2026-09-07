"""Prueba universal de proveedor: valida el bucle completo de yunta contra
cualquier modelo configurado con variables de entorno.

Uso:
    export LLM_MODEL=... [LLM_API_KEY=...] [LLM_API_BASE=...]
    python scripts/prueba_proveedor.py

Cubre: envío básico, tool call real (write_file), lectura y respuesta final.
Aprobación automática: es un entorno de prueba.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yunta import Agent
from yunta.cli import load_system_prompt
from yunta.provider import LiteLLMProvider

TAREA = (
    "Usa write_file para crear prueba_proveedor.txt con el texto "
    "'verificado por yunta'. Luego léeelo con read_file y confirma su "
    "contenido en una frase."
)


def main():
    provider = LiteLLMProvider(system=load_system_prompt())
    print(f"proveedor/modelo: {provider.model()}")
    agent = Agent(
        provider=provider, system=provider.system, confirm=lambda n, d: True
    )
    agent.send(TAREA)
    u = provider.total_usage
    print(f"\n--- tokens: in={u.input_tokens} out={u.output_tokens} ---")
    ok = os.path.exists("prueba_proveedor.txt")
    if ok:
        os.remove("prueba_proveedor.txt")
    print("RESULTADO:", "OK" if ok else "FALLO")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
