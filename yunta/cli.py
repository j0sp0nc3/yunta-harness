import os
import sys
from pathlib import Path

from .agent import Agent
from .compact import SlidingWindow
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

Eficiencia de pruebas y contexto:
- Durante la iteración activa, ejecuta únicamente la prueba relevante para tu cambio (ej. `pytest tests/test_mi_modulo.py` o `pytest -k mi_funcion`) para mantener la sesión rápida y ágil.
- Ejecuta la suite completa (`pytest`) únicamente como paso de certificación final antes de dar por concluida la tarea.

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
    mcp_clients: list = []
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

    max_messages = int(os.environ.get("YUNTA_MAX_MESSAGES", "40"))
    compactor = SlidingWindow(max_messages=max_messages)

    # Despacho single-shot: `yunta "mi tarea directa"`
    if len(sys.argv) > 1:
        agent = Agent(provider=provider, system=system, compactor=compactor)
        prompt = " ".join(sys.argv[1:]).strip()
        try:
            agent.send(prompt)
        except KeyboardInterrupt:
            print()
        return

    mcp_clients = load_mcp_servers()
    agent = Agent(provider=provider, system=system, compactor=compactor)

    print(f"yunta — modelo: {provider.model()}")
    print("Escribe tu consulta, /help para ver comandos, o /exit para salir.\n")

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
                print("  /undo          - Deshace la última edición de archivos y restaura su estado anterior")
                print("  /roi           - Muestra el dashboard de valor y ahorro económico de API")
                print("  /tokens        - Muestra el consumo de tokens y tasa de acierto de caché")
                print("  /metrics       - Muestra la telemetría detallada de uso y herramientas")
                print("  /clear         - Limpia el historial de la conversación actual")
                print("  /exit          - Guarda lecciones de sesión y sale de Yunta\n")
                continue
            if prompt == "/clear":
                agent.messages.clear()
                print("(historial limpio)\n")
                continue
            if prompt == "/undo":
                restored = agent.undo()
                if restored:
                    for r in restored:
                        print(f"✨ Archivo {r}")
                else:
                    print("(no hay cambios previos para deshacer)")
                print()
                continue
            if prompt == "/roi":
                u = agent.total_usage
                tokens_in = u.input_tokens
                tokens_cached = u.cached_tokens
                raw_tokens = u.theoretical_raw_tokens
                tokens_saved = max(0, raw_tokens - (tokens_in + tokens_cached))
                savings = (tokens_cached * 0.00000095) + (tokens_saved * 0.00000125)
                print("┌────────────────────────────────────────────────────────┐")
                print("│ YUNTA — DASHBOARD DE TELEMETRÍA Y RETORNO (ROI)        │")
                print("├────────────────────────────────────────────────────────┤")
                print(f"│ ⚡ Acierto de Caché (Hit Rate):        {u.cache_rate:>6.1f}%          │")
                print(f"│ 🛡️ Tokens Cacheados (Ahorro de API):   {tokens_cached:>10,} tokens  │")
                print(f"│ 📦 Tokens Evitados vs Chat Crudo:      {tokens_saved:>10,} tokens  │")
                print(f"│ 💰 Ahorro Estimado de Costo API:     ~${savings:>9.4f} USD     │")
                print(f"│ 🔧 Herramientas Ejecutadas:            {u.total_tool_calls:>6} ({u.tool_errors} err)     │")
                print(f"│ 💬 Turnos de Interacción:              {u.turns:>6}               │")
                print("└────────────────────────────────────────────────────────┘\n")
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
