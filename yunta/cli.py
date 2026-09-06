import sys

from .agent import Agent
from .provider import LiteLLMProvider
from .tools import bash, files  # noqa: F401 — registro vía decoradores

SYSTEM_PROMPT = """Eres un agente de código que opera en la terminal del usuario.
Trabajas iterando: lees archivos, ejecutas comandos y editas código usando tus tools.
Sé conciso. Si un tool falla, el error vuelve a tu contexto: ajústalo y reintenta.
Responde en el idioma del usuario."""


def main():
    provider = LiteLLMProvider(system=SYSTEM_PROMPT)
    agent = Agent(provider=provider, system=SYSTEM_PROMPT)

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
