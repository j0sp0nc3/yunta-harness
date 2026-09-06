import sys
from pathlib import Path

from .agent import Agent
from .feedback import FeedbackStore
from .provider import LiteLLMProvider
from .tools import bash, files  # noqa: F401 — registro vía decoradores

SYSTEM_PROMPT = """Eres un agente de código que opera en la terminal del usuario.
Trabajas iterando: lees archivos, ejecutas comandos y editas código usando tus tools.
Sé conciso. Si un tool falla, el error vuelve a tu contexto: ajústalo y reintenta.
Responde en el idioma del usuario.

Reglas de honestidad:
- NUNCA afirmes haber ejecutado o editado algo sin haberlo hecho con una tool
  real en esta conversación. Narrar acciones imaginarias es un fallo grave.
- Verifica tu trabajo: tras editar código, ejecuta los tests o el comando
  que demuestre el resultado antes de declararlo resuelto."""


def load_system_prompt(feedback: FeedbackStore | None = None) -> str:
    prompt = SYSTEM_PROMPT
    agents_md = Path("AGENTS.md")
    if agents_md.exists():
        prompt += "\n\n# Contexto del proyecto (AGENTS.md)\n\n" + agents_md.read_text(
            encoding="utf-8"
        )
    if feedback is not None:
        prompt += feedback.preamble()
    return prompt


def main():
    feedback = FeedbackStore()
    system = load_system_prompt(feedback)
    provider = LiteLLMProvider(system=system)
    agent = Agent(provider=provider, system=system)

    print(f"yunta — modelo: {provider.model()}")
    print("Escribe tu consulta, /clear para limpiar, /exit para salir.\n")

    while True:
        try:
            prompt = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not prompt:
            continue
        if prompt == "/exit":
            if agent.messages:
                feedback.summarize(provider, agent.messages)
            break
        if prompt == "/clear":
            agent.messages.clear()
            print("(historial limpio)\n")
            continue
        if prompt == "/tokens":
            u = provider.total_usage
            print(f"in={u.input_tokens} out={u.output_tokens}\n")
            continue

        try:
            agent.send(prompt)
        except SystemExit:
            raise
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
        print()


if __name__ == "__main__":
    main()
