"""Prueba cruzada: yunta + GLM (Z.ai) desde ZCode.

Uso:
    export ZAI_API_KEY=<tu key>          # https://z.ai  → API Keys
    export LLM_MODEL=zai/glm-4.6         # o el modelo GLM disponible en tu plan
    python scripts/prueba_glm.py

La prueba ejercita el bucle completo: tool call real (write_file con diff),
lectura y respuesta final. Aprobación automática — es un entorno de prueba.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yunta.agent import Agent
from yunta.cli import load_system_prompt
from yunta.provider import LiteLLMProvider

TAREA = (
    "Usa la tool write_file para crear el archivo prueba_glm.txt con el texto "
    "'generado por GLM via yunta'. Luego usa read_file para leerlo y dime "
    "qué contiene, en una frase."
)


def main():
    provider = LiteLLMProvider(system=load_system_prompt())
    print(f"modelo: {provider.model()}\n")
    agent = Agent(provider=provider, system=provider.system, confirm=lambda n, d: True)
    agent.send(TAREA)
    u = provider.total_usage
    print(f"\n--- tokens: in={u.input_tokens} out={u.output_tokens} ---")
    ok = os.path.exists("prueba_glm.txt") and "GLM" in open("prueba_glm.txt").read()
    print("RESULTADO:", "OK" if ok else "FALLO")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
