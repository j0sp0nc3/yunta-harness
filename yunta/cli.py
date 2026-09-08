import os
import sys
from pathlib import Path

from .agent import Agent
from .feedback import FeedbackStore
from .init import run_init
from .mcp import load_mcp_servers
from .provider import LiteLLMProvider
from .tools import bash, delegate, files, memory, search  # noqa: F401 — registro vía decoradores

SYSTEM_PROMPT = """Eres un ingeniero de software que programa en pareja a través del harness Yunta.
Trabajas iterando: lees archivos, ejecutas comandos y editas código usando tus tools.
Sé conciso. Si un tool falla, el error vuelve a tu contexto: ajústalo y reintenta.
Responde en el idioma del usuario.

Frontera de rol y entorno de ejecución:
- Yunta es tu banco de herramientas en terminal (read_file, str_replace, bash), NO el runtime de la aplicación.
- Tu objetivo es desarrollar el código del proyecto del usuario en este espacio de trabajo.
- NUNCA crees servicios, daemons ni plugins que corran "dentro de Yunta". El software desarrollado vivirá en su propio entorno de producción (ej. nube, contenedor, Power Automate, web, CLI propio, etc.).

Filosofía Spec-Driven Development (SDD):
- Si el proyecto contiene `SPEC.md` y `PLAN.md`, respeta la fase activa del plan y guía al usuario en la resolución paso a paso (TDD: prueba de borde -> implementación -> verificación).

Reglas de honestidad y verificación:
- NUNCA afirmes haber ejecutado o editado algo sin haberlo hecho con una tool
  real en esta conversación. Narrar acciones imaginarias es un fallo grave.
- Verifica tu trabajo: tras editar código, ejecuta los tests o el comando
  que demuestre el resultado antes de declararlo resuelto."""


def load_system_prompt(feedback: FeedbackStore | None = None) -> str:
    env_prompt = os.environ.get("YUNTA_SYSTEM_PROMPT")
    user_prompt_file = Path.home() / ".yunta" / "system_prompt.md"
    if env_prompt:
        prompt = env_prompt
    elif user_prompt_file.exists():
        prompt = user_prompt_file.read_text(encoding="utf-8")
    else:
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
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    # Despacho de comando `yunta init [idea]`
    if len(sys.argv) > 1 and sys.argv[1].lower() == "init":
        idea = " ".join(sys.argv[2:]).strip()
        run_init(idea)
        return

    feedback = FeedbackStore()
    system = load_system_prompt(feedback)
    provider = LiteLLMProvider(system=system)
    delegate.set_provider(provider)

    # Despacho single-shot: `yunta "mi tarea directa"`
    if len(sys.argv) > 1:
        agent = Agent(provider=provider, system=system)
        prompt = " ".join(sys.argv[1:]).strip()
        try:
            agent.send(prompt)
        except KeyboardInterrupt:
            print()
        return

    mcp_clients = load_mcp_servers()
    agent = Agent(provider=provider, system=system)

    print(f"yunta — modelo: {provider.model()}")
    print("Escribe tu consulta, /init [idea], /tokens, /metrics, /clear o /exit.\n")

    try:
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
            if prompt == "/help":
                print("Comandos disponibles:")
                print("  /init [idea]   - Inicializa el proyecto con SPEC.md, PLAN.md y AGENTS.md (SDD)")
                print("  /tokens        - Muestra el consumo de tokens y tasa de acierto de caché")
                print("  /metrics       - Muestra la telemetría detallada de uso y herramientas")
                print("  /clear         - Limpia el historial de la conversación actual")
                print("  /exit          - Guarda lecciones de sesión y sale de Yunta\n")
                continue
            if prompt == "/clear":
                agent.messages.clear()
                print("(historial limpio)\n")
                continue
            if prompt.startswith("/init"):
                idea = prompt[5:].strip()
                run_init(idea)
                continue
            if prompt in ("/tokens", "/metrics"):
                u = agent.total_usage
                print(u.format_summary() + "\n")
                continue

            try:
                agent.send(prompt)
            except KeyboardInterrupt:
                print()
            except SystemExit:
                raise
            except Exception as e:
                print(f"error: {e}", file=sys.stderr)
            print()
    finally:
        for c in mcp_clients:
            c.close()


if __name__ == "__main__":
    main()
